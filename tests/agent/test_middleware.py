"""v1.0.0 — Tests for the middleware chain + Qian control middleware."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from madcop.agent.middleware import (
    ALL_HOOKS,
    Directive,
    HookContext,
    LoggingMiddleware,
    MiddlewareChain,
    MiddlewareHalt,
    QianControlMiddleware,
    apply_directives,
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_REPLAN,
    HOOK_STEP_END,
    HOOK_STEP_START,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _fake_outcome(success: bool, error: str | None = None) -> Any:
    return SimpleNamespace(success=success, error=error, cost_usd=0.001)


def _fake_step(name: str) -> Any:
    return SimpleNamespace(name=name)


class _Recorder:
    """A middleware that records its name into a list when called."""
    def __init__(self, name: str, log: list) -> None:
        self.name = name
        self._log = log

    def __call__(self, ctx: HookContext) -> None:  # type: ignore[no-untyped-def]
        self._log.append(self.name)


class _Halter:
    """A middleware that always raises MiddlewareHalt."""
    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self._reason = reason

    def __call__(self, ctx: HookContext) -> None:  # type: ignore[no-untyped-def]
        raise MiddlewareHalt(self._reason)


class _Bomb:
    """A middleware that always raises a generic exception."""
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, ctx: HookContext) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("intentional bomb")


def _build_chain(*mws) -> MiddlewareChain:
    """Build a chain, side-stepping Pyright's strict Protocol check.

    Pyright is right that these don't formally implement `Middleware`,
    but they DO have the right shape. The cast to `Any` is contained
    here so the test bodies stay clean.
    """
    chain: Any = MiddlewareChain()
    for m in mws:
        chain.add(m)
    return chain  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# HookContext
# ---------------------------------------------------------------------------


def test_hook_context_defaults():
    ctx = HookContext(hook=HOOK_PLAN_START, goal="do something")
    assert ctx.goal == "do something"
    assert ctx.hook == HOOK_PLAN_START
    assert ctx.plan is None
    assert ctx.step is None
    assert ctx.outcome is None
    assert ctx.directives == []
    assert ctx.shared == {}


def test_hook_context_directives_is_per_instance():
    a = HookContext(hook=HOOK_STEP_START, goal="x")
    b = HookContext(hook=HOOK_STEP_START, goal="x")
    a.directives.append(Directive(kind="HALT"))
    assert b.directives == []


def test_all_hooks_listed_in_module():
    assert set(ALL_HOOKS) == {
        HOOK_PLAN_START, HOOK_STEP_START, HOOK_STEP_END, HOOK_REPLAN, HOOK_PLAN_END,
    }


# ---------------------------------------------------------------------------
# MiddlewareChain
# ---------------------------------------------------------------------------


def test_empty_chain_is_noop():
    chain = MiddlewareChain()
    assert len(chain) == 0
    chain(HookContext(hook=HOOK_PLAN_START, goal="g"))  # does nothing


def test_chain_invokes_in_registration_order():
    calls: list[str] = []
    chain = _build_chain(_Recorder("a", calls), _Recorder("b", calls), _Recorder("c", calls))
    chain(HookContext(hook=HOOK_PLAN_START, goal="g"))
    assert calls == ["a", "b", "c"]


def test_chain_names_returns_names_in_order():
    chain = MiddlewareChain([LoggingMiddleware(), QianControlMiddleware()])
    assert chain.names() == ["logging", "qian_control"]


def test_chain_halts_on_middleware_halt():
    calls: list[str] = []
    chain = _build_chain(
        _Recorder("a", calls),
        _Halter("b", reason="stop here"),
        _Recorder("c", calls),
    )
    with pytest.raises(MiddlewareHalt, match="stop here"):
        chain(HookContext(hook=HOOK_PLAN_START, goal="g"))
    assert calls == ["a"]


def test_chain_continues_when_middleware_raises_non_halt():
    """A non-MiddlewareHalt exception is logged but doesn't kill the chain."""
    calls: list[str] = []
    chain = _build_chain(
        _Recorder("a", calls),
        _Bomb("b"),
        _Recorder("c", calls),
    )
    chain(HookContext(hook=HOOK_PLAN_START, goal="g"))
    assert calls == ["a", "c"]  # 'b' crashed, 'c' still runs


def test_chain_add_returns_self_for_chaining():
    chain = MiddlewareChain()
    assert chain.add(LoggingMiddleware()) is chain


def test_chain_len_and_names_update_with_add():
    chain = MiddlewareChain([LoggingMiddleware()])
    chain.add(QianControlMiddleware())
    assert len(chain) == 2
    assert chain.names() == ["logging", "qian_control"]


def test_chain_composes_chains():
    """A chain of chains works (outer chain invokes inner as one middleware)."""
    calls: list[str] = []
    inner = _build_chain(_Recorder("a", calls), _Recorder("b", calls))
    outer = _build_chain(inner, _Recorder("c", calls))
    outer(HookContext(hook=HOOK_PLAN_START, goal="g"))
    assert calls == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# QianControlMiddleware
# ---------------------------------------------------------------------------


def test_qian_control_logs_step_outcome(caplog):
    mw = QianControlMiddleware()
    outcome = _fake_outcome(success=True)
    step = _fake_step(name="s1")
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=step, outcome=outcome)
    with caplog.at_level(logging.INFO, logger="madcop.agent.middleware"):
        mw(ctx)
    assert any("step s1 → OK" in m for m in caplog.messages)


