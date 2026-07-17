"""Evaluate a ChatTaskHarness on a fixed case set (inner loop of Meta-Harness)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from madcop.eval import EvalCase, EvalReport, EvalRunner, contains, max_length, regex_match
from madcop.meta_harness.task_harness import ChatTaskHarness


def default_chat_cases() -> list[EvalCase]:
    """Cheap offline-ish cases: language policy + format + brevity.

    These do **not** need real tools; they score the *shape* of answers under
    a harness-aware system prompt. Expand with domain suites later.
    """
    return [
        EvalCase(
            name="zh_language",
            prompt="用一句话介绍你自己。",
            scorer=regex_match(r"[\u4e00-\u9fff]{4,}"),
            tags=("lang",),
        ),
        EvalCase(
            name="direct_answer_no_meta",
            prompt="What is 2+2? Answer with just the number.",
            scorer=contains("4"),
            tags=("format",),
        ),
        EvalCase(
            name="brief",
            prompt="Say hi in under 20 words.",
            scorer=max_length(120),
            tags=("brevity",),
        ),
    ]


def build_system_for_harness(h: ChatTaskHarness, model_label: str = "test-model") -> str:
    """Lightweight stand-in for production system prompt under harness knobs.

    Full memory injection still lives in app._build_memory_system_prompt;
    evaluation uses a compact prompt that respects the same knobs for
    offline search without a full SQLite memory store.
    """
    parts = [
        "You are MadCop Agent, a personal AI agent.",
        "Always respond in the SAME language the user wrote in.",
        "Give the user-facing answer only. No meta-commentary.",
        f"(harness budgets: profile={h.profile_budget}, relevant={h.relevant_budget}, "
        f"prefs={h.preferences_budget}, skills={h.skills_budget if h.inject_skills else 0})",
    ]
    if h.inject_skills and h.max_skills > 0:
        parts.append(
            f"You may reference up to {h.max_skills} SKILLs when relevant "
            f"(budget ~{h.skills_budget} tokens)."
        )
    if h.system_addendum.strip():
        parts.append(h.system_addendum.strip())
    parts.append(f"Active model label: {model_label}.")
    return "\n\n".join(parts)


@dataclass
class EvalArtifacts:
    report: EvalReport
    case_traces: dict[str, str]


def evaluate_harness(
    h: ChatTaskHarness,
    *,
    agent_fn: Callable[[str, str | None], str] | None = None,
    cases: list[EvalCase] | None = None,
    model_label: str = "test-model",
) -> EvalArtifacts:
    """Run cases; default agent is MockClient-backed for offline loops."""
    cases = cases or default_chat_cases()
    system = build_system_for_harness(h, model_label=model_label)

    if agent_fn is None:
        agent_fn = _default_agent_factory(system)

    runner = EvalRunner(cases)
    # Wrap so each case gets harness system unless case overrides
    def fn(prompt: str, case_system: str | None) -> str:
        return agent_fn(prompt, case_system or system)

    report = runner.run(fn)
    traces = {
        r.case_name: f"passed={r.passed}\ndetail={r.detail}\n---\n{r.output}"
        for r in report.results
    }
    return EvalArtifacts(report=report, case_traces=traces)


def _default_agent_factory(default_system: str) -> Callable[[str, str | None], str]:
    from madcop.llm.client import Message, MockClient

    client = MockClient(
        default_response="4",
        scripted=[
            "我是 MadCop Agent，你的个人 AI 助手。",
            "4",
            "Hi there!",
        ],
    )

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

    return evaluate_harness(h, agent_fn=agent, cases=cases)
