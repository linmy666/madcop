"""Tests for the disk-backed scratchpad."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from madcop.strategy.scratchpad import (
    Scratchpad,
    ScratchpadState,
    StepRecord,
    MAX_SUMMARY_CHARS,
)


# ---------------------------------------------------------------------------
# Creation + load roundtrip
# ---------------------------------------------------------------------------


def test_create_scratchpad_writes_to_disk(tmp_path: Path):
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="diagnose OMS spike", path=path)
    assert path.exists()
    assert sp.run_id
    assert sp.state.goal == "diagnose OMS spike"
    assert sp.step_count == 0


def test_load_scratchpad_roundtrips(tmp_path: Path):
    """Save and reload preserves the state."""
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="g1", path=path, budget_usd=0.5)
    sp.append_step(StepRecord(
        step_index=0,
        step_name="plan",
        tier="T1",
        provider="nvidia_glm",
        model="glm-5",
        input_summary="goal: g1",
        output_summary="plan: 5 steps",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
        wallclock_ms=100,
    ))
    sp2 = Scratchpad.load(path)
    assert sp2.run_id == sp.run_id
    assert sp2.state.goal == "g1"
    assert sp2.step_count == 1
    assert sp2.state.budget_usd == 0.5


def test_load_nonexistent_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        Scratchpad.load(tmp_path / "missing.json")


# ---------------------------------------------------------------------------
# StepRecord + truncation
# ---------------------------------------------------------------------------


def test_long_summaries_get_truncated(tmp_path: Path):
    """Heavy fields are truncated to MAX_SUMMARY_CHARS on save."""
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="x", path=path)
    huge_input = "a" * 5000
    huge_output = "b" * 5000
    sp.append_step(StepRecord(
        step_index=0,
        step_name="plan",
        tier="T1",
        provider="nvidia_glm",
        model="glm-5",
        input_summary=huge_input,
        output_summary=huge_output,
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
        wallclock_ms=100,
    ))
    saved = sp.steps()[0]
    assert len(saved.input_summary) <= MAX_SUMMARY_CHARS
    assert len(saved.output_summary) <= MAX_SUMMARY_CHARS
    # Truncation marker should be present
    assert "..." in saved.input_summary


def test_step_records_retain_step_index_order(tmp_path: Path):
    """Steps are appended in the order they're added."""
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="x", path=path)
    for i in range(5):
        sp.append_step(StepRecord(
            step_index=i,
            step_name="execute",
            tier="T2",
            provider="nvidia_nim",
            model="m",
            input_summary=f"in {i}",
            output_summary=f"out {i}",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            wallclock_ms=1,
        ))
    steps = sp.steps()
    assert [s.step_index for s in steps] == [0, 1, 2, 3, 4]
    assert [s.input_summary for s in steps] == [f"in {i}" for i in range(5)]


# ---------------------------------------------------------------------------
# Plan + findings + final report
# ---------------------------------------------------------------------------


def test_set_plan_persists(tmp_path: Path):
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="x", path=path)
    sp.set_plan([{"step": 1, "action": "load events"}, {"step": 2, "action": "detect"}])
    sp2 = Scratchpad.load(path)
    assert sp2.state.plan == [
        {"step": 1, "action": "load events"},
        {"step": 2, "action": "detect"},
    ]


def test_add_finding_appends(tmp_path: Path):
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="x", path=path)
    sp.add_finding({"rule": "CUSUM", "score": 0.92})
    sp.add_finding({"rule": "OMS cancel", "score": 0.81})
    sp2 = Scratchpad.load(path)
    assert len(sp2.state.findings) == 2
    assert sp2.state.findings[0]["rule"] == "CUSUM"


def test_set_final_report(tmp_path: Path):
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="x", path=path)
    sp.set_final_report("# Final Report\nDiagnosis: ...")
    sp2 = Scratchpad.load(path)
    assert sp2.state.final_report is not None
    assert "Final Report" in sp2.state.final_report


# ---------------------------------------------------------------------------
# Atomic write — no partial files on disk after a save
# ---------------------------------------------------------------------------


def test_scratchpad_file_is_valid_json_after_save(tmp_path: Path):
    """The on-disk file is parseable JSON after every save."""
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="x", path=path)
    sp.append_step(StepRecord(
        step_index=0,
        step_name="plan",
        tier="T1",
        provider="p",
        model="m",
        input_summary="i",
        output_summary="o",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
        wallclock_ms=1,
    ))
    sp.set_plan([{"a": 1}])
    sp.add_finding({"b": 2})
    sp.set_final_report("r")
    # Read raw bytes and parse
    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["goal"] == "x"
    assert parsed["plan"] == [{"a": 1}]
    assert parsed["findings"] == [{"b": 2}]
    assert parsed["final_report"] == "r"


def test_scratchpad_no_leftover_temp_files(tmp_path: Path):
    """Atomic write uses a temp file that should be cleaned up."""
    path = tmp_path / "sp.json"
    Scratchpad.create(goal="x", path=path)
    # No files starting with .scratchpad-
    leftovers = list(tmp_path.glob(".scratchpad-*"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# Metadata + run_id
# ---------------------------------------------------------------------------


def test_run_id_is_unique_across_creates(tmp_path: Path):
    a = Scratchpad.create(goal="a", path=tmp_path / "a.json")
    b = Scratchpad.create(goal="b", path=tmp_path / "b.json")
    assert a.run_id != b.run_id


def test_update_metadata_persists(tmp_path: Path):
    path = tmp_path / "sp.json"
    sp = Scratchpad.create(goal="x", path=path)
    sp.update_metadata(domain="supply_chain", version="0.6.0")
    sp.update_metadata(version="0.6.1")  # overwrite
    sp2 = Scratchpad.load(path)
    assert sp2.state.metadata == {"domain": "supply_chain", "version": "0.6.1"}
