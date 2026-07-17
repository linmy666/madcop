"""Evaluate a ChatTaskHarness on a suite (inner loop of Meta-Harness)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from madcop.eval import EvalCase, EvalReport, EvalRunner, contains, max_length, regex_match
from madcop.meta_harness.suites import get_suite, run_full_suite_side_effects
from madcop.meta_harness.task_harness import ChatTaskHarness


def default_chat_cases() -> list[EvalCase]:
    return get_suite("smoke")


def build_system_for_harness(h: ChatTaskHarness, model_label: str = "test-model") -> str:
    """Lightweight stand-in for production system prompt under harness knobs."""
    parts = [
        "You are MadCop Agent, a personal AI agent.",
        "Always respond in the SAME language the user wrote in.",
        "Give the user-facing answer only. No meta-commentary.",
        f"(harness budgets: profile={h.profile_budget}, relevant={h.relevant_budget}, "
        f"prefs={h.preferences_budget}, skills={h.skills_budget if h.inject_skills else 0})",
        f"(tools: enable={h.enable_tools}, max={h.max_tools}, "
        f"allow={list(h.tool_allowlist) or 'ALL'})",
        f"(agent: deep={h.enable_deep_mode}, plan={h.enable_plan_mode}, "
        f"compact={h.enable_context_compact}@{h.compact_threshold_messages})",
    ]
    if h.inject_skills and h.max_skills > 0:
        parts.append(
            f"You may reference up to {h.max_skills} SKILLs when relevant "
            f"(budget ~{h.skills_budget} tokens)."
        )
    if h.enable_tools:
        parts.append(
            "You can use tools such as read_file, write_file, echo when needed."
        )
    if h.system_addendum.strip():
        parts.append(h.system_addendum.strip())
    parts.append(f"Active model label: {model_label}.")
    return "\n\n".join(parts)


@dataclass
class EvalArtifacts:
    report: EvalReport
    case_traces: dict[str, str]
    side_effects: dict[str, Any] | None = None


def evaluate_harness(
    h: ChatTaskHarness,
    *,
    agent_fn: Callable[[str, str | None], str] | None = None,
    cases: list[EvalCase] | None = None,
    suite: str = "smoke",
    model_label: str = "test-model",
    include_side_effects: bool = True,
    tmp_root: Path | None = None,
) -> EvalArtifacts:
    """Run cases; default agent is MockClient-backed for offline loops."""
    cases = cases or get_suite(suite)
    system = build_system_for_harness(h, model_label=model_label)

    if agent_fn is None:
        agent_fn = _default_agent_factory(system, suite=suite)

    runner = EvalRunner(cases)

    def fn(prompt: str, case_system: str | None) -> str:
        return agent_fn(prompt, case_system or system)

    report = runner.run(fn)
    traces = {
        r.case_name: f"passed={r.passed}\ndetail={r.detail}\n---\n{r.output}"
        for r in report.results
    }

    side: dict[str, Any] | None = None
    if include_side_effects and suite in ("full", "phase1", "all"):
        side = run_full_suite_side_effects(h, tmp_root=tmp_root)
        # Fold side-effect results into pass_rate via synthetic CaseResults
        from madcop.eval.harness import CaseResult

        extra: list[CaseResult] = []
        for key in ("distill", "coding", "tools"):
            block = side.get(key) or {}
            passed = bool(block.get("passed"))
            extra.append(
                CaseResult(
                    case_name=f"side_{key}",
                    output=str(block.get("detail") or ""),
                    passed=passed,
                    detail=str(block.get("detail") or key),
                )
            )
            traces[f"side_{key}"] = (
                f"passed={passed}\ndetail={block.get('detail')}\n---\n{block}"
            )
        all_results = list(report.results) + extra
        n_pass = sum(1 for r in all_results if r.passed)
        n_total = len(all_results)
        report = EvalReport(
            total=n_total,
            passed=n_pass,
            failed=n_total - n_pass,
            pass_rate=(n_pass / n_total) if n_total else 0.0,
            results=tuple(all_results),
        )

    return EvalArtifacts(report=report, case_traces=traces, side_effects=side)


def _default_agent_factory(
    default_system: str,
    *,
    suite: str = "smoke",
) -> Callable[[str, str | None], str]:
    from madcop.llm.client import Message, MockClient

    # Scripted answers covering smoke + full suite prompts in order
    scripted = [
        "我是 MadCop Agent，你的个人 AI 助手。",
        "4",
        "Hi there!",
        # teach_me — long enough for distill signal scorer
        (
            "使用 pytest 的步骤：1) pip install pytest 2) 写 test_*.py "
            "3) def test_add(): assert 1+1==2 4) 运行 pytest -q。"
            "技能 skill:pytest-basics 可复用这些步骤。"
        ),
        "You can use the read_file tool to load a file path.",
        "I will write HELLO_MADCOP into hello.txt using write_file.",
    ]
    client = MockClient(default_response="4", scripted=scripted)

    def agent(prompt: str, system: str | None) -> str:
        msgs = []
        if system or default_system:
            msgs.append(Message(role="system", content=system or default_system))
        msgs.append(Message(role="user", content=prompt))
        return client.chat(msgs).content

    return agent


def evaluate_with_live_llm(
    h: ChatTaskHarness,
    *,
    cases: list[EvalCase] | None = None,
    suite: str = "smoke",
) -> EvalArtifacts:
    """Use active provider from settings (costs tokens)."""
    from madcop.config import settings as settings_store
    from madcop.llm.client import Message
    from madcop.llm.factory import build_client_from_config

    s = settings_store.load_settings()
    cfg = settings_store.get_active_client_config(s)
    client = build_client_from_config(cfg, timeout=60.0)
    system = build_system_for_harness(h, model_label=(cfg or {}).get("model") or "")

    def agent(prompt: str, case_system: str | None) -> str:
        msgs = [
            Message(role="system", content=case_system or system),
            Message(role="user", content=prompt),
        ]
        return client.chat(msgs, temperature=0.2, max_tokens=256).content or ""

    return evaluate_harness(h, agent_fn=agent, cases=cases, suite=suite)
