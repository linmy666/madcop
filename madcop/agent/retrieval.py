"""v1.3.0 — agent.retrieval (L2 half of loop engineering)

`RetrievalMiddleware` runs at `HOOK_PLAN_START` and asks the brain for
prior lessons relevant to the current goal. The hits are written to
`ctx.shared["prior_lessons"]` so the planner can pick them up.

Why a middleware
----------------
Retrieval is a cross-cutting concern — it affects how the planner
generates its plan, not the plan-execute loop's mechanics. Putting it
in a middleware means:
  - No coupling to the planner's prompt construction.
  - Easy to disable (`chain.remove(RetrievalMiddleware)`).
  - Composes with ReflectionMiddleware: the same brain is the source
    and the destination.

Why FTS5 (not vector search)
---------------------------
Single-user, single-machine. We have structured `type=skill` pages
with frontmatter. FTS5 is enough to "find reflections relevant to
this goal" at our scale. Vector search is a v1.4.0 candidate.

Why tag-filter support
----------------------
A `applies_to` tag (set by `ReflectionMiddleware`) lets a user say
"only show me lessons that apply to `tool:bash`". This is a cheap,
high-signal filter. We surface it as a constructor argument.

Why recency weighting
---------------------
A 6-month-old lesson about a Python 2 → Python 3 transition is probably
wrong now. We bias toward recent pages. The decay is linear in
`last_accessed_at` days; we don't pull in real half-life modelling
because we'd need to tune it and we don't have a benchmark.

This module does NOT call the LLM. It only:
  1. Reads `ctx.goal`.
  2. Calls `db.search(goal, types=["skill"], tags=[...], limit=top_k)`.
  3. Writes the formatted hits into `ctx.shared["prior_lessons"]`.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from madcop.agent.middleware import (
    HOOK_PLAN_START,
    HookContext,
)
from madcop.brain.store import PageDB, SearchHit

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #


DEFAULT_TOP_K = 3
DEFAULT_RECENCY_WEIGHT = 0.3
DEFAULT_RECENCY_HALF_LIFE_DAYS = 30.0
# FTS5 bm25: more negative = better match. Default 0.0 means "keep any
# hit FTS5 actually returned". Single-user brains are small, so we
# don't need aggressive filtering. Set to e.g. -0.5 in a corpus of
# 10k+ pages where you want strong matches only.
DEFAULT_MIN_BM25 = 0.0


# --------------------------------------------------------------------------- #
# Hit shape
# --------------------------------------------------------------------------- #


@dataclass
class PriorLesson:
    """A brain hit ready for injection into a planner prompt.

    v1.3.0-rc.2 adds ``outcome`` (``success`` / ``failure`` / ``unknown``)
    so the planner can weight lessons by whether the prior run that
    wrote this lesson actually succeeded. ``None`` until
    ``RetrievalMiddleware`` populates it.
    """
    topic: str
    applies_to: str
    body: str  # the compiled_truth or a short summary
    score: float
    last_accessed_at: str | None
    slug: str
    outcome: str | None = None  # 'success' / 'failure' / 'unknown' / None

    def to_prompt_line(self) -> str:
        """Format as one line: '- topic (applies_to): body'."""
        body = self.body
        if len(body) > 200:
            body = body[:197] + "..."
        applies = self.applies_to or "all"
        return f"- **{self.topic}** (`{applies}`): {body}"


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def _recency_bonus(last_accessed_at: str | None, half_life_days: float) -> float:
    """A small additive bonus for recent pages.

    Returns a value in [0, 1]. Today's page: ~1. 30-day-old: 0.5. 90-day-old: ~0.16.
    Falls back to 0.5 when the timestamp is missing.
    """
    if not last_accessed_at:
        return 0.5
    # ISO-ish timestamp; treat as UTC.
    s = last_accessed_at.rstrip("Z")
    try:
        t = time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        epoch = time.mktime(t)
    except (ValueError, TypeError):
        return 0.5
    age_days = max(0.0, (time.time() - epoch) / 86400.0)
    if half_life_days <= 0:
        return 0.0
    return 0.5 ** (age_days / half_life_days)


def rerank(
    hits: Sequence[SearchHit],
    *,
    recency_weight: float = DEFAULT_RECENCY_WEIGHT,
    half_life_days: float = DEFAULT_RECENCY_HALF_LIFE_DAYS,
) -> list[SearchHit]:
    """Re-rank FTS5 hits with a small recency bonus.

    FTS5 bm25 is more-negative-better, so we negate it to get a
    positive score, then add `recency_weight * recency_bonus`.
    """
    if recency_weight == 0:
        return list(hits)
    reranked: list[tuple[float, SearchHit]] = []
    for h in hits:
        # bm25 is negative; flip to positive (higher is better).
        fts_score = -float(h.score)
        bonus = _recency_bonus(h.page.last_accessed_at, half_life_days)
        combined = fts_score + recency_weight * bonus
        reranked.append((combined, h))
    reranked.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in reranked]


def _hit_to_lesson(hit: SearchHit) -> PriorLesson:
    """Turn a SearchHit into a PriorLesson.

    v1.3.0-rc.2: also carries the ``outcome:`` frontmatter value so
    the planner (or the L3 ``OutcomePrioritizer``) can bias on it.
    """
    fm = hit.page.frontmatter or {}
    topic = (
        str(fm.get("topic") or "")
        or str(fm.get("title") or hit.page.title)
        or hit.page.slug
    )
    # Default to 'unknown' when frontmatter doesn't carry it (rc.1
    # pages and pages written before v1.3.0-rc.2).
    raw_outcome = fm.get("outcome")
    outcome = None
    if isinstance(raw_outcome, str):
        s = raw_outcome.strip().lower()
        if s in ("success", "failure", "unknown"):
            outcome = s
    return PriorLesson(
        topic=topic,
        applies_to=str(fm.get("applies_to") or "all"),
        body=hit.page.compiled_truth or hit.page.timeline or hit.page.title,
        score=float(hit.score),
        last_accessed_at=hit.page.last_accessed_at,
        slug=hit.page.slug,
        outcome=outcome,
    )


def filter_hits(
    hits: Iterable[SearchHit],
    *,
    min_bm25: float = DEFAULT_MIN_BM25,
) -> list[SearchHit]:
    """Drop weak FTS5 hits. `min_bm25` is the threshold — keep hits with
    a score *more negative* than this (FTS5 bm25: more negative = better
    match). Default -0.5 keeps anything that matched at least one term.
    """
    out = []
    for h in hits:
        if float(h.score) <= min_bm25:
            out.append(h)
    return out


# --------------------------------------------------------------------------- #
# RetrievalMiddleware
# --------------------------------------------------------------------------- #


class RetrievalMiddleware:
    """Inject prior lessons from the brain at HOOK_PLAN_START.

    The middleware runs a `db.search()` on `ctx.goal`, re-ranks with
    recency, filters weak hits, and writes the result to
    `ctx.shared["prior_lessons"]` as a list of `PriorLesson`.

    The planner is expected to read `ctx.shared["prior_lessons"]` and
    inject them into its system prompt under a `## Prior lessons`
    heading. v1.3.0 does NOT auto-edit the planner; this middleware
    just publishes the data.

    Args:
        db: A `PageDB` instance.
        top_k: Max lessons to inject. Default 3.
        types: Page types to consider. Default `["skill"]`.
        tags: Optional tag filter (lowercased). E.g. `["applies:tool:bash"]`.
        recency_weight: Bonus for recent pages. 0 disables rerank.
        half_life_days: Half-life of the recency bonus. Default 30.
        min_bm25: Drop hits weaker than this. Default -0.5.
        inject_key: The `ctx.shared` key to write lessons under.
            Default "prior_lessons".
    """

    name = "retrieval"

    def __init__(
        self,
        db: PageDB,
        *,
        top_k: int = DEFAULT_TOP_K,
        types: Sequence[str] = ("skill",),
        tags: Sequence[str] | None = None,
        recency_weight: float = DEFAULT_RECENCY_WEIGHT,
        half_life_days: float = DEFAULT_RECENCY_HALF_LIFE_DAYS,
        min_bm25: float = DEFAULT_MIN_BM25,
        inject_key: str = "prior_lessons",
    ) -> None:
        self._db = db
        self._top_k = max(0, int(top_k))
        self._types = tuple(types) if types else ("skill",)
        self._tags = list(tags) if tags else None
        self._recency_weight = float(recency_weight)
        self._half_life_days = float(half_life_days)
        self._min_bm25 = float(min_bm25)
        self._inject_key = inject_key

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook != HOOK_PLAN_START:
            return
        if self._top_k == 0:
            ctx.shared[self._inject_key] = []
            return
        goal = (ctx.goal or "").strip()
        if not goal:
            ctx.shared[self._inject_key] = []
            return
        # Search the brain. Pull a generous over-fetch so rerank has
        # something to work with.
        fetch = max(self._top_k * 4, 12)
        try:
            hits = self._db.search(
                goal,
                types=list(self._types),
                tags=self._tags,
                limit=fetch,
            )
        except Exception as exc:
            logger.warning("RetrievalMiddleware search failed: %s", exc)
            ctx.shared[self._inject_key] = []
            return
        hits = filter_hits(hits, min_bm25=self._min_bm25)
        hits = rerank(
            hits,
            recency_weight=self._recency_weight,
            half_life_days=self._half_life_days,
        )
        hits = hits[: self._top_k]
        lessons = [_hit_to_lesson(h) for h in hits]
        ctx.shared[self._inject_key] = lessons


# --------------------------------------------------------------------------- #
# Prompt formatting (for planners that want a ready-to-paste string)
# --------------------------------------------------------------------------- #


def format_lessons(lessons: Iterable[PriorLesson]) -> str:
    """Render a list of lessons as a markdown block for system-prompt injection.

    Returns an empty string when there are no lessons — the caller
    can decide whether to skip the `## Prior lessons` heading or
    drop the section entirely.
    """
    lines = list(lessons)
    if not lines:
        return ""
    out = ["## Prior lessons", ""]
    for l in lines:
        out.append(l.to_prompt_line())
    return "\n".join(out)


__all__ = [
    "DEFAULT_TOP_K",
    "DEFAULT_RECENCY_WEIGHT",
    "DEFAULT_RECENCY_HALF_LIFE_DAYS",
    "DEFAULT_MIN_BM25",
    "PriorLesson",
    "RetrievalMiddleware",
    "rerank",
    "filter_hits",
    "format_lessons",
]
