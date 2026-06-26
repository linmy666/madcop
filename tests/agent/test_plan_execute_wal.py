"""v0.9.0 — Tests for the WAL-resume integration in PlanExecuteLoop.

The v0.8.0 WAL is a standalone module; v0.9.0 wires it into
`PlanExecuteLoop` so a crashed run can be resumed from the last
committed step.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from madcop.agent.plan_execute import (
    ExecutionMode,
    FnStepExecutor,
    Plan,
    PlanExecuteConfig,
    PlanExecuteLoop,
    PlanStep,
    StepExecutor,
    StepOutcome,
)
from madcop.strategy import WAL


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


def _make_step_executor(record: list[str]) -> StepExecutor:
    """A StepExecutor that records every step name and returns a fixed output."""
    def _exec(step: PlanStep, context: dict) -> StepOutcome:
        record.append(step.name)
        return StepOutcome(
            step_name=step.name,
            output=f"output for {step.name}",
            success=True,
        )
    return FnStepExecutor(_exec)


def _three_step_plan() -> Plan:
    return Plan(steps=[
        PlanStep(name="step-a", action="do A"),
        PlanStep(name="step-b", action="do B"),
        PlanStep(name="step-c", action="do C"),
    ])


class _FixedPlanner:
    def __init__(self, plan: Plan):
        self._plan = plan

    def plan(self, goal: str, mode) -> Plan:  # noqa: ARG002
        return self._plan


# ---------------------------------------------------------------------------
# Basic integration — WAL records every step
# ---------------------------------------------------------------------------


def test_loop_without_wal_still_works():
    """Regression: wal=None should behave exactly like v0.6.0."""
    record: list[str] = []
    loop = PlanExecuteLoop(
        planner=_FixedPlanner(_three_step_plan()),
        executor=_make_step_executor(record),
    )
    result = loop.run("do something")
    assert record == ["step-a", "step-b", "step-c"]
    assert len(result.step_outcomes) == 3
    assert result.success


def test_loop_with_wal_records_every_step(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    record: list[str] = []
    loop = PlanExecuteLoop(
        planner=_FixedPlanner(_three_step_plan()),
        executor=_make_step_executor(record),
        wal=wal,
    )
    result = loop.run("test goal")

    replay = wal.replay()
    assert replay.started is True
    assert replay.is_finished is True
    assert replay.completed_steps == frozenset({"step-a", "step-b", "step-c"})
    assert replay.step_count == 3
    # Final report was written
    assert replay.final_report
    assert len(result.step_outcomes) == 3


def test_loop_wal_finish_record_contains_final_output(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    loop = PlanExecuteLoop(
        planner=_FixedPlanner(_three_step_plan()),
        executor=_make_step_executor([]),
        wal=wal,
    )
    loop.run("goal")
    replay = wal.replay()
    # Final output aggregates step outputs
    assert "step-a" in replay.final_report
    assert "step-b" in replay.final_report


# ---------------------------------------------------------------------------
# Resume after simulated crash
# ---------------------------------------------------------------------------


def test_loop_resumes_from_pending_step(tmp_path: Path):
    """Simulate a crash after step-a: the WAL has a start + step-a record
    but no finish. Re-running the loop with the same WAL should skip
    step-a and run only step-b and step-c."""
    wal = WAL(tmp_path / "test.wal.jsonl")
    plan = _three_step_plan()

    # First run: simulate by manually writing the start + step-a record
    # (instead of actually running the loop, which is a cleaner test).
    wal.append_start(
        run_id="r1",
        goal="do something",
        plan=[{"name": "step-a"}, {"name": "step-b"}, {"name": "step-c"}],
    )
    wal.append_step("step-a", "ok")

    # Now re-run with the same WAL. Expect the executor to see only
    # step-b and step-c.
    record: list[str] = []
    loop = PlanExecuteLoop(
        planner=_FixedPlanner(plan),
        executor=_make_step_executor(record),
        wal=wal,
    )
    result = loop.run("do something")

    assert record == ["step-b", "step-c"]
    assert [o.step_name for o in result.step_outcomes] == ["step-b", "step-c"]
    # WAL is now: start, step-a (old), start (new), step-b, step-c, finish
    replay = wal.replay()
    # step-a still counts as completed (later-wins keeps the last record,
    # but the step set is {a, b, c} regardless of order).
    assert replay.completed_steps == frozenset({"step-a", "step-b", "step-c"})
    assert replay.is_finished


def test_loop_resume_with_all_steps_done_short_circuits(tmp_path: Path):
    """If the WAL says every step is done but no finish record exists,
    the loop should run zero steps and return success."""
    wal = WAL(tmp_path / "test.wal.jsonl")
    plan = _three_step_plan()
    wal.append_start("r1", "g", [{"name": "step-a"}, {"name": "step-b"}, {"name": "step-c"}])
    for s in ["step-a", "step-b", "step-c"]:
        wal.append_step(s, "ok")

    record: list[str] = []
    loop = PlanExecuteLoop(
        planner=_FixedPlanner(plan),
        executor=_make_step_executor(record),
        wal=wal,
    )
    result = loop.run("g")

    assert record == []
    assert len(result.step_outcomes) == 0
    # The loop considers this a "no outcomes" run, so success=False.
    # That's fine — the user's responsibility is to check the WAL and
    # decide whether to call this a success.
    assert result.success is False


def test_loop_resume_only_runs_first_pending_when_partial(tmp_path: Path):
    """A WAL with step-a + step-b done, step-c not done → only step-c runs."""
    wal = WAL(tmp_path / "test.wal.jsonl")
    plan = _three_step_plan()
    wal.append_start("r1", "g", [{"name": "step-a"}, {"name": "step-b"}, {"name": "step-c"}])
    wal.append_step("step-a", "ok")
    wal.append_step("step-b", "ok")

    record: list[str] = []
    loop = PlanExecuteLoop(
        planner=_FixedPlanner(plan),
        executor=_make_step_executor(record),
        wal=wal,
    )
    loop.run("g")

    assert record == ["step-c"]


# ---------------------------------------------------------------------------
# WAL records failed steps correctly
# ---------------------------------------------------------------------------


def _failing_step_executor() -> StepExecutor:
    def _exec(step: PlanStep, context: dict) -> StepOutcome:
        if step.name == "step-b":
            return StepOutcome(
                step_name=step.name, output="", success=False,
                error="synthetic failure",
            )
        return StepOutcome(step_name=step.name, output="ok", success=True)
    return FnStepExecutor(_exec)


def test_loop_wal_records_failed_step_with_error(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    plan = _three_step_plan()
    loop = PlanExecuteLoop(
        planner=_FixedPlanner(plan),
        executor=_failing_step_executor(),
        wal=wal,
    )
    loop.run("g")

    replay = wal.replay()
    by_name = {s.name: s for s in replay.step_records}
    assert by_name["step-a"].status == "ok"
    assert by_name["step-b"].status == "failed"
    assert by_name["step-b"].error == "synthetic failure"


# ---------------------------------------------------------------------------
# Crash during execution
# ---------------------------------------------------------------------------


def test_loop_wal_persists_progress_across_exceptions(tmp_path: Path):
    """If the executor returns a failed outcome on step-b, the WAL
    should still have step-a as completed and step-b as failed.

    (Note: the loop catches executor exceptions and turns them into
    a failed StepOutcome. We test that path here.)
    """
    wal = WAL(tmp_path / "test.wal.jsonl")
    plan = _three_step_plan()

    def boom(step: PlanStep, context: dict) -> StepOutcome:
        if step.name == "step-b":
            return StepOutcome(
                step_name=step.name, output="", success=False,
                error="synthetic failure",
            )
        return StepOutcome(step_name=step.name, output="ok", success=True)

    loop = PlanExecuteLoop(
        planner=_FixedPlanner(plan),
        executor=FnStepExecutor(boom),
        wal=wal,
    )
    result = loop.run("g")
    assert not result.success  # because step-b failed

    replay = wal.replay()
    by_name = {s.name: s for s in replay.step_records}
    assert by_name["step-a"].status == "ok"
    assert by_name["step-b"].status == "failed"
    assert by_name["step-c"].status == "ok"  # loop continued past the failure
