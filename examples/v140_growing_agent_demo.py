"""v1.4.0 — End-to-end demo: the growing agent.

This demo shows madcop's four-layer closed-loop feedback in action:

  Run 1: Agent fails at a task → ReflectionMiddleware writes a lesson.
  Run 2: Agent retries a similar task → RetrievalMiddleware finds the
         lesson and injects it into context.
  Crystallize: Three related lessons are clustered into one named skill.

No real LLM API key needed — we use a ScriptedClient that returns
canned responses. The brain state is real (SQLite + FTS5).

Run:
  python examples/v140_growing_agent_demo.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

# Make `madcop` importable when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madcop.agent.crystallize import crystallize_skills
from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HookContext,
    MiddlewareChain,
)
from madcop.agent.reflection import ReflectionMiddleware
from madcop.agent.retrieval import RetrievalMiddleware, format_lessons
from madcop.brain.store import PageDB


# ---------------------------------------------------------------------------
# Scripted LLM client — returns canned reflection responses
# ---------------------------------------------------------------------------


class ScriptedClient:
    """Returns a fixed sequence of JSON responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._idx = 0

    def chat(self, **kwargs):
        if self._idx >= len(self._responses):
            raise AssertionError("ScriptedClient exhausted")
        resp = self._responses[self._idx]
        self._idx += 1
        return {"choices": [{"message": {"content": resp}}]}


def _make_ctx(
    goal: str,
    hook: str,
    steps: list[dict] | None = None,
    outcomes: dict[str, dict] | None = None,
    plan_success: bool = False,
) -> HookContext:
    plan = SimpleNamespace(steps=[])
    step_outcomes: dict = {}
    for s in steps or []:
        step = SimpleNamespace(name=s["name"], action=s.get("action", ""))
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


