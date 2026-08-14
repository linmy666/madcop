"""Resume-Claim-5: auto-grow the knowledge graph from chat conversations.

After each substantive chat turn (same "valuable" threshold as skill_distill),
extract the topic + a compact truth statement and save it as a knowledge
page in the brain graph (brain.db). This makes the claim "a knowledge graph
that keeps growing with use, understanding you better over time" literally
true — every long, structured answer adds a node to the graph that the
Knowledge Canvas displays and that future memory recall can surface.

Design choices:
- Reuse skill_distill's topic extraction (proven heuristic).
- page_type = "skill" (the brain's term for a how-to / explanatory node).
- slug is derived from the topic (pinyin-safe, timestamp-suffixed to
  avoid collisions across turns about the same topic — each turn is a
  new version of understanding).
- compiled_truth is the assistant's answer (capped at 4000 chars so a
  huge reply doesn't bloat the graph).
- We DON'T auto-create edges (links) — that's a future enhancement.
  The node itself is the "growing with use" signal.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from madcop.memory.skill_distill import _is_valuable_skill
from madcop.brain.store import PageDB

logger = logging.getLogger(__name__)

_MIN_BRAIN_RESPONSE_LEN = 400  # same threshold as skill_distill: any
                               # structured answer worth saving as a skill
                               # is also worth a knowledge-graph node.


def _topic_to_slug(topic: str) -> str:
    """Convert a topic string into a brain-graph-safe slug.

    Brain slugs must be lowercase [a-z0-9-]. CJK characters aren't allowed
    by validate_slug, so we fall back to a timestamp-based slug while
    keeping the original topic as the page title (which has no charset
    restriction). This means the canvas shows "Vue 3 组合式 API" as the
    title but the internal slug is e.g. "chat-20260807-1432-a1b2".
    """
    # Try to keep ascii-only topics readable.
    cleaned = re.sub(r"[^a-zA-Z0-9-]+", "-", topic).strip("-").lower()
    if cleaned and re.fullmatch(r"[a-z0-9-]+", cleaned) and len(cleaned) >= 3:
        # Suffix with short timestamp to avoid collisions on repeat topics.
        return f"{cleaned[:40]}-{datetime.now().strftime('%m%d%H%M')}"
    # CJK / mixed: use a stable timestamp-based slug.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"chat-{ts}"


def auto_extract_to_brain(user_query: str, assistant_response: str) -> str | None:
    """If the conversation turn is valuable, save it as a brain node.

    Returns the slug of the created page, or None if the turn didn't
    meet the bar (too short, chitchat, no structure).
    """
    if not user_query or not assistant_response:
        return None
    if len(assistant_response.strip()) < _MIN_BRAIN_RESPONSE_LEN:
        return None

    topic = _is_valuable_skill(user_query, assistant_response)
    if not topic:
        return None

    try:
        db = PageDB.default()
        slug = _topic_to_slug(topic)
        # Cap the truth content so a 10K-char essay doesn't bloat the row.
        truth = assistant_response.strip()[:4000]
        # Extract a one-line summary from the first heading or first sentence.
        summary = ""
        for line in assistant_response.splitlines():
            s = line.strip()
            if s.startswith("# "):
                summary = s[2:].strip()[:120]
                break
            if s and not s.startswith("```") and not s.startswith("|"):
                summary = s[:120]
                break

        page = db.save(
            slug=slug,
            title=topic[:120],
            page_type="skill",
            compiled_truth=truth,
            timeline=f"--- auto-extracted from chat ({datetime.now().isoformat(timespec='seconds')}) ---\n"
                     f"Q: {user_query[:200]}\n"
                     f"Summary: {summary}",
            frontmatter={
                "source": "chat-auto",
                "query": user_query[:200],
                "extracted_at": datetime.now().isoformat(timespec="seconds"),
            },
            source="chat-auto",
            saved_by="brain_auto",
            tags=["auto", "chat"],
        )
        logger.info("brain_auto: saved knowledge page '%s' (slug=%s, %d chars)",
                    topic[:40], slug, len(truth))
        return slug
    except Exception as e:
        logger.debug("brain_auto: skipped (%s)", e)
        return None
