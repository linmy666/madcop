"""v1.2.0 — Tests for the JSONL tracer."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_REPLAN,
    HOOK_STEP_END,
    HOOK_STEP_START,
    HookContext,
    Directive,
)
from madcop.agent.tracing import (
    Tracer,
    TraceMiddleware,
    read_traces,
    print_summary,
)


def _step(name: str, action: str = "do something") -> Any:
    return SimpleNamespace(name=name, action=action)


def _outcome(success: bool, output: str = "ok", error: str | None = None,
             cost_usd: float = 0.001, duration_s: float = 0.1) -> Any:
    return SimpleNamespace(
        success=success, output=output, error=error,
        cost_usd=cost_usd, duration_s=duration_s,
    )


# ---------------------------------------------------------------------------
# Tracer basic
# ---------------------------------------------------------------------------


def test_tracer_creates_file_on_init(tmp_path: Path):
    path = tmp_path / "trace.jsonl"
    Tracer(path)
    assert path.exists()


def test_tracer_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "deep" / "nested" / "trace.jsonl"
    Tracer(path)
    assert path.exists()


def test_tracer_record_writes_one_json_per_call(tmp_path: Path):
    path = tmp_path / "trace.jsonl"
    tracer = Tracer(path)
    tracer.record("plan_start", data={"goal": "g"})
    tracer.record("step_end", step_name="s1", data={"success": True})
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    rec1 = json.loads(lines[0])
    rec2 = json.loads(lines[1])
    assert rec1["event"] == "plan_start"
    assert rec1["data"]["goal"] == "g"
    assert rec2["event"] == "step_end"
    assert rec2["step_name"] == "s1"


def test_tracer_runs_use_a_unique_run_id(tmp_path: Path):
    t1 = Tracer(tmp_path / "a.jsonl")
    t2 = Tracer(tmp_path / "b.jsonl")
    assert t1.run_id != t2.run_id
    assert t1.run_id.startswith("r-")


def test_tracer_custom_run_id(tmp_path: Path):
    tracer = Tracer(tmp_path / "t.jsonl", run_id="my-run-42")
    tracer.record("plan_start")
    recs = read_traces(tmp_path / "t.jsonl")
    assert recs[0]["run_id"] == "my-run-42"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_tracer_handles_concurrent_writes(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    tracer = Tracer(path)
    n_per_thread = 50
    n_threads = 5

    def worker(start: int) -> None:
        for i in range(start, start + n_per_thread):
            tracer.record("step_end", step_name=f"s{i}", data={"i": i})

    threads = [threading.Thread(target=worker, args=(i * 100,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    recs = read_traces(path)
    assert len(recs) == n_per_thread * n_threads
    # No two records should be the same step_name (deterministic check)
    seen = set()
    for r in recs:
        key = (r["step_name"], r["data"]["i"])
        assert key not in seen
        seen.add(key)


# ---------------------------------------------------------------------------
# TraceMiddleware
# ---------------------------------------------------------------------------


def test_trace_middleware_records_plan_start(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    tracer = Tracer(path)
    mw = TraceMiddleware(tracer)
    mw(HookContext(hook=HOOK_PLAN_START, goal="diagnose the spike"))
    recs = read_traces(path)
    assert len(recs) == 1
    assert recs[0]["event"] == "plan_start"
    assert recs[0]["data"]["goal"] == "diagnose the spike"


def test_trace_middleware_records_step_lifecycle(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    tracer = Tracer(path)
    mw = TraceMiddleware(tracer)
    # Simulate a step lifecycle
    mw(HookContext(hook=HOOK_STEP_START, goal="g", step=_step("s1")))
    mw(HookContext(hook=HOOK_STEP_END, goal="g", step=_step("s1"), outcome=_outcome(True)))
    recs = read_traces(path)
    events = [r["event"] for r in recs]
    assert events == ["step_start", "step_end"]


def test_trace_middleware_records_replan_and_plan_end(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    tracer = Tracer(path)
    mw = TraceMiddleware(tracer)
    plan = SimpleNamespace(steps=[_step("a"), _step("b")])
    mw(HookContext(hook=HOOK_REPLAN, goal="g", plan=plan))
    mw(HookContext(hook=HOOK_PLAN_END, goal="g"))
    recs = read_traces(path)
    assert recs[0]["event"] == "replan"
    assert recs[0]["data"]["plan_steps"] == 2
    assert recs[1]["event"] == "plan_end"


def test_trace_middleware_records_directives(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    tracer = Tracer(path)
    mw = TraceMiddleware(tracer)
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("s1"), outcome=_outcome(False))
    ctx.directives.append(Directive(kind="HALT", detail="loop detected"))
    mw(ctx)
    recs = read_traces(path)
    events = [r["event"] for r in recs]
    assert "step_end" in events
    assert "directive" in events
    directive = next(r for r in recs if r["event"] == "directive")
    assert directive["data"]["kind"] == "HALT"


# ---------------------------------------------------------------------------
# read_traces
# ---------------------------------------------------------------------------


def test_read_traces_handles_missing_file(tmp_path: Path):
    assert read_traces(tmp_path / "does_not_exist.jsonl") == []


def test_read_traces_handles_torn_line(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        '{"event": "plan_start"}\n'
        '{"event": "step_end", "incomp'   # torn
    )
    recs = read_traces(path)
    assert len(recs) == 1
    assert recs[0]["event"] == "plan_start"


def test_read_traces_handles_blank_lines(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        '{"event": "plan_start"}\n'
        '\n'
        '{"event": "step_end"}\n'
        '\n'
    )
    recs = read_traces(path)
    assert len(recs) == 2


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------


def test_print_summary_empty_list(capsys):
    print_summary([])
    out = capsys.readouterr().out
    assert "no traces" in out


def test_print_summary_counts_by_event(capsys, tmp_path: Path):
    path = tmp_path / "t.jsonl"
    tracer = Tracer(path)
    tracer.record("plan_start", data={"goal": "g"})
    tracer.record("step_start", step_name="s1", data={"action": "a"})
    tracer.record("step_end", step_name="s1", data={"success": True})
    tracer.record("step_start", step_name="s2", data={"action": "b"})
    tracer.record("step_end", step_name="s2", data={"success": True})
    recs = read_traces(path)
    print_summary(recs)
    out = capsys.readouterr().out
    assert "events:" in out
    assert "plan_start" in out
    assert "step_start" in out
    assert "step order:" in out
    assert "s1" in out
    assert "s2" in out
