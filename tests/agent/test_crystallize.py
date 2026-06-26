"""v1.3.0-rc.3 — Tests for the L4 skill crystallization layer."""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from madcop.agent.crystallize import (
    CRYSTALLIZED_SAVED_BY,
    CRYSTALLIZED_SOURCE,
    CRYSTALLIZED_TAG,
    DEFAULT_MIN_CLUSTER_SIZE,
    DEFAULT_PREFIX_SPLIT,
    SkillCrystallizer,
    aggregate_outcome,
    cluster_topics,
    crystallize_skills,
    render_skill_body,
)
from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HookContext,
)
from madcop.brain.store import Page, PageDB


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def db(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    yield db
    db.close()


def _make_page(
    slug: str,
    topic: str,
    *,
    outcome: str | None = "unknown",
    applies_to: str = "all",
    page_type: str = "skill",
    updated_at: str | None = None,
    tags: list[str] | None = None,
) -> Page:
    """Construct an in-memory Page without going through db.save()."""
    frontmatter: dict[str, Any] = {"topic": topic, "applies_to": applies_to}
    if outcome is not None:
        frontmatter["outcome"] = outcome
    return Page(
        id=hash(slug) & 0x7FFFFFFF,
        slug=slug,
        type=page_type,
        title=topic,
        compiled_truth=f"body of {slug}",
        timeline="",
        frontmatter=frontmatter,
        tags=tags if tags is not None else ["reflection", f"topic:{topic}"],
        created_at=updated_at or "2026-06-26T00:00:00Z",
        updated_at=updated_at or "2026-06-26T00:00:00Z",
        last_accessed_at=updated_at or "2026-06-26T00:00:00Z",
        content_hash="x" * 40,
    )


# --------------------------------------------------------------------------- #
# cluster_topics
# --------------------------------------------------------------------------- #


def test_cluster_topics_groups_by_prefix():
    p1 = _make_page("reflection-rate-limit-retry", "rate-limit-retry")
    p2 = _make_page("reflection-rate-limit-burst", "rate-limit-burst")
    p3 = _make_page("reflection-rate-limit-headers", "rate-limit-headers")
    p4 = _make_page("reflection-input-validation", "input-validation")
    out = cluster_topics([p1, p2, p3, p4], min_cluster_size=3)
    assert "rate-limit" in out
    assert len(out["rate-limit"]) == 3
    # input-validation is alone; should be dropped (cluster size 1).
    assert "input-validation" not in out


def test_cluster_topics_respects_min_cluster_size():
    p1 = _make_page("reflection-rate-limit-retry", "rate-limit-retry")
    p2 = _make_page("reflection-rate-limit-burst", "rate-limit-burst")
    out = cluster_topics([p1, p2], min_cluster_size=3)
    # min_cluster_size=3 excludes 2-element clusters.
    assert out == {}


def test_cluster_topics_empty_input_is_empty():
    assert cluster_topics([]) == {}


def test_cluster_topics_handles_underscore_split():
    p1 = _make_page("a", "rate_limit_retry")
    p2 = _make_page("b", "rate_limit_burst")
    p3 = _make_page("c", "rate_limit_headers")
    out = cluster_topics([p1, p2, p3], min_cluster_size=3, split="_")
    assert "rate_limit" in out
    assert len(out["rate_limit"]) == 3


def test_cluster_topics_sorts_members_by_updated_at_desc():
    p_old = _make_page("a", "rate-limit-retry", updated_at="2026-01-01T00:00:00Z")
    p_new = _make_page("b", "rate-limit-burst", updated_at="2026-06-01T00:00:00Z")
    p_mid = _make_page("c", "rate-limit-headers", updated_at="2026-03-01T00:00:00Z")
    out = cluster_topics([p_old, p_new, p_mid], min_cluster_size=3)
    assert [p.slug for p in out["rate-limit"]] == ["b", "c", "a"]


def test_cluster_topics_includes_crystallized_pages_in_input():
    """cluster_topics does NOT filter out crystallized pages — the
    caller (crystallize_skills) is responsible. We pass them through
    and let cluster_topics group them like any other page.
    """
    p1 = _make_page("a", "rate-limit-retry")
    p2 = _make_page("b", "rate-limit-burst")
    p3 = _make_page("c", "rate-limit-headers")
    # pre-existing crystallized page (its own topic = the cluster prefix)
    p4 = _make_page("skill-rate-limit", "rate-limit", tags=["crystallized"])
    out = cluster_topics([p1, p2, p3, p4], min_cluster_size=3)
    # All 4 pages share the rate-limit prefix; all end up in the cluster.
    assert "rate-limit" in out
    assert len(out["rate-limit"]) == 4


# --------------------------------------------------------------------------- #
# aggregate_outcome
# --------------------------------------------------------------------------- #


def test_aggregate_outcome_majority_success():
    pages = [
        _make_page("a", "x", outcome="success"),
        _make_page("b", "y", outcome="success"),
        _make_page("c", "z", outcome="failure"),
    ]
    assert aggregate_outcome(pages) == "success"


def test_aggregate_outcome_majority_failure():
    pages = [
        _make_page("a", "x", outcome="failure"),
        _make_page("b", "y", outcome="failure"),
        _make_page("c", "z", outcome="success"),
    ]
    assert aggregate_outcome(pages) == "failure"


def test_aggregate_outcome_tie_is_unknown():
    pages = [
        _make_page("a", "x", outcome="success"),
        _make_page("b", "y", outcome="failure"),
    ]
    assert aggregate_outcome(pages) == "unknown"


def test_aggregate_outcome_all_unknown_is_unknown():
    pages = [_make_page("a", "x", outcome="unknown")]
    assert aggregate_outcome(pages) == "unknown"


def test_aggregate_outcome_empty_input_is_unknown():
    assert aggregate_outcome([]) == "unknown"


# --------------------------------------------------------------------------- #
# render_skill_body
# --------------------------------------------------------------------------- #


def test_render_skill_body_has_frontmatter():
    members = [_make_page("a", "rate-limit-retry", outcome="success")]
    body = render_skill_body("rate-limit", members)
    assert body.startswith("---\n")
    assert "type: skill" in body
    assert "topic: rate-limit" in body
    assert "outcome: success" in body


def test_render_skill_body_lists_all_members():
    members = [
        _make_page("a", "rate-limit-retry", outcome="success"),
        _make_page("b", "rate-limit-burst", outcome="failure"),
        _make_page("c", "rate-limit-headers", outcome="success"),
    ]
    body = render_skill_body("rate-limit", members)
    assert "rate-limit-retry" in body
    assert "rate-limit-burst" in body
    assert "rate-limit-headers" in body
    # Member slugs also appear (for the membership-set check).
    assert "a" in body
    assert "b" in body
    assert "c" in body


def test_render_skill_body_aggregates_outcome():
    members = [
        _make_page("a", "x", outcome="success"),
        _make_page("b", "y", outcome="success"),
        _make_page("c", "z", outcome="failure"),
    ]
    body = render_skill_body("rate-limit", members)
    assert "outcome: success" in body  # 2/3 majority


# --------------------------------------------------------------------------- #
# crystallize_skills — full E2E on PageDB
# --------------------------------------------------------------------------- #


def test_crystallize_skills_writes_skill_pages(db):
    """3 reflections sharing the prefix rate-limit should produce 1 skill page."""
    for i, topic in enumerate(["retry", "burst", "headers"]):
        db.save(
            slug=f"reflection-rate-limit-{topic}",
            title=f"rate-limit-{topic}",
            page_type="skill",
            compiled_truth=f"Lesson about rate-limit-{topic}.",
            frontmatter={
                "applies_to": "all",
                "topic": f"rate-limit-{topic}",
                "outcome": "success",
            },
            tags=["reflection", f"topic:rate-limit-{topic}"],
        )
    new_slugs = crystallize_skills(db, min_cluster_size=3)
    assert "skill-rate-limit" in new_slugs
    page = db.get(slug="skill-rate-limit")
    assert page is not None
    assert page.type == "skill"
    assert "crystallized" in page.tags
    # The body should mention the 3 member topics.
    for topic in ["retry", "burst", "headers"]:
        assert topic in page.compiled_truth


def test_crystallize_skills_no_clusters_no_writes(db):
    """When no cluster meets the threshold, no skill pages are written.

    Use *truly* distinct topic prefixes so no cluster forms. The
    test originally used 'reflection-a/b/c' which all share the
    prefix 'reflection' (3-cluster) and incorrectly formed a cluster.
    """
    for slug, topic in [
        ("reflection-alpha", "alpha"),
        ("reflection-beta", "beta"),
        ("reflection-gamma", "gamma"),
    ]:
        db.save(
            slug=slug,
            title=slug,
            page_type="skill",
            compiled_truth="x",
            frontmatter={"topic": topic, "outcome": "success"},
            tags=["reflection"],
        )
    new_slugs = crystallize_skills(db, min_cluster_size=3)
    # Each topic is in its own prefix; no cluster forms.
    assert new_slugs == []


def test_crystallize_skills_idempotent(db):
    """Re-running crystallize_skills without new members should not create a new version."""
    for topic in ["retry", "burst", "headers"]:
        db.save(
            slug=f"reflection-rate-limit-{topic}",
            title=topic,
            page_type="skill",
            compiled_truth="x",
            frontmatter={"topic": f"rate-limit-{topic}", "outcome": "success"},
            tags=["reflection"],
        )
    new_slugs_1 = crystallize_skills(db, min_cluster_size=3)
    assert "skill-rate-limit" in new_slugs_1
    new_slugs_2 = crystallize_skills(db, min_cluster_size=3)
    # Idempotency: same member set, no new slugs.
    assert new_slugs_2 == []


def test_crystallize_skills_picks_up_new_member(db):
    """When a 4th member joins the cluster, re-crystallize picks it up."""
    for topic in ["retry", "burst", "headers"]:
        db.save(
            slug=f"reflection-rate-limit-{topic}",
            title=topic,
            page_type="skill",
            compiled_truth="x",
            frontmatter={"topic": f"rate-limit-{topic}", "outcome": "success"},
            tags=["reflection"],
        )
    new_slugs_1 = crystallize_skills(db, min_cluster_size=3)
    assert "skill-rate-limit" in new_slugs_1
    # Add a 4th member.
    db.save(
        slug="reflection-rate-limit-quota",
        title="quota",
        page_type="skill",
        compiled_truth="x",
        frontmatter={"topic": "rate-limit-quota", "outcome": "success"},
        tags=["reflection"],
    )
    new_slugs_2 = crystallize_skills(db, min_cluster_size=3)
    # New member joined -> re-crystallize.
    assert "skill-rate-limit" in new_slugs_2


def test_crystallize_skills_outcome_is_aggregated(db):
    """Cluster outcome is the majority of member outcomes."""
    for topic, outcome in [
        ("retry", "success"),
        ("burst", "success"),
        ("headers", "failure"),
    ]:
        db.save(
            slug=f"reflection-rate-limit-{topic}",
            title=topic,
            page_type="skill",
            compiled_truth="x",
            frontmatter={
                "topic": f"rate-limit-{topic}",
                "outcome": outcome,
            },
            tags=["reflection"],
        )
    crystallize_skills(db, min_cluster_size=3)
    page = db.get(slug="skill-rate-limit")
    assert page.frontmatter.get("outcome") == "success"


def test_crystallize_skills_excludes_non_skill_pages(db):
    """Non-skill pages (e.g. 'person') should be ignored even if their topic shares a prefix."""
    for topic in ["retry", "burst", "headers"]:
        db.save(
            slug=f"reflection-rate-limit-{topic}",
            title=topic,
            page_type="skill",
            compiled_truth="x",
            frontmatter={"topic": f"rate-limit-{topic}", "outcome": "success"},
            tags=["reflection"],
        )
    # Add a non-skill page with a matching topic.
    db.save(
        slug="person-rate-limit",
        title="rate-limit person",
        page_type="person",
        compiled_truth="a person",
        frontmatter={"topic": "rate-limit"},
        tags=["person"],
    )
    new_slugs = crystallize_skills(db, min_cluster_size=3)
    assert "skill-rate-limit" in new_slugs
    page = db.get(slug="skill-rate-limit")
    # The person page should NOT appear in the member list.
    assert "person-rate-limit" not in page.compiled_truth


# --------------------------------------------------------------------------- #
# SkillCrystallizer middleware
# --------------------------------------------------------------------------- #


def test_crystallizer_middleware_disabled_by_default(db):
    mw = SkillCrystallizer(db)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=None, shared={})
    mw(ctx)
    assert ctx.shared.get("crystallized_skills") == []