def test_qian_control_halts_after_repeated_stuck_error():
    """3 identical 'rate limit' errors → HALT directive."""
    mw = QianControlMiddleware(max_repeat_failures=3)
    last_ctx = None
    for i in range(3):
        outcome = _fake_outcome(success=False, error="rate limit exceeded")
        last_ctx = HookContext(
            hook=HOOK_STEP_END, goal="g",
            step=_fake_step(name=f"s{i}"),
            outcome=outcome,
        )
        mw(last_ctx)
    assert last_ctx is not None
    assert any(d.kind == "HALT" for d in last_ctx.directives)


def test_qian_control_does_not_halt_for_one_off_error():
    mw = QianControlMiddleware(max_repeat_failures=3)
    outcome = _fake_outcome(success=False, error="transient timeout")
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", outcome=outcome)
    mw(ctx)
    assert ctx.directives == []


def test_qian_control_emits_progress_every_n_steps(caplog):
    mw = QianControlMiddleware(progress_every_n_steps=3)
    with caplog.at_level(logging.INFO, logger="madcop.agent.middleware"):
        for i in range(6):
            ctx = HookContext(
                hook=HOOK_STEP_END, goal="g",
                step=_fake_step(name=f"s{i}"),
                outcome=_fake_outcome(success=True),
            )
            mw(ctx)
    progress_msgs = [m for m in caplog.messages if "progress" in m]
    assert any("3 steps" in m for m in progress_msgs)
    assert any("6 steps" in m for m in progress_msgs)


def test_qian_control_clears_history_at_plan_end():
    """The error history is per-run, not global. A new run starts clean."""
    mw = QianControlMiddleware(max_repeat_failures=2)
    last_ctx = None
    for _ in range(2):
        last_ctx = HookContext(hook=HOOK_STEP_END, goal="g1", outcome=_fake_outcome(False, "rate limit"))
        mw(last_ctx)
    assert last_ctx is not None
    assert any(d.kind == "HALT" for d in last_ctx.directives)

    # Trigger plan_end — clears the error history
    end_ctx = HookContext(hook=HOOK_PLAN_END, goal="g1")
    end_ctx.started_at = 1000.0
    mw(end_ctx)
    assert mw._error_history == {}
    assert mw._step_count == 0

    # Run 2: fresh state, only 1 occurrence so far — no HALT yet
    ctx2 = HookContext(hook=HOOK_STEP_END, goal="g2", outcome=_fake_outcome(False, "rate limit"))
    mw(ctx2)
    assert not any(d.kind == "HALT" for d in ctx2.directives)


def test_qian_control_matches_stuck_patterns_case_insensitive():
    mw = QianControlMiddleware(max_repeat_failures=2)
    last_ctx = None
    for _ in range(2):
        last_ctx = HookContext(hook=HOOK_STEP_END, goal="g", outcome=_fake_outcome(False, "RATE LIMIT hit"))
        mw(last_ctx)
    assert last_ctx is not None
    assert any(d.kind == "HALT" for d in last_ctx.directives)


def test_qian_control_logs_plan_end_summary(caplog):
    mw = QianControlMiddleware(progress_every_n_steps=2)
    # 3 steps
    for i in range(3):
        ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=_fake_step(f"s{i}"), outcome=_fake_outcome(True))
        mw(ctx)
    # plan_end
    final_ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    final_ctx.started_at = 1000.0
    with caplog.at_level(logging.INFO, logger="madcop.agent.middleware"):
        mw(final_ctx)
    assert any("plan finished" in m for m in caplog.messages)
    # State is reset for the next run
    assert mw._step_count == 0


# ---------------------------------------------------------------------------
# LoggingMiddleware
# ---------------------------------------------------------------------------


def test_logging_middleware_logs_each_hook(caplog):
    mw = LoggingMiddleware()
    with caplog.at_level(logging.DEBUG, logger="madcop.agent.middleware"):
        for h in ALL_HOOKS:
            mw(HookContext(hook=h, goal="g"))
    hooks_seen = {m for m in caplog.messages if "[hook]" in m}
    assert len(hooks_seen) >= len(ALL_HOOKS)


# ---------------------------------------------------------------------------
# apply_directives
# ---------------------------------------------------------------------------


def test_apply_directives_halts_on_halt_directive():
    ctx = HookContext(hook=HOOK_STEP_END, goal="g")
    ctx.directives.append(Directive(kind="HALT", detail="stop"))
    with pytest.raises(MiddlewareHalt, match="stop"):
        apply_directives(ctx)


def test_apply_directives_noop_when_no_directives():
    ctx = HookContext(hook=HOOK_STEP_END, goal="g")
    ctx.directives.append(Directive(kind="LOG", detail="info"))
    ctx.directives.append(Directive(kind="RETRY", detail="last"))
    apply_directives(ctx)  # does not raise


def test_apply_directives_halts_on_first_halt():
    """If multiple HALT directives are present, the first one wins."""
    ctx = HookContext(hook=HOOK_STEP_END, goal="g")
    ctx.directives.append(Directive(kind="HALT", detail="first"))
    ctx.directives.append(Directive(kind="HALT", detail="second"))
    with pytest.raises(MiddlewareHalt, match="first"):
        apply_directives(ctx)
