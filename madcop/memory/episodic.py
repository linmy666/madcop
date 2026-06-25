"""L2 — Episodic memory.

"What I've done" — one record per agent run, capturing the goal, the steps
taken, the findings produced, and the final outcome. This is the layer
the agent queries when it sees a similar goal and asks "did I do this
before? how did it go?".

Capacity: unbounded by default. The store's `rotate(kind, keep_recent)`
method enforces the PRD's 10K-episode cap.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum

from .store import MemoryStore, MemoryKind, MemoryRecord


class EpisodeOutcome(str, Enum):
    """How the episode finished."""

    SUCCESS = "success"     # agent completed, user accepted
    PARTIAL = "partial"     # agent completed, partial result
    FAILED = "failed"       # agent gave up, replan loop exhausted
    UNKNOWN = "unknown"     # in progress, not yet evaluated


@dataclass
class Episode:
    """An episode is a structured view of one MemoryRecord (kind=episodic)."""

    id: str
    goal: str
    outcome: EpisodeOutcome
    steps_taken: int
    total_cost_usd: float
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_at: float = field(default_factory=time.time)
    # JSON-encoded lists/dicts in content for richer data
    findings: list[dict] = field(default_factory=list)
    final_report: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_record(self) -> dict:
        """Serialise for storage in MemoryRecord.content (JSON)."""
        return {
            "goal": self.goal,
            "outcome": self.outcome.value,
            "steps_taken": self.steps_taken,
            "total_cost_usd": self.total_cost_usd,
            "findings": self.findings,
            "final_report": self.final_report,
            "metadata": self.metadata,
        }

    @classmethod
    def from_record(cls, rec: MemoryRecord) -> "Episode":
        """Reconstruct from a MemoryRecord (kind=episodic)."""
        data = json.loads(rec.content) if rec.content else {}
        return cls(
            id=rec.id,
            goal=data.get("goal", rec.title),
            outcome=EpisodeOutcome(data.get("outcome", "unknown")),
            steps_taken=int(data.get("steps_taken", 0)),
            total_cost_usd=float(data.get("total_cost_usd", 0.0)),
            tags=rec.tags,
            created_at=rec.created_at,
            findings=list(data.get("findings", [])),
            final_report=data.get("final_report"),
            metadata=dict(data.get("metadata", {})),
        )


class EpisodicMemory:
    """High-level wrapper around MemoryStore for episodic records."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    @property
    def store(self) -> MemoryStore:
        return self._store

    def record(
        self,
        goal: str,
        outcome: EpisodeOutcome,
        steps_taken: int,
        total_cost_usd: float,
        *,
        findings: list[dict] | None = None,
        final_report: str | None = None,
        tags: tuple[str, ...] = (),
        metadata: dict | None = None,
    ) -> Episode:
        """Persist a completed episode."""
        ep = Episode(
            id="",  # filled by store
            goal=goal,
            outcome=outcome,
            steps_taken=steps_taken,
            total_cost_usd=total_cost_usd,
            tags=tags,
            findings=list(findings or []),
            final_report=final_report,
            metadata=dict(metadata or {}),
        )
        content = json.dumps(ep.to_record(), ensure_ascii=False)
        rec = self._store.insert(
            kind=MemoryKind.EPISODIC,
            title=goal[:80],
            content=content,
            tags=tags,
        )
        ep.id = rec.id
        return ep

    def get(self, episode_id: str) -> Episode | None:
        rec = self._store.get(episode_id)
        if rec is None or rec.kind != MemoryKind.EPISODIC:
            return None
        return Episode.from_record(rec)

    def list_recent(self, limit: int = 20) -> list[Episode]:
        """Most recent N episodes (newest first)."""
        records = self._store.list_by_kind(MemoryKind.EPISODIC, limit=limit)
        return [Episode.from_record(r) for r in records]

    def find_similar(self, goal_substring: str, limit: int = 5) -> list[Episode]:
        """Find episodes whose goal mentions the given substring (FTS5 search)."""
        # Quote to avoid FTS5 syntax issues with free-form goal text
        safe_query = goal_substring.replace('"', '""')
        records = self._store.search_fts(
            query=f'"{safe_query}"',
            kinds=[MemoryKind.EPISODIC],
            limit=limit,
        )
        return [Episode.from_record(r) for r in records]

    def count(self) -> int:
        return self._store.count_by_kind(MemoryKind.EPISODIC)


__all__ = [
    "Episode",
    "EpisodeOutcome",
    "EpisodicMemory",
]
