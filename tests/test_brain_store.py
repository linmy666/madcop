"""v1.2.0 — Tests for PageDB CRUD, FTS5 search, and version/audit trails."""
from __future__ import annotations

import json
import sqlite3

import pytest

from madcop.brain.store import Page, PageDB, SearchHit


@pytest.fixture
def db(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_init_creates_db_file(tmp_path):
    path = tmp_path / "fresh.db"
    assert not path.exists()
    PageDB(path)
    assert path.exists()


def test_init_creates_parent_dirs(tmp_path):
    nested = tmp_path / "deep" / "nested" / "brain.db"
    PageDB(nested)
    assert nested.exists()


def test_schema_version_is_1(db):
    assert db.schema_version == 1


def test_stats_includes_all_tables(db):
    stats = db.stats()
    for t in ("pages", "versions", "links", "timeline_entries",
              "tags", "review_queue", "ingest_log"):
        assert t in stats
    assert stats["schema_version"] == 1
    assert stats["pages"] == 0


def test_context_manager_closes(tmp_path):
    path = tmp_path / "ctx.db"
    with PageDB(path) as db:
        db.save(slug="x", title="X", page_type="person")
    # Should be safe to re-open.
    with PageDB(path) as db2:
        assert db2.get("x") is not None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_slug_accepts():
    PageDB.validate_slug("alice")
    PageDB.validate_slug("alice-park")
    PageDB.validate_slug("a1")
    PageDB.validate_slug("a" * 128)


def test_validate_slug_rejects():
    with pytest.raises(ValueError):
        PageDB.validate_slug("Alice")  # uppercase
    with pytest.raises(ValueError):
        PageDB.validate_slug("alice park")
    with pytest.raises(ValueError):
        PageDB.validate_slug("-alice")  # leading dash
    with pytest.raises(ValueError):
        PageDB.validate_slug("alice-")  # trailing dash
    with pytest.raises(ValueError):
        PageDB.validate_slug("a" * 129)  # too long
    with pytest.raises(ValueError):
        PageDB.validate_slug("")


def test_validate_type_rejects():
    with pytest.raises(ValueError):
        PageDB.validate_type("bogus")


def test_save_rejects_bad_slug(db):
    with pytest.raises(ValueError):
        db.save(slug="Bad", title="X", page_type="person")


def test_save_rejects_bad_type(db):
    with pytest.raises(ValueError):
        db.save(slug="ok", title="X", page_type="bogus")


# ---------------------------------------------------------------------------
# Save / get / delete
# ---------------------------------------------------------------------------


def test_save_inserts_page(db):
    p = db.save(slug="alice", title="Alice Park", page_type="person",
                compiled_truth="hi", timeline="- 2026: said hi")
    assert p.id > 0
    assert p.slug == "alice"
    assert p.title == "Alice Park"
    assert p.compiled_truth == "hi"


def test_save_returns_full_page_with_tags(db):
    p = db.save(slug="alice", title="Alice", page_type="person",
                tags=["alice", "friend", "alice"])  # dedup
    assert sorted(p.tags) == ["alice", "friend"]


def test_save_creates_initial_version(db):
    db.save(slug="alice", title="Alice", page_type="person")
    history = db.history("alice")
    assert len(history) == 1
    assert history[0]["version_no"] == 1


def test_save_idempotent_when_content_unchanged(db):
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="x")
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="x")
    assert len(db.history("alice")) == 1  # no new version


def test_save_bumps_version_on_content_change(db):
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="x")
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="y")
    assert len(db.history("alice")) == 2


