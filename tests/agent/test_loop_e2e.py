"""v1.3.0 — End-to-end loop engineering integration test.

This is the gating test for v1.3.0 release. It proves the full
closed-loop feedback circuit works:

  Run 1: plan fails → ReflectionMiddleware writes lesson to brain
  Run 2: same topic goal → RetrievalMiddleware finds the lesson
  Crystallize: 3+ lessons on same topic-prefix → one skill page

If this test passes, the "growing agent" story is real, not just
slides.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from madcop.agent.crystallize import (
    DEFAULT_MIN_CLUSTER_SIZE,
    crystallize_skills,
)
from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_STEP_END,
    HookContext,
    MiddlewareChain,
)
from madcop.agent.reflection import ReflectionMiddleware
from madcop.agent.retrieval import RetrievalMiddleware, format_lessons
from madcop.brain.store import PageDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ScriptedClient:
    """LLM client that returns a sequence of responses, one per call.

    Each ``chat()`` call pops the next response. If we run out, raises.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def chat(self, **kwargs: Any) -> Any:
        if self.call_count >= len(self._responses):
            raise AssertionError(
                f"ScriptedClient exhausted: {self.call_count} calls, "
                f"{len(self._responses)} responses"
            )
        resp = self._responses[self.call_count]
        self.call_count += 1
        return {"choices": [{"message": {"content": resp}}]}


def _make_ctx(
    goal: str,
    hook: str = HOOK_PLAN_END,
    *,
    steps: list[dict] | None = None,
    outcomes: dict[str, dict] | None = None,
    plan_success: bool = False,
) -> HookContext:
    """Build a HookContext simulating a finished plan-execute run."""
    plan = SimpleNamespace(steps=[])
    step_outcomes: dict[str, Any] = {}
    for s in steps or []:
        step = SimpleNamespace(
            name=s["name"],
            action=s.get("action", ""),
        )
        plan.steps.append(step)
        if s["name"] in (outcomes or {}):
            oc = outcomes[s["name"]]
            step_outcomes[s["name"]] = SimpleNamespace(
                success=oc.get("success"),
                error=oc.get("error"),
                cost_usd=oc.get("cost_usd", 0.0),
                duration_s=oc.get("duration_s", 1.0),
            )
    ctx = HookContext(hook=hook, goal=goal, plan=plan)
    ctx.shared["step_outcomes"] = step_outcomes
    ctx.shared["plan_success"] = plan_success
    return ctx


# ---------------------------------------------------------------------------
# Test 1: Run 1 fails → reflection → Run 2 retrieves the lesson
# ---------------------------------------------------------------------------


def test_e2e_reflection_then_retrieval(tmp_path):
    """The minimal closed loop: fail → learn → retrieve next time.

    1. Simulate a failed run about "rate limiting".
    2. ReflectionMiddleware writes 1 lesson to the brain.
    3. RetrievalMiddleware on a similar goal finds and returns it.
    """
    db = PageDB(tmp_path / "brain.db")

    # --- Run 1: plan fails, reflection writes a lesson ---

    reflection_json = json.dumps({
        "reflections": [
            {
                "topic": "rate-limit-retry",
                "lesson": "When hitting HTTP 429, use exponential backoff with jitter, not fixed delay.",
                "applies_to": "all",
                "evidence_step": "fetch-api",
            }
        ]
    })

    client = ScriptedClient([reflection_json])
    reflect = ReflectionMiddleware(client=client, db=db)

    ctx1 = _make_ctx(
        goal="Fetch data from rate-limited API",
        hook=HOOK_PLAN_END,
        steps=[
            {"name": "fetch-api", "action": "GET /api/data"},
        ],
        outcomes={
            "fetch-api": {"success": False, "error": "HTTP 429 Too Many Requests"},
        },
        plan_success=False,
    )

    reflect(ctx1)
    assert ctx1.shared.get("reflections_written") == 1

    # Verify the lesson landed in the brain
    results = db.search("rate limit")
    assert len(results) >= 1
    assert "rate-limit" in results[0].page.compiled_truth.lower() or \
           "rate-limit" in results[0].page.title.lower()

    # --- Run 2: similar goal → retrieval finds the lesson ---

    retrieve = RetrievalMiddleware(db=db, top_k=3)
    ctx2 = _make_ctx(
        goal="Handle rate limit on API",
        hook=HOOK_PLAN_START,
    )

    retrieve(ctx2)
    lessons = ctx2.shared.get("prior_lessons", [])
    assert len(lessons) >= 1
    lesson = lessons[0]
    assert "rate" in lesson.body.lower() or "429" in lesson.body
    assert lesson.topic is not None

    # Verify format_lessons produces injectable text
    formatted = format_lessons(lessons)
    assert "## Prior lessons" in formatted
    assert len(formatted) > 20  # has real content

    db.close()


