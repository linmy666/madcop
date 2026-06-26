"""v1.0.0 — Tests for the TodoMiddleware (LLM dynamic plan generation)."""
from __future__ import annotations

import pytest

from madcop.agent.middleware import (
    Directive,
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HookContext,
)
from madcop.agent.todo_middleware import TodoMiddleware, TodoPlan, TodoStep


# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------


def test_todo_middleware_exposes_todo_update_tool():
    mw = TodoMiddleware()
    specs = mw.tool_specs()
    assert len(specs) == 1
    assert specs[0]["type"] == "function"
    assert specs[0]["function"]["name"] == "todo_update"
    assert "steps" in specs[0]["function"]["parameters"]["properties"]


def test_todo_middleware_tool_spec_respects_min_max_steps():
    mw = TodoMiddleware(min_steps=2, max_steps=5)
    spec = mw.tool_specs()[0]["function"]["parameters"]["properties"]["steps"]
    assert spec["minItems"] == 2
    assert spec["maxItems"] == 5


# ---------------------------------------------------------------------------
# on_tool_call happy path
# ---------------------------------------------------------------------------


def test_todo_middleware_accepts_valid_plan():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="diagnose the spike")
    result = mw.on_tool_call("todo_update", {
        "steps": [
            {"name": "load_events", "action": "load OMS events"},
            {"name": "detect_anomalies", "action": "run anomaly rules"},
        ]
    }, ctx)
    assert mw.has_plan()
    plan = mw.get_plan()
    assert plan is not None
    assert plan.goal == "diagnose the spike"
    assert len(plan.steps) == 2
    assert plan.steps[0].name == "load_events"
    assert plan.steps[0].action == "load OMS events"
    # Result is a JSON string the LLM will see
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is True
    assert parsed["step_count"] == 2


def test_todo_middleware_stores_plan_in_ctx_shared():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    mw.on_tool_call("todo_update", {"steps": [{"name": "s1", "action": "a"}]}, ctx)
    assert "todo_plan" in ctx.shared
    assert isinstance(ctx.shared["todo_plan"], TodoPlan)


def test_todo_middleware_emits_log_directive():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    mw.on_tool_call("todo_update", {"steps": [{"name": "s1", "action": "a"}]}, ctx)
    assert any(d.kind == "LOG" for d in ctx.directives)


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_todo_middleware_rejects_unknown_tool():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    result = mw.on_tool_call("definitely_not_todo_update", {}, ctx)
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "unknown tool" in parsed["error"]
    assert not mw.has_plan()


def test_todo_middleware_rejects_empty_steps():
    mw = TodoMiddleware(min_steps=1)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    result = mw.on_tool_call("todo_update", {"steps": []}, ctx)
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "at least" in parsed["error"]


def test_todo_middleware_rejects_too_many_steps():
    mw = TodoMiddleware(max_steps=3)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    result = mw.on_tool_call("todo_update", {
        "steps": [
            {"name": f"s{i}", "action": f"a{i}"} for i in range(5)
        ]
    }, ctx)
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "max" in parsed["error"]


def test_todo_middleware_rejects_duplicate_step_names():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    result = mw.on_tool_call("todo_update", {
        "steps": [
            {"name": "dup", "action": "first"},
            {"name": "dup", "action": "second"},
        ]
    }, ctx)
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "duplicate" in parsed["error"]


def test_todo_middleware_rejects_empty_step_name():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    result = mw.on_tool_call("todo_update", {
        "steps": [{"name": "", "action": "x"}],
    }, ctx)
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is False


def test_todo_middleware_rejects_non_string_action():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    result = mw.on_tool_call("todo_update", {
        "steps": [{"name": "s1", "action": 42}],
    }, ctx)
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is False


def test_todo_middleware_rejects_non_list_steps():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    result = mw.on_tool_call("todo_update", {"steps": "not a list"}, ctx)
    import json
    parsed = json.loads(result)
    assert parsed["ok"] is False


# ---------------------------------------------------------------------------
# Hook behaviour: plan_start resets, plan_end logs
# ---------------------------------------------------------------------------


def test_todo_middleware_resets_on_plan_start():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g1")
    mw.on_tool_call("todo_update", {"steps": [{"name": "s1", "action": "a"}]}, ctx)
    assert mw.has_plan()

    # New run: plan_start resets
    ctx2 = HookContext(hook=HOOK_PLAN_START, goal="g2")
    mw(ctx2)
    assert not mw.has_plan()


def test_todo_middleware_plan_end_logs_summary(caplog):
    import logging
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    mw.on_tool_call("todo_update", {"steps": [{"name": "s1", "action": "a"}]}, ctx)
    with caplog.at_level(logging.INFO, logger="madcop.agent.todo_middleware"):
        end_ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
        mw(end_ctx)
    assert any("final plan" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Plan serialization
# ---------------------------------------------------------------------------


def test_todo_plan_round_trips_through_dict():
    plan = TodoPlan(goal="g", steps=[
        TodoStep(name="a", action="do a"),
        TodoStep(name="b", action="do b", status="in_progress", notes="halfway"),
    ])
    d = plan.to_dict()
    plan2 = TodoPlan.from_dict(d)
    assert plan2.goal == "g"
    assert len(plan2.steps) == 2
    assert plan2.steps[1].status == "in_progress"
    assert plan2.steps[1].notes == "halfway"


def test_todo_plan_names_returns_step_names():
    plan = TodoPlan(goal="g", steps=[
        TodoStep(name="a", action="x"),
        TodoStep(name="b", action="y"),
    ])
    assert plan.names() == ["a", "b"]


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


def test_reset_clears_plan():
    mw = TodoMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g")
    mw.on_tool_call("todo_update", {"steps": [{"name": "s1", "action": "a"}]}, ctx)
    assert mw.has_plan()
    mw.reset()
    assert not mw.has_plan()
