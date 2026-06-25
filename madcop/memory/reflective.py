"""L4 — Reflective memory.

"What I've learned about how to work" — the user's preferences, my own
behaviour patterns, and meta-strategies the agent has mined from
experience. This is the layer that drives the "growth" effect.

Two kinds of reflection:
  - USER_PREFERENCE: "user prefers ≤ 5 bullet summaries"
  - META_STRATEGY:  "if task keyword is '诊断', use rule-based CUSUM first"

The growth engine (growth.py) is the primary writer. v0.6.0 users can
also rate episodes 1-5 stars, which triggers a LLM to extract a
preference into this layer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from .store import MemoryStore, MemoryKind, MemoryRecord


class ReflectionKind(str, Enum):
    """What kind of reflection is this?"""

    USER_PREFERENCE = "user_preference"   # "user prefers X"
    USER_DISLIKE = "user_dislike"         # "user dislikes X"
    META_STRATEGY = "meta_strategy"       # "if X, then Y"
    LESSON_LEARNED = "lesson_learned"     # general insight
    WORKING_NOTE = "working_note"         # a small note about the agent itself


@dataclass
class Reflection:
    """One reflective memory."""

    id: str
    text: str                                # the human-readable reflection
    kind: ReflectionKind = ReflectionKind.LESSON_LEARNED
    source_episode: str | None = None         # which episode triggered this
    source_rating: int | None = None          # 1-5 stars from user (if any)
    confidence: float = 1.0
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_at: float = 0.0

    def to_record(self) -> dict:
        return {
            "text": self.text,
            "kind": self.kind.value,
            "source_episode": self.source_episode,
            "source_rating": self.source_rating,
            "confidence": self.confidence,
        }

    @classmethod
    def from_record(cls, rec: MemoryRecord) -> "Reflection":
        data = json.loads(rec.content) if rec.content else {}
        return cls(
            id=rec.id,
            text=data.get("text", rec.title),
            kind=ReflectionKind(data.get("kind", "lesson_learned")),
            source_episode=data.get("source_episode"),
            source_rating=data.get("source_rating"),
            confidence=float(data.get("confidence", 1.0)),
            tags=rec.tags,
            created_at=rec.created_at,
        )


class ReflectiveMemory:
    """High-level wrapper for L4 reflections."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    @property
    def store(self) -> MemoryStore:
        return self._store

    def add(
        self,
        text: str,
        *,
        kind: ReflectionKind = ReflectionKind.LESSON_LEARNED,
        source_episode: str | None = None,
        source_rating: int | None = None,
        confidence: float = 1.0,
        tags: tuple[str, ...] = (),
    ) -> Reflection:
        rec = self._store.insert(
            kind=MemoryKind.REFLECTIVE,
            title=text[:80],
            content=json.dumps({
                "text": text,
                "kind": kind.value,
                "source_episode": source_episode,
                "source_rating": source_rating,
                "confidence": confidence,
            }, ensure_ascii=False),
            tags=tags,
        )
        return Reflection(
            id=rec.id,
            text=text,
            kind=kind,
            source_episode=source_episode,
            source_rating=source_rating,
            confidence=confidence,
            tags=tags,
            created_at=rec.created_at,
        )

    def get(self, reflection_id: str) -> Reflection | None:
        rec = self._store.get(reflection_id)
        if rec is None or rec.kind != MemoryKind.REFLECTIVE:
            return None
        return Reflection.from_record(rec)

    def find_preferences(self, limit: int = 20) -> list[Reflection]:
        """All USER_PREFERENCE and USER_DISLIKE reflections, newest first."""
        records = self._store.list_by_kind(MemoryKind.REFLECTIVE, limit=200)
        prefs = [
            Reflection.from_record(r) for r in records
            if r.tags  # filtered via the kind in content; we accept all for simplicity
        ]
        return [p for p in prefs if p.kind in (
            ReflectionKind.USER_PREFERENCE,
            ReflectionKind.USER_DISLIKE,
        )][:limit]

    def find_meta_strategies(self, limit: int = 20) -> list[Reflection]:
        """All META_STRATEGY reflections."""
        records = self._store.list_by_kind(MemoryKind.REFLECTIVE, limit=200)
        metas = [Reflection.from_record(r) for r in records if r.tags]
        return [m for m in metas if m.kind == ReflectionKind.META_STRATEGY][:limit]

    def search(self, query: str, limit: int = 20) -> list[Reflection]:
        records = self._store.search_fts(
            query=query,
            kinds=[MemoryKind.REFLECTIVE],
            limit=limit,
        )
        return [Reflection.from_record(r) for r in records]

    def list_recent(self, limit: int = 50) -> list[Reflection]:
        records = self._store.list_by_kind(MemoryKind.REFLECTIVE, limit=limit)
        return [Reflection.from_record(r) for r in records]

    def count(self) -> int:
        return self._store.count_by_kind(MemoryKind.REFLECTIVE)


__all__ = [
    "Reflection",
    "ReflectionKind",
    "ReflectiveMemory",
]
