"""v0.8.0 — Tests for the crash-recovery WAL (write-ahead log)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from madcop.strategy import (
    FinishRecord,
    Replay,
    StartRecord,
    WAL,
    WALStepRecord,
)
from madcop.strategy.scratchpad import Scratchpad


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


def test_wal_creates_file_on_init(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    assert wal.path.exists()
    assert wal.replay().started is False


def test_wal_for_scratchpad_helper(tmp_path: Path):
    sp_path = tmp_path / "run_abc.json"
    wal = WAL.for_scratchpad(sp_path)
    assert wal.path == tmp_path / "run_abc.json.wal.jsonl"


# ---------------------------------------------------------------------------
# Append + replay
# ---------------------------------------------------------------------------


def test_wal_append_start_then_replay(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start(run_id="r1", goal="find bug", plan=[{"name": "s1"}, {"name": "s2"}])
    r = wal.replay()
    assert r.started
    assert r.run_id == "r1"
    assert r.goal == "find bug"
    assert r.plan == ({"name": "s1"}, {"name": "s2"})
    assert r.completed_steps == frozenset()
    assert not r.is_finished


def test_wal_append_step_appears_in_replay(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "g", [{"name": "a"}, {"name": "b"}])
    wal.append_step("a", "ok")
    wal.append_step("b", "failed", error="boom")
    r = wal.replay()
    assert r.completed_steps == frozenset({"a", "b"})
    assert r.step_count == 2
    by_name = {s.name: s for s in r.step_records}
    assert by_name["a"].status == "ok"
    assert by_name["a"].error is None
    assert by_name["b"].status == "failed"
    assert by_name["b"].error == "boom"


def test_wal_append_finish_marks_run_finished(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "g", [])
    wal.append_step("s1", "ok")
    wal.append_finish("all good")
    r = wal.replay()
    assert r.is_finished
    assert r.final_report == "all good"


def test_wal_later_step_record_wins_on_dup(tmp_path: Path):
    """If a step is recorded twice (e.g. retry), the LATER status wins."""
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "g", [])
    wal.append_step("s", "failed", error="first try")
    wal.append_step("s", "ok")
    r = wal.replay()
    assert r.completed_steps == frozenset({"s"})
    [rec] = r.step_records
    assert rec.status == "ok"
    assert rec.error is None


# ---------------------------------------------------------------------------
# next_pending — the actual "resume from step N" API
# ---------------------------------------------------------------------------


def test_next_pending_returns_steps_not_in_wal(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "g", [{"name": "a"}, {"name": "b"}, {"name": "c"}])
    wal.append_step("a", "ok")
    r = wal.replay()
    assert r.next_pending(["a", "b", "c"]) == ["b", "c"]


def test_next_pending_preserves_input_order(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "g", [])
    wal.append_step("c", "ok")
    r = wal.replay()
    # User asks about [a, b, c, d] in that order, but only c is done.
    assert r.next_pending(["a", "b", "c", "d"]) == ["a", "b", "d"]


def test_next_pending_with_empty_plan(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    r = wal.replay()
    assert r.next_pending([]) == []


# ---------------------------------------------------------------------------
# Crash resilience — torn line, missing file, empty file
# ---------------------------------------------------------------------------


def test_replay_tolerates_torn_last_line(tmp_path: Path):
    """A half-written line at the end (crash mid-write) is silently skipped."""
    path = tmp_path / "test.wal.jsonl"
    path.write_text(
        '{"event": "start", "run_id": "r", "goal": "g", "plan": [], "ts": 0}\n'
        '{"event": "step", "name": "a", "status": "ok", "ts": 0}\n'
        '{"event": "step", "name": "b", "status": "ok", "ts":'   # TORN
    )
    wal = WAL(path, _create=False)
    r = wal.replay()
    assert r.started
    assert r.completed_steps == frozenset({"a"})  # b not recorded
    assert r.step_count == 1


def test_replay_tolerates_blank_lines(tmp_path: Path):
    path = tmp_path / "test.wal.jsonl"
    path.write_text(
        '{"event": "start", "run_id": "r", "goal": "g", "plan": [], "ts": 0}\n'
        '\n'
        '{"event": "step", "name": "a", "status": "ok", "ts": 0}\n'
        '\n'
    )
    wal = WAL(path, _create=False)
    r = wal.replay()
    assert r.completed_steps == frozenset({"a"})


def test_replay_of_empty_file(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    r = wal.replay()
    assert not r.started
    assert r.completed_steps == frozenset()
    assert not r.is_finished


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_wal_appends_from_multiple_threads(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "g", [])

    def worker(start: int, count: int):
        for i in range(start, start + count):
            wal.append_step(f"s{i}", "ok")

    threads = [threading.Thread(target=worker, args=(i * 10, 10)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    r = wal.replay()
    assert r.step_count == 50
    # Every step name should be present
    expected = {f"s{i}" for i in range(50)}
    assert r.completed_steps == expected


# ---------------------------------------------------------------------------
# Truncate — "start a fresh run"
# ---------------------------------------------------------------------------


def test_truncate_removes_wal_file(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "g", [])
    assert wal.path.exists()
    wal.truncate()
    assert not wal.path.exists()
    r = wal.replay()
    assert not r.started


# ---------------------------------------------------------------------------
# Replay metadata — for cold reads from the scratchpad alone
# ---------------------------------------------------------------------------


def test_to_metadata_makes_scratchpad_self_describing(tmp_path: Path):
    wal = WAL(tmp_path / "test.wal.jsonl")
    wal.append_start("r1", "diagnose", [{"name": "a"}, {"name": "b"}])
    wal.append_step("a", "ok")
    sp = Scratchpad.create(goal="diagnose", path=tmp_path / "run.json")
    sp.update_metadata(**wal.replay().to_metadata())
    sp.save()
    # Cold read: only the scratchpad, but it tells us the WAL state.
    sp2 = Scratchpad.load(tmp_path / "run.json")
    meta = sp2.state.metadata
    assert meta["wal_started"] is True
    assert meta["wal_run_id"] == "r1"
    assert meta["wal_completed_steps"] == ["a"]
    assert meta["wal_step_count"] == 1
    assert meta["wal_finished"] is False


# ---------------------------------------------------------------------------
# Record serialisation
# ---------------------------------------------------------------------------


def test_start_record_to_json_is_valid_json():
    rec = StartRecord(run_id="r", goal="g", plan=({"a": 1},), ts=1.0)
    parsed = json.loads(rec.to_json())
    assert parsed["event"] == "start"
    assert parsed["run_id"] == "r"
    assert parsed["plan"] == [{"a": 1}]


def test_step_record_to_json_omits_error_when_none():
    rec = WALStepRecord(name="x", status="ok", ts=1.0)
    parsed = json.loads(rec.to_json())
    assert "error" not in parsed


def test_finish_record_to_json():
    rec = FinishRecord(final_report="done", ts=1.0)
    parsed = json.loads(rec.to_json())
    assert parsed["event"] == "finish"
    assert parsed["final_report"] == "done"