def test_save_double_save_long_body_with_unicode(db):
    """Regression: SQLite 3.40.x pages_touch trigger bug.

    Re-saving the same slug with a different *long* body (with
    multi-byte UTF-8 like em-dash and section headers) used to trip
    a "database disk image is malformed" error on the inner UPDATE
    in the ``pages_touch`` AFTER UPDATE trigger. The fix is in
    ``db.save()``: the outer UPDATE now explicitly sets
    ``updated_at = strftime(...)`` so the trigger's WHEN-guard is
    always false and the trigger body never runs.

    This test exercises the exact pattern that crystallize_skills
    hit: 600+ byte body with em-dash and backticks.
    """
    long_body_1 = (
        "---\n"
        "type: skill\n"
        "topic: rate-limit\n"
        "applies_to: all\n"
        "outcome: success\n"
        "---\n\n"
        "## Cluster topic\n\n`rate-limit`\n\n"
        "## Member reflections\n\n"
        "- **rate-limit-retry** (success, `all`) \u2014 `reflection-rate-limit-retry`\n"
        "- **rate-limit-burst** (success, `all`) \u2014 `reflection-rate-limit-burst`\n"
    )
    long_body_2 = long_body_1 + "- **rate-limit-headers** (success, `all`) \u2014 `reflection-rate-limit-headers`\n"
    db.save(slug="skill-rate-limit", title="rate-limit", page_type="skill",
            compiled_truth=long_body_1,
            frontmatter={"topic": "rate-limit", "members": ["a", "b"]},
            tags=["crystallized", "topic:rate-limit", "members:2"])
    # 2nd save: same slug, longer body, larger members list. This
    # is the exact pattern that triggered the bug.
    db.save(slug="skill-rate-limit", title="rate-limit", page_type="skill",
            compiled_truth=long_body_2,
            frontmatter={"topic": "rate-limit", "members": ["a", "b", "c"]},
            tags=["crystallized", "topic:rate-limit", "members:3"])
    # 3rd save to be sure: same slug, different body.
    db.save(slug="skill-rate-limit", title="rate-limit", page_type="skill",
            compiled_truth=long_body_2 + "\nextra line",
            frontmatter={"topic": "rate-limit", "members": ["a", "b", "c", "d"]},
            tags=["crystallized", "topic:rate-limit", "members:4"])
    versions = db.history("skill-rate-limit")
    assert len(versions) == 3


def test_get_returns_none_for_missing(db):
    assert db.get("ghost") is None


def test_get_returns_page(db):
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="hi", tags=["a"])
    p = db.get("alice")
    assert p is not None
    assert p.title == "Alice"
    assert "a" in p.tags


def test_get_updates_last_accessed_at(db):
    db.save(slug="alice", title="Alice", page_type="person")
    assert db.get("alice").last_accessed_at is not None


def test_delete_removes_page(db):
    db.save(slug="alice", title="Alice", page_type="person")
    assert db.delete("alice") is True
    assert db.get("alice") is None


def test_delete_returns_false_for_missing(db):
    assert db.delete("ghost") is False


def test_delete_cascades_tags_and_links(db):
    db.save(slug="alice", title="Alice", page_type="person")
    db.save(slug="bob", title="Bob", page_type="person")
    db.add_link("alice", "bob", context="knows")
    db.delete("alice")
    # Bob still has no incoming link from alice (cascade kicked in).
    assert db.get_links("bob", direction="in") == []


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


def test_search_finds_content_word(db):
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="Alice is a coworker at Acme.")
    hits = db.search("coworker")
    assert len(hits) == 1
    assert hits[0].page.slug == "alice"
    assert "<<coworker>>" in hits[0].snippet


def test_search_finds_title_word(db):
    db.save(slug="alice", title="Alice the Magnificent", page_type="person")
    hits = db.search("Magnificent")
    assert len(hits) == 1


def test_search_filters_by_type(db):
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="engineer")
    db.save(slug="proj", title="Project", page_type="project",
            compiled_truth="engineer")
    hits = db.search("engineer", types=["person"])
    assert all(h.page.type == "person" for h in hits)


def test_search_filters_by_tag(db):
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="engineer", tags=["team-a"])
    db.save(slug="bob", title="Bob", page_type="person",
            compiled_truth="engineer", tags=["team-b"])
    hits = db.search("engineer", tags=["team-a"])
    assert {h.page.slug for h in hits} == {"alice"}


def test_search_empty_query_returns_empty(db):
    db.save(slug="alice", title="Alice", page_type="person")
    assert db.search("") == []
    assert db.search("   ") == []


def test_search_invalid_types_returns_empty(db):
    db.save(slug="alice", title="Alice", page_type="person")
    assert db.search("engineer", types=["bogus"]) == []


def test_search_no_match_returns_empty(db):
    db.save(slug="alice", title="Alice", page_type="person")
    assert db.search("nonexistent-xyz") == []


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_add_tags_creates_new_tags(db):
    db.save(slug="alice", title="Alice", page_type="person")
    added = db.add_tags("alice", ["x", "y", "x"])
    assert added == 2  # x, y (dup skipped)
    p = db.get("alice")
    assert sorted(p.tags) == ["x", "y"]