def test_crystallizer_middleware_runs_when_enabled(db):
    for topic in ["retry", "burst", "headers"]:
        db.save(
            slug=f"reflection-rate-limit-{topic}",
            title=topic,
            page_type="skill",
            compiled_truth="x",
            frontmatter={"topic": f"rate-limit-{topic}", "outcome": "success"},
            tags=["reflection"],
        )
    mw = SkillCrystallizer(db, enabled=True)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=None, shared={})
    mw(ctx)
    assert "skill-rate-limit" in ctx.shared["crystallized_skills"]


def test_crystallizer_middleware_only_runs_on_plan_end(db):
    for topic in ["retry", "burst", "headers"]:
        db.save(
            slug=f"reflection-rate-limit-{topic}",
            title=topic,
            page_type="skill",
            compiled_truth="x",
            frontmatter={"topic": f"rate-limit-{topic}", "outcome": "success"},
            tags=["reflection"],
        )
    mw = SkillCrystallizer(db, enabled=True)
    # plan_start should be a no-op
    from madcop.agent.middleware import HOOK_PLAN_START
    ctx = HookContext(hook=HOOK_PLAN_START, goal="g", plan=None, shared={})
    mw(ctx)
    assert ctx.shared.get("crystallized_skills") is None


def test_crystallizer_middleware_swallows_exceptions(db, monkeypatch):
    def _boom(**_):
        raise RuntimeError("synthetic")
    monkeypatch.setattr("madcop.agent.crystallize.crystallize_skills", _boom)
    mw = SkillCrystallizer(db, enabled=True)
    ctx = HookContext(hook=HOOK_PLAN_END, goal="g", plan=None, shared={})
    mw(ctx)  # should not raise
    assert ctx.shared["crystallized_skills"] == []


