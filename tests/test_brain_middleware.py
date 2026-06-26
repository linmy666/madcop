"""v1.2.0 — Tests for BrainMiddleware (auto-record from plan-execute)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_STEP_END,
    HookContext,
)
from madcop.brain.middleware import LEARN_PREFIX, BrainMiddleware
from madcop.brain.store import PageDB


@pytest.fixture
def db(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# learn: prefix path
# ---------------------------------------------------------------------------


def test_learn_prefix_creates_page(db):
    mw = BrainMiddleware(db)
    step = SimpleNamespace(name="observe", action="watch")
    outcome = SimpleNamespace(
        success=True, output="ok", error=None, cost_usd=0.0, duration_s=0.1,
        notes=f"{LEARN_PREFIX}---\ntitle: Note 1\ntype: skill\n---\n\n## Body\nX",
    )
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=step, outcome=outcome)
    mw(ctx)
    page = db.get("note-1")
    assert page is not None
    assert page.type == "skill"
    assert "Body" in page.compiled_truth


def test_non_learn_notes_ignored(db):
    mw = BrainMiddleware(db)
    step = SimpleNamespace(name="x", action="x")
    outcome = SimpleNamespace(
        success=True, output="ok", error=None, cost_usd=0.0, duration_s=0.1,
        notes="just an observation, no learn prefix",
    )
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=step, outcome=outcome)
    mw(ctx)
    assert db.list_all() == []


def test_learn_with_blank_body_ignored(db):
    mw = BrainMiddleware(db)
    step = SimpleNamespace(name="x", action="x")
    outcome = SimpleNamespace(
        success=True, output="ok", error=None, cost_usd=0.0, duration_s=0.1,
        notes=f"{LEARN_PREFIX}  \n  ",
    )
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=step, outcome=outcome)
    mw(ctx)
    assert db.list_all() == []


def test_learn_with_invalid_markdown_falls_back_to_step_slug(db):
    mw = BrainMiddleware(db)
    step = SimpleNamespace(name="load_data", action="x")
    # No frontmatter, no H1 — the markdown parser will slugify the
    # body text instead. The middleware's `slug` fallback only fires
    # when the parser returns an empty slug.
    outcome = SimpleNamespace(
        success=True, output="ok", error=None, cost_usd=0.0, duration_s=0.1,
        notes=f"{LEARN_PREFIX}??? !!!",
    )
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=step, outcome=outcome)
    mw(ctx)
    # The slug falls back to the step name slugified.
    page = db.get("load-data")
    assert page is not None
    assert page.type == "skill"


def test_learn_with_failed_outcome_still_saves(db):
    # The middleware writes regardless of success; the user opts in by
    # adding the learn: prefix.
    mw = BrainMiddleware(db)
    step = SimpleNamespace(name="x", action="x")
    outcome = SimpleNamespace(
        success=False, output="", error="oops", cost_usd=0.0, duration_s=0.1,
        notes=f"{LEARN_PREFIX}---\ntitle: Lesson 1\ntype: skill\n---\n\n## Insight\nX",
    )
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=step, outcome=outcome)
    mw(ctx)
    assert db.get("lesson-1") is not None


def test_middleware_swallows_save_errors(tmp_path, caplog):
    # If save() raises (e.g. invalid slug), middleware should not raise.
    db = PageDB(tmp_path / "brain.db")
    mw = BrainMiddleware(db)
    step = SimpleNamespace(name="x", action="x")
    outcome = SimpleNamespace(
        success=True, output="ok", error=None, cost_usd=0.0, duration_s=0.1,
        notes=f"{LEARN_PREFIX}---\ntitle: Bad\ntype: bogus\n---\n\nX",
    )
    ctx = HookContext(hook=HOOK_STEP_END, goal="g", step=step, outcome=outcome)
    # Should not raise even though type is invalid.
    mw(ctx)


# ---------------------------------------------------------------------------
# plan_end summary path
# ---------------------------------------------------------------------------


def test_plan_end_summary_writes_skill_page(db):
    mw = BrainMiddleware(db)
    step1 = SimpleNamespace(name="a", action="x")
    step2 = SimpleNamespace(name="b", action="y")
    plan = SimpleNamespace(steps=[step1, step2])
    shared = {
        "brain_summary": True,
        "step_outcomes": {
            "a": SimpleNamespace(success=True, output="ok", error=None,
                                 cost_usd=0.0, duration_s=0.1),
            "b": SimpleNamespace(success=False, output="", error="e",
                                 cost_usd=0.0, duration_s=0.1),
        },
    }
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=plan, shared=shared)
    mw(ctx)
    # Should have created a 'plan-summary' page (because no explicit slug)
    # — but the markdown parser sees the title "Plan summary" and
    # derives slug "plan-summary".
    page = db.get("plan-summary")
    assert page is not None
    assert page.type == "skill"


def test_plan_end_without_brain_summary_flag_is_noop(db):
    mw = BrainMiddleware(db)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=None, shared={})
    mw(ctx)
    assert db.list_all() == []


def test_plan_end_with_no_steps_is_noop(db):
    mw = BrainMiddleware(db)
    plan = SimpleNamespace(steps=[])
    shared = {"brain_summary": True}
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=plan, shared=shared)
    mw(ctx)
    assert db.list_all() == []


# ---------------------------------------------------------------------------
# learn prefix value
# ---------------------------------------------------------------------------


def test_learn_prefix_value():
    assert LEARN_PREFIX == "learn:"
