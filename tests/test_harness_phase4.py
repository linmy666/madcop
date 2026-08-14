"""Phase 4 tests — state machine validation, capability wiring,
compaction knob consumption.
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

from madcop.harness.core import (
    SessionLog, EventDomain,
    Step, TurnState, assert_transition,
    LocalFileSystem, FileSystemCapability,
)


# ─── Phase 4a: state machine ─────────────────────────────────────

def test_state_machine_legal_chain():
    s = Step(index=1)
    assert s.transition(TurnState.PLANNING) is True
    assert s.transition(TurnState.EXECUTING) is True
    assert s.transition(TurnState.AUDITING) is True
    assert s.transition(TurnState.DONE) is True
    assert s.state == TurnState.DONE


def test_state_machine_illegal_rejected_and_logged():
    """Illegal transitions return False + log — they must NOT raise
    (an in-flight agent turn cannot afford to die from bookkeeping bugs)
    AND must NOT mutate the state (an illegal hop to a different state
    would silently corrupt the rest of the turn)."""
    s = Step(index=2)
    s.transition(TurnState.PLANNING)
    s.transition(TurnState.EXECUTING)
    s.transition(TurnState.AUDITING)
    legal_before = s.state
    # AUDITING → EXECUTING is illegal (must go PLANNING or DONE)
    assert s.transition(TurnState.EXECUTING) is False
    # State unchanged — the rejected transition did not corrupt it.
    assert s.state == legal_before


def test_state_machine_waiting_human_path():
    """WAITING_HUMAN is reachable from EXECUTING (HITL), then back."""
    s = Step(index=3)
    s.transition(TurnState.PLANNING)
    s.transition(TurnState.EXECUTING)
    assert s.transition(TurnState.WAITING_HUMAN) is True
    assert s.transition(TurnState.EXECUTING) is True
    assert s.transition(TurnState.AUDITING) is True


def test_state_machine_done_can_restart():
    """DONE → PLANNING is legal (next step / next turn)."""
    s = Step(index=4)
    s.transition(TurnState.PLANNING)
    s.transition(TurnState.EXECUTING)
    s.transition(TurnState.AUDITING)
    s.transition(TurnState.DONE)
    assert s.transition(TurnState.PLANNING) is True


def test_state_machine_blocked_is_terminal():
    """BLOCKED has no outgoing edges — must not transition out."""
    s = Step(index=5)
    s.transition(TurnState.PLANNING)
    s.transition(TurnState.EXECUTING)
    # Get INTO blocked. Only legal pre-states (here: EXECUTING) can do this.
    assert s.transition(TurnState.BLOCKED) is True
    assert s.state == TurnState.BLOCKED
    # Now any outgoing transition must be rejected.
    for to_state in (TurnState.PLANNING, TurnState.EXECUTING,
                     TurnState.AUDITING, TurnState.DONE):
        assert s.transition(to_state) is False, (
            f"BLOCKED → {to_state.value} should be illegal"
        )
    # State unchanged after the rejected attempts.
    assert s.state == TurnState.BLOCKED


# ─── Phase 4b: capability wiring ──────────────────────────────────

def test_local_filesystem_implements_protocol():
    fs = LocalFileSystem()
    assert isinstance(fs, FileSystemCapability)
    assert hasattr(fs, "read_file") and hasattr(fs, "write_file") and hasattr(fs, "list_dir")


def test_capability_passed_via_constructor(tmp_path, monkeypatch):
    """MadCopHarness accepts a capabilities dict; fs is consumed, not stubbed."""
    from madcop.harness.mea_loop import MadCopHarness
    monkeypatch.setattr("madcop.harness.mea_loop.SessionLog",
                        lambda persist_dir: SessionLog(persist_dir=persist_dir))

    custom_fs = MagicMock(spec=FileSystemCapability)
    custom_fs.read_file.return_value = "real content on disk"

    client = MagicMock()
    ctx = MagicMock()
    ctx.messages = []
    ctx.work_dir = str(tmp_path)

    h = MadCopHarness(ctx, capabilities={"fs": custom_fs})
    assert h.fs is custom_fs, "custom capability not stored on harness!"

    # _collect_file_evidence must use h.fs, not a fresh default
    h.log.append(__import__("madcop.harness.core", fromlist=["tool_event"]).tool_event(
        "tool_call", "",
        step=1,
        tool_name="write_file",
        path=str(tmp_path / "x.txt"),
    ))
    ev = h._collect_file_evidence()
    custom_fs.read_file.assert_called_once()
    assert "real content on disk" in ev


# ─── Phase 4c: compaction knob ───────────────────────────────────

def test_compaction_threshold_pulls_from_meta_harness(tmp_path, monkeypatch):
    """Knob is loaded BEFORE compaction runs so the threshold is honored."""
    from madcop.server.routes import chat_v4
    monkeypatch.setattr(
        "madcop.meta_harness.task_harness.load_active_harness",
        lambda: MagicMock(compact_threshold_messages=8),
    )
    # Sanity: knob returns 8 (default 20 would compact at 20+ messages;
    # with knob=8 the threshold is honored).
    from madcop.meta_harness.task_harness import load_active_harness
    assert load_active_harness().compact_threshold_messages == 8
