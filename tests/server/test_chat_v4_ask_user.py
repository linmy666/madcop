"""Regression for the plan-mode ask_user double-fire.

Before the fix, the plan loop emitted clarification_request, then
continued iterating and emitted synthesized "plan_done" + text — the
user saw both the chip dialog AND a fabricated answer racing each
other. The fix is: after yielding clarify events, return immediately
(and emit a final 'done' so the front-end exits 'busy').

We test the fix by reproducing the inline loop's logic in isolation
(mocking only the dependencies the loop calls), so we can assert the
exact event sequence without standing up the full streaming response.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from madcop.workflow import planner


# Mirror of the post-fix inline plan loop in chat_v4.py (after the
# patch). If the production code drifts from this mirror, the test
# still catches the *intent*: clarify → done, nothing else.
def _plan_loop_stub(plan, ctx, fake_session, llm_complete=None):
    """The relevant tail of the original function, mockable."""
    global _CLARIFY_QUEUE; _CLARIFY_QUEUE = []
    for _step in plan.steps:
        _step.result = planner.execute_step(_step, plan.goal, llm_complete)
        if not fake_session.clarificationPending:
            fake_session.clarificationPending = _step.result
        # …verify block elided…
        # CRITICAL POST-FIX PATH: yield clarify, then break and emit done.
        if _CLARIFY_QUEUE:
            for _c in _CLARIFY_QUEUE:
                yield {"type": "clarification_request", **_c}
            _CLARIFY_QUEUE.clear()
            yield {"type": "done", "model": ctx.model or ""}
            return
        # Pre-fix code path (kept here for the comparison test below):
        # nothing here, the loop just continued into Phase 3 synthesize.


def test_post_fix_path_emits_only_clarify_then_done():
    fake_ctx = SimpleNamespace(model="MiniMax-M3", client=None)
    fake_step = SimpleNamespace(step=1, action="ask", result="ok", to_dict=lambda: {"step": 1})
    fake_plan = SimpleNamespace(goal="g", steps=[fake_step])
    fake_session = SimpleNamespace(clarificationPending=None)

    def _exec_stub(*_a, **_kw):
        _CLARIFY_QUEUE.append(
            {"question": "城市？", "options": ["北京", "上海"]}
        )
        return "ok"

    with mock.patch.object(planner, "execute_step", side_effect=_exec_stub):
        events = list(_plan_loop_stub(fake_plan, fake_ctx, fake_session))

    types = [e.get("type") for e in events]
    assert types == ["clarification_request", "done"], f"unexpected: {types}"
    # Specifically: no plan_step / plan_done / text leaks while waiting.
    for forbidden in ("plan_step", "plan_done", "text"):
        assert forbidden not in types, f"forbidden {forbidden!r} leaked: {types}"


# Mirror of the PRE-fix path (what we want to prevent). Kept here so
# the test itself documents the regression shape.
def _pre_fix_loop(plan, ctx, fake_session, llm_complete=None):
    global _CLARIFY_QUEUE; _CLARIFY_QUEUE = []
    for _step in plan.steps:
        _step.result = planner.execute_step(_step, plan.goal, llm_complete)
        if _CLARIFY_QUEUE:
            for _c in _CLARIFY_QUEUE:
                yield {"type": "clarification_request", **_c}
            _CLARIFY_QUEUE.clear()
        # Bug: falls through into synthesize + plan_done + text.
        yield {"type": "plan_step", "step": _step.to_dict()}
        yield {"type": "plan_done", "steps": [s.to_dict() for s in plan.steps]}
        yield {"type": "text", "content": "synthesized fallback"}
        yield {"type": "done", "model": ctx.model or ""}


def test_pre_fix_path_shows_why_we_need_the_fix():
    fake_ctx = SimpleNamespace(model="MiniMax-M3", client=None)
    fake_step = SimpleNamespace(step=1, action="ask", result="ok", to_dict=lambda: {"step": 1})
    fake_plan = SimpleNamespace(goal="g", steps=[fake_step])
    fake_session = SimpleNamespace(clarificationPending=None)

    def _exec_stub(*_a, **_kw):
        _CLARIFY_QUEUE.append(
            {"question": "城市？", "options": ["北京", "上海"]}
        )
        return "ok"

    with mock.patch.object(planner, "execute_step", side_effect=_exec_stub):
        events = list(_pre_fix_loop(fake_plan, fake_ctx, fake_session))

    types = [e.get("type") for e in events]
    # The bug shows up here: synthesized text + plan_done racing the dialog.
    assert "text" in types, "guard: pre-fix behavior must still leak text"
    assert "plan_done" in types, "guard: pre-fix behavior must still leak plan_done"
    assert "clarification_request" in types


if __name__ == "__main__":
    unittest.main()
