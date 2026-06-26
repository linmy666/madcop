"""v1.2.0 — SQLite schema for the PageDB knowledge brain.

A "knowledge brain" is the storage layer a long-running agent uses
to remember what it has learned across sessions and runs. This module
defines the 8 tables + 4 triggers + 5 indices that back it.

Design notes
------------
madcop's brain is a single-database, single-user store. We share some
shape with project memory tools but the schema is our own:

  pages      — a typed entry (person / project / concept / skill / event)
  page_fts   — FTS5 content-table over title + compiled_truth + timeline
  links      — directed graph between pages (context-aware)
  timeline_entries — per-page dated facts
  tags       — flat key/value per page (for filtering)
  versions   — full version history (every write snapshots a row) — our
               edge over project memory tools that overwrite in place
  review_queue — sensitive content caught by the prescreen; freed for
               manual review before merging into the brain
  ingest_log — append-only audit trail of every write, used by Dream
               consolidation to detect duplicate writes

We intentionally *don't* mirror every column of any external knowledge
store. The point of building our own is the affordances: snapshots
without forking Git, review queues without an external service, FTS5
without a search cluster.
"""
from __future__ import annotations

import sqlite3

# ----------------------------------------------------------------------------
# Schema DDL — every statement run by PageDB.init_db().
# ----------------------------------------------------------------------------

# `pages` is the central typed unit. compiled_truth is the dense summary
# (what other models see when they query); timeline is the chronological
# log (what humans see when they browse).
PAGES_DDL = """
CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL CHECK (
    type IN ('person','project','concept','skill','event')
  ),
  title TEXT NOT NULL,
  compiled_truth TEXT NOT NULL DEFAULT '',
  timeline TEXT NOT NULL DEFAULT '',
  frontmatter TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_accessed_at TEXT,
  stale_after_days INTEGER
);
"""

# FTS5 index over the dense summary and the chronological log.
# `content=pages` makes it automatically maintained via triggers.
PAGE_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(
  title,
  compiled_truth,
  timeline,
  content='pages',
  content_rowid='id',
  tokenize='porter unicode61'
);
"""

# Directed graph between pages. `context` describes how they relate
# ("works at", "references", "tried after", ...).
LINKS_DDL = """
CREATE TABLE IF NOT EXISTS links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  to_page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  context TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(from_page_id, to_page_id)
);
"""

TIMELINE_DDL = """
CREATE TABLE IF NOT EXISTS timeline_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""

TAGS_DDL = """
CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  UNIQUE(page_id, tag)
);
"""

# Full version history — every successful save appends a row. Doubled
# storage cost in exchange for time-travel reads (used by Dream
# consolidation when it suspects drift).
VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  version_no INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  compiled_truth TEXT NOT NULL,
  timeline TEXT NOT NULL,
  frontmatter TEXT NOT NULL DEFAULT '{}',
  saved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  saved_by TEXT NOT NULL DEFAULT 'system',
  UNIQUE(page_id, version_no)
);
"""

# Review queue: content the prescreen flagged as possibly sensitive.
# Kept separate from `pages` so a single bad inference doesn't pollute
# the brain. A reviewer (human) clears rows from this queue.
REVIEW_QUEUE_DDL = """
CREATE TABLE IF NOT EXISTS review_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  type TEXT NOT NULL,
  reason TEXT NOT NULL,
  content TEXT NOT NULL,
  pattern TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  reviewed INTEGER NOT NULL DEFAULT 0
);
"""

# Append-only audit log. Every write path appends a row. Dream
# consolidation reads from this to find duplicate writes and detect
# drift; `madcop doctor` reads from this to surface error patterns.
INGEST_LOG_DDL = """
CREATE TABLE IF NOT EXISTS ingest_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  operation TEXT NOT NULL CHECK (
    operation IN ('insert','update','delete','review','consolidate','access')
  ),
  source TEXT NOT NULL DEFAULT 'system',
  detail TEXT NOT NULL DEFAULT '',
  content_hash TEXT,
  page_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""

# Indices — kept narrow; most lookups hit only one or two columns.
INDICES_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_pages_type ON pages(type);",
    "CREATE INDEX IF NOT EXISTS idx_pages_updated ON pages(updated_at);",
    "CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_page_id);",
    "CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_page_id);",
    "CREATE INDEX IF NOT EXISTS idx_timeline_page ON timeline_entries(page_id);",
    "CREATE INDEX IF NOT EXISTS idx_timeline_date ON timeline_entries(date);",
    "CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);",
    "CREATE INDEX IF NOT EXISTS idx_tags_page ON tags(page_id);",
    "CREATE INDEX IF NOT EXISTS idx_versions_page ON versions(page_id);",
    "CREATE INDEX IF NOT EXISTS idx_review_queue_reviewed ON review_queue(reviewed);",
    "CREATE INDEX IF NOT EXISTS idx_review_queue_slug ON review_queue(slug);",
    "CREATE INDEX IF NOT EXISTS idx_ingest_log_slug ON ingest_log(slug);",
]

# Triggers — keep FTS5 in sync with `pages`. We use the standard
# `node_delete` / `node_insert` / `node_update` pattern so the FTS
# mirror reflects content mass + tokenisation.
TRIGGERS_DDL = [
    """
    CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
      INSERT INTO page_fts(rowid, title, compiled_truth, timeline)
      VALUES (new.id, new.title, new.compiled_truth, new.timeline);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
      INSERT INTO page_fts(page_fts, rowid, title, compiled_truth, timeline)
      VALUES ('delete', old.id, old.title, old.compiled_truth, old.timeline);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
      INSERT INTO page_fts(page_fts, rowid, title, compiled_truth, timeline)
      VALUES ('delete', old.id, old.title, old.compiled_truth, old.timeline);
      INSERT INTO page_fts(rowid, title, compiled_truth, timeline)
      VALUES (new.id, new.title, new.compiled_truth, new.timeline);
    END;
    """,
    # NOTE: The pages_touch trigger was removed in v1.2.1.
    #
    # On SQLite 3.40.x the combination of FTS5 external-content
    # triggers (pages_au) and an AFTER UPDATE trigger that itself
    # UPDATEs the same row causes a "database disk image is malformed"
    # error.  The trigger body fires pages_au a second time while the
    # FTS5 shadow tables still have the first delta pending, corrupting
    # the internal b-tree.
    #
    # Application code now sets updated_at explicitly on every UPDATE.
]


_DDL_ORDER = (
    PAGES_DDL + PAGE_FTS_DDL + LINKS_DDL + TIMELINE_DDL + TAGS_DDL
    + VERSIONS_DDL + REVIEW_QUEUE_DDL + INGEST_LOG_DDL
)


def init_db(conn: sqlite3.Connection) -> None:
    """Create all 8 tables + 5 indices + 4 triggers if they don't exist.

    Idempotent — safe to call on every startup.
    """
    cur = conn.cursor()
    cur.executescript(_DDL_ORDER)
    for stmt in INDICES_DDL:
        cur.execute(stmt)
    for stmt in TRIGGERS_DDL:
        cur.execute(stmt)
    conn.commit()


def current_schema_version(conn: sqlite3.Connection) -> int:
    """Look up the schema version. Returns 1 for v1.2.0."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cur.fetchone() is None:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY)"
        )
        cur.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (1,))
        conn.commit()
        return 1
    cur.execute("SELECT version FROM schema_version LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else 1