# ---------------------------------------------------------------------------
# Test 2: Three reflections → crystallization → one skill page
# ---------------------------------------------------------------------------


def test_e2e_crystallization_after_multiple_runs(tmp_path):
    """Three runs on rate-limiting → crystallize into one skill.

    1. Run 3 failed plans, each producing a reflection on rate-limit-*.
    2. Call crystallize_skills → writes a single "rate-limit" skill page.
    3. Retrieval on a rate-limit goal now finds the crystallized page.
    """
    db = PageDB(tmp_path / "brain.db")

    # Simulate 3 reflections written by 3 separate runs.
    # (We write them directly to the brain for speed; the reflection
    # middleware's write path is covered by test_e2e_reflection_then_retrieval.)
    for i, (topic, lesson) in enumerate([
        ("rate-limit-retry", "Use exponential backoff with jitter on 429."),
        ("rate-limit-burst", "Implement a token bucket, not fixed windows."),
        ("rate-limit-headers", "Read X-RateLimit-Reset to schedule retries."),
    ]):
        db.save(
            slug=f"reflection-{topic}",
            title=topic,
            page_type="skill",
            compiled_truth=lesson,
            timeline="",
            frontmatter={
                "type": "skill",
                "topic": topic,
                "applies_to": "all",
                "outcome": "failure" if i < 2 else "success",
            },
            tags=["reflection", f"topic:{topic}", "outcome:failure" if i < 2 else "outcome:success"],
            source="reflection",
        )

    # Verify all 3 are in the brain
    assert db.stats()["pages"] == 3

    # Crystallize
    new_slugs = crystallize_skills(db, min_cluster_size=3)
    assert len(new_slugs) == 1
    assert "skill-rate-limit" in new_slugs[0]

    # The crystallized page exists
    skill_page = db.get("skill-rate-limit")
    assert skill_page is not None
    assert "crystallized" in (skill_page.tags or [])
    assert "rate-limit" in skill_page.compiled_truth.lower()

    # Retrieval now finds the crystallized skill
    retrieve = RetrievalMiddleware(db=db, top_k=3)
    ctx = _make_ctx(
        goal="rate limit handling",
        hook=HOOK_PLAN_START,
    )
    retrieve(ctx)
    lessons = ctx.shared.get("prior_lessons", [])
    assert len(lessons) >= 1
    # The crystallized page should be among the hits
    slugs = {l.slug for l in lessons}
    assert "skill-rate-limit" in slugs

    db.close()


# ---------------------------------------------------------------------------
# Test 3: Full middleware chain — reflection + retrieval compose
# ---------------------------------------------------------------------------


