"""v1.2.0 — Tests for the brain schema and the markdown parser."""
from __future__ import annotations

import sqlite3

import pytest

from madcop.brain.markdown import (
    SLUG_RE,
    VALID_TYPES,
    ParseResult,
    extract_inline_tags,
    parse,
)
from madcop.brain.schema import current_schema_version, init_db


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def test_init_db_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    # 8 base tables + FTS5 internals
    assert {"pages", "page_fts", "links", "timeline_entries", "tags",
            "versions", "review_queue", "ingest_log"}.issubset(names)


def test_init_db_creates_indices():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"idx_pages_type", "idx_links_from", "idx_links_to",
            "idx_timeline_page", "idx_tags_tag", "idx_tags_page",
            "idx_versions_page", "idx_review_queue_reviewed",
            "idx_ingest_log_slug"}.issubset(names)


def test_init_db_creates_triggers():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"pages_ai", "pages_ad", "pages_au", "pages_touch"}.issubset(names)


def test_init_db_is_idempotent():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    init_db(conn)  # second call must not raise
    row = conn.execute("SELECT COUNT(*) FROM pages").fetchone()
    assert row[0] == 0


def test_current_schema_version_returns_1():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    assert current_schema_version(conn) == 1


# ---------------------------------------------------------------------------
# markdown parser
# ---------------------------------------------------------------------------


def test_parse_minimal_markdown():
    r = parse("## Hello\nWorld")
    # H1/H2 fallback lifts "Hello" into the title and slugifies it.
    assert r.title == "Hello"
    assert r.compiled_truth == "## Hello\nWorld"
    assert r.timeline == ""
    assert r.slug == "hello"


def test_parse_extracts_frontmatter():
    r = parse("---\ntitle: Alice\ntype: person\ntags: [a, b]\n---\n\n## Body\nstuff")
    assert r.title == "Alice"
    assert r.type == "person"
    assert r.frontmatter.get("tags") == ["a", "b"]


def test_parse_splits_at_timeline():
    raw = "## Body\nStuff\n\n## Timeline\n- 2026: did it"
    r = parse(raw)
    assert r.compiled_truth == "## Body\nStuff"
    assert r.timeline == "- 2026: did it"


def test_parse_slug_from_comment_declaration():
    raw = """---
title: Alice
type: person
---
<!--- madcop: slug = alice-park --->

## Body
Hi.
"""
    r = parse(raw)
    assert r.slug == "alice-park"
    assert "madcop: slug" not in r.compiled_truth  # comment stripped


def test_parse_slug_falls_back_to_title_slugify():
    r = parse("---\ntitle: My Project Page\ntype: project\n---\n\n## Body\nx")
    assert r.slug == "my-project-page"


def test_parse_rejects_invalid_type():
    r = parse("---\ntitle: A\ntype: bogus\n---\n\n## Body\nx")
    # Bogus type becomes None so caller can decide.
    assert r.type is None


def test_parse_quoted_frontmatter_string():
    r = parse('---\ntitle: "Quoted Name"\ntype: concept\n---\n\nx')
    assert r.title == "Quoted Name"


def test_parse_truthy_frontmatter_literal():
    r = parse("---\ntitle: A\ntype: concept\narchived: true\nhidden: false\n---\n\nx")
    assert r.frontmatter.get("archived") is True
    assert r.frontmatter.get("hidden") is False


def test_parse_empty_input():
    r = parse("")
    assert r.title == ""
    assert r.compiled_truth == ""
    assert r.timeline == ""


def test_parse_raises_on_non_string():
    with pytest.raises(TypeError):
        parse(123)  # type: ignore[arg-type]


def test_parse_falls_back_to_first_h1_as_title():
    r = parse("# This is the Title\n\nbody")
    assert r.title == "This is the Title"


def test_parse_handles_inline_tag_extraction():
    raw = "## Body\nSome #inline-tag and #type/skills mentioned"
    tags = extract_inline_tags(raw)
    assert "inline-tag" in tags
    assert "skills" in tags


def test_parse_handles_negative_slug_candidate():
    # Title with all special chars → title-slugify is empty; type
    # `project` is a valid slug so it becomes the slug.
    r = parse('---\ntitle: "??!!!"\ntype: project\n---\n\nx')
    assert r.slug == "project"


# ---------------------------------------------------------------------------
# SLUG_RE
# ---------------------------------------------------------------------------


def test_slug_re_accepts_valid_slugs():
    for s in ["a", "alice", "alice-park", "alice_p", "abc-123"]:
        assert SLUG_RE.match(s), s


def test_slug_re_rejects_invalid_slugs():
    for s in ["", "Alice", "alice park", "-alice", "alice-", "a" * 129, "$"]:
        assert not SLUG_RE.match(s), s


# ---------------------------------------------------------------------------
# VALID_TYPES
# ---------------------------------------------------------------------------


def test_valid_types_contents():
    assert VALID_TYPES == frozenset({"person", "project", "concept", "skill", "event"})


def test_parse_result_to_kwargs_round_trip():
    r = parse("---\ntitle: A\ntype: person\n---\n\n## Body\nX")
    kw = r.to_kwargs()
    assert kw["title"] == "A"
    assert kw["page_type"] == "person"
    assert kw["compiled_truth"] == "## Body\nX"
    assert kw["timeline"] == ""
    assert kw["slug"]  # non-empty