def test_add_tags_to_missing_page_raises(db):
    with pytest.raises(KeyError):
        db.add_tags("ghost", ["x"])


def test_pages_with_tag(db):
    db.save(slug="alice", title="Alice", page_type="person", tags=["a"])
    db.save(slug="bob", title="Bob", page_type="person", tags=["a", "b"])
    pages = db.pages_with_tag("a")
    assert {p.slug for p in pages} == {"alice", "bob"}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def test_add_timeline_appends_entry(db):
    db.save(slug="alice", title="Alice", page_type="person")
    db.add_timeline("alice", "2026-04-09", "smoke", "did thing")
    entries = db.timeline_for("alice")
    assert len(entries) == 1
    assert entries[0]["summary"] == "did thing"


def test_add_timeline_to_missing_page_raises(db):
    with pytest.raises(KeyError):
        db.add_timeline("ghost", "2026-01-01", "x", "y")


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def test_add_link_creates_directed_edge(db):
    db.save(slug="alice", title="Alice", page_type="person")
    db.save(slug="bob", title="Bob", page_type="person")
    assert db.add_link("alice", "bob", context="knows") is True


def test_add_link_dedup_returns_false(db):
    db.save(slug="alice", title="Alice", page_type="person")
    db.save(slug="bob", title="Bob", page_type="person")
    db.add_link("alice", "bob")
    assert db.add_link("alice", "bob") is False  # already exists


def test_add_link_rejects_self_loop(db):
    db.save(slug="alice", title="Alice", page_type="person")
    with pytest.raises(ValueError):
        db.add_link("alice", "alice")


def test_add_link_to_missing_target_raises(db):
    db.save(slug="alice", title="Alice", page_type="person")
    with pytest.raises(KeyError):
        db.add_link("alice", "ghost")


def test_get_links_outgoing(db):
    db.save(slug="alice", title="Alice", page_type="person")
    db.save(slug="bob", title="Bob", page_type="person")
    db.save(slug="carol", title="Carol", page_type="person")
    db.add_link("alice", "bob", context="a→b")
    db.add_link("alice", "carol", context="a→c")
    links = db.get_links("alice", direction="out")
    assert ("bob", "a→b") in links
    assert ("carol", "a→c") in links


def test_get_links_incoming(db):
    db.save(slug="alice", title="Alice", page_type="person")
    db.save(slug="bob", title="Bob", page_type="person")
    db.add_link("alice", "bob")
    links = db.get_links("bob", direction="in")
    assert links == [("alice", "")]


def test_get_links_both(db):
    db.save(slug="a", title="A", page_type="person")
    db.save(slug="b", title="B", page_type="person")
    db.save(slug="c", title="C", page_type="person")
    db.add_link("a", "b")
    db.add_link("c", "b")
    links = sorted(db.get_links("b", direction="both"))
    assert ("a", "") in links
    assert ("c", "") in links


def test_get_links_invalid_direction(db):
    db.save(slug="a", title="A", page_type="person")
    with pytest.raises(ValueError):
        db.get_links("a", direction="sideways")


# ---------------------------------------------------------------------------
# list_by_type / list_all
# ---------------------------------------------------------------------------


def test_list_by_type(db):
    for i in range(3):
        db.save(slug=f"p{i}", title=f"P{i}", page_type="person")
    db.save(slug="q", title="Q", page_type="project")
    persons = db.list_by_type("person")
    assert len(persons) == 3


def test_list_by_type_rejects_bad_type(db):
    with pytest.raises(ValueError):
        db.list_by_type("bogus")


def test_list_all_respects_limit(db):
    for i in range(5):
        db.save(slug=f"p{i}", title=f"P{i}", page_type="person")
    assert len(db.list_all(limit=2)) == 2


# ---------------------------------------------------------------------------
# audit log
# ---------------------------------------------------------------------------


def test_audit_log_records_writes(db):
    db.save(slug="alice", title="Alice", page_type="person")
    log = db.audit_log("alice")
    assert any(e["operation"] == "insert" for e in log)


def test_audit_log_filters_by_operation(db):
    db.save(slug="alice", title="Alice", page_type="person")
    db.save(slug="alice", title="Alice2", page_type="person")
    log = db.audit_log("alice", operation="update")
    assert all(e["operation"] == "update" for e in log)