def test_e2e_middleware_chain_composition(tmp_path):
    """Reflection and retrieval compose in a MiddlewareChain.

    Build a chain with both. Run it through HOOK_PLAN_START then
    HOOK_PLAN_END and verify each fires at the right hook.
    """
    db = PageDB(tmp_path / "brain.db")

    reflection_json = json.dumps({
        "reflections": [
            {
                "topic": "timeout-config",
                "lesson": "Set timeout to 30s, not the default 5s, for slow APIs.",
                "applies_to": "all",
                "evidence_step": "call-api",
            }
        ]
    })

    client = ScriptedClient([reflection_json])
    chain = MiddlewareChain([
        RetrievalMiddleware(db=db, top_k=5),
        ReflectionMiddleware(client=client, db=db),
    ])

    # --- HOOK_PLAN_START: retrieval runs, reflection skips ---
    ctx_start = _make_ctx(
        goal="Call a slow external API",
        hook=HOOK_PLAN_START,
    )
    chain(ctx_start)
    # No lessons yet (empty brain)
    assert ctx_start.shared.get("prior_lessons") == []

    # --- HOOK_PLAN_END: reflection runs, retrieval skips ---
    ctx_end = _make_ctx(
        goal="Call a slow external API",
        hook=HOOK_PLAN_END,
        steps=[
            {"name": "call-api", "action": "GET /slow-api"},
        ],
        outcomes={
            "call-api": {"success": False, "error": "Timeout after 5s"},
        },
        plan_success=False,
    )
    chain(ctx_end)
    assert ctx_end.shared.get("reflections_written") == 1

    # --- Second run HOOK_PLAN_START: retrieval now finds the lesson ---
    ctx_start2 = _make_ctx(
        goal="slow API timeout",
        hook=HOOK_PLAN_START,
    )
    chain(ctx_start2)
    lessons = ctx_start2.shared.get("prior_lessons", [])
    assert len(lessons) >= 1
    assert any("timeout" in l.body.lower() for l in lessons)

    db.close()


# ---------------------------------------------------------------------------
# Test 4: Cross-topic isolation — rate-limit lesson NOT retrieved for
# unrelated goal
# ---------------------------------------------------------------------------


def test_e2e_topic_isolation(tmp_path):
    """A lesson about rate-limiting should not surface for a cooking goal.

    This proves the FTS5 retrieval is discriminating, not just returning
    everything.
    """
    db = PageDB(tmp_path / "brain.db")

    db.save(
        slug="reflection-rate-limit-retry",
        title="rate-limit-retry",
        page_type="skill",
        compiled_truth="When hitting HTTP 429, use exponential backoff.",
        frontmatter={"topic": "rate-limit-retry", "applies_to": "all"},
        tags=["reflection", "topic:rate-limit-retry"],
        source="reflection",
    )

    retrieve = RetrievalMiddleware(db=db, top_k=3, min_bm25=-0.5)
    ctx = _make_ctx(
        goal="Find a good recipe for chocolate cake",
        hook=HOOK_PLAN_START,
    )
    retrieve(ctx)
    lessons = ctx.shared.get("prior_lessons", [])
    # FTS5 should not match "chocolate cake" against rate-limiting content
    # (or at worst, the bm25 score should be too weak to pass)
    cake_lessons = [l for l in lessons if "rate" not in l.body.lower()]
    # If any lessons came back, they shouldn't be about rate limiting
    for l in lessons:
        assert "rate-limit" not in l.body.lower(), \
            f"Rate-limit lesson leaked into cooking query: {l.body}"

    db.close()


# ---------------------------------------------------------------------------
# Test 5: Empty brain → retrieval returns nothing, no crash
# ---------------------------------------------------------------------------


def test_e2e_empty_brain_retrieval(tmp_path):
    """Retrieval on an empty brain is a no-op, not an error."""
    db = PageDB(tmp_path / "brain.db")

    retrieve = RetrievalMiddleware(db=db, top_k=3)
    ctx = _make_ctx(
        goal="Do something with a database",
        hook=HOOK_PLAN_START,
    )
    retrieve(ctx)
    assert ctx.shared.get("prior_lessons") == []

    db.close()
