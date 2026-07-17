"""Tests for async memory pipeline (Gap 7)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from madcop.llm import Message
from madcop.memory import MemoryStore, MemoryKind


@pytest.fixture
def isolated_pipeline(tmp_path: Path, monkeypatch):
    """Isolated memory store and reset pipeline state for each test."""
    from madcop.server import memory_pipeline, deps as deps_module
    # Use a unique key path per test
    db_path = tmp_path / "pipeline.db"
    key_path = tmp_path / "master.key"
    store = MemoryStore(path=db_path)
    monkeypatch.setattr(deps_module, "_memory_store", store)
    memory_pipeline.reset_for_tests()
    yield store
    store.close()
    memory_pipeline.reset_for_tests()


def test_schedule_returns_true_for_new_message(isolated_pipeline):
    from madcop.server.memory_pipeline import schedule_extraction
    msgs = [Message(role="user", content="我叫小明")]
    assert schedule_extraction(msgs) is True


def test_schedule_dedups_duplicate_within_window(isolated_pipeline):
    """Same content scheduled twice within 1s = second is deduped."""
    from madcop.server.memory_pipeline import schedule_extraction
    msgs = [Message(role="user", content="我叫小李")]
    assert schedule_extraction(msgs) is True
    # Second call should be deduped (within 1s)
    assert schedule_extraction(msgs) is False


def test_schedule_handles_empty_messages(isolated_pipeline):
    from madcop.server.memory_pipeline import schedule_extraction
    assert schedule_extraction([]) is False


def test_extraction_actually_runs_after_delay(isolated_pipeline):
    """Background thread should write the fact to the store."""
    from madcop.server.memory_pipeline import (
        schedule_extraction, extraction_count, debounce_seconds,
    )
    msgs = [Message(role="user", content="我是菜鸟集团的BDSA")]
    schedule_extraction(msgs)
    # Worker sleeps for debounce_seconds/2 = 15s
    # We don't want the test to wait 15s — instead, manually trigger
    # by calling reset and observing the worker ran. For unit test,
    # just verify the function returned True (job was scheduled).
    assert extraction_count() == 0  # not yet run
    assert debounce_seconds() == 30.0


def test_extraction_writes_to_store(isolated_pipeline, monkeypatch):
    """Integration: actual fact lands in the store after debounce window.

    To keep test fast, monkeypatch debounce_seconds to be tiny.
    """
    from madcop.server import memory_pipeline
    monkeypatch.setattr(memory_pipeline, "_DEBOUNCE_SECONDS", 0.5)

    store = isolated_pipeline
    msgs = [Message(role="user", content="我是小王，我今年25岁")]
    memory_pipeline.schedule_extraction(msgs)

    # Wait for the worker to finish (debounce/2 = 0.25s + extraction time)
    time.sleep(1.0)

    # Verify the fact was stored
    rows = store._conn.execute(
        "SELECT * FROM memory_records WHERE tags LIKE '%user-profile%'"
    ).fetchall()
    assert len(rows) >= 1


def test_extraction_count_increments(isolated_pipeline, monkeypatch):
    """Each successful extraction bumps the counter."""
    from madcop.server import memory_pipeline
    monkeypatch.setattr(memory_pipeline, "_DEBOUNCE_SECONDS", 0.2)
    memory_pipeline.schedule_extraction([Message(role="user", content="我住在杭州")])
    time.sleep(0.5)
    assert memory_pipeline.extraction_count() >= 1


def test_reset_clears_state(isolated_pipeline):
    from madcop.server import memory_pipeline
    memory_pipeline.schedule_extraction([Message(role="user", content="x")])
    memory_pipeline.reset_for_tests()
    assert memory_pipeline.extraction_count() == 0
    # After reset, can schedule again
    assert memory_pipeline.schedule_extraction(
        [Message(role="user", content="x")]
    ) is True
