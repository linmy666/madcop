"""v1.3.0 — Tests for the reflection middleware (L1) and the reflection prompt parser."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_STEP_END,
    HookContext,
)
from madcop.agent.reflection import (
    DEFAULT_REFLECTION_PROMPT,
    ReflectionMiddleware,
    parse_reflections,
    summarize_plan,
)
from madcop.brain.store import PageDB


# ---------------------------------------------------------------------------
# Fake LLM client
# ---------------------------------------------------------------------------


class FakeClient:
    """Minimal OpenAI-compat client for tests. Returns a fixed response."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.last_kwargs: dict[str, Any] | None = None
        self.call_count = 0

    def chat(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        self.call_count += 1
        return self._response


def _fake_response(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture
def db(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# parse_reflections
# ---------------------------------------------------------------------------


def test_parse_reflections_happy_path():
    raw = '''Here you go:

```json
{
  "reflections": [
    {"topic": "rate-limit-retry", "lesson": "Retry once on 5xx.", "applies_to": "tool:http", "evidence_step": "fetch"},
    {"topic": "prefer-bm25", "lesson": "Use BM25 not cosine for small corpora.", "applies_to": "all", "evidence_step": "search_docs"}
  ]
}
```

Hope that helps.'''
    out = parse_reflections(raw)
    assert len(out) == 2
    assert out[0]["topic"] == "rate-limit-retry"
    assert out[0]["applies_to"] == "tool:http"
    assert out[1]["topic"] == "prefer-bm25"


def test_parse_reflections_inline_json():
    raw = '{"reflections": [{"topic": "x", "lesson": "y", "applies_to": "all", "evidence_step": "s"}]}'
    out = parse_reflections(raw)
    assert len(out) == 1


def test_parse_reflections_empty_input():
    assert parse_reflections("") == []
    assert parse_reflections("   ") == []


def test_parse_reflections_invalid_json():
    assert parse_reflections("not json at all") == []


def test_parse_reflections_wrong_shape():
    # JSON but not a dict
    assert parse_reflections("[1,2,3]") == []
    # Dict but no "reflections" key
    assert parse_reflections('{"foo": "bar"}') == []
    # reflections is not a list
    assert parse_reflections('{"reflections": "string"}') == []


def test_parse_reflections_skips_invalid_items():
    raw = '''{
        "reflections": [
            {"topic": "good", "lesson": "y", "applies_to": "all", "evidence_step": ""},
            {"topic": "", "lesson": "y", "applies_to": "all"},
            {"topic": "no_lesson", "lesson": "", "applies_to": "all"},
            "not a dict",
            {"topic": "also_good", "lesson": "y2", "applies_to": "tool:x", "evidence_step": "step2"}
        ]
    }'''
    out = parse_reflections(raw)
    assert len(out) == 2
    assert out[0]["topic"] == "good"
    assert out[1]["topic"] == "also_good"


def test_parse_reflections_caps_at_three():
    raw = json.dumps({
        "reflections": [
            {"topic": f"t{i}", "lesson": "y", "applies_to": "all"} for i in range(10)
        ]
    })
    out = parse_reflections(raw)
    assert len(out) == 3


def test_parse_reflections_normalises_topic():
    raw = '{"reflections": [{"topic": "Rate Limit Retry", "lesson": "y", "applies_to": "all"}]}'
    out = parse_reflections(raw)
    assert out[0]["topic"] == "rate-limit-retry"


# ---------------------------------------------------------------------------
# summarize_plan
# ---------------------------------------------------------------------------


def test_summarize_plan_empty():
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    summary = summarize_plan(ctx)
    assert summary["steps_total"] == 0
    assert summary["plan_success"] is False


def test_summarize_plan_all_success():
    s1 = SimpleNamespace(name="a", action="do a")
    s2 = SimpleNamespace(name="b", action="do b")
    plan = SimpleNamespace(steps=[s1, s2])
    o1 = SimpleNamespace(success=True, output="ok", error=None, cost_usd=0.01, duration_s=0.1)
    o2 = SimpleNamespace(success=True, output="ok", error=None, cost_usd=0.01, duration_s=0.1)
    ctx = HookContext(
        hook=HOOK_PLAN_END,
        goal="g",
        plan=plan,
        shared={"step_outcomes": {"a": o1, "b": o2}},
    )
    summary = summarize_plan(ctx)
    assert summary["steps_completed"] == 2
    assert summary["steps_total"] == 2
    assert summary["plan_success"] is True
    assert "a: do a" in summary["plan_lines"]
    assert "ok" in summary["outcome_lines"]
    assert summary["failure_modes"] == ["(none)"]


def test_summarize_plan_with_failures():
    s1 = SimpleNamespace(name="a", action="do a")
    s2 = SimpleNamespace(name="b", action="do b")
    plan = SimpleNamespace(steps=[s1, s2])
    o1 = SimpleNamespace(success=True, output="ok", error=None, cost_usd=0.01, duration_s=0.1)
    o2 = SimpleNamespace(success=False, output="", error="429 too many requests", cost_usd=0.01, duration_s=0.1)
    ctx = HookContext(
        hook=HOOK_PLAN_END,
        goal="g",
        plan=plan,
        shared={"step_outcomes": {"a": o1, "b": o2}},
    )
    summary = summarize_plan(ctx)
    assert summary["plan_success"] is False
    assert summary["steps_completed"] == 1
    assert "b: 429 too many requests" in summary["failure_modes"]


def test_summarize_plan_truncates_long_actions():
    s1 = SimpleNamespace(name="a", action="x" * 200)
    plan = SimpleNamespace(steps=[s1])
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=plan)
    summary = summarize_plan(ctx)
    assert "..." in summary["plan_lines"]


# ---------------------------------------------------------------------------
# ReflectionMiddleware
# ---------------------------------------------------------------------------


def test_middleware_only_runs_on_plan_end(db):
    mw = ReflectionMiddleware(FakeClient(_fake_response("{}")), db)
    ctx = HookContext(hook=HOOK_STEP_END, goal="g")
    mw(ctx)
    assert "reflections_written" not in ctx.shared
    assert mw._client.call_count == 0  # type: ignore[attr-defined]


def test_middleware_writes_reflections_to_brain(db):
    client = FakeClient(_fake_response('''{
        "reflections": [
            {"topic": "rate-limit", "lesson": "check status code", "applies_to": "tool:http", "evidence_step": "fetch"},
            {"topic": "input-validation", "lesson": "validate first", "applies_to": "all", "evidence_step": "fetch"}
        ]
    }'''))
    mw = ReflectionMiddleware(client, db, source="t")
    plan = SimpleNamespace(steps=[SimpleNamespace(name="fetch", action="x")])
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=plan)
    mw(ctx)
    assert ctx.shared["reflections_written"] == 2
    p1 = db.get("reflection-rate-limit")
    p2 = db.get("reflection-input-validation")
    assert p1 is not None and p2 is not None
    assert p1.type == "skill"
    assert "check status code" in p1.compiled_truth
    assert "applies:tool:http" in p1.tags


def test_middleware_swallows_llm_errors(db, caplog):
    class BadClient:
        def chat(self, **kwargs):
            raise RuntimeError("LLM down")
    mw = ReflectionMiddleware(BadClient(), db)  # type: ignore[arg-type]
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)  # should not raise
    assert db.list_all() == []