def main() -> int:
    print("=" * 72)
    print("  madcop v1.4.0 — The Growing Agent Demo")
    print("  Four-layer closed-loop: reflection → retrieval → crystallization")
    print("=" * 72)
    print()

    # Use a temp brain (clean slate)
    brain_path = Path(tempfile.mkdtemp()) / "demo_brain.db"
    db = PageDB(brain_path)

    # Build the middleware chain
    chain = MiddlewareChain([
        RetrievalMiddleware(db=db, top_k=3),
        ReflectionMiddleware(client=ScriptedClient([]), db=db, max_reflections=3),
    ])

    # =========================================================================
    # Run 1: Agent fails at calling a rate-limited API
    # =========================================================================
    print("▶ RUN 1: 'Fetch data from a rate-limited API'")
    print("  goal: Diagnose why the API keeps returning 429 errors")
    print("  result: FAIL (HTTP 429 Too Many Requests)")
    print()

    # Inject a reflection response for Run 1
    chain._middlewares[1]._client = ScriptedClient([
        json.dumps({
            "reflections": [
                {
                    "topic": "rate-limit-retry",
                    "lesson": "When hitting HTTP 429, use exponential backoff with "
                              "jitter (1s, 2s, 4s, 8s, cap 60s) instead of fixed delays.",
                    "applies_to": "all",
                    "evidence_step": "fetch-api",
                }
            ]
        })
    ])

    ctx1 = _make_ctx(
        goal="Diagnose API 429 errors",
        hook=HOOK_PLAN_END,
        steps=[{"name": "fetch-api", "action": "GET /api/data"}],
        outcomes={"fetch-api": {"success": False, "error": "HTTP 429"}},
        plan_success=False,
    )
    chain(ctx1)
    written = ctx1.shared.get("reflections_written", 0)
    print(f"  → ReflectionMiddleware wrote {written} lesson(s) to brain")
    print(f"  → Topics: {ctx1.shared.get('reflection_topics', [])}")
    print()

    # =========================================================================
    # Run 2: Agent retries — retrieval finds the lesson
    # =========================================================================
    print("▶ RUN 2: 'Fetch data from a rate-limited API (retry)'")
    print("  RetrievalMiddleware searches the brain for relevant lessons...")
    print()

    ctx2 = _make_ctx(
        goal="Diagnose API rate limiting issues",
        hook=HOOK_PLAN_START,
    )
    chain(ctx2)
    lessons = ctx2.shared.get("prior_lessons", [])

    if lessons:
        print(f"  → Found {len(lessons)} prior lesson(s):")
        for l in lessons:
            print(f"    • [{l.topic}] {l.body[:100]}...")
        print()
        formatted = format_lessons(lessons)
        print("  → Injected into planner context:")
        for line in formatted.split("\n"):
            print(f"    {line}")
    else:
        print("  → No prior lessons found (brain empty or no match)")
    print()

    # =========================================================================
    # Run 3 & 4: Two more reflections on the same topic-prefix
    # =========================================================================
    print("▶ RUN 3 & 4: Two more runs produce related lessons")
    print()

    chain._middlewares[1]._client = ScriptedClient([
        json.dumps({
            "reflections": [{
                "topic": "rate-limit-burst",
                "lesson": "Implement a token bucket algorithm instead of fixed windows "
                          "to handle burst traffic more gracefully.",
                "applies_to": "all",
                "evidence_step": "throttle-check",
            }]
        }),
        json.dumps({
            "reflections": [{
                "topic": "rate-limit-headers",
                "lesson": "Read the X-RateLimit-Reset and X-RateLimit-Remaining headers "
                          "to schedule retries at the exact reset time.",
                "applies_to": "all",
                "evidence_step": "header-parse",
            }]
        }),
    ])

    for i, (topic, step) in enumerate([
        ("rate-limit-burst", "throttle-check"),
        ("rate-limit-headers", "header-parse"),
    ], 3):
        ctx_n = _make_ctx(
            goal=f"Fix API rate limiting — {topic}",
            hook=HOOK_PLAN_END,
            steps=[{"name": step, "action": f"analyze {topic}"}],
            outcomes={step: {"success": True}},
            plan_success=True,
        )
        chain(ctx_n)
        print(f"  Run {i}: wrote lesson '{topic}'")

    print()
    print(f"  Brain now has {db.stats()['pages']} skill pages:")
    for p in db.list_by_type("skill"):
        print(f"    • {p.slug}: {p.title}")
    print()

    # =========================================================================
    # Crystallize: 3 lessons → 1 skill
    # =========================================================================
    print("▶ CRYSTALLIZE: Cluster 3 rate-limit lessons into one skill")
    print()

    new_slugs = crystallize_skills(db, min_cluster_size=3)

    print(f"  → Created {len(new_slugs)} crystallized skill(s):")
    for slug in new_slugs:
        page = db.get(slug)
        print(f"    • {slug}")
        print(f"      title: {page.title}")
        print(f"      tags: {', '.join(page.tags)}")
        # Show first 200 chars of compiled_truth
        truth_preview = page.compiled_truth[:200]
        print(f"      body: {truth_preview}...")
    print()

    # =========================================================================
    # Final: retrieval now finds the crystallized skill
    # =========================================================================
    print("▶ FINAL CHECK: Retrieval on 'rate limit' finds the crystallized skill")
    ctx_final = _make_ctx(
        goal="rate limit handling",
        hook=HOOK_PLAN_START,
    )
    chain(ctx_final)
    final_lessons = ctx_final.shared.get("prior_lessons", [])
    print(f"  → {len(final_lessons)} lesson(s) retrieved:")
    for l in final_lessons:
        print(f"    • [{l.topic}] ({l.slug}) {l.body[:80]}...")
    print()

    # =========================================================================
    # Summary
    # =========================================================================
    stats = db.stats()
    print("=" * 72)
    print("  SUMMARY: The agent grew.")
    print("=" * 72)
    print(f"  Brain pages:     {stats['pages']}")
    print(f"  Brain versions:  {stats['versions']}")
    print(f"  Audit log:       {stats['ingest_log']} entries")
    print()
    print("  Run 1 failed  →  wrote 1 lesson  →  Run 2 found it")
    print("  Runs 3+4       →  wrote 2 more lessons")
    print("  Crystallize    →  3 lessons became 1 skill page")
    print("  Final retrieval →  crystallized skill surfaces for related queries")
    print()
    print("  This is the closed-loop feedback circuit in action.")
    print("  No fine-tuning. No vector DB. No cloud. Just SQLite + FTS5 + middleware.")
    print("=" * 72)

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
