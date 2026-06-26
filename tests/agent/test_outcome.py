"""v1.3.0-rc.2 — Tests for the outcome-aware rerank layer (L3)."""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HookContext,
)
from madcop.agent.outcome import (
    DEFAULT_OUTCOME_HALF_LIFE_DAYS,
    DEFAULT_OUTCOME_WEIGHT,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    OUTCOME_UNKNOWN,
    OutcomePrioritizer,
    boost_outcome,
    format_lessons_with_outcome,
    lesson_outcome_score,
)
from madcop.agent.retrieval import (
    PriorLesson,
    RetrievalMiddleware,
    format_lessons,
)
from madcop.brain.store import PageDB


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def db(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    yield db
    db.close()


def _seed_outcome(db: PageDB) -> None:
    """Three skill pages, each with a different outcome stamp."""
    db.save(
        slug="reflection-success-1",
        title="success-recipe-1",
        page_type="skill",
        compiled_truth="Recipe A worked end-to-end last time.",
        frontmatter={
            "applies_to": "all",
            "topic": "success-recipe-1",
            "outcome": "success",
        },
        tags=["applies:all", "reflection", "outcome:success"],
    )
    db.save(
        slug="reflection-failure-1",
        title="failure-1",
        page_type="skill",
        compiled_truth="Recipe B failed at step 2 last time.",
        frontmatter={
            "applies_to": "all",
            "topic": "failure-1",
            "outcome": "failure",
        },
        tags=["applies:all", "reflection", "outcome:failure"],
    )
    db.save(
        slug="reflection-unknown-1",
        title="unknown-1",
        page_type="skill",
        compiled_truth="Recipe C has no outcome stamp yet.",
        frontmatter={
            "applies_to": "all",
            "topic": "unknown-1",
            # no outcome key
        },
        tags=["applies:all", "reflection"],
    )


def _ctx() -> HookContext:
    return HookContext(hook=HOOK_PLAN_START, goal="anything", plan=None, shared={})


def _lesson(
    topic: str,
    *,
    outcome: str | None = None,
    last_accessed_at: str | None = None,
    slug: str = "s",
    applies_to: str = "all",
    body: str = "x",
) -> PriorLesson:
    return PriorLesson(
        topic=topic,
        applies_to=applies_to,
        body=body,
        score=-1.0,
        last_accessed_at=last_accessed_at,
        slug=slug,
        outcome=outcome,
    )


# --------------------------------------------------------------------------- #
# boost_outcome — pure rerank
# --------------------------------------------------------------------------- #


def test_boost_outcome_returns_empty_for_empty_input():
    assert boost_outcome([]) == []


def test_boost_outcome_zero_weight_is_passthrough():
    L = [_lesson("a"), _lesson("b"), _lesson("c")]
    assert boost_outcome(L, outcome_weight=0.0) == L


def test_boost_outcome_promotes_success_over_failure():
    success = _lesson("success", outcome="success")
    failure = _lesson("failure", outcome="failure")
    unknown = _lesson("unknown", outcome="unknown")
    out = boost_outcome(
        [failure, unknown, success],
        outcome_weight=1.0,
        half_life_days=1000.0,  # No decay.
    )
    # success should be first, failure last; unknown in the middle.
    assert out[0] is success
    assert out[-1] is failure
    assert out[1] is unknown


def test_boost_outcome_stable_for_ties():
    a = _lesson("a", outcome="success")
    b = _lesson("b", outcome="success")
    c = _lesson("c", outcome="success")
    out = boost_outcome([a, b, c], outcome_weight=0.5, half_life_days=1000.0)
    # All same outcome → order preserved.
    assert out == [a, b, c]


def test_boost_outcome_recency_decays_old_outcome_tags():
    fresh_success = _lesson(
        "fresh", outcome="success",
        last_accessed_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    )
    old_failure = _lesson(
        "old", outcome="failure",
        last_accessed_at="2000-01-01T00:00:00Z",
    )
    out = boost_outcome(
        [old_failure, fresh_success],
        outcome_weight=1.0,
        half_life_days=30.0,
    )
    # Old failure tag is decayed to ~0; fresh success is +1.0 → success first.
    assert out[0] is fresh_success


def test_boost_outcome_works_with_searchhit_shaped_objects():
    """SearchHit-shaped objects carry the frontmatter on .page.frontmatter."""
    hit_success = SimpleNamespace(
        score=-1.0,
        page=SimpleNamespace(
            frontmatter={"outcome": "success"},
            last_accessed_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        ),
    )
    hit_failure = SimpleNamespace(
        score=-1.0,
        page=SimpleNamespace(
            frontmatter={"outcome": "failure"},
            last_accessed_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        ),
    )
    out = boost_outcome([hit_failure, hit_success], outcome_weight=1.0, half_life_days=1000.0)
    assert out[0] is hit_success


# --------------------------------------------------------------------------- #
# OutcomePrioritizer middleware
# --------------------------------------------------------------------------- #


def test_outcome_prioritizer_no_op_on_other_hooks():
    mw = OutcomePrioritizer()
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=None, shared={"prior_lessons": [_lesson("a")]})
    mw(ctx)
    assert ctx.shared["prior_lessons"][0].topic == "a"  # untouched


