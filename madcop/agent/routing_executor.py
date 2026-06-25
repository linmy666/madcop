"""v0.7.2 — RoutingStepExecutor: sub-agent dispatch in the main loop.

Wraps an inline executor + a sub-agent executor; routes each step
to the right place based on `step.subagent`:

  - step.subagent is None  → call the inline executor
  - step.subagent is set   → dispatch to the named sub-agent

The plan-execute loop doesn't know about sub-agents — it just calls
`executor.execute(step, context)` like always. This class is the
glue that lets the user write a plan with mixed inline + sub-agent
steps without having to write their own routing function.

Usage:
    inline = FnStepExecutor(my_inline_fn)
    subagent = SubagentExecutor(runner=LLMRunner(client), parent_tools=("read", "write", "bash"))
    router = RoutingStepExecutor(inline=inline, subagent=subagent)
    loop = PlanExecuteLoop(my_planner, router)
    loop.run("diagnose something")  # steps with subagent="..." go to subagent

The router also passes the live context into sub-agents (so they see
results from prior steps) and converts the sub-agent's SubagentResult
into a step's StepOutcome (so the loop's accounting is consistent).
"""
from __future__ import annotations

import logging
from typing import Any

from .plan_execute import StepExecutor, StepOutcome
from .subagent import SubagentExecutor, SubagentStatus

logger = logging.getLogger(__name__)


class RoutingStepExecutor(StepExecutor):
    """Dispatch plan steps to inline executor OR sub-agent executor.

    Either `inline` or `subagent` may be None. If both are None, every
    step fails with an error (caller misconfiguration).
    """

    def __init__(
        self,
        inline: StepExecutor | None,
        subagent: SubagentExecutor | None = None,
    ):
        if inline is None and subagent is None:
            raise ValueError(
                "RoutingStepExecutor requires at least one of inline / subagent"
            )
        self._inline = inline
        self._subagent = subagent

    def execute(self, step, context: dict) -> StepOutcome:
        if step.subagent is not None:
            return self._dispatch_subagent(step, context)
        return self._dispatch_inline(step, context)

    # ----- internals ------------------------------------------------------

    def _dispatch_inline(self, step, context: dict) -> StepOutcome:
        if self._inline is None:
            return StepOutcome(
                step_name=step.name,
                output="",
                success=False,
                error=f"step {step.name!r} has no subagent and no inline executor is configured",
            )
        return self._inline.execute(step, context)

    def _dispatch_subagent(self, step, context: dict) -> StepOutcome:
        if self._subagent is None:
            return StepOutcome(
                step_name=step.name,
                output="",
                success=False,
                error=f"step {step.name!r} requested subagent {step.subagent!r} but no subagent executor is configured",
            )

        # Dispatch (sub-agent sees parent's context — deep-copy is
        # done inside SubagentExecutor._run_one for isolation).
        results = self._subagent.run_many([(step.subagent, step.action, context)])
        r = results[0]
        # Map SubagentResult → StepOutcome
        return StepOutcome(
            step_name=step.name,
            output=r.result or "",
            success=(r.status == SubagentStatus.COMPLETED),
            cost_usd=r.cost_usd,
            duration_s=r.duration_s or 0.0,
            error=r.error,
        )


__all__ = ["RoutingStepExecutor"]
