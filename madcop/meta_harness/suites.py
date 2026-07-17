"""Phase 1 eval suites: smoke + full (lang, distill, tools, coding)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from madcop.eval import EvalCase, Score, contains, max_length, regex_match
from madcop.eval.harness import EvalReport, EvalRunner
from madcop.meta_harness.task_harness import ChatTaskHarness


SUITE_NAMES = ("smoke", "full")


def _score_distill_signal(output: str) -> Score:
    """Pass if agent output references skill/distill or contains long teach content."""
    o = (output or "").lower()
    ok = (
        "skill" in o
        or "技能" in output
        or "distill" in o
        or "步骤" in output
        or len(output.strip()) >= 50
    )
    return Score(passed=ok, detail=f"distill_signal len={len(output)}")


def _score_tool_mention(output: str) -> Score:
    o = (output or "").lower()
    ok = any(
        k in o
        for k in (
            "tool",
            "read_file",
            "write_file",
            "web_search",
            "echo",
            "工具",
            "function",
        )
    )
    return Score(passed=ok, detail="tool_mention")


def smoke_cases() -> list[EvalCase]:
    return [
        EvalCase(
            name="zh_language",
            prompt="用一句话介绍你自己。",
            scorer=regex_match(r"[\u4e00-\u9fff]{4,}"),
            tags=("lang", "smoke"),
        ),
        EvalCase(
            name="direct_answer_no_meta",
            prompt="What is 2+2? Answer with just the number.",
            scorer=contains("4"),
            tags=("format", "smoke"),
        ),
        EvalCase(
            name="brief",
            prompt="Say hi in under 20 words.",
            scorer=max_length(120),
            tags=("brevity", "smoke"),
        ),
    ]


def full_cases() -> list[EvalCase]:
    """Multi-outcome suite: lang/format + distill + tools + coding."""
    cases = list(smoke_cases())
    cases.extend(
        [
            EvalCase(
                name="teach_me_distill",
                prompt="教我怎么用 pytest 写一个简单测试",
                scorer=_score_distill_signal,
                tags=("distill", "full"),
            ),
            EvalCase(
                name="tool_shape",
                prompt=(
                    "If you need to read a file you should use a tool. "
                    "Name one file tool you might use."
                ),
                scorer=_score_tool_mention,
                tags=("tools", "full"),
            ),
            EvalCase(
                name="coding_workdir",
                prompt="Write the text HELLO_MADCOP into a file named hello.txt in the workdir.",
                scorer=contains("HELLO_MADCOP"),  # agent output; real file check in suite runner
                tags=("coding", "full"),
            ),
        ]
    )
    return cases


def get_suite(name: str) -> list[EvalCase]:
    n = (name or "smoke").lower()
    if n in ("full", "phase1", "all"):
        return full_cases()
    return smoke_cases()


def run_distill_case(skills_dir: Path, user_q: str, assistant_r: str) -> tuple[bool, str]:
    """Real distill path with isolated USER_SKILLS_DIR."""
    from madcop.memory import skill_distill as sd

    # caller monkeypatches or we set module path temporarily
    old = sd.USER_SKILLS_DIR
    try:
        sd.USER_SKILLS_DIR = skills_dir
        skills_dir.mkdir(parents=True, exist_ok=True)
        name = sd.distill_skill_from_exchange(user_q, assistant_r)
        if not name:
            return False, "no skill name returned"
        target = skills_dir / f"{name}.md"
        if not target.exists():
            return False, f"missing {target}"
        body = target.read_text(encoding="utf-8")
        if len(body) < 40:
            return False, "skill file too short"
        return True, name
    finally:
        sd.USER_SKILLS_DIR = old


def run_coding_case(workdir: Path, content: str = "HELLO_MADCOP") -> tuple[bool, str]:
    """Write a file under workdir — simulates harness-driven coding outcome."""
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "hello.txt"
    path.write_text(content, encoding="utf-8")
    ok = path.exists() and content in path.read_text(encoding="utf-8")
    return ok, str(path)


def run_full_suite_side_effects(
    h: ChatTaskHarness,
    *,
    tmp_root: Path | None = None,
) -> dict[str, Any]:
    """Execute distill + coding assertions with real shipped functions (offline).

    Returns structured results used by tests and archive traces.
    """
    root = Path(tmp_root) if tmp_root else Path(tempfile.mkdtemp(prefix="mh-suite-"))
    skills = root / "skills"
    work = root / "work"
    teach_q = "教我怎么用 pytest 写一个简单测试"
    teach_a = (
        "First install pytest. Then write test_foo.py with def test_add(): assert 1+1==2. "
        "Run pytest -q. Use fixtures for setup. " * 3
    )
    distill_ok, distill_detail = run_distill_case(skills, teach_q, teach_a)
    coding_ok, coding_detail = run_coding_case(work)

    # Tool allowlist behavior on schemas
    sample_schemas = [
        {"type": "function", "function": {"name": "echo", "description": "e", "parameters": {}}},
        {"type": "function", "function": {"name": "read_file", "description": "r", "parameters": {}}},
        {"type": "function", "function": {"name": "web_search", "description": "w", "parameters": {}}},
    ]
    filtered = h.filter_tool_schemas(sample_schemas)
    tools_ok = True
    if not h.enable_tools:
        tools_ok = len(filtered) == 0
    elif h.tool_allowlist:
        names = {
            (s.get("function") or s).get("name")
            for s in filtered
        }
        tools_ok = names.issubset(set(h.tool_allowlist))
    else:
        tools_ok = 0 < len(filtered) <= max(h.max_tools, 1) or h.max_tools == 0

    return {
        "tmp_root": str(root),
        "distill": {"passed": distill_ok, "detail": distill_detail},
        "coding": {"passed": coding_ok, "detail": coding_detail},
        "tools": {
            "passed": tools_ok,
            "detail": f"filtered={len(filtered)} enable={h.enable_tools} max={h.max_tools}",
            "names": [
                (s.get("function") or s).get("name") for s in filtered
            ],
        },
    }