def test_outcome_prioritizer_no_lessons_no_crash():
    mw = OutcomePrioritizer()
    ctx = _ctx()
    mw(ctx)
    assert ctx.shared.get("prior_lessons") is None


def test_outcome_prioritizer_reorders_in_place():
    success = _lesson("success", outcome="success")
    failure = _lesson("failure", outcome="failure")
    ctx = _ctx()
    ctx.shared["prior_lessons"] = [failure, success]
    mw = OutcomePrioritizer(outcome_weight=1.0, half_life_days=1000.0)
    mw(ctx)
    assert ctx.shared["prior_lessons"][0] is success
    assert ctx.shared["prior_lessons"][1] is failure


def test_outcome_prioritizer_custom_inject_key():
    a = _lesson("a", outcome="success")
    b = _lesson("b", outcome="failure")
    ctx = _ctx()
    ctx.shared["my_lessons"] = [b, a]
    mw = OutcomePrioritizer(outcome_weight=1.0, half_life_days=1000.0, inject_key="my_lessons")
    mw(ctx)
    assert ctx.shared["my_lessons"][0] is a


def test_outcome_prioritizer_filter_strategy_drops_failures():
    success = _lesson("success", outcome="success")
    failure = _lesson("failure", outcome="failure")
    unknown = _lesson("unknown", outcome="unknown")
    ctx = _ctx()
    ctx.shared["prior_lessons"] = [failure, success, unknown]
    mw = OutcomePrioritizer(strategy="filter")
    mw(ctx)
    kept_topics = [l.topic for l in ctx.shared["prior_lessons"]]
    assert "failure" not in kept_topics
    assert "success" in kept_topics
    assert "unknown" in kept_topics


def test_outcome_prioritizer_swallows_exceptions(monkeypatch):
    def _boom(lessons, **_):
        raise RuntimeError("synthetic")
    monkeypatch.setattr("madcop.agent.outcome.boost_outcome", _boom)
    mw = OutcomePrioritizer()
    ctx = _ctx()
    ctx.shared["prior_lessons"] = [_lesson("a"), _lesson("b")]
    mw(ctx)  # should not raise
    assert len(ctx.shared["prior_lessons"]) == 2


# --------------------------------------------------------------------------- #
# format_lessons_with_outcome
# --------------------------------------------------------------------------- #


def test_format_lessons_with_outcome_empty_returns_empty():
    assert format_lessons_with_outcome([]) == ""


