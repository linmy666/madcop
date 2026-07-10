"""v1.0 — Plan Executor: runs a Plan-and-Execute flow and yields SSE events.

Called from the chat endpoint when plan_mode=True. This module is the
bridge between the planner module and the SSE streaming chat.

SSE events emitted:
  {"type": "plan", "plan": {...}}          — the full plan
  {"type": "plan_step", "step": {...}}     — step status update
  {"type": "plan_done"}                    — all steps complete
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from .planner import Plan, PlanStep, StepStatus, generate_plan, verify_step

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 8
MAX_VERIFY_RETRIES = 2


async def execute_plan_flow(
    task: str,
    *,
    llm_complete: callable,
    yield_event: callable,
) -> Plan:
    """Run the full Plan-and-Execute flow, yielding SSE events.

    Args:
        task: The user's task description.
        llm_complete: Function that calls the LLM and returns text.
                      Signature: llm_complete(messages: list[dict]) -> str
        yield_event: Function to yield SSE events. Called with (event_type, data).
                     Signature: yield_event(type: str, data: dict)

    Returns:
        The completed Plan object (with all step results).
    """
    # ── Phase 1: Generate plan ──
    logger.info("[plan] generating plan for: %s", task[:100])
    plan = generate_plan(task, llm_complete=llm_complete, max_steps=MAX_PLAN_STEPS)
    plan.status = "running"
    yield_event("plan", plan.to_dict())

    # ── Phase 2: Execute steps ──
    context = plan.goal
    for step in plan.steps:
        step.status = StepStatus.IN_PROGRESS
        plan.current_step = step.step
        yield_event("plan_step", step.to_dict())

        max_retries = min(step.max_retries, MAX_VERIFY_RETRIES)
        success = False

        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info("[plan] retry %d/%d for step %d", attempt, max_retries, step.step)
                step.retry_count = attempt

            try:
                # Execute the step
                from .planner import execute_step
                result = execute_step(step, context, llm_complete=llm_complete)
                step.result = result

                # Verify the result
                passed, reason = verify_step(step, llm_complete=llm_complete)

                if passed:
                    step.status = StepStatus.COMPLETED
                    success = True
                    break
                else:
                    step.error = f"验证不通过: {reason}"
                    logger.warning("[plan] step %d failed verification: %s", step.step, reason)
                    step.status = StepStatus.FAILED

            except Exception as e:
                step.error = f"执行异常: {type(e).__name__}: {e}"
                logger.error("[plan] step %d error: %s", step.step, e)
                step.status = StepStatus.FAILED

        # Update plan status
        if not success:
            plan.status = "failed"
            yield_event("plan_step", step.to_dict())
            break

        yield_event("plan_step", step.to_dict())

    # ── Phase 3: Finalize ──
    if plan.failed_steps == 0:
        plan.status = "completed"
    plan.current_step = 0
    yield_event("plan", plan.to_dict())
    yield_event("plan_done", {})

    return plan