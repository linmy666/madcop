"""L2-L4 — Unified SQLite + FTS5 memory store.

The 4-layer memory all lives in ONE SQLite database. Different layers
are distinguished by `kind`:
  - "episodic"     (L2: every task we've done)
  - "semantic"     (L3: distilled facts / concepts / relations)
  - "reflective"   (L4: user prefs + meta-strategies)

Schema:
  - memory_records table: id, kind, title, content, tags, created_at, updated_at
  - memory_fts virtual table: FTS5 index on (title, content, tags)

Why FTS5 not vector search:
  - v0.6.0 is single-machine single-user, FTS5 is built into Python's sqlite3
  - Vector search adds an external dep (sqlite-vec, chroma, etc.)
  - FTS5 covers 90% of "find a memory that mentions X" needs
  - v0.7.0 can swap to vector search without API change

Path convention: ~/.madcop/memory.db by default.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence


class MemoryKind(str, Enum):
    """Three memory layers (L1 is in-memory ConversationBuffer, not persisted)."""

    EPISODIC = "episodic"     # L2: task history
    SEMANTIC = "semantic"     # L3: distilled knowledge
    REFLECTIVE = "reflective" # L4: feedback & meta


@dataclass
class MemoryRecord:
    """One row in the memory table. Immutable — mutate via the store."""

    id: str
    kind: MemoryKind
    title: str
    content: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    # Optional metadata as JSON-encoded string
    metadata: str = "{}"

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "MemoryRecord":
        return cls(
            id=row["id"],
            kind=MemoryKind(row["kind"]),
            title=row["title"],
            content=row["content"],
            tags=tuple(row["tags"].split(",")) if row["tags"] else (),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=row["metadata"] or "{}",
        )


# Schema is centralised here so all memory modules share the same table layout.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_records (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('episodic', 'semantic', 'reflective')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_records(kind);
CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory_records(created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    id UNINDEXED,
    kind UNINDEXED,
    title,
    content,
    tags,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


class MemoryStore:
    """SQLite-backed persistent store for the 4-layer memory.

    Use the high-level helpers (EpisodicMemory, SemanticMemory, ReflectiveMemory)
    for the public API. Direct MemoryStore use is for low-level operations.
    """

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path.home() / ".madcop" / "memory.db"
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(SCHEMA_SQL)

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ---- CRUD ------------------------------------------------------------

    def insert(
        self,
        kind: MemoryKind,
        title: str,
        content: str,
        tags: tuple[str, ...] = (),
        metadata: str = "{}",
    ) -> MemoryRecord:
        """Add a new memory record."""
        rid = uuid.uuid4().hex[:16]
        now = time.time()
        with self._conn:
            self._conn.execute(
                """INSERT INTO memory_records
                   (id, kind, title, content, tags, created_at, updated_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rid, kind.value, title, content, ",".join(tags), now, now, metadata),
            )
            self._conn.execute(
                """INSERT INTO memory_fts (id, kind, title, content, tags)
                   VALUES (?, ?, ?, ?, ?)""",
                (rid, kind.value, title, content, " ".join(tags)),
            )
        return MemoryRecord(
            id=rid,
            kind=kind,
            title=title,
            content=content,
            tags=tags,
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )

    def get(self, record_id: str) -> MemoryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM memory_records WHERE id = ?", (record_id,)
        ).fetchone()
        return MemoryRecord.from_row(row) if row else None

    def delete(self, record_id: str) -> bool:
        """Remove a record (and its FTS entry). Returns True if existed."""
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM memory_records WHERE id = ?", (record_id,)
            )
            self._conn.execute("DELETE FROM memory_fts WHERE id = ?", (record_id,))
        return cur.rowcount > 0

    def update(
        self,
        record_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: tuple[str, ...] | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> MemoryRecord | None:
        """Update fields of an existing record. Returns the updated record.

        - title/content/tags: if provided, replace the field
        - metadata_patch: dict of keys to merge into the JSON metadata
        - FTS index is kept in sync (delete + reinsert)
        - updated_at is bumped
        """
        existing = self.get(record_id)
        if existing is None:
            return None
        new_title = title if title is not None else existing.title
        new_content = content if content is not None else existing.content
        new_tags = tags if tags is not None else existing.tags
        if metadata_patch:
            try:
                meta = json.loads(existing.metadata or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}
            meta.update(metadata_patch)
        else:
            try:
                meta = json.loads(existing.metadata or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}
        new_metadata = json.dumps(meta, ensure_ascii=False)
        new_updated_at = time.time()
        with self._conn:
            self._conn.execute(
                "UPDATE memory_records SET title=?, content=?, tags=?, "
                "metadata=?, updated_at=? WHERE id=?",
                (new_title, new_content, ",".join(new_tags),
                 new_metadata, new_updated_at, record_id),
            )
            # FTS5 doesn't support UPDATE — delete + reinsert
            self._conn.execute("DELETE FROM memory_fts WHERE id = ?", (record_id,))
            self._conn.execute(
                "INSERT INTO memory_fts(id, kind, title, content, tags) "
                "VALUES (?, ?, ?, ?, ?)",
                (record_id, existing.kind.value, new_title, new_content,
                 ",".join(new_tags)),
            )
        return MemoryRecord(
            id=record_id,
            kind=existing.kind,
            title=new_title,
            content=new_content,
            tags=new_tags,
            created_at=existing.created_at,
            updated_at=new_updated_at,
            metadata=new_metadata,
        )

    def list_by_kind(
        self,
        kind: MemoryKind,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        rows = self._conn.execute(
            """SELECT * FROM memory_records
               WHERE kind = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (kind.value, limit, offset),
        ).fetchall()
        return [MemoryRecord.from_row(r) for r in rows]

    def count_by_kind(self, kind: MemoryKind) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS n FROM memory_records WHERE kind = ?",
            (kind.value,),
        ).fetchone()
        return int(cur["n"])

    def total_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM memory_records").fetchone()
        return int(cur["n"])

    # ---- Full-text search -----------------------------------------------

    def search_fts(
        self,
        query: str,
        kinds: Sequence[MemoryKind] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """FTS5 search across title/content/tags. Optional kind filter.

        The query uses FTS5 query syntax: 'oms AND spike', 'cancel*' for prefix.
        """
        # Always use a kind filter when specified; otherwise match all
        if kinds is not None and len(kinds) > 0:
            placeholders = ",".join("?" for _ in kinds)
            sql = f"""
                SELECT mr.* FROM memory_records mr
                JOIN memory_fts fts ON mr.id = fts.id
                WHERE memory_fts MATCH ?
                  AND mr.kind IN ({placeholders})
                ORDER BY rank
                LIMIT ?
            """
            params: list = [query] + [k.value for k in kinds] + [limit]
        else:
            sql = """
                SELECT mr.* FROM memory_records mr
                JOIN memory_fts fts ON mr.id = fts.id
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            params = [query, limit]
        rows = self._conn.execute(sql, params).fetchall()
        return [MemoryRecord.from_row(r) for r in rows]

    # ---- Maintenance -----------------------------------------------------

    def rotate(self, kind: MemoryKind, keep_recent: int) -> int:
        """Delete the oldest records of a given kind, keeping the N most recent.

        Returns number of rows deleted. Use to enforce the 10K episode cap
        from the PRD.
        """
        with self._conn:
            # Get IDs of the rows to delete (everything except the most recent N)
            to_delete = self._conn.execute(
                """SELECT id FROM memory_records
                   WHERE kind = ?
                   ORDER BY created_at DESC
                   LIMIT -1 OFFSET ?""",
                (kind.value, keep_recent),
            ).fetchall()
            if not to_delete:
                return 0
            ids = [r["id"] for r in to_delete]
            placeholders = ",".join("?" for _ in ids)
            self._conn.execute(
                f"DELETE FROM memory_records WHERE id IN ({placeholders})", ids
            )
            self._conn.execute(
                f"DELETE FROM memory_fts WHERE id IN ({placeholders})", ids
            )
        return len(ids)

    def vacuum(self) -> None:
        """Reclaim space after large deletes."""
        self._conn.execute("VACUUM")


__all__ = [
    "MemoryStore",
    "MemoryRecord",
    "MemoryKind",
    "SCHEMA_SQL",
]
