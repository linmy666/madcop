"""v1.7.0 — Streaming output middleware.

StreamStepMiddleware runs at HOOK_STEP_END and pushes each step's
output to a user-provided callback in real time. This gives the
CLI (or a future WebSocket server) a live view of what the agent
is doing — without modifying the core plan-execute loop.

Why a middleware (not a change to PlanExecuteLoop.run)?
  - The loop already has ``on_step_complete`` callback support.
  - But middleware composes with everything else (tracing,
    reflection, loop detection). Adding streaming as a middleware
    means you can mix and match without changing the core loop.
  - DeerFlow does the same: its StreamMiddleware wraps every agent
    turn, not the executor.

The callback signature is:
    on_stream(event_type: str, data: dict) -> None

Event types:
    "plan_start"    — {goal, mode, step_count}
    "step_start"    — {step_name, step_action, index, total}
    "step_end"      — {step_name, success, output, cost, duration}
    "plan_end"      — {success, total_cost, total_duration, output}

Design (Qian control theory):
  - 可观测性: streaming = observability; you can't fix what you can't see
  - 低开销: callback is synchronous but expected to be <1ms (just print/push)
  - 层次化: this middleware never modifies state — it's pure observation
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from .middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_STEP_END,
    HOOK_STEP_START,
    HookContext,
)

logger = logging.getLogger(__name__)

# Type alias for the streaming callback
StreamCallback = Callable[[str, dict[str, Any]], None]


class StreamStepMiddleware:
    """Stream plan-execute events to a callback in real time.

    Args:
        on_stream: Callback called with (event_type, data_dict).
            For CLI: ``lambda evt, data: print(f"[{evt}] {data}")``
            For WebSocket: ``lambda evt, data: ws.send(json.dumps({...}))``
        format: If "text", formats data as human-readable lines before
            passing to callback (useful for CLI). If "raw" (default),
            passes the raw dict.
    """

    name = "stream"

    def __init__(
        self,
        on_stream: StreamCallback,
        *,
        fmt: str = "raw",
    ) -> None:
        self._on_stream = on_stream
        self._format = fmt

    def __call__(self, ctx: HookContext) -> None:
        if self._format == "text":
            self._handle_text(ctx)
        else:
            self._handle_raw(ctx)

    def _handle_raw(self, ctx: HookContext) -> None:
        """Raw dict format — for programmatic consumers."""
        if ctx.hook == HOOK_PLAN_START:
            step_count = len(ctx.plan.steps) if ctx.plan else 0
            self._on_stream("plan_start", {
                "goal": ctx.goal,
                "step_count": step_count,
            })

        elif ctx.hook == HOOK_STEP_START:
            idx = ctx.shared.get("_step_index", 0)
            total = ctx.shared.get("_step_total", 0)
            self._on_stream("step_start", {
                "step_name": getattr(ctx.step, "name", "?"),
                "step_action": getattr(ctx.step, "action", ""),
                "index": idx,
                "total": total,
            })

        elif ctx.hook == HOOK_STEP_END:
            outcome = ctx.outcome
            self._on_stream("step_end", {
                "step_name": getattr(outcome, "step_name", "?"),
                "success": getattr(outcome, "success", None),
                "output": getattr(outcome, "output", ""),
                "cost": getattr(outcome, "cost_usd", 0.0),
                "duration": getattr(outcome, "duration_s", 0.0),
                "error": getattr(outcome, "error", None),
            })

        elif ctx.hook == HOOK_PLAN_END:
            summary = ctx.shared.get("plan_summary", {})
            self._on_stream("plan_end", {
                "success": summary.get("plan_success", False),
                "total_cost": summary.get("total_cost", 0.0),
                "total_duration": summary.get("total_duration", 0.0),
                "step_count": len(summary.get("plan_lines", [])),
                "failure_count": len(summary.get("failure_modes", [])),
            })

    def _handle_text(self, ctx: HookContext) -> None:
        """Human-readable text format — for CLI output."""
        if ctx.hook == HOOK_PLAN_START:
            step_count = len(ctx.plan.steps) if ctx.plan else 0
            self._on_stream("text", {
                "line": f"▶ Plan: {ctx.goal} ({step_count} step(s))",
            })

        elif ctx.hook == HOOK_STEP_START:
            name = getattr(ctx.step, "name", "?")
            action = getattr(ctx.step, "action", "")
            idx = ctx.shared.get("_step_index", 0)
            total = ctx.shared.get("_step_total", 0)
            self._on_stream("text", {
                "line": f"  [{idx + 1}/{total}] {name}: {action[:80]}",
            })

        elif ctx.hook == HOOK_STEP_END:
            outcome = ctx.outcome
            tag = "✓" if getattr(outcome, "success", False) else "✗"
            name = getattr(outcome, "step_name", "?")
            cost = getattr(outcome, "cost_usd", 0.0)
            dur = getattr(outcome, "duration_s", 0.0)
            output = getattr(outcome, "output", "")
            preview = output[:120] + "..." if len(output) > 120 else output
            self._on_stream("text", {
                "line": f"  {tag} {name}: {preview} (${cost:.4f}, {dur:.1f}s)",
            })

        elif ctx.hook == HOOK_PLAN_END:
            summary = ctx.shared.get("plan_summary", {})
            success = summary.get("plan_success", False)
            cost = summary.get("total_cost", 0.0)
            tag = "✓ DONE" if success else "✗ FAILED"
            self._on_stream("text", {
                "line": f"▶ {tag} — ${cost:.4f} total",
            })


__all__ = ["StreamStepMiddleware", "StreamCallback"]