def test_format_lessons_with_outcome_annotates_glyphs():
    a = _lesson("success-recipe-1", outcome="success", body="Recipe A.")
    b = _lesson("failure-1", outcome="failure", body="Recipe B.")
    c = _lesson("unknown-1", outcome="unknown", body="Recipe C.")
    out = format_lessons_with_outcome([a, b, c])
    assert "## Prior lessons (outcome-tagged)" in out
    # The topic is wrapped in **bold** by the formatter. Check the
    # post-bold glyph (one space, then glyph).
    assert "**success-recipe-1** ✓" in out
    assert "**failure-1** ✗" in out
    assert "**unknown-1** ?" in out


def test_format_lessons_with_outcome_truncates_long_body():
    a = _lesson("a", outcome="success", body="x" * 1000)
    out = format_lessons_with_outcome([a])
    assert "..." in out
    # Body part should be < 250 chars after the header
    body_line = out.split("\n")[-1]
    assert len(body_line) < 300


# --------------------------------------------------------------------------- #
# lesson_outcome_score
# --------------------------------------------------------------------------- #


def test_lesson_outcome_score_maps_labels():
    success = _lesson("s", outcome="success", last_accessed_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()))
    failure = _lesson("f", outcome="failure", last_accessed_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()))
    unknown = _lesson("u", outcome="unknown", last_accessed_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()))
    s_score, s_label = lesson_outcome_score(success, half_life_days=1000.0)
    f_score, f_label = lesson_outcome_score(failure, half_life_days=1000.0)
    u_score, u_label = lesson_outcome_score(unknown, half_life_days=1000.0)
    assert s_label == "success" and s_score > 0
    assert f_label == "failure" and f_score < 0
    assert u_label == "unknown" and u_score == 0.0


# --------------------------------------------------------------------------- #
# ReflectionMiddleware — outcome stamp at write time
# --------------------------------------------------------------------------- #


def test_reflection_writes_outcome_field_on_success(tmp_path):
    """ReflectionMiddleware stamps outcome=success when plan succeeded."""
    from madcop.agent.reflection import ReflectionMiddleware
    from madcop.brain.store import PageDB

    db = PageDB(tmp_path / "brain.db")
    captured: dict[str, Any] = {}

    class _Client:
        def chat(self, **_):
            captured["called"] = True
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"reflections": [{"topic": "rate-limit-retry", "lesson": "Wait then retry."}]}'
                        }
                    }
                ]
            }

    plan = SimpleNamespace(
        steps=[
            SimpleNamespace(name="s1", action="do thing"),
        ]
    )
    ctx = HookContext(
        hook=HOOK_PLAN_END,
        goal="g",
        plan=plan,
        shared={
            "step_outcomes": {"s1": SimpleNamespace(success=True, error=None, cost_usd=0.001, duration_s=0.5)},
        },
    )
    mw = ReflectionMiddleware(client=_Client(), db=db)
    mw(ctx)

    assert captured.get("called")
    assert ctx.shared.get("reflection_outcome") == "success"
    # The page should carry outcome=success in frontmatter and a tag.
    page = db.get(slug="reflection-rate-limit-retry")
    assert page is not None
    assert page.frontmatter.get("outcome") == "success"
    assert "outcome:success" in [t.lower() for t in page.tags]
    db.close()


def test_reflection_writes_outcome_field_on_failure(tmp_path):
    """ReflectionMiddleware stamps outcome=failure when plan failed."""
    from madcop.agent.reflection import ReflectionMiddleware
    from madcop.brain.store import PageDB

    db = PageDB(tmp_path / "brain.db")
    captured: dict[str, Any] = {}

    class _Client:
        def chat(self, **_):
            captured["called"] = True
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"reflections": [{"topic": "bm25-vs-cosine", "lesson": "Use BM25 not cosine."}]}'
                        }
                    }
                ]
            }

    plan = SimpleNamespace(
        steps=[
            SimpleNamespace(name="s1", action="search"),
            SimpleNamespace(name="s2", action="write"),
        ]
    )
    ctx = HookContext(
        hook=HOOK_PLAN_END,
        goal="g",
        plan=plan,
        shared={
            "step_outcomes": {
                "s1": SimpleNamespace(success=True, error=None, cost_usd=0.001, duration_s=0.5),
                "s2": SimpleNamespace(success=False, error="timeout", cost_usd=0.002, duration_s=10.0),
            },
        },
    )
    mw = ReflectionMiddleware(client=_Client(), db=db)
    mw(ctx)

    assert captured.get("called")
    assert ctx.shared.get("reflection_outcome") == "failure"
    page = db.get(slug="reflection-bm25-vs-cosine")
    assert page is not None
    assert page.frontmatter.get("outcome") == "failure"
    assert "outcome:failure" in [t.lower() for t in page.tags]
    db.close()


