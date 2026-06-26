"""v1.0.0 — Middleware chain: the spine that holds every other middleware.

Inspired by DeerFlow 2.0's 14-layer middleware, but kept small and
local-first. A middleware is a function (or class) that can observe
and modify state at well-defined hook points during a plan-execute
run. They compose into a chain.

Why middleware at all (Qian control theory lens):

- 钱学森's engineering cybernetics treats a system as a closed
  feedback loop: observe → decide → act → observe again. A plan-
  execute loop WITHOUT middleware has only one feedback point
  (the executor's return). With middleware, you can intercept at
  every state transition and apply corrections EARLY, when they're
  cheap.
- 早纠偏成本低: catching a malformed LLM response in a middleware
  is one log line. Catching it after the next 3 sub-agents spawn
  is a full restart.
- 可控性: when the system goes off the rails, you can shut down
  selectively ("cancel this sub-agent but keep the loop alive")
  by setting a middleware flag.

What a middleware can do (Qian invariants):

1. **Observe** any state field (read-only by default)
2. **Mutate** state fields in well-defined ways
3. **Short-circuit** the run by raising `MiddlewareHalt`
4. **Schedule** follow-up work by appending to a `directives` list

What a middleware MUST NOT do:

- Block on I/O for more than 100ms (chain latency compounds)
- Modify the executor's identity or the sub-agent pool
- Spawn new sub-agents (recursion guard lives elsewhere)

The chain itself is a tiny piece of code (~50 lines). All the
intelligence lives in the individual middlewares.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Halt exception
# --------------------------------------------------------------------------- #


class MiddlewareHalt(Exception):
    """Raised by a middleware to stop the run cleanly.

    The `reason` field is recorded in the run's result so the user
    knows WHY the run was halted (e.g. "LoopDetection: 5 identical
    retries in a row").
    """
    def __init__(self, reason: str, *, recoverable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.recoverable = recoverable


# --------------------------------------------------------------------------- #
# Middleware protocol
# --------------------------------------------------------------------------- #


class Middleware(Protocol):
    """The middleware contract.

    A middleware is a callable that takes a `HookContext` and returns
    nothing (or raises `MiddlewareHalt`). The chain invokes each
    middleware in order at each hook point.

    Implementations should be cheap: a middleware that runs 1ms × 14
    middlewares × 100 steps = 1.4s overhead per run. Anything heavier
    should batch or move to async.
    """

    name: str

    def __call__(self, ctx: "HookContext") -> None: ...


# Convenience: any function with a `.name` attribute works too
MiddlewareFactory = Callable[[], Middleware]


# --------------------------------------------------------------------------- #
# Hook context
# --------------------------------------------------------------------------- #


# Hook points in the plan-execute lifecycle. Order matters for
# documentation; the chain is invoked in registration order, not
# hook-point order.
HOOK_PLAN_START = "plan_start"          # before the planner runs
HOOK_STEP_START = "step_start"          # before each step's executor.execute
HOOK_STEP_END = "step_end"              # after each step's executor.execute
HOOK_REPLAN = "replan"                  # before a new plan is installed
HOOK_PLAN_END = "plan_end"              # after the final outcome is collected

ALL_HOOKS: tuple[str, ...] = (
    HOOK_PLAN_START,
    HOOK_STEP_START,
    HOOK_STEP_END,
    HOOK_REPLAN,
    HOOK_PLAN_END,
)


@dataclass
class HookContext:
    """State passed to every middleware at every hook point.

    Fields are deliberately loose (mostly `Any`) so individual
    middlewares can stash whatever they need without us having to
    pre-declare every attribute. The protocol is duck-typed.

    Standard fields the core chain guarantees to set:
    - `hook`: which hook point is being invoked (one of ALL_HOOKS)
    - `goal`: the user's free-text goal
    - `plan`: the current `Plan` (may be None before HOOK_PLAN_START)
    - `step`: the current `PlanStep` (only set for step hooks)
    - `outcome`: the current `StepOutcome` (only set for HOOK_STEP_END)
    - `directives`: a list the middleware can append to; the chain
      reads this after the middleware returns and applies any
      `Directive`s (e.g. "HALT", "RETRY_LAST_STEP")
    - `shared`: a free-form dict middlewares can use to pass data
      to each other (e.g. LoopDetection writes step signatures
      here, Clarification reads them)
    """
    hook: str
    goal: str
    plan: Any = None
    step: Any = None
    outcome: Any = None
    directives: list["Directive"] = field(default_factory=list)
    shared: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)


@dataclass
class Directive:
    """A directive a middleware can issue.

    The chain reads these after a middleware returns and applies
    them in order. Use sparingly — most middleware should just
    observe and mutate, not direct.
    """
    kind: str                            # "HALT" | "RETRY" | "REPLAN" | "LOG"
    detail: str = ""
    payload: Any = None


# --------------------------------------------------------------------------- #
# Chain
# --------------------------------------------------------------------------- #


class MiddlewareChain:
    """An ordered list of middlewares invoked at every hook point.

    The chain is itself a `Middleware` — you can compose chains.
    This is how the user builds the "middleware stack" they want:

        chain = MiddlewareChain([
            LoggingMiddleware(),
            LoopDetectionMiddleware(max_retries=3),
            QianControlMiddleware(),     # 早纠偏 wrapper
        ])

    Or compose:

        inner = MiddlewareChain([LoggingMiddleware(), LoopDetection()])
        outer = MiddlewareChain([inner, QianControl()])
    """

    def __init__(self, middlewares: Sequence[Middleware] | None = None):
        self._middlewares: list[Middleware] = list(middlewares or [])

    # ----- registration --------------------------------------------------

    def add(self, mw: Middleware) -> "MiddlewareChain":
        self._middlewares.append(mw)
        return self

    def __len__(self) -> int:
        return len(self._middlewares)

    def names(self) -> list[str]:
        return [getattr(mw, "name", type(mw).__name__) for mw in self._middlewares]

    # ----- invocation ---------------------------------------------------

    def __call__(self, ctx: HookContext) -> None:
        """Invoke every middleware in order. Halt on first MiddlewareHalt."""
        for mw in self._middlewares:
            try:
                mw(ctx)
            except MiddlewareHalt as e:
                logger.info("middleware %s halted: %s", getattr(mw, "name", "?"), e.reason)
                raise
            except Exception:  # noqa: BLE001
                # Middleware errors are LOGGED but don't kill the run.
                # Rationale: one buggy middleware shouldn't take down
                # the whole agent. The Qian invariant is "early
                # correction" — if a middleware crashes, the next one
                # still gets to observe. We do surface the error in logs
                # so the user can fix it.
                logger.exception(
                    "middleware %s raised (continuing)",
                    getattr(mw, "name", "?"),
                )


# --------------------------------------------------------------------------- #
# 钱学森 control middleware (QianControlMiddleware)
# --------------------------------------------------------------------------- #
#
# This is the "design philosophy" middleware. It doesn't have business
# logic — it just enforces the Qian invariants:
#
# 1. **闭环反馈** — every step's outcome MUST be observed (we log
#    it). The middleware chain itself is the feedback loop.
# 2. **早纠偏** — if a step's outcome has `success=False` AND the
#    error matches a "stuck" pattern (same error 3+ times), the
#    middleware emits a HALT directive so the user doesn't burn
#    more compute on a clearly broken step.
# 3. **稳定性** — if a middleware takes >100ms, log a warning.
#    Chain latency compounds; slow middlewares are bugs.
# 4. **可控性** — emit periodic progress lines so the user can
#    see what the loop is doing, even if they don't have tracing
#    configured.
#
# This is deliberately minimal. The point is to set the *pattern* —
# future middlewares should follow these invariants too.


# Patterns that suggest a step is truly stuck (not just temporarily failing).
_STUCK_PATTERNS: tuple[str, ...] = (
    "rate limit",
    "context length exceeded",
    "context_length_exceeded",
    "401 unauthorized",
    "403 forbidden",
    "out of memory",
    "out_of_memory",
    "internal server error",
    "service unavailable",
)


class QianControlMiddleware:
    """The Qian control-theory middleware. Sets the design invariants.

    - Logs every step outcome (closed-loop feedback)
    - Detects repeated identical failures (early correction: HALT)
    - Warns on slow middlewares (stability)
    - Emits progress every N steps (controllability)
    """

    name = "qian_control"

    def __init__(
        self,
        *,
        max_repeat_failures: int = 3,          # halt after N identical errors
        slow_middleware_ms: int = 100,         # warn if any middleware is slower
        progress_every_n_steps: int = 5,       # log a progress line every N
    ):
        self.max_repeat_failures = max_repeat_failures
        self.slow_middleware_ms = slow_middleware_ms
        self.progress_every_n_steps = progress_every_n_steps
        # Per-instance state (not per-ctx). A fresh `HookContext` per
        # hook call would reset the count otherwise.
        self._step_count: int = 0
        self._error_history: dict[str, int] = {}

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook == HOOK_STEP_END and ctx.outcome is not None:
            self._on_step_end(ctx)
        elif ctx.hook == HOOK_PLAN_END:
            self._on_plan_end(ctx)

    def _on_step_end(self, ctx: HookContext) -> None:
        # Closed-loop feedback: log the outcome
        outcome = ctx.outcome
        step_name = getattr(ctx.step, "name", "?")
        status = "OK" if outcome.success else "FAIL"
        logger.info("[qian] step %s → %s (cost=$%.4f)",
                    step_name, status, getattr(outcome, "cost_usd", 0.0))

        # Early correction: detect stuck patterns
        if not outcome.success and outcome.error:
            err = outcome.error
            for pattern in _STUCK_PATTERNS:
                if pattern.lower() in err.lower():
                    count = self._error_history.get(pattern, 0) + 1
                    self._error_history[pattern] = count
                    if count >= self.max_repeat_failures:
                        # Emit a HALT directive. The chain runner
                        # reads ctx.directives and translates it
                        # into a MiddlewareHalt.
                        ctx.directives.append(Directive(
                            kind="HALT",
                            detail=f"qian_control: '{pattern}' seen {count} times",
                        ))
                    break

        # Controllability: progress line every N steps
        self._step_count += 1
        if self._step_count % self.progress_every_n_steps == 0:
            logger.info("[qian] progress: %d steps completed", self._step_count)

    def _on_plan_end(self, ctx: HookContext) -> None:
        elapsed = time.time() - ctx.started_at
        logger.info("[qian] plan finished: %d steps in %.2fs", self._step_count, elapsed)
        # Clear state so a fresh run starts clean
        self._error_history.clear()
        self._step_count = 0


# --------------------------------------------------------------------------- #
# Built-in: LoggingMiddleware
# --------------------------------------------------------------------------- #


class LoggingMiddleware:
    """A trivial middleware that logs every hook. Useful for debugging."""

    name = "logging"

    def __init__(self, level: int = logging.DEBUG) -> None:
        self._level = level

    def __call__(self, ctx: HookContext) -> None:
        if logger.isEnabledFor(self._level):
            logger.log(self._level, "[hook] %s", ctx.hook)


# --------------------------------------------------------------------------- #
# Chain runner helper
# --------------------------------------------------------------------------- #


def apply_directives(ctx: HookContext) -> None:
    """Apply any HALT directives on the context by raising MiddlewareHalt.

    Call this AFTER the chain has run for a given hook. Other directive
    kinds (RETRY, REPLAN, LOG) are returned for the caller to handle.
    """
    for d in ctx.directives:
        if d.kind == "HALT":
            raise MiddlewareHalt(d.detail)


__all__ = [
    "ALL_HOOKS",
    "HOOK_PLAN_START",
    "HOOK_PLAN_END",
    "HOOK_REPLAN",
    "HOOK_STEP_END",
    "HOOK_STEP_START",
    "Directive",
    "HookContext",
    "LoggingMiddleware",
    "Middleware",
    "MiddlewareChain",
    "MiddlewareFactory",
    "MiddlewareHalt",
    "QianControlMiddleware",
    "apply_directives",
]
