"""v1.2.0 — PageDB: CRUD layer for the knowledge brain.

This module is the only public surface for writing to pages, links,
timeline entries, and tags. Higher-level operations (Dream consolidation,
prescreen guards) are separate modules that take a `PageDB` instance.

Why so flat?
We resist the temptation to expose "rich model classes" that hide the
schema. The brain is small and dense — eight tables, four indices,
four triggers — and we'd rather have callers see exactly what happens
than an OO abstraction that papers over joins.

What this module gives you
--------------------------
  PageDB(path)
    .save(slug, title, page_type, compiled_truth, timeline, frontmatter, ...)
    .get(slug)
    .delete(slug)
    .search(query, types=None, tags=None, limit=20)
    .get_links(slug)               -> list[(slug, context)]
    .add_link(from_slug, to_slug, context)
    .add_timeline(page_id, date, source, summary, detail)
    .add_tags(slug, tags)
    .list_by_type(type_, limit=100)
    .history(slug)                 -> list of versions
    .audit_log(slug, operation=None)

All save paths go through one helper that bumps `versions` and writes
an `ingest_log` entry — this is the invariant that Dream consolidation
relies on when it later asks "what changed and when".

The store is single-process SQLite via Python stdlib. For multi-process
use cases (workers writing to the same brain) wrap with `WAL` mode
(_conn.execute("PRAGMA journal_mode=WAL")) — not provided here because
madcop v1.2.0 is single-process.

Validation
----------
- `slug` must match `^[a-z0-9][a-z0-9_-]{0,127}$` (validated here, not
  only at parse time; the public API is the real gate).
- `page_type` must be one of VALID_TYPES.
- `frontmatter` is serialised as JSON blob (we don't depend on PyYAML).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .markdown import SLUG_RE, VALID_TYPES
from .schema import init_db, current_schema_version


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #


@dataclass
class Page:
    """One brain page, in-memory. Use `Page.from_row` to construct from DB."""
    id: int
    slug: str
    type: str
    title: str
    compiled_truth: str = ""
    timeline: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    last_accessed_at: str | None = None
    stale_after_days: int | None = None
    tags: list[str] = field(default_factory=list)
    content_hash: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Page":
        try:
            fm = json.loads(row["frontmatter"] or "{}")
        except json.JSONDecodeError:
            fm = {}
        keys = row.keys() if hasattr(row, "keys") else ()
        return cls(
            id=int(row["id"]),
            slug=row["slug"],
            type=row["type"],
            title=row["title"],
            compiled_truth=row["compiled_truth"] or "",
            timeline=row["timeline"] or "",
            frontmatter=fm,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            last_accessed_at=(row["last_accessed_at"] if "last_accessed_at" in keys else None),
            stale_after_days=(int(row["stale_after_days"]) if "stale_after_days" in keys and row["stale_after_days"] is not None else None),
        )

    def touch_hash(self) -> str:
        """Hash the dense summary so we can detect identical saves."""
        h = hashlib.sha256()
        h.update((self.title or "").encode("utf-8"))
        h.update(b"\x00")
        h.update((self.compiled_truth or "").encode("utf-8"))
        h.update(b"\x00")
        h.update((self.timeline or "").encode("utf-8"))
        h.update(b"\x00")
        h.update(json.dumps(self.frontmatter or {}, sort_keys=True).encode("utf-8"))
        return h.hexdigest()


@dataclass
class SearchHit:
    """A row from `PageDB.search()`. FTS5 score, plus the matched page."""
    page: Page
    score: float
    snippet: str = ""


# --------------------------------------------------------------------------- #
# PageDB
# --------------------------------------------------------------------------- #


class PageDB:
    """SQLite-backed store for the knowledge brain.

    Open a single instance per process. Wrap in `with PageDB(path) as db:`
    for auto-close, or call `db.close()` yourself.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL reduces "database is locked" under concurrent readers/writers.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            pass
        init_db(self._conn)
        self._schema_version = current_schema_version(self._conn)

    # ---- lifecycle --------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def schema_version(self) -> int:
        return self._schema_version

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.ProgrammingError:
            pass

    def __enter__(self) -> "PageDB":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._conn:
            yield self._conn

    # ---- validation -------------------------------------------------------

    @staticmethod
    def validate_slug(slug: str) -> None:
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            raise ValueError(
                f"slug must match [a-z0-9][a-z0-9_-]{{0,127}} (got {slug!r})"
            )

    @staticmethod
    def validate_type(page_type: str) -> None:
        if page_type not in VALID_TYPES:
            raise ValueError(
                f"type must be one of {sorted(VALID_TYPES)} (got {page_type!r})"
            )

    # ---- save (insert / update) ------------------------------------------

    def save(
        self,
        slug: str,
        title: str,
        page_type: str,
        compiled_truth: str = "",
        timeline: str = "",
        frontmatter: dict[str, Any] | None = None,
        *,
        source: str = "manual",
        saved_by: str = "system",
        tags: Iterable[str] | None = None,
    ) -> Page:
        """Insert or update a page. Writes a `versions` row and an
        `ingest_log` entry. Returns the new page state.

        Raises ValueError on bad slug / type. Does NOT auto-merge:
        callers overwrite. If you want append-only behaviour, use
        `add_timeline` instead.
        """
        self.validate_slug(slug)
        self.validate_type(page_type)
        fm = frontmatter or {}
        fm_json = json.dumps(fm, sort_keys=True, ensure_ascii=False)

        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM pages WHERE slug=?", (slug,)
            ).fetchone()
            if existing is None:
                cur = conn.execute(
                    """
                    INSERT INTO pages(
                      slug, type, title, compiled_truth, timeline, frontmatter
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (slug, page_type, title, compiled_truth, timeline, fm_json),
                )
                page_id = int(cur.lastrowid)
                op = "insert"
                prev_hash = ""
            else:
                page_id = int(existing["id"])
                # Look up the previous hash from the most recent version.
                row = conn.execute(
                    "SELECT content_hash FROM versions "
                    "WHERE page_id=? ORDER BY version_no DESC LIMIT 1",
                    (page_id,),
                ).fetchone()
                prev_hash = row["content_hash"] if row else ""
                # Explicitly set updated_at — the pages_touch trigger
                # was removed in v1.2.1 (see schema.py) so we manage
                # timestamps in application code.
                conn.execute(
                    """
                    UPDATE pages
                       SET type=?, title=?, compiled_truth=?, timeline=?,
                           frontmatter=?,
                           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                     WHERE id=?
                    """,
                    (page_type, title, compiled_truth, timeline, fm_json, page_id),
                )
                op = "update"

            page = self._get_by_id(page_id)
            new_hash = page.touch_hash()

            if prev_hash == new_hash and op == "update":
                # No-op write: still bump ingest_log as "access" so we
                # have a record, but skip a new version row.
                self._audit(conn, slug, "access", source, new_hash, page_id)
                return page

            version_no = self._next_version_no(conn, page_id)
            conn.execute(
                """
                INSERT INTO versions(
                  page_id, version_no, content_hash, compiled_truth,
                  timeline, frontmatter, saved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id, version_no, new_hash, compiled_truth, timeline,
                    fm_json, saved_by,
                ),
            )
            self._audit(conn, slug, op, source, new_hash, page_id)

            if tags is not None:
                self._set_tags(conn, page_id, list(tags))

        # Re-fetch so the returned Page includes the just-set tags.
        return self._get_by_id(page_id)

    @staticmethod
    def _next_version_no(conn: sqlite3.Connection, page_id: int) -> int:
        cur = conn.execute(
            "SELECT COALESCE(MAX(version_no), 0) + 1 FROM versions WHERE page_id=?",
            (page_id,),
        )
        return int(cur.fetchone()[0])

    @staticmethod
    def _audit(
        conn: sqlite3.Connection,
        slug: str,
        operation: str,
        source: str,
        content_hash: str,
        page_id: int | None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ingest_log(slug, operation, source, content_hash, page_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (slug, operation, source or "system", content_hash or "", page_id),
        )

    @staticmethod
    def _set_tags(conn: sqlite3.Connection, page_id: int, tags: list[str]) -> None:
        conn.execute("DELETE FROM tags WHERE page_id=?", (page_id,))
        seen: set[str] = set()
        for t in tags:
            t = (t or "").strip().lower()
            if not t or t in seen:
                continue
            seen.add(t)
            conn.execute(
                "INSERT OR IGNORE INTO tags(page_id, tag) VALUES (?, ?)",
                (page_id, t),
            )

    # ---- get / delete / list --------------------------------------------

    def _get_by_id(self, page_id: int) -> Page:
        row = self._conn.execute(
            "SELECT * FROM pages WHERE id=?", (page_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"page id {page_id} not found")
        page = Page.from_row(row)
        page.tags = self._tags_for(page_id)
        return page

    def get(self, slug: str) -> Page | None:
        row = self._conn.execute(
            "SELECT * FROM pages WHERE slug=?", (slug,)
        ).fetchone()
        if row is None:
            return None
        page_id = int(row["id"])
        page = Page.from_row(row)
        page.tags = self._tags_for(page_id)
        # Bump last_accessed_at — used by Dream consolidation to
        # decide what's stale.
        self._conn.execute(
            "UPDATE pages SET last_accessed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE id=?",
            (page_id,),
        )
        # Re-read the column so the returned Page reflects the bump.
        row2 = self._conn.execute(
            "SELECT last_accessed_at FROM pages WHERE id=?", (page_id,)
        ).fetchone()
        if row2 is not None:
            page.last_accessed_at = row2["last_accessed_at"]
        return page

    def delete(self, slug: str, *, source: str = "manual") -> bool:
        row = self._conn.execute("SELECT id FROM pages WHERE slug=?", (slug,)).fetchone()
        if row is None:
            return False
        page_id = int(row["id"])
        with self.transaction() as conn:
            conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
            self._audit(conn, slug, "delete", source, "", page_id)
        return True

    def list_by_type(self, type_: str, *, limit: int = 100) -> list[Page]:
        self.validate_type(type_)
        rows = self._conn.execute(
            "SELECT * FROM pages WHERE type=? ORDER BY updated_at DESC LIMIT ?",
            (type_, int(limit)),
        ).fetchall()
        pages = [Page.from_row(r) for r in rows]
        for p in pages:
            p.tags = self._tags_for(p.id)
        return pages

    def list_all(self, *, limit: int = 1000) -> list[Page]:
        rows = self._conn.execute(
            "SELECT * FROM pages ORDER BY updated_at DESC LIMIT ?", (int(limit),)
        ).fetchall()
        pages = [Page.from_row(r) for r in rows]
        for p in pages:
            p.tags = self._tags_for(p.id)
        return pages

    def _tags_for(self, page_id: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT tag FROM tags WHERE page_id=? ORDER BY tag", (page_id,)
        ).fetchall()
        return [r["tag"] for r in rows]

    # ---- search (FTS5) ---------------------------------------------------

    def search(
        self,
        query: str,
        *,
        types: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        """Full-text search via FTS5.

        Returns a list of `SearchHit` ordered by FTS5 rank (BM25).
        A snippet is constructed from the first matching row.
        """
        if not query or not query.strip():
            return []
        # FTS5 query format. We join tokens with OR so that a
        # natural-language query ("Handle rate limit on API") can
        # match documents containing *any* of the words, not requiring
        # all of them. Quoted phrases are preserved for exact-match.
        # Stopwords are filtered to reduce false positives in OR mode.
        q = query.replace('"', ' ').strip()
        if not q:
            return []
        _STOPWORDS = frozenset(
            "a an the on in at to of for and or not is it its "
            "be by do if so as my we us our you your this that "
            "with from into onto over under up down out off "
            "how why what when where who which whom whose "
            "am are was were been being has have had did does "
            "will would could should might can may must shall "
            "i me him her them they he she his hers their "
            "no yes more most some any all each every other "
            "than then too very just only also here there "
            "about above below between among through during "
            "after before since until while because though "
            "although unless whereas whether".split()
        )
        tokens = [t for t in q.split() if len(t) > 1 and t.lower() not in _STOPWORDS]
        if not tokens:
            return []
        if len(tokens) == 1:
            fts_query = f'"{tokens[0]}"'
        else:
            fts_query = " OR ".join(f'"{t}"' for t in tokens)

        sql = [
            "SELECT p.*, bm25(page_fts) AS score, ",
            "       snippet(page_fts, 1, '<<', '>>', '...', 16) AS snippet",
            "FROM page_fts JOIN pages p ON p.id = page_fts.rowid",
            f"WHERE page_fts MATCH ?",
        ]
        params: list[Any] = [fts_query]

        if types:
            valid = [t for t in types if t in VALID_TYPES]
            if not valid:
                return []
            placeholders = ",".join("?" for _ in valid)
            sql.append(f"  AND p.type IN ({placeholders})")
            params.extend(valid)

        if tags:
            placeholders = ",".join("?" for _ in tags)
            sql.append(
                f"  AND p.id IN (SELECT page_id FROM tags WHERE tag IN ({placeholders}))"
            )
            params.extend(t.lower() for t in tags)

        sql.append("ORDER BY score LIMIT ?")
        params.append(int(limit))

        rows = self._conn.execute("\n".join(sql), params).fetchall()
        hits: list[SearchHit] = []
        for r in rows:
            page = Page.from_row(r)
            page.tags = self._tags_for(page.id)
            hits.append(SearchHit(
                page=page,
                score=float(r["score"]),
                snippet=str(r["snippet"] or ""),
            ))
        return hits

    # ---- links ------------------------------------------------------------

    def add_link(
        self,
        from_slug: str,
        to_slug: str,
        context: str = "",
        *,
        source: str = "manual",
    ) -> bool:
        """Create a directed link. Returns True if newly created, False if existed."""
        self.validate_slug(from_slug)
        self.validate_slug(to_slug)
        if from_slug == to_slug:
            raise ValueError("from_slug and to_slug must differ")
        a = self.get(from_slug)
        b = self.get(to_slug)
        if a is None or b is None:
            raise KeyError(
                f"link target missing: from={from_slug!r} to={to_slug!r}"
            )
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO links(from_page_id, to_page_id, context)
                VALUES (?, ?, ?)
                """,
                (a.id, b.id, context),
            )
            created = cur.rowcount > 0
            if created:
                self._audit(conn, from_slug, "update", source, "", a.id)
        return created

    def get_links(self, slug: str, *, direction: str = "out") -> list[tuple[str, str]]:
        """Return list of (other_slug, context) for links touching `slug`.

        `direction`:
          "out"  -> edges leaving slug  (from_slug=slug)
          "in"   -> edges arriving at slug (to_slug=slug)
          "both" -> union of both
        """
        if direction not in ("out", "in", "both"):
            raise ValueError(f"direction must be out/in/both (got {direction!r})")
        page = self.get(slug)
        if page is None:
            return []
        out: list[tuple[str, str]] = []
        with self.transaction() as conn:
            if direction in ("out", "both"):
                rows = conn.execute(
                    """
                    SELECT p.slug AS s, l.context AS ctx
                      FROM links l JOIN pages p ON p.id = l.to_page_id
                     WHERE l.from_page_id = ?
                    """,
                    (page.id,),
                ).fetchall()
                out.extend((r["s"], r["ctx"]) for r in rows)
            if direction in ("in", "both"):
                rows = conn.execute(
                    """
                    SELECT p.slug AS s, l.context AS ctx
                      FROM links l JOIN pages p ON p.id = l.from_page_id
                     WHERE l.to_page_id = ?
                    """,
                    (page.id,),
                ).fetchall()
                out.extend((r["s"], r["ctx"]) for r in rows)
        return out

    # ---- timeline / tags ------------------------------------------------

    def add_timeline(
        self,
        slug: str,
        date: str,
        source: str,
        summary: str,
        detail: str = "",
    ) -> int:
        """Append a dated fact to a page. Returns the new entry id."""
        page = self.get(slug)
        if page is None:
            raise KeyError(f"page {slug!r} not found")
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO timeline_entries(page_id, date, source, summary, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (page.id, date, source or "", summary, detail or ""),
            )
            self._audit(conn, slug, "update", source, "", page.id)
            return int(cur.lastrowid)

    def timeline_for(self, slug: str, *, limit: int = 100) -> list[dict[str, Any]]:
        page = self.get(slug)
        if page is None:
            return []
        rows = self._conn.execute(
            """
            SELECT id, date, source, summary, detail, created_at
              FROM timeline_entries
             WHERE page_id=?
             ORDER BY date DESC, id DESC
             LIMIT ?
            """,
            (page.id, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_tags(self, slug: str, tags: Iterable[str]) -> int:
        """Add tags without removing existing ones. Returns count of new tags."""
        page = self.get(slug)
        if page is None:
            raise KeyError(f"page {slug!r} not found")
        added = 0
        with self.transaction() as conn:
            for t in tags:
                t = (t or "").strip().lower()
                if not t:
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO tags(page_id, tag) VALUES (?, ?)",
                    (page.id, t),
                )
                added += cur.rowcount
            if added:
                self._audit(conn, slug, "update", "tags", "", page.id)
        return added

    def pages_with_tag(self, tag: str, *, limit: int = 100) -> list[Page]:
        rows = self._conn.execute(
            """
            SELECT p.* FROM pages p
              JOIN tags t ON t.page_id = p.id
             WHERE t.tag = ?
             ORDER BY p.updated_at DESC
             LIMIT ?
            """,
            (tag.lower(), int(limit)),
        ).fetchall()
        pages = [Page.from_row(r) for r in rows]
        for p in pages:
            p.tags = self._tags_for(p.id)
        return pages

    # ---- versions / audit ------------------------------------------------

    def history(self, slug: str) -> list[dict[str, Any]]:
        page = self.get(slug)
        if page is None:
            return []
        rows = self._conn.execute(
            """
            SELECT version_no, content_hash, saved_at, saved_by,
                   length(compiled_truth) AS ct_len, length(timeline) AS tl_len
              FROM versions
             WHERE page_id=?
             ORDER BY version_no DESC
            """,
            (page.id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def audit_log(
        self,
        slug: str | None = None,
        *,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ingest_log WHERE 1=1"
        params: list[Any] = []
        if slug is not None:
            sql += " AND slug=?"
            params.append(slug)
        if operation is not None:
            sql += " AND operation=?"
            params.append(operation)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ---- introspection ---------------------------------------------------

    def stats(self) -> dict[str, int]:
        """Counts of pages / versions / links / etc. for diagnostics."""
        out: dict[str, int] = {}
        for table in (
            "pages", "versions", "links", "timeline_entries",
            "tags", "review_queue", "ingest_log",
        ):
            row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            out[table] = int(row["n"])
        out["schema_version"] = self._schema_version
        return out


__all__ = ["Page", "PageDB", "SearchHit"]
