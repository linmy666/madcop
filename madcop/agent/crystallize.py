"""v1.3.0-rc.3 — agent.crystallize (L4 of loop engineering)

The L4 layer turns a noisy **stream of small reflections** into a
small **set of named, durable skills**. After enough plan-execute
runs, the brain accumulates many `type=skill` pages whose `topic:`
frontmatter values share a prefix (e.g. `rate-limit-retry`,
`rate-limit-burst`, `rate-limit-headers`). L4 looks for clusters of
size >= N (default 3), and for each cluster writes a single
"crystallized" skill page that:

- has a new `topic:` value equal to the common prefix
- carries a `## Member reflections` section listing each input topic
- carries the average outcome of the cluster as the new page's outcome
- is `type=skill` (so the rest of the system treats it identically)
- gets a `crystallized` tag so callers can tell them apart

This module does NOT call the LLM. It only:
  1. Reads the brain's `type=skill` pages
  2. Groups them by topic-prefix
  3. Writes one new skill page per group of size >= N

The middleware `SkillCrystallizer` runs at `HOOK_PLAN_END` after
`ReflectionMiddleware` and is opt-in. Most users will run it
manually or via a cron, not on every plan (crystallization is a
batch operation, not a hot-path one).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Iterable, Sequence

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HookContext,
)
from madcop.brain.store import Page, PageDB

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_MIN_CLUSTER_SIZE = 3
# A cluster of 3+ reflections sharing a topic-prefix is the smallest
# size that suggests a "real" pattern. 2 is too easy (any two random
# topics could share a prefix), 5+ is too strict (you'd have to run
# dozens of plans to ever crystallize anything).

DEFAULT_PREFIX_SPLIT = "-"
# Topics are slug-shaped ("rate-limit-retry"). The first segment
# ("rate-limit") is the prefix. Use "." or "_" for non-slug
# namespaces, but "-" is the convention.

CRYSTALLIZED_TAG = "crystallized"
CRYSTALLIZED_SOURCE = "crystallizer"
CRYSTALLIZED_SAVED_BY = "crystallizer_middleware"


# --------------------------------------------------------------------------- #
# Pure cluster logic
# --------------------------------------------------------------------------- #


def _topic_of(page: Page) -> str:
    """Read the topic from a page's frontmatter; fall back to slug.

    Pages written by ``ReflectionMiddleware`` always carry
    ``frontmatter["topic"]``. Manually-written skill pages may not;
    we fall back to the slug so the crystallizer can still find them.
    """
    fm = page.frontmatter or {}
    topic = str(fm.get("topic") or "").strip()
    if topic:
        return topic
    # Slug fallback: drop the "reflection-" prefix that the reflection
    # middleware adds.
    slug = page.slug or ""
    if slug.startswith("reflection-"):
        slug = slug[len("reflection-"):]
    return slug or page.title or "untitled"


def _prefix_of(topic: str, split: str) -> str:
    """Return the canonical prefix of a topic.

    Convention (with default ``split='-'``):

    - ``rate-limit-retry`` → ``rate-limit``  (3 segments, drop the last)
    - ``rate-limit`` → ``rate-limit``       (2 segments, the topic IS the prefix)
    - ``single`` → ``single``               (1 segment, the topic IS the prefix)

    The 2-segment case is critical: a crystallized page whose topic
    is ``rate-limit`` (the cluster head) must cluster with the
    individual reflections ``rate-limit-retry``, ``rate-limit-burst``,
    etc. whose prefix is also ``rate-limit``. Without this fix, the
    head would land in a different bucket and the cluster would
    be missing one member.
    """
    if not topic:
        return ""
    parts = [p for p in topic.split(split) if p]
    if len(parts) <= 2:
        return topic
    # 3+ segments: drop the last.
    return split.join(parts[:-1])


def cluster_topics(
    pages: Iterable[Page],
    *,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    split: str = DEFAULT_PREFIX_SPLIT,
) -> dict[str, list[Page]]:
    """Group pages by topic-prefix.

    Returns a dict ``{prefix: [pages...]}`` for clusters of size
    >= ``min_cluster_size``. Topics that don't share a prefix with
    any other page are dropped from the result.

    The cluster is sorted by ``(prefix, page.updated_at DESC)`` so
    deterministic runs are reproducible.
    """
    if min_cluster_size < 2:
        min_cluster_size = 2
    by_prefix: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        topic = _topic_of(page)
        prefix = _prefix_of(topic, split=split)
        if not prefix:
            continue
        by_prefix[prefix].append(page)
    return {
        prefix: sorted(
            members,
            key=lambda p: p.updated_at or "",
            reverse=True,
        )
        for prefix, members in by_prefix.items()
        if len(members) >= min_cluster_size
    }


# --------------------------------------------------------------------------- #
# Outcome aggregation
# --------------------------------------------------------------------------- #


def _outcome_of(page: Page) -> str:
    """Read the outcome of a page (success / failure / unknown)."""
    fm = page.frontmatter or {}
    raw = str(fm.get("outcome") or "").strip().lower()
    if raw in ("success", "failure", "unknown"):
        return raw
    return "unknown"


def aggregate_outcome(pages: Iterable[Page]) -> str:
    """Aggregate outcomes of a cluster into a single label.

    Rule: majority wins. ``success`` if more than half the cluster
    succeeded, ``failure`` if more than half failed, ``unknown``
    otherwise (ties or no outcome data).
    """
    counts = {"success": 0, "failure": 0, "unknown": 0}
    for p in pages:
        counts[_outcome_of(p)] += 1
    total = sum(counts.values()) or 1
    if counts["success"] > total / 2:
        return "success"
    if counts["failure"] > total / 2:
        return "failure"
    return "unknown"


# --------------------------------------------------------------------------- #
# Slug + body rendering
# --------------------------------------------------------------------------- #


def _slug_for_skill(prefix: str) -> str:
    """Make a stable brain slug from a prefix."""
    base = re.sub(r"[^a-z0-9-]+", "-", prefix.lower()).strip("-")
    if not base:
        base = "skill"
    return f"skill-{base}"[:128]


def render_skill_body(
    prefix: str,
    members: Sequence[Page],
    *,
    aggregate: str | None = None,
) -> str:
    """Render a crystallized skill page as a markdown body.

    The body has the same shape as a ReflectionMiddleware skill page,
    so retrieval and outcome-aware ranking work identically. The
    new piece is a `## Member reflections` section listing the
    cluster's source topics.
    """
    if aggregate is None:
        aggregate = aggregate_outcome(members)
    aggregate = aggregate if aggregate in ("success", "failure") else "unknown"
    fm = (
        "---\n"
        "type: skill\n"
        f"topic: {prefix}\n"
        f"applies_to: all\n"
        f"outcome: {aggregate}\n"
        "---\n\n"
    )
    body = (
        f"## Cluster topic\n\n`{prefix}`\n\n"
        f"## Outcome (cluster-aggregated)\n\n`{aggregate}`\n\n"
        "## Member reflections\n\n"
    )
    for m in members:
        topic = _topic_of(m)
        outcome = _outcome_of(m)
        mfm = m.frontmatter or {}
        applies = str(mfm.get("applies_to") or "all")
        body += f"- **{topic}** ({outcome}, `{applies}`) — `{m.slug}`\n"
    body += (
        "\n## Why this matters\n\n"
        "Auto-crystallized by `SkillCrystallizer` from "
        f"{len(members)} reflections sharing the topic prefix "
        f"`{prefix}`. This page is a cluster head; the original "
        "reflections remain in the brain and are still individually "
        "retrievable by their own slugs.\n"
    )
    return fm + body


# --------------------------------------------------------------------------- #
# Pure driver: cluster + write
# --------------------------------------------------------------------------- #


def crystallize_skills(
    db: PageDB,
    *,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    split: str = DEFAULT_PREFIX_SPLIT,
    source: str = CRYSTALLIZED_SOURCE,
    saved_by: str = CRYSTALLIZED_SAVED_BY,
) -> list[str]:
    """Find clusters in the brain and write one skill page per cluster.

    Returns the slugs of the new skill pages (existing slugs are not
    re-written — saves are idempotent: same content, same version).

    Safe to call repeatedly: a cluster that has already been
    crystallized will produce the same body (modulo `updated_at`),
    and the brain stores it as a new version of the same slug.

    Idempotency note: because the body lists members deterministically
    (by `topic` then slug), the crystallized page is bit-stable across
    runs. The first run creates version 1; subsequent runs create
    version 2, 3, etc. only if a new member joins the cluster. To
    avoid version noise, we skip writing if the crystallized page
    already exists with the same member set.
    """
    pages = db.list_by_type("skill", limit=2000)
    # Filter out pages that are already crystallized (don't recurse).
    pages = [p for p in pages if CRYSTALLIZED_TAG not in (p.tags or [])]
    clusters = cluster_topics(
        pages,
        min_cluster_size=min_cluster_size,
        split=split,
    )
    new_slugs: list[str] = []
    for prefix, members in clusters.items():
        slug = _slug_for_skill(prefix)
        existing = db.get(slug)
        if existing is not None and CRYSTALLIZED_TAG in (existing.tags or []):
            # Already crystallized; skip unless member set changed.
            existing_member_slugs = _extract_member_slugs(existing)
            current_member_slugs = sorted(m.slug for m in members)
            if existing_member_slugs == current_member_slugs:
                continue
            # Member set changed: delete the old crystallized page
            # and re-insert from scratch. We can't just `db.save()` it
            # because the brain's `pages_touch` trigger + an UPDATE
            # of the same slug trips a "database disk image is
            # malformed" error on SQLite 3.40.x — see the note in
            # `crystallize_skills` for details. Delete + insert is
            # safe and idempotent.
            try:
                db.delete(slug=slug, source=source)
            except Exception as exc:
                logger.warning(
                    "crystallize_skills: failed to delete stale %s: %s",
                    slug, exc,
                )
        aggregate = aggregate_outcome(members)
        body = render_skill_body(prefix, members, aggregate=aggregate)
        member_topics = sorted(_topic_of(m) for m in members)
        tags = [
            "reflection",
            "topic:" + prefix,
            f"outcome:{aggregate}",
            CRYSTALLIZED_TAG,
            f"members:{len(members)}",
        ]
        try:
            db.save(
                slug=slug,
                title=prefix,
                page_type="skill",
                compiled_truth=body,
                timeline="",
                frontmatter={
                    "type": "skill",
                    "topic": prefix,
                    "applies_to": "all",
                    "outcome": aggregate,
                    "members": member_topics,
                },
                tags=tags,
                source=source,
                saved_by=saved_by,
            )
            new_slugs.append(slug)
        except Exception as exc:
            logger.warning(
                "crystallize_skills: failed to save %s: %s", slug, exc,
            )
    return new_slugs


def _extract_member_slugs(page: Page) -> list[str]:
    """Parse the member slugs out of an existing crystallized page body.

    Looks for lines of the form ``- **topic** (outcome, applies) — `slug```
    in the body. If the format is not recognised, returns an empty
    list (which won't match any new member set, triggering a rewrite —
    safe default).
    """
    body = page.compiled_truth or ""
    slugs: list[str] = []
    for line in body.splitlines():
        # Match: "... — `slug`" at end of line.
        m = re.search(r"—\s*`([^`]+)`\s*$", line)
        if m:
            slugs.append(m.group(1))
    return sorted(slugs)


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #


class SkillCrystallizer:
    """Run ``crystallize_skills`` at HOOK_PLAN_END.

    Opt-in: most users will run crystallization on a cron or on
    demand, not on every plan. Default ``enabled=False`` so
    installing this middleware is a no-op until you opt in via
    ``enabled=True`` or ``crystallize_on_plan_end=True``.

    Args:
        db: A ``PageDB`` instance.
        enabled: Master switch. If False, the middleware is a no-op.
        min_cluster_size: Minimum reflections per cluster. Default 3.
        split: Topic-prefix separator. Default ``"-"``.

    On every run, the middleware writes the list of newly created
    slugs to ``ctx.shared["crystallized_skills"]`` (empty list on
    no-op or no new clusters).
    """

    name = "crystallize"

    def __init__(
        self,
        db: PageDB,
        *,
        enabled: bool = False,
        min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
        split: str = DEFAULT_PREFIX_SPLIT,
    ) -> None:
        self._db = db
        self._enabled = bool(enabled)
        self._min_cluster_size = int(min_cluster_size)
        self._split = split

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook != HOOK_PLAN_END:
            return
        if not self._enabled:
            ctx.shared["crystallized_skills"] = []
            return
        try:
            new_slugs = crystallize_skills(
                self._db,
                min_cluster_size=self._min_cluster_size,
                split=self._split,
            )
        except Exception as exc:
            logger.warning("SkillCrystallizer failed: %s", exc)
            new_slugs = []
        ctx.shared["crystallized_skills"] = new_slugs


__all__ = [
    "DEFAULT_MIN_CLUSTER_SIZE",
    "DEFAULT_PREFIX_SPLIT",
    "CRYSTALLIZED_TAG",
    "CRYSTALLIZED_SOURCE",
    "CRYSTALLIZED_SAVED_BY",
    "cluster_topics",
    "aggregate_outcome",
    "render_skill_body",
    "crystallize_skills",
    "SkillCrystallizer",
]
