"""v1.2.0 — Tests for Dream consolidation."""
from __future__ import annotations

import json

import pytest

from madcop.brain.consolidate import (
    ConsolidationReport,
    Dream,
    maintain,
)
from madcop.brain.store import PageDB


@pytest.fixture
def db(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Basic Dream runs
# ---------------------------------------------------------------------------


def test_empty_db_run(db):
    rep = Dream(db).run()
    assert rep.duplicates_collapsed == 0
    assert rep.orphan_links_removed == 0
    assert rep.stale_pages_marked == []
    assert rep.review_queue_size == 0
    assert rep.started_at != ""
    assert rep.finished_at != ""
    assert rep.duration_s >= 0


def test_dream_audit_log_records_pass(db):
    rep = Dream(db).run()
    log = db.audit_log(operation="consolidate")
    assert len(log) == 1
    assert log[0]["source"] == "dream"
    detail = json.loads(log[0]["detail"])
    assert detail["duplicates_collapsed"] == rep.duplicates_collapsed


def test_dream_uses_custom_stale_days(db):
    rep = Dream(db, stale_after_days=7).run()
    assert isinstance(rep, ConsolidationReport)


def test_dream_rejects_negative_stale_days(db):
    with pytest.raises(ValueError):
        Dream(db, stale_after_days=-1)


def test_maintain_convenience_calls_dream(db):
    rep = maintain(db)
    assert isinstance(rep, ConsolidationReport)


# ---------------------------------------------------------------------------
# Duplicate collapse
# ---------------------------------------------------------------------------


def test_collapses_byte_identical_pages(db):
    db.save(slug="alice", title="Alice", page_type="person", compiled_truth="hi")
    db.save(slug="alice-copy", title="Alice", page_type="person", compiled_truth="hi")
    rep = Dream(db).run()
    assert rep.duplicates_collapsed == 1
    remaining = {p.slug for p in db.list_all()}
    assert remaining == {"alice", "alice-copy"} or len(remaining) == 1
    # The older one (alice) is the survivor; alice-copy is gone.
    assert db.get("alice-copy") is None
    assert db.get("alice") is not None


def test_collapse_merges_tags(db):
    db.save(slug="alice", title="Alice", page_type="person",
            compiled_truth="x", tags=["shared", "alice-only"])
    db.save(slug="alice-copy", title="Alice", page_type="person",
            compiled_truth="x", tags=["shared", "copy-only"])
    Dream(db).run()
    p = db.get("alice")
    assert "shared" in p.tags
    assert "alice-only" in p.tags
    assert "copy-only" in p.tags


def test_collapse_merges_timeline(db):
    db.save(slug="alice", title="Alice", page_type="person", compiled_truth="x")
    db.save(slug="alice-copy", title="Alice", page_type="person", compiled_truth="x")
    db.add_timeline("alice", "2026-01-01", "x", "a")
    db.add_timeline("alice-copy", "2026-02-02", "x", "b")
    Dream(db).run()
    entries = db.timeline_for("alice")
    summaries = {e["summary"] for e in entries}
    assert summaries == {"a", "b"}


def test_collapse_repoints_links(db):
    db.save(slug="alice", title="Alice", page_type="person", compiled_truth="x")
    db.save(slug="alice-copy", title="Alice", page_type="person", compiled_truth="x")
    db.save(slug="bob", title="Bob", page_type="person")
    db.add_link("alice", "bob", context="a→b")
    db.add_link("alice-copy", "bob", context="copy→b")
    Dream(db).run()
    # The UNIQUE (from_page_id, to_page_id) constraint collapses
    # alice-copy→bob into alice→bob (same source after collapse).
    # We expect exactly 1 row pointing to bob, from alice.
    in_links = db.get_links("bob", direction="in")
    assert len(in_links) == 1
    assert in_links[0][0] == "alice"


def test_dry_run_does_not_modify(db):
    db.save(slug="alice", title="Alice", page_type="person", compiled_truth="x")
    db.save(slug="alice-copy", title="Alice", page_type="person", compiled_truth="x")
    rep = Dream(db).run(dry_run=True)
    assert rep.duplicates_collapsed == 1
    # Both still exist
    assert db.get("alice") is not None
    assert db.get("alice-copy") is not None


def test_three_way_collapse(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db.save(slug="a2", title="A", page_type="person", compiled_truth="x")
    db.save(slug="a3", title="A", page_type="person", compiled_truth="x")
    rep = Dream(db).run()
    assert rep.duplicates_collapsed == 2
    remaining = {p.slug for p in db.list_all()}
    assert remaining == {"a"}


# ---------------------------------------------------------------------------
# Orphan link pruning
# ---------------------------------------------------------------------------


def test_prune_orphan_links_dry_run_does_not_remove(db):
    # We can't easily create orphan links (ON DELETE CASCADE handles
    # them). Insert a row directly.
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db.save(slug="b", title="B", page_type="person", compiled_truth="x")
    db.add_link("a", "b")
    # Now force orphan: delete the FK by raw SQL.
    db._conn.execute("DELETE FROM pages WHERE slug='b'")
    db._conn.commit()
    rep = Dream(db).run(dry_run=True)
    assert rep.orphan_links_removed == 1
    # In dry-run the link is NOT removed.
    assert db._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 1


def test_prune_orphan_links_real_run_removes(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db.save(slug="b", title="B", page_type="person", compiled_truth="x")
    db.add_link("a", "b")
    db._conn.execute("DELETE FROM pages WHERE slug='b'")
    db._conn.commit()
    rep = Dream(db).run()
    assert rep.orphan_links_removed == 1
    assert db._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Stale marking
# ---------------------------------------------------------------------------


def test_stale_marking_reports_old_pages(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db._conn.execute("UPDATE pages SET last_accessed_at='2000-01-01T00:00:00Z' WHERE slug='a'")
    db._conn.commit()
    rep = Dream(db, stale_after_days=30).run()
    assert db.get("a") is not None  # not deleted
    assert rep.stale_pages_marked  # non-empty


def test_stale_marking_dry_run_does_not_update(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db._conn.execute("UPDATE pages SET last_accessed_at='2000-01-01T00:00:00Z' WHERE slug='a'")
    db._conn.commit()
    Dream(db, stale_after_days=30).run(dry_run=True)
    # stale_after_days is still NULL because dry-run
    row = db._conn.execute("SELECT stale_after_days FROM pages WHERE slug='a'").fetchone()
    assert row["stale_after_days"] is None


def test_stale_marking_real_run_sets_zero(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db._conn.execute("UPDATE pages SET last_accessed_at='2000-01-01T00:00:00Z' WHERE slug='a'")
    db._conn.commit()
    Dream(db, stale_after_days=30).run()
    row = db._conn.execute("SELECT stale_after_days FROM pages WHERE slug='a'").fetchone()
    assert row["stale_after_days"] == 0


def test_fresh_page_not_marked_stale(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    # The save was just now; updated_at is fresh.
    rep = Dream(db, stale_after_days=365).run()
    assert rep.stale_pages_marked == []


def test_updated_at_fallback_for_never_accessed(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    # Force updated_at to 2000
    db._conn.execute("UPDATE pages SET updated_at='2000-01-01T00:00:00Z' WHERE slug='a'")
    db._conn.commit()
    rep = Dream(db, stale_after_days=30).run()
    assert rep.stale_pages_marked  # non-empty list


# ---------------------------------------------------------------------------
# Granular flags
# ---------------------------------------------------------------------------


def test_disable_collapse_duplicates(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db.save(slug="a2", title="A", page_type="person", compiled_truth="x")
    rep = Dream(db).run(collapse_duplicates=False)
    assert rep.duplicates_collapsed == 0
    assert db.get("a2") is not None


def test_disable_prune_orphans(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db.save(slug="b", title="B", page_type="person", compiled_truth="x")
    db.add_link("a", "b")
    db._conn.execute("DELETE FROM pages WHERE slug='b'")
    db._conn.commit()
    rep = Dream(db).run(prune_orphans=False)
    assert rep.orphan_links_removed == 0
    assert db._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 1


def test_disable_mark_stale(db):
    db.save(slug="a", title="A", page_type="person", compiled_truth="x")
    db._conn.execute("UPDATE pages SET last_accessed_at='2000-01-01T00:00:00Z' WHERE slug='a'")
    db._conn.commit()
    rep = Dream(db, stale_after_days=30).run(mark_stale=False)
    assert rep.stale_pages_marked == []


# ---------------------------------------------------------------------------
# Report shape
# ---------------------------------------------------------------------------


def test_report_to_dict_round_trip():
    r = ConsolidationReport(
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        duration_s=1.0,
        duplicates_collapsed=2,
        orphan_links_removed=0,
        stale_pages_marked=[1, 2],
        review_queue_size=0,
        notes=["x"],
    )
    d = r.to_dict()
    assert d["duplicates_collapsed"] == 2
    assert d["stale_pages_marked"] == [1, 2]
    assert d["notes"] == ["x"]
