"""v1.0.0 — Tests for LoopDetectionMiddleware."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from madcop.agent.loop_detection import LoopDetectionMiddleware
from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_STEP_END,
    HookContext,
)


def _step(name: str, action: str = "do something"):
    return SimpleNamespace(name=name, action=action)


def _outcome(output: str | None, success: bool = True):
    return SimpleNamespace(success=success, output=output, error=None)


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


def test_loop_detection_does_not_halt_on_unique_steps():
    mw = LoopDetectionMiddleware()
    ctx: HookContext = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("s0"), outcome=_outcome("out-0"))
    for i in range(5):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step(f"s{i}"), outcome=_outcome(f"out-{i}"))
        mw(ctx)
        assert ctx.directives == []


def test_loop_detection_halts_on_consecutive_identical_steps():
    mw = LoopDetectionMiddleware(max_consecutive_identical=3)
    ctx: HookContext = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome("x"))
    for _ in range(3):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome("x"))
        mw(ctx)
    assert any(d.kind == "HALT" for d in ctx.directives)


def test_loop_detection_resets_consecutive_count_on_different_step():
    mw = LoopDetectionMiddleware(max_consecutive_identical=3)
    # Two retries, then a different step
    for _ in range(2):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome("x"))
        mw(ctx)
    # Different step resets the counter
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("different"), outcome=_outcome("y"))
    mw(ctx)
    assert ctx.directives == []


def test_loop_detection_resets_on_plan_start():
    mw = LoopDetectionMiddleware(max_consecutive_identical=3)
    for _ in range(2):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome("x"))
        mw(ctx)
    plan_start = HookContext(hook=HOOK_PLAN_START, goal="g2")
    mw(plan_start)
    # After reset, 2 more retries should not halt
    for _ in range(2):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g2", step=_step("retry"), outcome=_outcome("x"))
        mw(ctx)
    assert not any(d.kind == "HALT" for d in ctx.directives)


def test_loop_detection_resets_on_plan_end():
    mw = LoopDetectionMiddleware(max_consecutive_identical=3)
    for _ in range(2):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome("x"))
        mw(ctx)
    end = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(end)
    # Fresh start should not halt
    for _ in range(2):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome("x"))
        mw(ctx)
    assert not any(d.kind == "HALT" for d in ctx.directives)


# ---------------------------------------------------------------------------
# Output-similarity detection
# ---------------------------------------------------------------------------


def test_loop_detection_halts_on_repeated_outputs():
    """Different steps that all return the same string should halt."""
    mw = LoopDetectionMiddleware(
        max_consecutive_identical=10,         # high — disable layer 1
        recent_window=5,
        max_recent_duplicates=3,
    )
    # 5 different steps, 3 of them return "same"
    outputs = ["same", "other1", "same", "other2", "same"]
    for i, out in enumerate(outputs):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step(f"s{i}", f"action-{i}"), outcome=_outcome(out))
        mw(ctx)
    # The 3rd "same" (5th step) should trigger halt
    assert any(d.kind == "HALT" for d in ctx.directives)


def test_loop_detection_does_not_halt_on_distinct_outputs():
    mw = LoopDetectionMiddleware(recent_window=5, max_recent_duplicates=3)
    for i in range(5):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step(f"s{i}"), outcome=_outcome(f"unique-{i}"))
        mw(ctx)
        assert ctx.directives == []


def test_loop_detection_recent_window_caps_at_maxlen():
    """The deque is bounded — old hashes fall out."""
    mw = LoopDetectionMiddleware(
        max_consecutive_identical=10,
        recent_window=3,                       # tiny window
        max_recent_duplicates=3,
    )
    # Step 1: output "x"  (window: [x])
    ctx1 = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("s1"), outcome=_outcome("x"))
    mw(ctx1)
    # Step 2: different
    ctx2 = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("s2"), outcome=_outcome("y"))
    mw(ctx2)
    # Step 3: different
    ctx3 = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("s3"), outcome=_outcome("z"))
    mw(ctx3)
    # Step 4: back to "x" but window has [y, z, x] — only 1 x in window
    ctx4 = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("s4"), outcome=_outcome("x"))
    mw(ctx4)
    assert not any(d.kind == "HALT" for d in ctx4.directives)


# ---------------------------------------------------------------------------
# Layer interaction
# ---------------------------------------------------------------------------


def test_loop_detection_layer1_triggers_before_layer2():
    """When both layers COULD trigger, layer 1 (consecutive) wins because
    it checks first. This is the expected behaviour — consecutive same
    steps are more obviously a loop than similar outputs."""
    mw = LoopDetectionMiddleware(max_consecutive_identical=2, recent_window=3, max_recent_duplicates=2)
    for _ in range(2):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome("same"))
        mw(ctx)
    # First HALT from layer 1 — layer 2 didn't get to fire
    halt = [d for d in ctx.directives if d.kind == "HALT"][0]
    assert "in a row" in halt.detail


def test_loop_detection_handles_missing_step():
    """Defensive: ctx without step or outcome should not crash."""
    mw = LoopDetectionMiddleware()
    ctx = HookContext(hook=HOOK_STEP_END, goal="g")  # no step, no outcome
    mw(ctx)
    assert ctx.directives == []


def test_loop_detection_handles_none_output():
    mw = LoopDetectionMiddleware(max_consecutive_identical=3)
    for _ in range(2):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_step("retry"), outcome=_outcome(None))
        mw(ctx)
    # None output → empty string for hashing
    assert not any(d.kind == "HALT" for d in ctx.directives)
