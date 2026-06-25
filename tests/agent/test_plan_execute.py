"""Tests for v0.6.0 plan-execute-replan loop (DeerFlow-style harness).

Design borrowed from DeerFlow 2.0 (see ~/.hermes/skills/research/
deerflow-architecture-reference.md) — specifically the TodoMiddleware
pattern and the 4 execution modes (flash/standard/pro/ultra). We don't
copy code, just the shape.
"""
from __future__ import annotations

import pytest

from madcop.agent.plan_execute import (
    ExecutionMode,
    MAX_REPLANS,
    Plan,
    PlanExecuteConfig,
    PlanExecuteLoop,
    PlanStep,
    StepOutcome,
    TrivialPlanner,
    FnStepExecutor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exec_returning(text: str, cost: float = 0.001, duration: float = 0.01):
    """Build an FnStepExecutor that always returns `text` as success."""
    def fn(step: PlanStep, context: dict) -> StepOutcome:
        return StepOutcome(
            step_name=step.name,
            output=text,
            success=True,
            cost_usd=cost,
            duration_s=duration,
        )
    return FnStepExecutor(fn)


def _exec_failing_on(name: str):
    def fn(step: PlanStep, context: dict) -> StepOutcome:
        if step.name == name:
            return StepOutcome(
                step_name=step.name,
                output="",
                success=False,
                error="simulated failure",
            )
        return StepOutcome(step_name=step.name, output="ok", success=True)
    return FnStepExecutor(fn)


# ---------------------------------------------------------------------------
# Mode + max_replans
# ---------------------------------------------------------------------------


def test_default_max_replans_per_mode():
    assert MAX_REPLANS[ExecutionMode.FLASH] == 0
    assert MAX_REPLANS[ExecutionMode.STANDARD] == 0
    assert MAX_REPLANS[ExecutionMode.PRO] == 2
    assert MAX_REPLANS[ExecutionMode.ULTRA] == 2


def test_execution_mode_values():
    assert ExecutionMode.FLASH.value == "flash"
    assert ExecutionMode.STANDARD.value == "standard"
    assert ExecutionMode.PRO.value == "pro"
    assert ExecutionMode.ULTRA.value == "ultra"


# ---------------------------------------------------------------------------
# TrivialPlanner
# ---------------------------------------------------------------------------


def test_trivial_planner_flash_returns_single_step():
    p = TrivialPlanner()
    plan = p.plan("diagnose oms spike", ExecutionMode.FLASH)
    assert plan.n_steps == 1
    assert plan.steps[0].name == "flash"


def test_trivial_planner_standard_splits_on_dot():
    p = TrivialPlanner()
    plan = p.plan("step one. step two. step three", ExecutionMode.STANDARD)
    assert plan.n_steps == 3
    assert [s.name for s in plan.steps] == ["s1", "s2", "s3"]


def test_trivial_planner_no_dots_yields_single_step():
    p = TrivialPlanner()
    plan = p.plan("just one thing", ExecutionMode.STANDARD)
    assert plan.n_steps == 1


# ---------------------------------------------------------------------------
# Loop — happy paths
# ---------------------------------------------------------------------------


def test_flash_mode_runs_single_step():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_returning("boom"),
        PlanExecuteConfig(mode=ExecutionMode.FLASH),
    )
    result = loop.run("anything")
    assert result.success
    assert result.mode == ExecutionMode.FLASH
    assert result.replan_count == 0
    assert result.final_output == "boom"
    assert len(result.step_outcomes) == 1


def test_standard_mode_runs_each_step_in_sequence():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_returning("ok"),
        PlanExecuteConfig(mode=ExecutionMode.STANDARD),
    )
    result = loop.run("a. b. c")
    assert result.success
    assert len(result.step_outcomes) == 3
    # context aggregation: each step's output overwrote the same key
    # (since the trivial planner only names them s1, s2, s3)


def test_total_cost_is_summed():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_returning("ok", cost=0.01),
        PlanExecuteConfig(mode=ExecutionMode.STANDARD),
    )
    result = loop.run("a. b. c")
    assert abs(result.total_cost_usd - 0.03) < 0.0001


def test_total_duration_is_positive():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_returning("ok", duration=0.001),
        PlanExecuteConfig(mode=ExecutionMode.FLASH),
    )
    result = loop.run("anything")
    assert result.total_duration_s >= 0.0


# ---------------------------------------------------------------------------
# Loop — failure + replan (pro mode)
# ---------------------------------------------------------------------------


