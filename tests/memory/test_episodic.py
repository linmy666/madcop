"""Tests for EpisodicMemory (L2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from madcop.memory.store import MemoryStore
from madcop.memory.episodic import EpisodicMemory, Episode, EpisodeOutcome


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(path=tmp_path / "episodic.db")
    yield EpisodicMemory(s)
    s.close()


def test_record_creates_episode_with_id(memory):
    ep = memory.record(
        goal="Diagnose OMS cancel spike",
        outcome=EpisodeOutcome.SUCCESS,
        steps_taken=5,
        total_cost_usd=0.034,
        findings=[{"rule": "CUSUM", "score": 0.92}],
        final_report="# Summary\n3 findings found.",
        tags=("oms", "supply_chain"),
    )
    assert ep.id
    assert ep.goal == "Diagnose OMS cancel spike"
    assert ep.outcome == EpisodeOutcome.SUCCESS
    assert ep.steps_taken == 5
    assert ep.total_cost_usd == 0.034
    assert len(ep.findings) == 1
    assert ep.final_report is not None


def test_get_retrieves_recorded_episode(memory):
    ep = memory.record(goal="x", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    fetched = memory.get(ep.id)
    assert fetched is not None
    assert fetched.id == ep.id
    assert fetched.goal == "x"


def test_get_nonexistent_returns_none(memory):
    assert memory.get("does-not-exist") is None


def test_list_recent_returns_newest_first(memory):
    ids = []
    for i in range(5):
        ep = memory.record(goal=f"task {i}", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
        ids.append(ep.id)
        import time
        time.sleep(0.001)  # ensure distinct created_at
    recent = memory.list_recent(limit=3)
    assert len(recent) == 3
    # Newest first
    assert recent[0].id == ids[-1]
    assert recent[2].id == ids[-3]


def test_list_recent_respects_limit(memory):
    for i in range(10):
        memory.record(goal=f"t {i}", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    assert len(memory.list_recent(limit=3)) == 3
    assert len(memory.list_recent(limit=20)) == 10


def test_find_similar_matches_substring(memory):
    memory.record(goal="Diagnose OMS cancel spike yesterday", outcome=EpisodeOutcome.SUCCESS, steps_taken=3, total_cost_usd=0.05)
    memory.record(goal="Investigate WMS temperature breach", outcome=EpisodeOutcome.PARTIAL, steps_taken=4, total_cost_usd=0.07)
    memory.record(goal="Plan next quarter's safety stock", outcome=EpisodeOutcome.SUCCESS, steps_taken=2, total_cost_usd=0.02)

    results = memory.find_similar("OMS cancel")
    # FTS5 finds at least the OMS episode; possibly more
    assert any("OMS" in r.goal for r in results)


def test_count_reflects_records(memory):
    assert memory.count() == 0
    memory.record(goal="a", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    memory.record(goal="b", outcome=EpisodeOutcome.FAILED, steps_taken=1, total_cost_usd=0.0)
    assert memory.count() == 2


def test_episode_to_record_from_record_roundtrip(memory):
    """The serialise/deserialise cycle preserves all fields."""
    ep = memory.record(
        goal="roundtrip test",
        outcome=EpisodeOutcome.PARTIAL,
        steps_taken=7,
        total_cost_usd=0.123,
        findings=[{"rule": "X", "score": 0.5}, {"rule": "Y", "score": 0.7}],
        final_report="report text",
        tags=("t1", "t2"),
    )
    fetched = memory.get(ep.id)
    assert fetched is not None
    assert fetched.goal == "roundtrip test"
    assert fetched.outcome == EpisodeOutcome.PARTIAL
    assert fetched.steps_taken == 7
    assert fetched.total_cost_usd == 0.123
    assert fetched.findings == [{"rule": "X", "score": 0.5}, {"rule": "Y", "score": 0.7}]
    assert fetched.final_report == "report text"
    assert fetched.tags == ("t1", "t2")


def test_episode_outcome_enum_values():
    assert EpisodeOutcome.SUCCESS.value == "success"
    assert EpisodeOutcome.PARTIAL.value == "partial"
    assert EpisodeOutcome.FAILED.value == "failed"
    assert EpisodeOutcome.UNKNOWN.value == "unknown"
