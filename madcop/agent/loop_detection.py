"""v1.0.0 — LoopDetectionMiddleware: catch the infinite loop early.

When a plan-execute loop gets stuck, it usually looks like this:

  step 1 → "couldn't find X, try again"
  step 2 → "still no X, try a different approach"
  step 3 → "still no X, try yet another approach"
  ...
  step 30 → "still no X, try..."

This is a real failure mode (replanner keeps giving the LLM the same
problem, the LLM keeps trying, you burn $$). DeerFlow's
LoopDetectionMiddleware catches it by tracking a hash of each
step's `(action, output_signature)` tuple and halting when the same
hash appears too many times.

We do the same, with two layers of detection:

1. **Identical-step detection**: N consecutive steps with the same
   `(step_name, action)` are treated as a loop. Default N=3.
2. **Output-similarity detection**: a deque of the last M outcomes,
   and if K of them are byte-equal, halt. Default M=5, K=3.

The two layers catch different failure modes:
- (1) catches "the LLM is just retrying the same step"
- (2) catches "different steps that all produce the same output"

Qian invariants:
- **早纠偏**: halting after 3-5 retries is WAY cheaper than letting
  the LLM burn 30+ iterations.
- **可控性**: the user gets a clear "halt reason" they can act on.
- **稳定性**: detection is local to the middleware, no LLM calls.
"""
from __future__ import annotations

import hashlib
import logging
from collections import deque
from typing import Any

from .middleware import (
    Directive,
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_STEP_END,
    HookContext,
)

logger = logging.getLogger(__name__)


class LoopDetectionMiddleware:
    """Detect stuck loops and halt the run.

    Tunables:
    - max_consecutive_identical: halt after N steps with the same
      (name, action) in a row. Default 3.
    - max_recent_duplicates: halt if K of the last M step outputs are
      byte-equal. Default K=3 of M=5.
    """

    name = "loop_detection"

    def __init__(
        self,
        *,
        max_consecutive_identical: int = 3,
        recent_window: int = 5,
        max_recent_duplicates: int = 3,
    ) -> None:
        self.max_consecutive_identical = max_consecutive_identical
        self.recent_window = recent_window
        self.max_recent_duplicates = max_recent_duplicates
        # Per-instance state
        self._last_step_key: tuple[str, str] | None = None
        self._consecutive_count: int = 0
        self._recent_output_hashes: deque[str] = deque(maxlen=recent_window)

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook == HOOK_PLAN_START:
            self._reset()
        elif ctx.hook == HOOK_STEP_END:
            self._check_step(ctx)
        elif ctx.hook == HOOK_PLAN_END:
            self._reset()

    # ----- detection ----------------------------------------------------

    def _check_step(self, ctx: HookContext) -> None:
        step = ctx.step
        outcome = ctx.outcome
        if step is None or outcome is None:
            return
        step_name = getattr(step, "name", "?")
        step_action = getattr(step, "action", "")
        output = outcome.output or ""

        # Layer 1: consecutive identical (name, action)
        key = (step_name, step_action)
        if key == self._last_step_key:
            self._consecutive_count += 1
        else:
            self._last_step_key = key
            self._consecutive_count = 1

        if self._consecutive_count >= self.max_consecutive_identical:
            ctx.directives.append(Directive(
                kind="HALT",
                detail=f"loop_detection: step {step_name!r} repeated "
                       f"{self._consecutive_count}x in a row (same action)",
            ))
            return

        # Layer 2: recent output hash duplicates
        h = self._hash(output)
        self._recent_output_hashes.append(h)
        if self._recent_output_hashes.count(h) >= self.max_recent_duplicates:
            ctx.directives.append(Directive(
                kind="HALT",
                detail=f"loop_detection: same output appeared "
                       f"{self.max_recent_duplicates}x in last "
                       f"{self.recent_window} steps",
            ))

    # ----- helpers ------------------------------------------------------

    @staticmethod
    def _hash(s: str) -> str:
        # BLAKE2b is fast + has no length limit like md5/sha1. We
        # only need a stable hash to compare; not cryptographic.
        return hashlib.blake2b(s.encode("utf-8"), digest_size=8).hexdigest()

    def _reset(self) -> None:
        self._last_step_key = None
        self._consecutive_count = 0
        self._recent_output_hashes.clear()


__all__ = ["LoopDetectionMiddleware"]