def test_pro_mode_replans_on_failure():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_failing_on("s2"),
        PlanExecuteConfig(mode=ExecutionMode.PRO),
    )
    result = loop.run("a. b. c")
    assert result.replan_count == 1
    # s2 was the failed step; the default replan drops it.
    # So the new plan has only s1 + s3 (and they get retried).
    step_names = [o.step_name for o in result.step_outcomes]
    # s1 was executed before the failure AND after the replan
    assert step_names.count("s1") == 2
    # s2 only appears once (the initial failure)
    assert step_names.count("s2") == 1
    # s3 is in the new plan, gets executed
    assert "s3" in step_names


def test_pro_mode_replan_respects_max_attempts():
    # A custom replan that always returns a plan that still contains "s2"
    always_s2 = lambda prev_plan, n, failed: Plan(
        steps=[PlanStep(name="s2", action="retry")],
        rationale="stubborn replan",
    )
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_failing_on("s2"),
        PlanExecuteConfig(mode=ExecutionMode.PRO, on_replan=always_s2),
    )
    result = loop.run("a. b. c")
    # max_replans=2 for PRO, so we should see 2 replans
    assert result.replan_count == 2


def test_standard_mode_does_not_replan_even_on_failure():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_failing_on("s1"),
        PlanExecuteConfig(mode=ExecutionMode.STANDARD),
    )
    result = loop.run("a. b. c")
    assert result.replan_count == 0
    assert not result.success


# ---------------------------------------------------------------------------
# on_step_complete hook
# ---------------------------------------------------------------------------


def test_on_step_complete_receives_every_outcome():
    seen: list[str] = []
    cfg = PlanExecuteConfig(
        mode=ExecutionMode.STANDARD,
        on_step_complete=lambda outcome, ctx: seen.append(outcome.step_name),
    )
    loop = PlanExecuteLoop(TrivialPlanner(), _exec_returning("ok"), cfg)
    loop.run("a. b. c")
    assert seen == ["s1", "s2", "s3"]


def test_on_replan_receives_failed_outcome():
    received: list[StepOutcome] = []

    def replan(prev_plan, n, failed):
        received.append(failed)
        return Plan(steps=[], rationale="abort")

    cfg = PlanExecuteConfig(
        mode=ExecutionMode.PRO,
        on_replan=replan,
    )
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_failing_on("s1"),
        cfg,
    )
    loop.run("a. b. c")
    assert len(received) == 1
    assert received[0].step_name == "s1"
    assert "simulated failure" in received[0].error


# ---------------------------------------------------------------------------
# Override max replans
# ---------------------------------------------------------------------------


def test_max_replans_override_works():
    # Force 5 replans in standard mode (default is 0)
    cfg = PlanExecuteConfig(mode=ExecutionMode.STANDARD, max_replans_override=5)
    always_s2 = lambda prev_plan, n, failed: Plan(
        steps=[PlanStep(name="s2", action="retry")]
    )
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_failing_on("s2"),
        PlanExecuteConfig(mode=ExecutionMode.PRO, on_replan=always_s2, max_replans_override=5),
    )
    result = loop.run("a. b. c")
    # 5 replans allowed, but the replan callback always returns a 1-step
    # plan that still fails s2, so 5 replans are attempted
    assert result.replan_count == 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_planner_returning_empty_plan_yields_no_output():
    class EmptyPlanner:
        def plan(self, goal, mode): return Plan(steps=[])

    loop = PlanExecuteLoop(EmptyPlanner(), _exec_returning("ok"))
    result = loop.run("nothing")
    assert result.success is False  # no outcomes → not success
    assert result.final_output == ""


def test_executor_exception_is_caught():
    def fn(step, ctx):
        raise ValueError("oops")

    loop = PlanExecuteLoop(TrivialPlanner(), FnStepExecutor(fn))
    result = loop.run("a. b")
    # 2 outcomes, both failed
    assert len(result.step_outcomes) == 2
    assert all(not o.success for o in result.step_outcomes)
    assert "ValueError" in result.step_outcomes[0].error


def test_final_output_single_step_returns_just_output():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_returning("SOLO"),
        PlanExecuteConfig(mode=ExecutionMode.FLASH),
    )
    result = loop.run("x")
    assert result.final_output == "SOLO"


def test_final_output_multi_step_includes_status_tags():
    loop = PlanExecuteLoop(
        TrivialPlanner(),
        _exec_returning("ok"),
        PlanExecuteConfig(mode=ExecutionMode.STANDARD),
    )
    result = loop.run("a. b")
    assert "[OK] s1" in result.final_output
    assert "[OK] s2" in result.final_output
