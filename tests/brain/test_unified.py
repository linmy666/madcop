"""Tests for unified Brain + Memory façade (Gap 10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from madcop.brain import UnifiedKnowledge, UnifiedConfig, UnifiedEntry


@pytest.fixture
def unified(tmp_path: Path, monkeypatch) -> UnifiedKnowledge:
    """UnifiedKnowledge with isolated paths so tests don't pollute real data."""
    monkeypatch.setattr("pathlib.Path.expanduser", lambda self: tmp_path / self.name)
    # Patch default DB paths to tmp
    cfg = UnifiedConfig(
        memory_db=tmp_path / "memory.db",
        memory_key=tmp_path / "master.key",
        brain_db=tmp_path / "brain.db",
    )
    u = UnifiedKnowledge(cfg)
    yield u
    u.close()


# --------------------------------------------------------------------------- #
# Lazy loading
# --------------------------------------------------------------------------- #

def test_unified_loads_memory_store(unified):
    ms = unified.memory()
    assert ms is not None
    assert ms.path == unified.config.memory_db


def test_unified_loads_brain_store(unified):
    bs = unified.brain()
    assert bs is not None
    assert bs.path == unified.config.brain_db


def test_unified_close_clears_caches(unified):
    unified.memory()
    unified.brain()
    unified.close()
    # After close, accessing again should re-open
    ms2 = unified.memory()
    assert ms2 is not None


# --------------------------------------------------------------------------- #
# list_all
# --------------------------------------------------------------------------- #

def test_list_all_empty(unified):
    assert unified.list_all() == []


def test_list_all_includes_memory_records(unified):
    import madcop.memory as mem
    ms = unified.memory()
    ms.insert(
        kind=mem.MemoryKind.SEMANTIC,
        title="test fact",
        content="user lives in Shanghai",
        tags=("user-profile",),
    )
    entries = unified.list_all(limit=10)
    assert len(entries) >= 1
    assert any(e.source == "memory" for e in entries)
    assert any("Shanghai" in e.content for e in entries)


def test_list_all_respects_limit(unified):
    ms = unified.memory()
    import madcop.memory as mem
    for i in range(20):
        ms.insert(
            kind=mem.MemoryKind.SEMANTIC,
            title=f"fact {i}",
            content=f"content number {i}",
            tags=(),
        )
    entries = unified.list_all(limit=5)
    assert len(entries) == 5


# --------------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------------- #

def test_search_empty(unified):
    assert unified.search("anything") == []


def test_search_finds_memory_record(unified):
    import madcop.memory as mem
    ms = unified.memory()
    ms.insert(
        kind=mem.MemoryKind.SEMANTIC,
        title="user name",
        content="User name is Lin Ruihan",
        tags=("user-profile",),
    )
    results = unified.search("Lin Ruihan", limit=10)
    assert any("Lin Ruihan" in r.content for r in results)
    assert any(r.source == "memory" for r in results)


def test_search_returns_unified_entries(unified):
    """Each result is a UnifiedEntry dataclass with all expected fields."""
    import madcop.memory as mem
    unified.memory().insert(
        kind=mem.MemoryKind.SEMANTIC,
        title="x", content="y", tags=()
    )
    results = unified.search("y", limit=5)
    assert all(isinstance(r, UnifiedEntry) for r in results)
    for r in results:
        assert hasattr(r, "id")
        assert hasattr(r, "source")
        assert hasattr(r, "content")
        assert r.source in ("memory", "brain")
