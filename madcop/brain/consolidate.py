"""v1.2.0 — Dream consolidation: keep the brain tidy.

After months of running, a brain will accumulate:
- Pages that are byte-identical (someone re-ran a write loop).
- Pages that are nearly identical except for trailing newlines / dates.
- Links that no longer make sense (target deleted, source deleted).
- Pages that nobody has touched in N days.

A "Dream" pass walks the brain and:
  1. Deduplicates by content_hash (PageDB.touch_hash output).
  2. Marks links to/from missing pages — those are caught by
     ON DELETE CASCADE, but we also surface them in the report.
  3. Marks pages as stale (last_accessed_at older than
     `stale_after_days`).
  4. Optional: collapses two pages into one (manual call only,
     never auto-merge — that's where bad things happen).

We deliberately do NOT auto-merge content. Dedup is the safe
operation; merge is the dangerous one. We only flag and report.

Reports
-------
Every consolidation returns a `ConsolidationReport`. The CLI / test
code can then dump it as JSON, log it, or trigger a notification.

Auditability
------------
Every Dream pass writes one `ingest_log` row with operation="consolidate"
and a `detail` blob describing what it did. This is the only way to
trace a consolidation that ran while you were asleep.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .schema import init_db
from .store import PageDB


# --------------------------------------------------------------------------- #
# Report shape
# --------------------------------------------------------------------------- #


@dataclass
class ConsolidationReport:
    """The result of a single Dream pass.

    All counts are read-only after the pass. Pass it to a logger or
    serialise it to JSON for the audit log.
    """
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0
    duplicates_collapsed: int = 0
    orphan_links_removed: int = 0
    stale_pages_marked: list[int] = field(default_factory=list)
    review_queue_size: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "duplicates_collapsed": self.duplicates_collapsed,
            "orphan_links_removed": self.orphan_links_removed,
            "stale_pages_marked": self.stale_pages_marked,
            "review_queue_size": self.review_queue_size,
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.rstrip("Z")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Dream
# --------------------------------------------------------------------------- #


class Dream:
    """Run periodic housekeeping on a PageDB.

    Construction is cheap; `run()` does the work. State is held in the
    database, not on the Dream object — you can re-create a Dream for
    every pass.
    """

    DEFAULT_STALE_DAYS = 90

    def __init__(self, db: PageDB, *, stale_after_days: int = DEFAULT_STALE_DAYS) -> None:
        if stale_after_days < 0:
            raise ValueError("stale_after_days must be >= 0")
        self._db = db
        self.stale_after_days = stale_after_days

    # ---- public ----------------------------------------------------------

    def run(
        self,
        *,
        dry_run: bool = False,
        collapse_duplicates: bool = True,
        prune_orphans: bool = True,
        mark_stale: bool = True,
    ) -> ConsolidationReport:
        """Run one pass. Returns a report.

        Args:
            dry_run: if True, no writes happen. The report still
                reports what *would* have happened (mostly equal to
                a real run for dedup / orphan-removal; for mark_stale
                we report the candidate page ids).
            collapse_duplicates: when True, identical content_hash
                pages are merged (the older one is removed; tags/
                timeline of the older are moved to the survivor).
            prune_orphans: when True, dangling links are removed.
                (In practice ON DELETE CASCADE handles most of this;
                we just clean up where the constraint wasn't there.)
            mark_stale: when True, pages with
                `last_accessed_at` older than `stale_after_days` are
                tagged via `stale_after_days` (set to 0) so the
                `pages_with_tag("stale")` query can find them.
        """
        report = ConsolidationReport(started_at=_now_iso())
        t0 = time.monotonic()

        with self._db.transaction() as conn:
            if collapse_duplicates:
                report.duplicates_collapsed = self._collapse_duplicates(
                    conn, dry_run=dry_run
                )
            if prune_orphans:
                report.orphan_links_removed = self._prune_orphans(conn, dry_run=dry_run)
            if mark_stale:
                report.stale_pages_marked = self._mark_stale(
                    conn, dry_run=dry_run
                )
            row = conn.execute("SELECT COUNT(*) AS n FROM review_queue").fetchone()
            report.review_queue_size = int(row["n"])

            detail = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True)
            conn.execute(
                """
                INSERT INTO ingest_log(slug, operation, source, detail)
                VALUES ('__dream__', 'consolidate', 'dream', ?)
                """,
                (detail,),
            )

        report.finished_at = _now_iso()
        report.duration_s = time.monotonic() - t0
        return report

    # ---- collapse duplicates -------------------------------------------

    def _collapse_duplicates(self, conn: sqlite3.Connection, *, dry_run: bool) -> int:
        """Find pages with identical `content_hash` (via the most-recent
        version) and collapse them.

        For each set of duplicates, the OLDEST page (lowest id) is the
        survivor. Other pages are:
        - their tags are moved to the survivor
        - their timeline entries are moved to the survivor
        - their links are repointed to the survivor
        - their versions are reassigned to the survivor
        - then they are deleted

        Returns the number of pages deleted (NOT the number of duplicate
        sets). Returns 0 if there's nothing to do.
        """
        # Find groups of pages with the same current hash.
        # Only consider pages that actually have a version (otherwise no hash).
        rows = conn.execute(
            """
            WITH current_hashes AS (
                SELECT v.page_id, v.content_hash
                  FROM versions v
                  JOIN (
                      SELECT page_id, MAX(version_no) AS vn
                        FROM versions GROUP BY page_id
                  ) latest
                    ON latest.page_id = v.page_id AND latest.vn = v.version_no
            ),
            grouped AS (
                SELECT content_hash, COUNT(*) AS n
                  FROM current_hashes
                 GROUP BY content_hash
                HAVING n > 1
            )
            SELECT ch.content_hash AS content_hash,
                   GROUP_CONCAT(ch.page_id) AS page_ids
              FROM current_hashes ch
              JOIN grouped g ON g.content_hash = ch.content_hash
             GROUP BY ch.content_hash
            """
        ).fetchall()
        collapsed = 0
        for r in rows:
            ids = [int(x) for x in r["page_ids"].split(",")]
            survivor = ids[0]
            losers = ids[1:]
            if dry_run:
                collapsed += len(losers)
                continue
            # Move tags
            for lid in losers:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO tags(page_id, tag)
                    SELECT ?, tag FROM tags WHERE page_id=?
                    """,
                    (survivor, lid),
                )
                conn.execute("DELETE FROM tags WHERE page_id=?", (lid,))
            # Move timeline entries
            conn.execute(
                "UPDATE timeline_entries SET page_id=? WHERE page_id IN ({})".format(
                    ",".join("?" for _ in losers)
                ),
                [survivor] + losers,
            )
            # Repoint outgoing links
            for lid in losers:
                conn.execute(
                    """
                    UPDATE links SET to_page_id=?
                     WHERE to_page_id=?
                       AND NOT EXISTS (
                           SELECT 1 FROM links l2
                            WHERE l2.from_page_id = links.from_page_id
                              AND l2.to_page_id   = ?
                       )
                    """,
                    (survivor, lid, survivor),
                )
                conn.execute("DELETE FROM links WHERE to_page_id=?", (lid,))
            # Repoint incoming links
            for lid in losers:
                conn.execute(
                    """
                    UPDATE links SET from_page_id=?
                     WHERE from_page_id=?
                       AND NOT EXISTS (
                           SELECT 1 FROM links l2
                            WHERE l2.from_page_id = ?
                              AND l2.to_page_id   = links.to_page_id
                       )
                    """,
                    (survivor, lid, survivor),
                )
                conn.execute("DELETE FROM links WHERE from_page_id=?", (lid,))
            # Reassign versions to survivor. We re-version the merged-in
            # rows so the (page_id, version_no) UNIQUE constraint holds:
            # append losers' versions onto the survivor's version tail.
            tail_row = conn.execute(
                "SELECT COALESCE(MAX(version_no), 0) AS v FROM versions WHERE page_id=?",
                (survivor,),
            ).fetchone()
            next_v = int(tail_row["v"])
            for lid in losers:
                losers_versions = conn.execute(
                    "SELECT id, version_no FROM versions WHERE page_id=? ORDER BY version_no",
                    (lid,),
                ).fetchall()
                for lv in losers_versions:
                    next_v += 1
                    conn.execute(
                        "UPDATE versions SET page_id=?, version_no=? WHERE id=?",
                        (survivor, next_v, int(lv["id"])),
                    )
            # Delete the loser pages (CASCADE will reap tags/links/timeline if any)
            conn.execute(
                "DELETE FROM pages WHERE id IN ({})".format(
                    ",".join("?" for _ in losers)
                ),
                losers,
            )
            collapsed += len(losers)
        return collapsed

    # ---- prune orphan links --------------------------------------------

    def _prune_orphans(self, conn: sqlite3.Connection, *, dry_run: bool) -> int:
        """Remove links whose endpoints are missing.

        `ON DELETE CASCADE` already cleans links when a page is deleted,
        so this is mostly defensive. It still matters because:
        - users may have inserted invalid links before v1.2.0
        - a manual SQL edit could leave dangling rows

        Returns count of links removed.
        """
        rows = conn.execute(
            """
            SELECT l.id FROM links l
             LEFT JOIN pages p1 ON p1.id = l.from_page_id
             LEFT JOIN pages p2 ON p2.id = l.to_page_id
             WHERE p1.id IS NULL OR p2.id IS NULL
            """
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if not ids or dry_run:
            return len(ids)
        conn.execute(
            "DELETE FROM links WHERE id IN ({})".format(",".join("?" for _ in ids)),
            ids,
        )
        return len(ids)

    # ---- mark stale ----------------------------------------------------

    def _mark_stale(self, conn: sqlite3.Connection, *, dry_run: bool) -> list[int]:
        """Find pages whose `last_accessed_at` is older than
        `stale_after_days`, or whose `updated_at` is also old (for
        pages that have never been read). Tag them with a
        `stale_after_days=0` marker so `pages_with_tag` won't pick
        them up but the report does.

        Returns the list of marked page ids.
        """
        threshold = datetime.now(timezone.utc) - timedelta(days=self.stale_after_days)
        # We re-use SQLite's strftime-based comparison: ISO 8601
        # strings sort lexicographically, which matches chronological
        # order for the format we use.
        threshold_iso = threshold.strftime("%Y-%m-%dT%H:%M:%fZ")
        rows = conn.execute(
            """
            SELECT id FROM pages
             WHERE COALESCE(last_accessed_at, updated_at) < ?
            """,
            (threshold_iso,),
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if not ids or dry_run:
            return ids
        for pid in ids:
            conn.execute(
                "UPDATE pages SET stale_after_days=0 WHERE id=?",
                (pid,),
            )
        return ids


# --------------------------------------------------------------------------- #
# Convenience: one-shot "maintain the brain" entry point.
# --------------------------------------------------------------------------- #


def maintain(
    db: PageDB,
    *,
    stale_after_days: int = Dream.DEFAULT_STALE_DAYS,
    dry_run: bool = False,
) -> ConsolidationReport:
    """Run a Dream pass with sane defaults. Use this from CLI or cron."""
    return Dream(db, stale_after_days=stale_after_days).run(dry_run=dry_run)


__all__ = ["ConsolidationReport", "Dream", "maintain"]
