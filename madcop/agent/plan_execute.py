"""L5 — v0.6.0 plan-execute-replan loop (DeerFlow-style harness).

What v0.5.0 had:
  - a fixed linear graph: ingest → detect → counterfactual → decision → summarise
  - great for known cases, no replan if LLM gives bad plan

What v0.6.0 adds:
  - a free-form plan-execute-replan loop with 4 execution modes
  - inspired by DeerFlow 2.0's flash/standard/pro/ultra + TodoMiddleware
    (we copy the *design pattern*, not the code — see
    ~/.hermes/skills/research/deerflow-architecture-reference.md)

The 4 modes (DeerFlow's flash/standard/pro/ultra, but ours is simpler):
  - flash:  no plan, just one-shot LLM call
  - standard: 1 plan + execute each step in sequence
  - pro: plan + execute + replan on failure (up to 2x)
  - ultra: like pro, but step calls can use the "parallel" flag (v0.7.0)

This module is the high-level loop. The actual LLM work happens
through a `StepExecutor` protocol (you provide one; the tests use a
mock). Real wiring (router + scratchpad + memory) is layered on top
in `madcop.cli` or wherever.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, Sequence


# ---------------------------------------------------------------------------
# Mode + step model
# ---------------------------------------------------------------------------


class ExecutionMode(str, Enum):
    FLASH = "flash"        # no plan, one-shot
    STANDARD = "standard"  # plan + execute each step
    PRO = "pro"            # plan + execute + replan on failure
    ULTRA = "ultra"        # pro + parallel step execution (v0.7.0)


# Default max replan attempts per mode
MAX_REPLANS: dict[ExecutionMode, int] = {
    ExecutionMode.FLASH: 0,
    ExecutionMode.STANDARD: 0,
    ExecutionMode.PRO: 2,
    ExecutionMode.ULTRA: 2,
}


@dataclass
class PlanStep:
    """One step in a plan. Kept small — the executor does the heavy lifting."""
    name: str
    action: str                   # free-form instruction for the executor
    parallel: bool = False        # v0.7.0 ultra mode
    depends_on: tuple[str, ...] = ()  # step names that must finish first


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)
    rationale: str = ""

    @property
    def n_steps(self) -> int:
        return len(self.steps)


@dataclass
class StepOutcome:
    """Result of executing one PlanStep."""
    step_name: str
    output: str
    success: bool
    cost_usd: float = 0.0
    duration_s: float = 0.0
    error: str | None = None


@dataclass
class PlanExecuteResult:
    """Final result of a full plan-execute-replan loop."""
    goal: str
    mode: ExecutionMode
    plan: Plan
    step_outcomes: list[StepOutcome] = field(default_factory=list)
    replan_count: int = 0
    final_output: str = ""
    total_cost_usd: float = 0.0
    total_duration_s: float = 0.0
    success: bool = False


# ---------------------------------------------------------------------------
# StepExecutor — the contract for "do one step"
# ---------------------------------------------------------------------------


class StepExecutor(Protocol):
    """Anyone implementing this protocol can be plugged into the loop.

    Real impl: a thin wrapper around madcop.llm.ChatClient with router
    + scratchpad + memory (see madcop.cli for the production wiring).
    Test impl: anything that takes a step and returns a string.
    """

    def execute(self, step: PlanStep, context: dict) -> StepOutcome: ...


# ---------------------------------------------------------------------------
# Planner protocol
# ---------------------------------------------------------------------------


class Planner(Protocol):
    """Generate a Plan from a goal. Real impl: LLM via madcop.llm. Test: stub."""

    def plan(self, goal: str, mode: ExecutionMode) -> Plan: ...


# ---------------------------------------------------------------------------
# Default implementations (small + useful for tests + simple CLI use)
# ---------------------------------------------------------------------------


class TrivialPlanner:
    """Always returns a single-step plan that just echoes the goal.

    Replace with a real LLM-backed planner for production.
    """

    def plan(self, goal: str, mode: ExecutionMode) -> Plan:
        if mode == ExecutionMode.FLASH:
            # flash should be plan-less; we still return one step
            # so the loop can be uniform
            return Plan(steps=[PlanStep(name="flash", action=goal)])
        # standard / pro / ultra: split on '.' to fake a plan
        chunks = [c.strip() for c in goal.split(".") if c.strip()]
        if not chunks:
            chunks = [goal]
        steps = [PlanStep(name=f"s{i+1}", action=chunk) for i, chunk in enumerate(chunks)]
        return Plan(steps=steps, rationale=f"trivial split into {len(steps)} chunk(s)")


class FnStepExecutor:
    """Run a Python callable for each step. Useful for tests + deterministic
    flows (rule-based pipelines, OMS adapter, etc.)."""

    def __init__(self, fn: Callable[[PlanStep, dict], StepOutcome]):
        self._fn = fn

    def execute(self, step: PlanStep, context: dict) -> StepOutcome:
        try:
            return self._fn(step, context)
        except Exception as e:  # noqa: BLE001
            return StepOutcome(
                step_name=step.name,
                output="",
                success=False,
                error=f"{type(e).__name__}: {e}",
            )


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


@dataclass
class PlanExecuteConfig:
    """Knobs for the loop."""
    mode: ExecutionMode = ExecutionMode.STANDARD
    max_replans_override: int | None = None
    on_step_complete: Callable[[StepOutcome, dict], None] | None = None
    on_replan: Callable[[Plan, int, StepOutcome], Plan] | None = None


class PlanExecuteLoop:
    """The main loop. Run a goal through plan → execute → (replan if needed).

    The loop is mode-aware: FLASH skips planning, PRO/ULTRA allow replans.
    Replans are triggered by a failed step (or by `on_replan` callback
    returning a new plan).
    """

    def __init__(
        self,
        planner: Planner,
        executor: StepExecutor,
        config: PlanExecuteConfig | None = None,
    ):
        self._planner = planner
        self._executor = executor
        self._config = config or PlanExecuteConfig()

    def run(self, goal: str) -> PlanExecuteResult:
        mode = self._config.mode
        t0 = time.time()
        plan = self._planner.plan(goal, mode)
        outcomes: list[StepOutcome] = []
        replan_count = 0
        max_replans = (
            self._config.max_replans_override
            if self._config.max_replans_override is not None
            else MAX_REPLANS[mode]
        )

        context: dict[str, Any] = {"goal": goal, "mode": mode.value, "results": {}}

        # We use a while loop with explicit "current plan" so replans
        # can chain (s2 fails → replan → s2 fails again → replan again).
        current_plan = plan
        outcomes: list[StepOutcome] = []
        step_index = 0  # tracks progress through current_plan
        while step_index < len(current_plan.steps):
            step = current_plan.steps[step_index]
            outcome = self._executor.execute(step, context)
            outcomes.append(outcome)
            context["results"][step.name] = outcome.output
            if self._config.on_step_complete is not None:
                self._config.on_step_complete(outcome, context)
            step_index += 1

            # Replan on failure (only if more replans allowed AND there are
            # more steps in the current plan we should re-think)
            if not outcome.success and replan_count < max_replans:
                if self._config.on_replan is not None:
                    new_plan = self._config.on_replan(current_plan, replan_count, outcome)
                else:
                    new_plan = self._default_replan(current_plan, outcome)
                current_plan = new_plan
                replan_count += 1
                # Restart at the first step of the new plan; subsequent
                # steps of the old plan are dropped. This matches DeerFlow's
                # behavior of "replan and try again, not resume the old one".
                step_index = 0

        # Aggregate
        final_output = self._aggregate(current_plan, outcomes)
        total_cost = sum(o.cost_usd for o in outcomes)
        total_duration = time.time() - t0
        success = all(o.success for o in outcomes) and len(outcomes) > 0

        return PlanExecuteResult(
            goal=goal,
            mode=mode,
            plan=current_plan,
            step_outcomes=outcomes,
            replan_count=replan_count,
            final_output=final_output,
            total_cost_usd=total_cost,
            total_duration_s=total_duration,
            success=success,
        )

    def _default_replan(self, plan: Plan, failed: StepOutcome) -> Plan:
        """Simple default: drop the failed step and retry the rest."""
        new_steps = [s for s in plan.steps if s.name != failed.step_name]
        # If everything was the failed step, append a single retry step
        if not new_steps:
            new_steps = [
                PlanStep(name=f"retry-{failed.step_name}", action=failed.output or "retry")
            ]
        return Plan(steps=new_steps, rationale=f"replan after {failed.step_name} failed")

    @staticmethod
    def _aggregate(plan: Plan, outcomes: Sequence[StepOutcome]) -> str:
        if not outcomes:
            return ""
        if len(outcomes) == 1:
            return outcomes[0].output
        # Multi-step: join with step names so the final report is readable
        parts: list[str] = []
        for o in outcomes:
            tag = "OK" if o.success else "FAIL"
            parts.append(f"[{tag}] {o.step_name}: {o.output}")
        return "\n".join(parts)


__all__ = [
    "ExecutionMode",
    "MAX_REPLANS",
    "PlanStep",
    "Plan",
    "StepOutcome",
    "PlanExecuteResult",
    "PlanExecuteConfig",
    "StepExecutor",
    "Planner",
    "TrivialPlanner",
    "FnStepExecutor",
    "PlanExecuteLoop",
]
