"""L2 — Scenario memory layer.

Scenes are mid-tier aggregates that bundle related atoms (L1) into
themed scenario blocks (e.g. "user's project setup", "user's Python
preferences"). They are persisted as plain Markdown in
``~/.madcop/memory/scenarios/<id>.md`` for human inspection.

This module mirrors the design of :mod:`madcop.memory.semantic` and
:mod:`madcop.memory.episodic` but for the L2 scenario layer.

Schema (SQLite table ``memory_scenarios``):
    id, title, summary, atom_ids (json), tags (json),
    source_session_id, created_at, updated_at, file_path
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .store import MemoryStore


@dataclass
class Scenario:
    """A mid-tier scenario aggregating related atoms into a themed block."""

    id: str
    title: str
    summary: str
    atom_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_session_id: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    file_path: str | None = None
    body: str = ""


class ScenarioMemory:
    """CRUD + search around the L2 scenario layer.

    Scenarios are stored both in SQLite (for fast FTS5 search) and as
    Markdown files (for human inspection). The two views are kept in
    sync by :meth:`write` / :meth:`update`.
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.scenarios_dir = store.path.parent / "memory" / "scenarios"
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.store.path))

    def _ensure_table(self) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_scenarios (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    atom_ids TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    source_session_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    file_path TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scenarios_session "
                "ON memory_scenarios(source_session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scenarios_updated "
                "ON memory_scenarios(updated_at DESC)"
            )
            # FTS5 index on title + summary + body (stored in .md file)
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_scenarios_fts "
                    "USING fts5(id UNINDEXED, title, summary)"
                )
            except sqlite3.OperationalError:
                # FTS5 unavailable, fall back to LIKE
                pass
            conn.commit()
        finally:
            conn.close()

    def write(self, scenario: Scenario) -> Scenario:
        """Insert or replace a scenario (and its Markdown file)."""
        scenario.updated_at = time.time()
        if not scenario.file_path:
            scenario.file_path = str(self.scenarios_dir / f"{scenario.id}.md")

        # Persist Markdown body
        Path(scenario.file_path).write_text(
            self._render_markdown(scenario), encoding="utf-8"
        )

        # Persist SQLite row
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO memory_scenarios
                   (id, title, summary, atom_ids, tags,
                    source_session_id, created_at, updated_at, file_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scenario.id, scenario.title, scenario.summary,
                    json.dumps(scenario.atom_ids, ensure_ascii=False),
                    json.dumps(scenario.tags, ensure_ascii=False),
                    scenario.source_session_id,
                    scenario.created_at, scenario.updated_at,
                    scenario.file_path,
                ),
            )
            try:
                conn.execute(
                    "DELETE FROM memory_scenarios_fts WHERE id = ?",
                    (scenario.id,),
                )
                conn.execute(
                    "INSERT INTO memory_scenarios_fts(id, title, summary) VALUES (?, ?, ?)",
                    (scenario.id, scenario.title, scenario.summary),
                )
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            conn.close()
        return scenario

    def get(self, scenario_id: str) -> Scenario | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM memory_scenarios WHERE id = ?",
                (scenario_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return self._row_to_scenario(row)

    def search(self, query: str, limit: int = 10) -> list[Scenario]:
        """FTS5 search over title + summary, fallback to LIKE."""
        conn = self._conn()
        try:
            try:
                rows = conn.execute(
                    """SELECT s.* FROM memory_scenarios_fts f
                       JOIN memory_scenarios s ON s.id = f.id
                       WHERE memory_scenarios_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if not rows:
                like = f"%{query}%"
                rows = conn.execute(
                    """SELECT * FROM memory_scenarios
                       WHERE title LIKE ? OR summary LIKE ?
                       ORDER BY updated_at DESC LIMIT ?""",
                    (like, like, limit),
                ).fetchall()
        finally:
            conn.close()
        return [self._row_to_scenario(r) for r in rows]

    def list_recent(self, limit: int = 20) -> list[Scenario]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM memory_scenarios ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_scenario(r) for r in rows]

    def by_session(self, session_id: str, limit: int = 50) -> list[Scenario]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM memory_scenarios
                   WHERE source_session_id = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_scenario(r) for r in rows]

    def by_atoms(self, atom_ids: Iterable[str]) -> list[Scenario]:
        ids = list(atom_ids)
        if not ids:
            return []
        conn = self._conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM memory_scenarios WHERE id IN ({','.join('?'*len(ids))})",
                ids,
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_scenario(r) for r in rows]

    def delete(self, scenario_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM memory_scenarios WHERE id = ?", (scenario_id,))
            try:
                conn.execute(
                    "DELETE FROM memory_scenarios_fts WHERE id = ?",
                    (scenario_id,),
                )
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            conn.close()
        # Best-effort delete the markdown file
        try:
            Path(self.scenarios_dir / f"{scenario_id}.md").unlink(missing_ok=True)
        except Exception:
            pass

    # -- internal ------------------------------------------------------- #

    def _render_markdown(self, scenario: Scenario) -> str:
        tags_line = (
            "  \n**Tags:** " + ", ".join(scenario.tags)
            if scenario.tags
            else ""
        )
        atoms_line = (
            "  \n**Atoms:** " + ", ".join(scenario.atom_ids)
            if scenario.atom_ids
            else ""
        )
        return (
            f"# {scenario.title}\n\n"
            f"_{scenario.summary}_\n\n"
            f"{scenario.body or '_No body yet._'}"
            f"{tags_line}{atoms_line}\n"
        )

    def _row_to_scenario(self, row: sqlite3.Row) -> Scenario:
        try:
            atom_ids = json.loads(row["atom_ids"] or "[]")
        except Exception:
            atom_ids = []
        try:
            tags = json.loads(row["tags"] or "[]")
        except Exception:
            tags = []
        # Read body from disk if available
        body = ""
        file_path = row["file_path"]
        if file_path and Path(file_path).exists():
            try:
                # Skip the header (first 3 lines) so we just return the body
                lines = Path(file_path).read_text(encoding="utf-8").splitlines()
                body = "\n".join(lines[3:]).strip() if len(lines) > 3 else ""
            except Exception:
                body = ""
        return Scenario(
            id=row["id"],
            title=row["title"],
            summary=row["summary"] or "",
            atom_ids=atom_ids,
            tags=tags,
            source_session_id=row["source_session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            file_path=file_path,
            body=body,
        )

    def to_public_dict(self, scenario: Scenario) -> dict[str, Any]:
        return {
            "id": scenario.id,
            "title": scenario.title,
            "summary": scenario.summary,
            "atom_ids": scenario.atom_ids,
            "tags": scenario.tags,
            "source_session_id": scenario.source_session_id,
            "created_at": scenario.created_at,
            "updated_at": scenario.updated_at,
            "file_path": scenario.file_path,
            "body": scenario.body,
        }