# --------------------------------------------------------------------------- #
# End-to-end: a full L1 -> L4 chain
# --------------------------------------------------------------------------- #


def test_full_chain_reflection_to_crystallization(db):
    """Simulate the full loop: write 3 reflections via the L1
    middleware, then crystallize via the L4 module, and confirm
    the brain now has 4 skill pages (3 reflections + 1 cluster
    head)."""
    from madcop.agent.reflection import ReflectionMiddleware

    plan = SimpleNamespace(
        steps=[
            SimpleNamespace(name="s1", action="do thing"),
        ]
    )
    # Three plan-end calls, each writing a rate-limit-* topic.
    topics = ["rate-limit-retry", "rate-limit-burst", "rate-limit-headers"]
    for t in topics:
        captured: dict[str, Any] = {}

        class _Client:
            def chat(self, **_):
                captured["called"] = True
                return {
                    "choices": [
                        {
                            "message": {
                                "content": f'{{"reflections": [{{"topic": "{t}", "lesson": "lesson for {t}"}}]}}'
                            }
                        }
                    ]
                }

        ctx = HookContext(
            hook=HOOK_PLAN_END,
            goal="g",
            plan=plan,
            shared={
                "step_outcomes": {
                    "s1": SimpleNamespace(success=True, error=None, cost_usd=0.001, duration_s=0.5)
                },
            },
        )
        ReflectionMiddleware(client=_Client(), db=db)(ctx)
        assert captured.get("called")
    # Now crystallize.
    new_slugs = crystallize_skills(db, min_cluster_size=3)
    assert "skill-rate-limit" in new_slugs
    # The cluster head must be retrievable like any other skill page.
    page = db.get(slug="skill-rate-limit")
    assert page is not None
    # And it must aggregate the cluster's outcome.
    assert page.frontmatter.get("outcome") == "success"


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #


def test_default_min_cluster_size_is_3():
    assert DEFAULT_MIN_CLUSTER_SIZE == 3


def test_default_prefix_split_is_dash():
    assert DEFAULT_PREFIX_SPLIT == "-"