# --------------------------------------------------------------------------- #
# End-to-end: RetrievalMiddleware → OutcomePrioritizer
# --------------------------------------------------------------------------- #


def test_end_to_end_retrieval_then_outcome_rerank(db):
    """A success-tagged lesson should outrank a failure-tagged one of equal FTS5 score."""
    _seed_outcome(db)
    retrieval = RetrievalMiddleware(db, top_k=3)
    outcome_pri = OutcomePrioritizer(outcome_weight=2.0, half_life_days=1000.0)
    chain_calls = [retrieval, outcome_pri]
    ctx = _ctx()
    # Each seeded page body contains the word "Recipe" — search for that.
    ctx.goal = "Recipe"
    for mw in chain_calls:
        mw(ctx)
    lessons = ctx.shared["prior_lessons"]
    assert len(lessons) == 3
    # The success lesson should be ranked first.
    assert lessons[0].outcome == "success"
    # The failure lesson should be ranked last.
    assert lessons[-1].outcome == "failure"


def test_outcome_aware_rerank_does_not_break_when_no_outcome_stamps(db):
    """When the brain has no outcome data, the order is unchanged."""
    # Seed a brain with no outcome field.
    db.save(
        slug="reflection-x",
        title="x",
        page_type="skill",
        compiled_truth="Lesson X.",
        frontmatter={"applies_to": "all", "topic": "x"},
        tags=["applies:all", "reflection"],
    )
    db.save(
        slug="reflection-y",
        title="y",
        page_type="skill",
        compiled_truth="Lesson Y.",
        frontmatter={"applies_to": "all", "topic": "y"},
        tags=["applies:all", "reflection"],
    )
    retrieval = RetrievalMiddleware(db, top_k=2)
    outcome_pri = OutcomePrioritizer(outcome_weight=1.0, half_life_days=1000.0)
    ctx = _ctx()
    ctx.goal = "common"
    retrieval(ctx)
    order_before = [l.slug for l in ctx.shared["prior_lessons"]]
    outcome_pri(ctx)
    order_after = [l.slug for l in ctx.shared["prior_lessons"]]
    # No outcome stamps → boost is 0 → order preserved.
    assert order_before == order_after


# --------------------------------------------------------------------------- #
# Backward-compat: rc.1 test brain without outcome stamps must still work
# --------------------------------------------------------------------------- #


def test_rc1_priors_have_outcome_none(db):
    """Old-style pages without outcome frontmatter → PriorLesson.outcome is None."""
    db.save(
        slug="legacy-skill",
        title="legacy",
        page_type="skill",
        compiled_truth="Old lesson.",
        frontmatter={"applies_to": "all", "topic": "legacy"},
        tags=["applies:all", "reflection"],
    )
    retrieval = RetrievalMiddleware(db, top_k=1)
    ctx = _ctx()
    ctx.goal = "old"
    retrieval(ctx)
    lessons = ctx.shared["prior_lessons"]
    assert len(lessons) == 1
    assert lessons[0].outcome is None  # No stamp — backward compat.


def test_default_outcome_weight_is_0_4():
    assert DEFAULT_OUTCOME_WEIGHT == 0.4


def test_default_outcome_half_life_days_is_60():
    assert DEFAULT_OUTCOME_HALF_LIFE_DAYS == 60.0