def test_middleware_handles_empty_reflections(db):
    client = FakeClient(_fake_response('{"reflections": []}'))
    mw = ReflectionMiddleware(client, db)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)
    assert db.list_all() == []


def test_middleware_handles_garbage_response(db):
    client = FakeClient(_fake_response("I cannot help with that, sorry."))
    mw = ReflectionMiddleware(client, db)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)  # should not raise
    assert db.list_all() == []


def test_middleware_max_reflections_caps_writes(db):
    payload = {
        "reflections": [
            {"topic": f"t{i}", "lesson": "y", "applies_to": "all"}
            for i in range(5)
        ]
    }
    client = FakeClient(_fake_response(json.dumps(payload)))
    mw = ReflectionMiddleware(client, db, max_reflections=2)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)
    assert ctx.shared["reflections_written"] == 2
    assert len(db.list_all()) == 2


def test_middleware_zero_max_reflections_is_noop(db):
    client = FakeClient(_fake_response('{"reflections": [{"topic":"x","lesson":"y"}]}'))
    mw = ReflectionMiddleware(client, db, max_reflections=0)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)
    assert client.call_count == 0
    assert db.list_all() == []


def test_middleware_skip_on_success(db):
    client = FakeClient(_fake_response('{"reflections": [{"topic":"x","lesson":"y"}]}'))
    mw = ReflectionMiddleware(client, db, skip_on_success=True)
    s = SimpleNamespace(name="a", action="x")
    plan = SimpleNamespace(steps=[s])
    o = SimpleNamespace(success=True, output="ok", error=None, cost_usd=0.01, duration_s=0.1)
    ctx = HookContext(
        hook=HOOK_PLAN_END,
        goal="g",
        plan=plan,
        shared={"step_outcomes": {"a": o}},
    )
    mw(ctx)
    assert client.call_count == 0


def test_middleware_calls_client_with_messages(db):
    client = FakeClient(_fake_response('{"reflections": []}'))
    mw = ReflectionMiddleware(client, db)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)
    assert client.call_count == 1
    assert "messages" in client.last_kwargs
    msgs = client.last_kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "g" in msgs[1]["content"]


def test_middleware_passes_model_when_set(db):
    client = FakeClient(_fake_response('{"reflections": []}'))
    mw = ReflectionMiddleware(client, db, model="custom-7b")
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)
    assert client.last_kwargs.get("model") == "custom-7b"


def test_middleware_extracts_content_from_object_response(db):
    """Object with .choices[0].message.content (the OpenAI shape)."""

    class ObjResponse:
        def __init__(self, content: str) -> None:
            self._content = content

        @property
        def choices(self):
            class _Msg:
                content = self._content
            class _Choice:
                message = _Msg()
            return [_Choice()]

    client = FakeClient(ObjResponse('{"reflections": [{"topic": "obj-shape", "lesson": "y"}]}'))
    mw = ReflectionMiddleware(client, db)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)
    assert ctx.shared["reflections_written"] == 1
    assert db.get("reflection-obj-shape") is not None


def test_middleware_passes_string_response(db):
    """A plain string (mock style) is also supported."""
    client = FakeClient('{"reflections": [{"topic": "str-shape", "lesson": "y"}]}')
    mw = ReflectionMiddleware(client, db)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g")
    mw(ctx)
    assert db.get("reflection-str-shape") is not None


# ---------------------------------------------------------------------------
# Prompt template sanity
# ---------------------------------------------------------------------------


def test_default_prompt_has_required_placeholders():
    required = [
        "{goal}", "{plan_success}", "{steps_completed}", "{steps_total}",
        "{total_cost}", "{total_duration}", "{failure_modes}",
        "{plan_lines}", "{outcome_lines}",
    ]
    for ph in required:
        assert ph in DEFAULT_REFLECTION_PROMPT, f"missing {ph}"


def test_default_prompt_uses_double_braces_in_json():
    """The embedded JSON example must use {{ ... }} to survive .format()."""
    assert '"reflections"' in DEFAULT_REFLECTION_PROMPT
    assert '{{' in DEFAULT_REFLECTION_PROMPT
    assert '}}' in DEFAULT_REFLECTION_PROMPT
