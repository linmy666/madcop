"""L3 — Semantic memory.

"What I know" — distilled facts, concepts, and relations extracted from
episodes. Where L2 records "I did X and it took Y seconds", L3 records
"X is correlated with Y" or "CUSUM threshold for ARL0=1000 is 4.78".

The growth engine (growth.py) is responsible for distilling L2 into L3
via the LLM. This module just stores and retrieves facts.

Schema for Fact:
  - subject:        primary entity (e.g. "CUSUM")
  - predicate:      relation (e.g. "has_threshold")
  - object:         target value (e.g. "4.78")
  - source_episode: optional id of the L2 episode this fact came from
  - confidence:     0.0 - 1.0 (the LLM's confidence in the fact)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from .store import MemoryStore, MemoryKind, MemoryRecord


class FactKind(str, Enum):
    """What kind of knowledge does this fact represent?"""

    FACT = "fact"             # "CUSUM threshold for ARL0=1000 is 4.78"
    CONCEPT = "concept"       # "CUSUM is a sequential analysis technique"
    RELATION = "relation"     # "A causes B with confidence 0.8"
    PATTERN = "pattern"       # "OMS cancel spike often follows price changes"


@dataclass
class Fact:
    """One piece of distilled knowledge."""

    id: str
    subject: str
    predicate: str
    object: str
    kind: FactKind = FactKind.FACT
    source_episode: str | None = None
    confidence: float = 1.0
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_at: float = 0.0

    def to_record(self) -> dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "kind": self.kind.value,
            "source_episode": self.source_episode,
            "confidence": self.confidence,
        }

    @classmethod
    def from_record(cls, rec: MemoryRecord) -> "Fact":
        data = json.loads(rec.content) if rec.content else {}
        return cls(
            id=rec.id,
            subject=data.get("subject", rec.title.split(" ")[0] if rec.title else ""),
            predicate=data.get("predicate", ""),
            object=data.get("object", ""),
            kind=FactKind(data.get("kind", "fact")),
            source_episode=data.get("source_episode"),
            confidence=float(data.get("confidence", 1.0)),
            tags=rec.tags,
            created_at=rec.created_at,
        )

    def natural_language(self) -> str:
        """Render the fact as a readable sentence."""
        return f"{self.subject} {self.predicate} {self.object}"


class SemanticMemory:
    """High-level wrapper for the L3 semantic memory."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    @property
    def store(self) -> MemoryStore:
        return self._store

    def add(
        self,
        subject: str,
        predicate: str,
        object: str,
        *,
        kind: FactKind = FactKind.FACT,
        source_episode: str | None = None,
        confidence: float = 1.0,
        tags: tuple[str, ...] = (),
    ) -> Fact:
        """Add one fact. Title format: 'subject predicate object' (truncated)."""
        nl = f"{subject} {predicate} {object}"
        rec = self._store.insert(
            kind=MemoryKind.SEMANTIC,
            title=nl[:80],
            content=json.dumps({
                "subject": subject,
                "predicate": predicate,
                "object": object,
                "kind": kind.value,
                "source_episode": source_episode,
                "confidence": confidence,
            }, ensure_ascii=False),
            tags=tags,
        )
        return Fact(
            id=rec.id,
            subject=subject,
            predicate=predicate,
            object=object,
            kind=kind,
            source_episode=source_episode,
            confidence=confidence,
            tags=tags,
            created_at=rec.created_at,
        )

    def get(self, fact_id: str) -> Fact | None:
        rec = self._store.get(fact_id)
        if rec is None or rec.kind != MemoryKind.SEMANTIC:
            return None
        return Fact.from_record(rec)

    def find_by_subject(self, subject: str, limit: int = 20) -> list[Fact]:
        """All facts where the subject matches."""
        return self.search(subject, limit=limit)

    def search(self, query: str, limit: int = 20) -> list[Fact]:
        """FTS5 search across subject / predicate / object."""
        records = self._store.search_fts(
            query=query,
            kinds=[MemoryKind.SEMANTIC],
            limit=limit,
        )
        return [Fact.from_record(r) for r in records]

    def list_recent(self, limit: int = 50) -> list[Fact]:
        records = self._store.list_by_kind(MemoryKind.SEMANTIC, limit=limit)
        return [Fact.from_record(r) for r in records]

    def count(self) -> int:
        return self._store.count_by_kind(MemoryKind.SEMANTIC)


__all__ = [
    "Fact",
    "FactKind",
    "SemanticMemory",
]
