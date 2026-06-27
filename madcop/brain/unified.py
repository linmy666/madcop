"""Unified Brain + Memory façade (Gap 10).

The `madcop.brain` (PageDB) and `madcop.memory` (4-layer) systems
were built independently and store data in two separate SQLite
files. The unified façade gives callers a single entry point so
the agent doesn't have to know which subsystem to query.

Design:
- Keep both backends intact (no data migration, no schema change)
- The façade opens both stores lazily and provides cross-system
  search/list APIs
- Search merges results from both with a uniform {id, source, ...}
  shape
- Tools / API can use the unified interface to reach either
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import brain as _brain
from .. import memory as _memory


@dataclass
class UnifiedEntry:
    """One normalised record from either Brain or Memory."""
    id: str
    source: str         # "memory" | "brain"
    kind: str           # layer (semantic/episodic/reflective) or brain page_type
    title: str
    content: str
    tags: tuple[str, ...] = ()
    created_at: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedConfig:
    """Where each subsystem's data lives."""
    memory_db: Path = field(
        default_factory=lambda: Path("~/.madcop/memory.db").expanduser()
    )
    memory_key: Path = field(
        default_factory=lambda: Path("~/.madcop/master.key").expanduser()
    )
    brain_db: Path = field(
        default_factory=lambda: Path("~/.madcop/brain.db").expanduser()
    )


class UnifiedKnowledge:
    """Open both subsystems lazily; provide merged search and list."""

    def __init__(self, config: UnifiedConfig | None = None):
        self.config = config or UnifiedConfig()
        self._memory_store: _memory.MemoryStore | None = None
        self._brain_store: Any = None

    # ----- lazy loaders -----
    def memory(self) -> _memory.MemoryStore:
        if self._memory_store is None:
            self._memory_store = _memory.MemoryStore(
                path=self.config.memory_db,
            )
        return self._memory_store

    def brain(self) -> Any:
        if self._brain_store is None:
            self._brain_store = _brain.PageDB(path=self.config.brain_db)
        return self._brain_store

    # ----- merged APIs -----
    def list_all(
        self, *, limit: int = 100,
    ) -> list[UnifiedEntry]:
        """List recent records from both subsystems."""
        out: list[UnifiedEntry] = []
        try:
            ms = self.memory()
            rows = ms._conn.execute(
                "SELECT id, kind, title, content, tags, created_at "
                "FROM memory_records ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            for r in rows:
                out.append(UnifiedEntry(
                    id=r["id"],
                    source="memory",
                    kind=r["kind"],
                    title=r["title"] or "",
                    content=r["content"] or "",
                    tags=tuple((r["tags"] or "").split(",")) if r["tags"] else (),
                    created_at=r["created_at"] or 0.0,
                ))
        except Exception:
            pass
        try:
            bs = self.brain()
            for page in bs.list_by_type("note", limit=limit):
                out.append(UnifiedEntry(
                    id=page.slug,
                    source="brain",
                    kind=getattr(page, "page_type", "note"),
                    title=getattr(page, "title", page.slug),
                    content=getattr(page, "compiled_truth", "") or "",
                    tags=tuple(getattr(page, "tags", []) or []),
                    created_at=getattr(page, "created_at", 0.0) or 0.0,
                ))
        except Exception:
            pass
        out.sort(key=lambda e: e.created_at, reverse=True)
        return out[:limit]

    def search(self, query: str, *, limit: int = 20) -> list[UnifiedEntry]:
        """Search both subsystems; merge by recency."""
        out: list[UnifiedEntry] = []
        # Memory search (FTS5 + LIKE)
        try:
            ms = self.memory()
            from ..memory.hybrid import hybrid_search
            for row in hybrid_search(ms, query, limit=limit):
                out.append(UnifiedEntry(
                    id=row.get("id", ""),
                    source="memory",
                    kind=row.get("kind", ""),
                    title=row.get("title", ""),
                    content=row.get("content", ""),
                    tags=tuple((row.get("tags") or "").split(",")) if row.get("tags") else (),
                    created_at=row.get("created_at", 0.0) or 0.0,
                ))
        except Exception:
            pass
        # Brain search
        try:
            bs = self.brain()
            for page in bs.search(query, limit=limit):
                out.append(UnifiedEntry(
                    id=page.slug,
                    source="brain",
                    kind=getattr(page, "page_type", "note"),
                    title=getattr(page, "title", page.slug),
                    content=getattr(page, "compiled_truth", "") or "",
                    tags=tuple(getattr(page, "tags", []) or []),
                    created_at=getattr(page, "created_at", 0.0) or 0.0,
                ))
        except Exception:
            pass
        out.sort(key=lambda e: e.created_at, reverse=True)
        return out[:limit]

    def close(self) -> None:
        if self._memory_store is not None:
            try:
                self._memory_store.close()
            except Exception:
                pass
            self._memory_store = None
        if self._brain_store is not None:
            try:
                self._brain_store.close()
            except Exception:
                pass
            self._brain_store = None


__all__ = [
    "UnifiedEntry",
    "UnifiedConfig",
    "UnifiedKnowledge",
]
