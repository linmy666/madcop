"""v1.3.0 — Tests for the retrieval middleware (L2)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_STEP_END,
    HookContext,
)
from madcop.agent.retrieval import (
    DEFAULT_MIN_BM25,
    DEFAULT_TOP_K,
    PriorLesson,
    RetrievalMiddleware,
    filter_hits,
    format_lessons,
    rerank,
)
from madcop.brain.store import PageDB


@pytest.fixture
def db(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    yield db
    db.close()


def _seed(db: PageDB) -> None:
    db.save(
        slug="reflection-rate-limit", title="rate-limit-retry",
        page_type="skill",
        compiled_truth="Retry once on 5xx with exponential backoff.",
        frontmatter={"applies_to": "tool:http", "topic": "rate-limit-retry"},
        tags=["applies:tool:http", "reflection"],
    )
    db.save(
        slug="reflection-bm25", title="prefer-bm25",
        page_type="skill",
        compiled_truth="Use BM25 not cosine for small corpora.",
        frontmatter={"applies_to": "all", "topic": "prefer-bm25"},
        tags=["applies:all", "reflection"],
    )
    db.save(
        slug="reflection-validate", title="input-validation",
        page_type="skill",
        compiled_truth="Validate JSON shape before dispatching to parser.",
        frontmatter={"applies_to": "all", "topic": "input-validation"},
        tags=["applies:all", "reflection"],
    )
    # Non-skill page — should be filtered out by the default types=["skill"].
    db.save(
        slug="person-alice", title="Alice Park",
        page_type="person",
        compiled_truth="Alice is a coworker.",
        frontmatter={"applies_to": "all", "topic": "alice"},
        tags=["applies:all"],
    )


# ---------------------------------------------------------------------------
# RetrievalMiddleware basics
# ---------------------------------------------------------------------------


def test_middleware_only_runs_on_plan_start(db):
    _seed(db)
    mw = RetrievalMiddleware(db)
    ctx = HookContext(hook=HOOK_STEP_END, goal="rate")
    mw(ctx)
    assert "prior_lessons" not in ctx.shared


def test_middleware_injects_lessons_into_shared(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=3)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="validate JSON")
    mw(ctx)
    lessons = ctx.shared["prior_lessons"]
    assert isinstance(lessons, list)
    assert all(isinstance(l, PriorLesson) for l in lessons)
    topics = [l.topic for l in lessons]
    assert "input-validation" in topics


def test_middleware_filters_by_type_skill_only(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=10)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="Alice coworker")
    mw(ctx)
    topics = [l.topic for l in ctx.shared["prior_lessons"]]
    assert "alice" not in topics  # person page, not skill


def test_middleware_filters_by_tags(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=10, tags=["applies:tool:http"])
    ctx = HookContext(hook=HOOK_PLAN_START, goal="rate")
    mw(ctx)
    topics = [l.topic for l in ctx.shared["prior_lessons"]]
    assert topics == ["rate-limit-retry"]


def test_middleware_respects_top_k(db):
    _seed(db)
    # A goal that matches multiple lessons — FTS5's porter+unicode61
    # tokeniser returns hits for short queries better than long ones.
    mw = RetrievalMiddleware(db, top_k=1)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="validate JSON")
    mw(ctx)
    assert len(ctx.shared["prior_lessons"]) == 1


def test_middleware_zero_top_k_is_empty(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=0)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="x")
    mw(ctx)
    assert ctx.shared["prior_lessons"] == []


def test_middleware_empty_goal_is_empty(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=3)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="")
    mw(ctx)
    assert ctx.shared["prior_lessons"] == []


def test_middleware_no_matches_is_empty(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=3)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="zzz not a real concept zzz")
    mw(ctx)
    assert ctx.shared["prior_lessons"] == []


def test_middleware_swallows_search_errors(db, monkeypatch):
    _seed(db)

    def bad_search(*args, **kwargs):
        raise RuntimeError("FTS5 down")

    monkeypatch.setattr(db, "search", bad_search)
    mw = RetrievalMiddleware(db, top_k=3)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="x")
    mw(ctx)
    assert ctx.shared["prior_lessons"] == []


def test_middleware_custom_inject_key(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=3, inject_key="my_lessons")
    ctx = HookContext(hook=HOOK_PLAN_START, goal="rate")
    mw(ctx)
    assert "my_lessons" in ctx.shared
    assert "prior_lessons" not in ctx.shared


# ---------------------------------------------------------------------------
# Recency rerank
# ---------------------------------------------------------------------------


def test_recency_bonus_with_no_timestamp_is_neutral():
    from madcop.agent.retrieval import _recency_bonus
    # Missing timestamp -> 0.5 (neutral).
    assert _recency_bonus(None, 30.0) == 0.5
    assert _recency_bonus("", 30.0) == 0.5


def test_recency_bonus_today_is_high():
    from madcop.agent.retrieval import _recency_bonus
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    assert _recency_bonus(now, 30.0) > 0.9


def test_recency_bonus_old_is_low():
    from madcop.agent.retrieval import _recency_bonus
    old = "2000-01-01T00:00:00"
    assert _recency_bonus(old, 30.0) < 0.1


def test_recency_bonus_zero_half_life_returns_zero():
    from madcop.agent.retrieval import _recency_bonus
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    assert _recency_bonus(now, 0.0) == 0.0


def test_rerank_preserves_when_recency_weight_zero(tmp_path):
    db = PageDB(tmp_path / "x.db")
    _seed(db)
    hits = db.search("rate", limit=5)
    out = rerank(hits, recency_weight=0.0)
    assert out == hits
    db.close()


def test_rerank_prefers_recent_with_recency_weight(db):
    _seed(db)
    # Manually mark rate-limit page as fresh, validate as old.
    db._conn.execute(
        "UPDATE pages SET last_accessed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE slug='reflection-rate-limit'"
    )
    db._conn.execute(
        "UPDATE pages SET last_accessed_at = '2000-01-01T00:00:00Z' WHERE slug='reflection-validate'"
    )
    db._conn.commit()
    # Force a search that matches both.
    hits = db.search("rate", limit=10)
    # Rerank.
    out = rerank(hits, recency_weight=1.0, half_life_days=7.0)
    # rate-limit is fresh; should rank first.
    assert out[0].page.slug == "reflection-rate-limit"


def test_recency_zero_weight_disables_bonus(tmp_path):
    db = PageDB(tmp_path / "x2.db")
    _seed(db)
    hits = db.search("rate", limit=5)
    out = rerank(hits, recency_weight=0.0, half_life_days=1.0)
    # Order should equal the search order.
    raw = db.search("rate", limit=5)
    assert [h.page.slug for h in out] == [h.page.slug for h in raw]
    db.close()


# ---------------------------------------------------------------------------
# filter_hits
# ---------------------------------------------------------------------------


def test_filter_hits_drops_weak():
    # Construct a hit manually.
    hit = SimpleNamespace(score=-0.001, page=SimpleNamespace())  # type: ignore[arg-type]
    out = filter_hits([hit], min_bm25=-0.5)
    assert out == []  # -0.001 is greater than -0.5, so dropped


def test_filter_hits_keeps_strong():
    hit = SimpleNamespace(score=-1.5, page=SimpleNamespace())  # type: ignore[arg-type]
    out = filter_hits([hit], min_bm25=-0.5)
    assert len(out) == 1


def test_filter_hits_default_min():
    # A score of -0.0001 should pass with default min_bm25=0.0
    hit = SimpleNamespace(score=-0.0001, page=SimpleNamespace())  # type: ignore[arg-type]
    out = filter_hits([hit])
    assert len(out) == 1


# ---------------------------------------------------------------------------
# PriorLesson + format_lessons
# ---------------------------------------------------------------------------


def test_prior_lesson_to_prompt_line_basic(db):
    _seed(db)
    mw = RetrievalMiddleware(db, top_k=1)
    ctx = HookContext(hook=HOOK_PLAN_START, goal="rate")
    mw(ctx)
    line = ctx.shared["prior_lessons"][0].to_prompt_line()
    assert line.startswith("- **")
    # The applies_to value (e.g. 'tool:http' or 'all') is wrapped in backticks.
    assert ("tool:http" in line) or ("all" in line)


def test_prior_lesson_truncates_long_body():
    pl = PriorLesson(
        topic="t", applies_to="all", body="x" * 1000, score=-1.0,
        last_accessed_at=None, slug="s",
    )
    line = pl.to_prompt_line()
    assert "..." in line
    assert len(line) < 300  # 1000 truncated


def test_format_lessons_empty_returns_empty_string():
    assert format_lessons([]) == ""


def test_format_lessons_creates_prompt_block():
    pl = [
        PriorLesson(topic="a", applies_to="all", body="lesson a", score=-1.0,
                    last_accessed_at=None, slug="sa"),
        PriorLesson(topic="b", applies_to="tool:bash", body="lesson b", score=-2.0,
                    last_accessed_at=None, slug="sb"),
    ]
    out = format_lessons(pl)
    assert out.startswith("## Prior lessons")
    assert "lesson a" in out
    assert "lesson b" in out
    assert "tool:bash" in out


def test_format_lessons_skips_section_when_empty(db):
    out = format_lessons([])
    # Empty list -> empty string (caller decides what to do).
    assert out == ""


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_default_top_k_is_3():
    assert DEFAULT_TOP_K == 3


def test_default_min_bm25_is_zero():
    assert DEFAULT_MIN_BM25 == 0.0
