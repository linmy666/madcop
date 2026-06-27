"""Tests for the unified MemoryStore (SQLite + FTS5 backend)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from madcop.memory.store import MemoryStore, MemoryRecord, MemoryKind


@pytest.fixture
def store(tmp_path: Path):
    """Fresh in-file SQLite store for each test."""
    db_path = tmp_path / "test_memory.db"
    s = MemoryStore(path=db_path)
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


def test_store_creates_db_file(tmp_path: Path):
    """The constructor creates the file (and parent dirs)."""
    db_path = tmp_path / "subdir" / "memory.db"
    s = MemoryStore(path=db_path)
    try:
        assert db_path.exists()
        assert db_path.parent.is_dir()
    finally:
        s.close()


def test_insert_returns_record_with_id(store: MemoryStore):
    rec = store.insert(MemoryKind.EPISODIC, title="test goal", content="some content")
    assert rec.id
    assert rec.kind == MemoryKind.EPISODIC
    assert rec.title == "test goal"
    assert rec.content == "some content"
    assert rec.created_at > 0
    assert rec.updated_at > 0


def test_get_returns_nonexistent_as_none(store: MemoryStore):
    assert store.get("does-not-exist") is None


def test_get_roundtrips_record(store: MemoryStore):
    """Insert then get returns the same fields."""
    rec = store.insert(
        MemoryKind.SEMANTIC, title="fact 1", content="CUSUM threshold is 4.78",
        tags=("cusum", "stats"),
    )
    fetched = store.get(rec.id)
    assert fetched is not None
    assert fetched.id == rec.id
    assert fetched.title == "fact 1"
    assert fetched.content == "CUSUM threshold is 4.78"
    assert fetched.tags == ("cusum", "stats")


def test_delete_removes_record(store: MemoryStore):
    rec = store.insert(MemoryKind.EPISODIC, "t", "c")
    assert store.delete(rec.id) is True
    assert store.get(rec.id) is None


def test_delete_nonexistent_returns_false(store: MemoryStore):
    assert store.delete("does-not-exist") is False


# ---------------------------------------------------------------------------
# list_by_kind + count
# ---------------------------------------------------------------------------


def test_list_by_kind_filters_correctly(store: MemoryStore):
    for i in range(3):
        store.insert(MemoryKind.EPISODIC, f"ep {i}", f"c {i}")
    for i in range(2):
        store.insert(MemoryKind.SEMANTIC, f"fact {i}", f"f {i}")
    eps = store.list_by_kind(MemoryKind.EPISODIC)
    facts = store.list_by_kind(MemoryKind.SEMANTIC)
    assert len(eps) == 3
    assert len(facts) == 2


def test_list_by_kind_respects_limit_and_offset(store: MemoryStore):
    for i in range(10):
        store.insert(MemoryKind.EPISODIC, f"ep {i}", f"c {i}")
    # Newest first (created_at DESC) — insertion order reversed
    page1 = store.list_by_kind(MemoryKind.EPISODIC, limit=3, offset=0)
    page2 = store.list_by_kind(MemoryKind.EPISODIC, limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 3
    # No overlap
    assert set(r.id for r in page1).isdisjoint(set(r.id for r in page2))


def test_count_by_kind(store: MemoryStore):
    assert store.count_by_kind(MemoryKind.EPISODIC) == 0
    store.insert(MemoryKind.EPISODIC, "a", "b")
    store.insert(MemoryKind.EPISODIC, "c", "d")
    store.insert(MemoryKind.SEMANTIC, "e", "f")
    assert store.count_by_kind(MemoryKind.EPISODIC) == 2
    assert store.count_by_kind(MemoryKind.SEMANTIC) == 1
    assert store.count_by_kind(MemoryKind.REFLECTIVE) == 0


def test_total_count(store: MemoryStore):
    assert store.total_count() == 0
    store.insert(MemoryKind.EPISODIC, "a", "b")
    store.insert(MemoryKind.SEMANTIC, "c", "d")
    store.insert(MemoryKind.REFLECTIVE, "e", "f")
    assert store.total_count() == 3


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


def test_fts_search_finds_by_content(store: MemoryStore):
    store.insert(MemoryKind.SEMANTIC, "oms", "Order cancel spike detected")
    store.insert(MemoryKind.SEMANTIC, "wms", "Temperature breach in frozen zone")
    results = store.search_fts("cancel")
    assert len(results) == 1
    assert "cancel" in results[0].content.lower()


def test_fts_search_finds_by_title(store: MemoryStore):
    store.insert(MemoryKind.EPISODIC, "OMS spike diagnosis", "ran for 30s")
    store.insert(MemoryKind.EPISODIC, "WMS cold chain check", "ran for 45s")
    results = store.search_fts("cold")
    assert any("WMS" in r.title for r in results)


def test_fts_search_filters_by_kind(store: MemoryStore):
    store.insert(MemoryKind.EPISODIC, "shared word episode", "content")
    store.insert(MemoryKind.SEMANTIC, "shared word fact", "content")
    results = store.search_fts("shared", kinds=[MemoryKind.SEMANTIC])
    assert len(results) == 1
    assert results[0].kind == MemoryKind.SEMANTIC


def test_fts_search_respects_limit(store: MemoryStore):
    for i in range(10):
        store.insert(MemoryKind.SEMANTIC, f"fact {i}", "common keyword here")
    results = store.search_fts("common", limit=3)
    assert len(results) == 3


def test_fts_search_returns_empty_for_no_match(store: MemoryStore):
    store.insert(MemoryKind.SEMANTIC, "x", "alpha")
    results = store.search_fts("zzzzz_nonexistent")
    assert results == []


# ---------------------------------------------------------------------------
# Rotation (cap enforcement)
# ---------------------------------------------------------------------------


def test_rotate_keeps_n_most_recent(store: MemoryStore):
    """Insert 5, rotate keep=2, only 2 newest remain."""
    ids = []
    for i in range(5):
        rec = store.insert(MemoryKind.EPISODIC, f"ep {i}", f"c {i}")
        ids.append(rec.id)
        # Force different created_at (so the newest ordering is clear)
        import time
        time.sleep(0.001)
    deleted = store.rotate(MemoryKind.EPISODIC, keep_recent=2)
    assert deleted == 3
    remaining = store.list_by_kind(MemoryKind.EPISODIC)
    assert len(remaining) == 2


def test_rotate_noop_when_under_limit(store: MemoryStore):
    for i in range(3):
        store.insert(MemoryKind.EPISODIC, f"ep {i}", "c")
    deleted = store.rotate(MemoryKind.EPISODIC, keep_recent=10)
    assert deleted == 0
    assert store.count_by_kind(MemoryKind.EPISODIC) == 3


# ---------------------------------------------------------------------------
# MemoryKind enum
# ---------------------------------------------------------------------------


def test_memory_kind_values():
    assert MemoryKind.EPISODIC.value == "episodic"
    assert MemoryKind.SEMANTIC.value == "semantic"
    assert MemoryKind.REFLECTIVE.value == "reflective"


# --------------------------------------------------------------------------- #
# Update method
# --------------------------------------------------------------------------- #


def test_update_content(store):
    """Updating content refreshes both the row and the FTS index."""
    rec = store.insert(
        kind=MemoryKind.SEMANTIC,
        title="old title",
        content="old content about cats",
        tags=("tag1",),
    )
    updated = store.update(rec.id, content="new content about dogs", title="new title")
    assert updated is not None
    assert updated.content == "new content about dogs"
    assert updated.title == "new title"
    # FTS should find the new content, not the old
    rows = store._conn.execute(
        "SELECT * FROM memory_fts WHERE memory_fts MATCH 'dogs'"
    ).fetchall()
    assert len(rows) == 1
    rows2 = store._conn.execute(
        "SELECT * FROM memory_fts WHERE memory_fts MATCH 'cats'"
    ).fetchall()
    assert len(rows2) == 0


def test_update_tags(store):
    rec = store.insert(
        kind=MemoryKind.SEMANTIC, title="x", content="y", tags=("a", "b"),
    )
    updated = store.update(rec.id, tags=("c", "d"))
    assert updated is not None
    assert updated.tags == ("c", "d")


def test_update_metadata_patch(store):
    rec = store.insert(
        kind=MemoryKind.SEMANTIC, title="x", content="y", tags=(),
    )
    updated = store.update(rec.id, metadata_patch={"superseded_by": "new-id", "confidence": 0.9})
    assert updated is not None
    import json
    meta = json.loads(updated.metadata)
    assert meta["superseded_by"] == "new-id"
    assert meta["confidence"] == 0.9


def test_update_nonexistent(store):
    result = store.update("nonexistent-id-xyz", content="x")
    assert result is None


def test_update_bumps_updated_at(store):
    rec = store.insert(
        kind=MemoryKind.SEMANTIC, title="x", content="y", tags=(),
    )
    original_updated = rec.updated_at
    import time as _t
    _t.sleep(0.01)
    updated = store.update(rec.id, content="y2")
    assert updated.updated_at > original_updated


# --------------------------------------------------------------------------- #
# Temporal validity (Gap 4)
# --------------------------------------------------------------------------- #


def test_update_metadata_valid_until(store):
    """Update with valid_until timestamp in metadata_patch."""
    rec = store.insert(
        kind=MemoryKind.SEMANTIC, title="x", content="y", tags=()
    )
    import time
    future = time.time() + 86400  # 1 day from now
    updated = store.update(rec.id, metadata_patch={"valid_until": future})
    assert updated is not None
    import json
    meta = json.loads(updated.metadata)
    assert abs(meta["valid_until"] - future) < 1
