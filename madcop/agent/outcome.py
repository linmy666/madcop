"""v1.3.0-rc.2 — agent.outcome (L3 of loop engineering)

The L3 layer closes a second feedback loop on top of rc.1's L1+L2:
it asks "did the lesson actually help?" and biases future retrieval
accordingly. Two pieces:

- ``boost_outcome(hits, ...)`` — pure function: re-rank FTS5 hits with
  a small +/– additive based on the page's ``outcome: success|failure``
  frontmatter (set by ``ReflectionMiddleware`` at the time the page
  was written).

- ``OutcomePrioritizer`` — middleware that runs at ``HOOK_PLAN_START``
  AFTER ``RetrievalMiddleware`` and post-processes the lessons list
  in place. Sits in the chain as a drop-in companion to
  ``RetrievalMiddleware``.

Why a separate module
---------------------
The ``RetrievalMiddleware`` itself stays rc.1-clean (bit-identical
behaviour for any brain whose pages have no ``outcome:`` frontmatter).
``OutcomePrioritizer`` is additive: when the brain has no outcome
data, it is a no-op. When it does, it shifts the rank.

Why additive, not multiplicative
--------------------------------
A small additive boost to a normalised score is more predictable
than multiplying FTS5 BM25 (which is unbounded negative) by a
multiplier. ``score + outcome_weight * outcome_value`` keeps the
unit of the existing rerank and the new boost in the same scale.

This module does NOT call the LLM. It does NOT write to the brain.
It only re-orders the lessons list that ``RetrievalMiddleware``
already published to ``ctx.shared["prior_lessons"]``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Sequence

from madcop.agent.middleware import (
    HOOK_PLAN_START,
    HookContext,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_OUTCOME_WEIGHT = 0.4
# outcome_weight * value (success: +1, failure: -1, unknown: 0). With
# the default 0.4, a "failure" lesson is 0.4 points behind an
# "unknown" lesson of equal FTS5 + recency score; a "success" lesson
# is 0.4 ahead. This is small enough to not override strong FTS5 hits
# but large enough to reorder ties.

DEFAULT_OUTCOME_HALF_LIFE_DAYS = 60.0
# Outcome annotations also decay: a 60-day-old "failure" tag should
# not dominate. Same half-life semantics as recency.

OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"
OUTCOME_UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Outcome value lookup
# --------------------------------------------------------------------------- #


def _outcome_value(frontmatter: dict[str, Any] | None) -> str:
    """Read ``outcome:`` from a page's frontmatter, default to 'unknown'.

    Coerces to lowercase + strips. Anything not in
    {success, failure, unknown} maps to unknown.
    """
    if not frontmatter:
        return OUTCOME_UNKNOWN
    raw = frontmatter.get("outcome")
    if raw is None:
        # Also accept a top-level ``tags``-derived outcome. If a tag
        # ``outcome:success`` or ``outcome:failure`` is present, that
        # counts. (The reflection middleware writes both.)
        for tag in frontmatter.get("tags") or []:
            ts = str(tag or "").strip().lower()
            if ts == "outcome:success":
                return OUTCOME_SUCCESS
            if ts == "outcome:failure":
                return OUTCOME_FAILURE
        return OUTCOME_UNKNOWN
    s = str(raw).strip().lower()
    if s in (OUTCOME_SUCCESS, OUTCOME_FAILURE):
        return s
    return OUTCOME_UNKNOWN


def _outcome_numeric(outcome: str) -> float:
    """Map outcome label to a signed scalar."""
    if outcome == OUTCOME_SUCCESS:
        return 1.0
    if outcome == OUTCOME_FAILURE:
        return -1.0
    return 0.0


def _recency_age_days(last_accessed_at: str | None) -> float:
    """Age of a page in days (used to decay outcome weight)."""
    if not last_accessed_at:
        return 30.0  # unknown age → treat as one recency half-life old
    s = last_accessed_at.rstrip("Z")
    try:
        t = time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        epoch = time.mktime(t)
    except (ValueError, TypeError):
        return 30.0
    return max(0.0, (time.time() - epoch) / 86400.0)


def _outcome_recency_factor(
    last_accessed_at: str | None, half_life_days: float
) -> float:
    """Returns 1.0 for a brand-new page, 0.5 at one half-life, etc.

    A 60-day-old outcome tag carries ~50% weight. A 1-year-old tag
    carries ~3%. The factor is what we *multiply* the outcome value
    by, so old "failure" tags are penalised less.
    """
    if half_life_days <= 0:
        return 1.0
    age = _recency_age_days(last_accessed_at)
    return 0.5 ** (age / half_life_days)


# --------------------------------------------------------------------------- #
# Pure ranker
# --------------------------------------------------------------------------- #


def lesson_outcome_score(lesson: Any, *, half_life_days: float = DEFAULT_OUTCOME_HALF_LIFE_DAYS) -> tuple[float, str]:
    """Return ``(signed_score, outcome_label)`` for one ``PriorLesson``.

    Score = outcome_numeric × recency_factor. Used by ``boost_outcome``
    to shift the rank in a way that respects recency (older outcome
    tags weigh less).
    """
    fm: dict[str, Any] = {}
    last_accessed: str | None = getattr(lesson, "last_accessed_at", None)
    # ``PriorLesson`` doesn't carry the raw frontmatter dict. We work
    # with the already-derived ``applies_to`` + slug + topic when
    # ``outcome`` isn't on the lesson object. Most callers pass
    # the SearchHit instead via ``boost_outcome``.
    outcome = OUTCOME_UNKNOWN
    if hasattr(lesson, "outcome") and lesson.outcome in (
        OUTCOME_SUCCESS,
        OUTCOME_FAILURE,
        OUTCOME_UNKNOWN,
    ):
        outcome = lesson.outcome
    if outcome == OUTCOME_UNKNOWN and hasattr(lesson, "frontmatter"):
        outcome = _outcome_value(getattr(lesson, "frontmatter"))
    factor = _outcome_recency_factor(last_accessed, half_life_days)
    return _outcome_numeric(outcome) * factor, outcome


def boost_outcome(
    lessons: Sequence[Any],
    *,
    outcome_weight: float = DEFAULT_OUTCOME_WEIGHT,
    half_life_days: float = DEFAULT_OUTCOME_HALF_LIFE_DAYS,
) -> list[Any]:
    """Re-rank an iterable of ``PriorLesson`` (or SearchHit) by outcome.

    The ranker is additive: a lesson with ``outcome: success`` and
    recency factor 1.0 is shifted up by ``outcome_weight``; one with
    ``outcome: failure`` and factor 1.0 is shifted down by
    ``outcome_weight``; ``unknown`` (or pages lacking the field) is
    unchanged.

    Stable order is preserved for ties (Python's sort is stable), so
    the existing FTS5+recency order is the tie-breaker.
    """
    if outcome_weight == 0:
        return list(lessons)
    if not lessons:
        return []
    scored: list[tuple[float, int, Any]] = []
    for i, lesson in enumerate(lessons):
        # ``boost_score`` is the additive delta; the existing
        # score/recency is preserved by sorting on a tuple
        # ``(delta, original_index)`` so within-tier order is
        # unchanged.
        fm: dict[str, Any] = {}
        if hasattr(lesson, "page") and lesson.page is not None:
            fm = getattr(lesson.page, "frontmatter", None) or {}
            last_accessed = getattr(lesson.page, "last_accessed_at", None)
        else:
            last_accessed = getattr(lesson, "last_accessed_at", None)
        outcome = _outcome_value(fm)
        # If the lesson itself carries a top-level ``outcome`` attr
        # (e.g. a SearchHit wrapped by ``_hit_to_lesson``), honour it.
        if hasattr(lesson, "outcome"):
            o = getattr(lesson, "outcome")
            if o in (OUTCOME_SUCCESS, OUTCOME_FAILURE, OUTCOME_UNKNOWN):
                outcome = o
        factor = _outcome_recency_factor(last_accessed, half_life_days)
        delta = outcome_weight * _outcome_numeric(outcome) * factor
        scored.append((delta, i, lesson))
    # Sort by delta desc, ties by original index asc (stable).
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item for _, _, item in scored]


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #


class OutcomePrioritizer:
    """Re-rank ``ctx.shared["prior_lessons"]`` by outcome at HOOK_PLAN_START.

    Args:
        outcome_weight: How strongly to bias rank. 0 disables. Default 0.4.
        half_life_days: Recency half-life of outcome tags. Default 60.
        inject_key: The ``ctx.shared`` key holding the lessons list.
            Default ``"prior_lessons"`` — same key ``RetrievalMiddleware``
            writes to, so this middleware composes by running after it
            in the chain.
        strategy: ``"boost"`` (default) uses ``boost_outcome``; ``"filter"``
            drops outcome=failure lessons entirely (last-resort). Default
            ``"boost"``.

    Usage::

        chain = MiddlewareChain([
            RetrievalMiddleware(db=db),         # writes prior_lessons
            OutcomePrioritizer(outcome_weight=0.4),  # shifts rank
            QianControlMiddleware(),
        ])

    The middleware is silent on failure (never breaks the run) and a
    no-op when there are no lessons to re-rank.
    """

    name = "outcome"

    def __init__(
        self,
        *,
        outcome_weight: float = DEFAULT_OUTCOME_WEIGHT,
        half_life_days: float = DEFAULT_OUTCOME_HALF_LIFE_DAYS,
        inject_key: str = "prior_lessons",
        strategy: str = "boost",
    ) -> None:
        self._outcome_weight = float(outcome_weight)
        self._half_life_days = float(half_life_days)
        self._inject_key = inject_key
        self._strategy = strategy if strategy in ("boost", "filter") else "boost"

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook != HOOK_PLAN_START:
            return
        lessons = ctx.shared.get(self._inject_key)
        if not lessons:
            return
        try:
            if self._strategy == "filter":
                # Drop outcome:failure lessons.
                filtered = []
                for lesson in lessons:
                    fm: dict[str, Any] = {}
                    if hasattr(lesson, "page") and lesson.page is not None:
                        fm = getattr(lesson.page, "frontmatter", None) or {}
                    outcome = _outcome_value(fm)
                    if hasattr(lesson, "outcome"):
                        o = getattr(lesson, "outcome")
                        if o in (OUTCOME_SUCCESS, OUTCOME_FAILURE, OUTCOME_UNKNOWN):
                            outcome = o
                    if outcome != OUTCOME_FAILURE:
                        filtered.append(lesson)
                ctx.shared[self._inject_key] = filtered
                return
            ctx.shared[self._inject_key] = boost_outcome(
                list(lessons),
                outcome_weight=self._outcome_weight,
                half_life_days=self._half_life_days,
            )
        except Exception as exc:
            logger.warning("OutcomePrioritizer failed: %s", exc)


# --------------------------------------------------------------------------- #
# Prompt formatting (L3-aware)
# --------------------------------------------------------------------------- #


def format_lessons_with_outcome(lessons: Iterable[Any]) -> str:
    """Render lessons as a markdown block that exposes the outcome tag.

    This is the L3 prompt injection helper. The output of
    ``format_lessons()`` is fine, but loses the outcome signal — the
    planner can't tell which lessons worked and which didn't. This
    helper annotates each line with a small ``✓``/``✗``/``?`` glyph
    so the planner can weight them visually. ``?`` for unknown.

    Example output::

        ## Prior lessons (outcome-tagged)

        - **rate-limit-retry** ✓ (`tool:http`): Retry once on 5xx...
        - **bm25-vs-cosine** ✗ (`tool:search`): Use BM25 not cosine...

    Returns an empty string when there are no lessons.
    """
    lines = list(lessons)
    if not lines:
        return ""
    out = ["## Prior lessons (outcome-tagged)", ""]
    for lesson in lines:
        fm: dict[str, Any] = {}
        last_accessed = getattr(lesson, "last_accessed_at", None)
        if hasattr(lesson, "page") and lesson.page is not None:
            fm = getattr(lesson.page, "frontmatter", None) or {}
            last_accessed = getattr(lesson.page, "last_accessed_at", last_accessed)
        outcome = _outcome_value(fm)
        if hasattr(lesson, "outcome"):
            o = getattr(lesson, "outcome")
            if o in (OUTCOME_SUCCESS, OUTCOME_FAILURE, OUTCOME_UNKNOWN):
                outcome = o
        glyph = {"success": "✓", "failure": "✗", "unknown": "?"}.get(outcome, "?")
        topic = getattr(lesson, "topic", "?")
        applies = getattr(lesson, "applies_to", "all") or "all"
        body = getattr(lesson, "body", "") or ""
        if len(body) > 200:
            body = body[:197] + "..."
        out.append(f"- **{topic}** {glyph} (`{applies}`): {body}")
    return "\n".join(out)


__all__ = [
    "DEFAULT_OUTCOME_WEIGHT",
    "DEFAULT_OUTCOME_HALF_LIFE_DAYS",
    "OUTCOME_SUCCESS",
    "OUTCOME_FAILURE",
    "OUTCOME_UNKNOWN",
    "boost_outcome",
    "lesson_outcome_score",
    "OutcomePrioritizer",
    "format_lessons_with_outcome",
]
