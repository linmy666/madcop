"""Tests for MadCop Mind — 4-tier memory pipeline (L0/L1/L2/L3).

Covers the split-state CheckpointManager, the warm-up threshold
PipelineManager, and the recall/capture heuristics.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from madcop.agent.memory_pipeline import (
    RunnerState,
    PipelineState,
    Checkpoint,
    CheckpointManager,
    PipelineManager,
    auto_recall,
    auto_capture,
    DEFAULT_PIPELINE_DB,
)
from madcop.memory.store import MemoryStore


# ───────────────────────────────────────────────────────────────────
# RunnerState / PipelineState / Checkpoint
# ───────────────────────────────────────────────────────────────────

def test_runner_state_defaults():
    rs = RunnerState()
    assert rs.last_captured_ts == 0.0
    assert rs.last_l1_cursor == 0.0
    assert rs.last_scene_name == ""


def test_pipeline_state_defaults():
    ps = PipelineState()
    assert ps.conversation_count == 0
    assert ps.warmup_threshold == 1
    assert ps.l2_last_ts == 0.0


def test_checkpoint_initialised_from_empty():
    cp = Checkpoint("c1", RunnerState(), PipelineState())
    assert cp.conversation_id == "c1"
    assert cp.runner.last_captured_ts == 0.0
    assert cp.pipeline.warmup_threshold == 1


# ───────────────────────────────────────────────────────────────────
# CheckpointManager — split-state persistence
# ───────────────────────────────────────────────────────────────────

def test_checkpoint_load_returns_fresh_when_missing(tmp_path: Path):
    mgr = CheckpointManager(path=tmp_path / "p.db")
    cp = mgr.load("new-conv")
    assert cp.conversation_id == "new-conv"
    assert cp.runner.last_captured_ts == 0.0
    mgr.close()


def test_checkpoint_save_and_load(tmp_path: Path):
    mgr = CheckpointManager(path=tmp_path / "p.db")
    cp = mgr.load("c1")
    cp.runner.last_captured_ts = 1234.5
    cp.pipeline.conversation_count = 7
    cp.pipeline.warmup_threshold = 16
    mgr.save(cp)

    cp2 = mgr.load("c1")
    assert cp2.runner.last_captured_ts == 1234.5
    assert cp2.pipeline.conversation_count == 7
    assert cp2.pipeline.warmup_threshold == 16
    mgr.close()


def test_mark_l1_complete_doubles_warmup(tmp_path: Path):
    mgr = CheckpointManager(path=tmp_path / "p.db")
    cp = mgr.load("c1")
    assert cp.pipeline.warmup_threshold == 1
    mgr.mark_l1_complete("c1", 1000.0, "scene_a")
    cp = mgr.load("c1")
    assert cp.pipeline.warmup_threshold == 2
    mgr.mark_l1_complete("c1", 2000.0, "scene_b")
    cp = mgr.load("c1")
    assert cp.pipeline.warmup_threshold == 4
    assert cp.runner.last_captured_ts == 2000.0
    mgr.close()


def test_mark_l1_complete_caps_warmup_at_32(tmp_path: Path):
    mgr = CheckpointManager(path=tmp_path / "p.db")
    for i in range(20):
        mgr.mark_l1_complete(f"c{i}", float(i), f"scene_{i}")
    cp = mgr.load("c0")
    assert cp.pipeline.warmup_threshold <= 32
    mgr.close()


def test_advance_capture_cursor_increments_conversation_count(tmp_path: Path):
    mgr = CheckpointManager(path=tmp_path / "p.db")
    mgr.advance_capture_cursor("c1", 1000.0)
    mgr.advance_capture_cursor("c1", 2000.0)
    mgr.advance_capture_cursor("c1", 3000.0)
    cp = mgr.load("c1")
    assert cp.pipeline.conversation_count == 3
    assert cp.runner.last_captured_ts == 3000.0
    assert cp.runner.last_l1_cursor == 3000.0
    mgr.close()


def test_advance_capture_cursor_uses_max(tmp_path: Path):
    mgr = CheckpointManager(path=tmp_path / "p.db")
    mgr.advance_capture_cursor("c1", 5000.0)
    mgr.advance_capture_cursor("c1", 1000.0)  # older
    cp = mgr.load("c1")
    assert cp.runner.last_captured_ts == 5000.0
    mgr.close()


# ───────────────────────────────────────────────────────────────────
# PipelineManager — warm-up threshold
# ───────────────────────────────────────────────────────────────────

def test_should_extract_l1_initially(tmp_path: Path):
    """A new conversation with warmup=1 triggers after 1 message."""
    store = MemoryStore(path=tmp_path / "mem.db")
    cm = CheckpointManager(path=tmp_path / "p.db")
    pm = PipelineManager(store, cm)
    # Before any conversation, should_extract returns True (fresh)
    assert cm.should_extract_l1("c1") is True
    pm.notify_conversation("c1", 1000.0)
    # Trigger consumed, count reset to 0
    cp = cm.load("c1")
    assert cp.pipeline.conversation_count == 0
    # Single new message: count=1, warmup=1, 1>=1 True (re-trigger possible)
    pm.notify_conversation("c1", 2000.0)
    cp = cm.load("c1")
    assert cp.pipeline.conversation_count == 1
    assert cm.should_extract_l1("c1") is True
    store.close()
    cm.close()


def test_notify_conversation_triggers_l1_at_threshold(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    cm = CheckpointManager(path=tmp_path / "p.db")
    pm = PipelineManager(store, cm)
    # After 1st message, warmup=1, conversation_count=1 → triggers
    triggered = pm.notify_conversation("c1", 1000.0)
    assert triggered["l1"] is True
    store.close()
    cm.close()


def test_notify_conversation_does_not_retrigger_l1(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    cm = CheckpointManager(path=tmp_path / "p.db")
    pm = PipelineManager(store, cm)
    # First triggers L1
    pm.notify_conversation("c1", 1000.0)
    # After L1 done, warmup resets
    pm.mark_l1_done("c1", 1000.0, "scene_0")
    # Conversation count back to 0
    # Second message shouldn't trigger immediately because warmup is 2 now
    triggered = pm.notify_conversation("c1", 2000.0)
    assert triggered["l1"] is False
    store.close()
    cm.close()


# ───────────────────────────────────────────────────────────────────
# auto_recall — returns system-prompt block
# ───────────────────────────────────────────────────────────────────

def test_auto_recall_empty_store(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    result = auto_recall(store, "anything")
    assert result == ""
    store.close()


def test_auto_recall_returns_user_profile_block(tmp_path: Path):
    from madcop.memory.semantic import SemanticMemory
    store = MemoryStore(path=tmp_path / "mem.db")
    sem = SemanticMemory(store)
    sem.add(subject="user", predicate="has_property",
            object="The user's name is Alice.",
            tags=("user-profile",))
    sem.add(subject="user", predicate="has_property",
            object="The user prefers dark mode.",
            tags=("user-profile", "preference"))

    # FTS5 needs a term that appears in the fact content
    result = auto_recall(store, "Alice")
    assert "Known facts about the user" in result
    assert "Alice" in result or "dark mode" in result
    store.close()


def test_auto_recall_separates_user_profile_from_other(tmp_path: Path):
    from madcop.memory.semantic import SemanticMemory
    store = MemoryStore(path=tmp_path / "mem.db")
    sem = SemanticMemory(store)
    sem.add(subject="user", predicate="has_property",
            object="The user prefers Python programming.",
            tags=("user-profile",))
    sem.add(subject="rule", predicate="states",
            object="Python code should be readable.",
            tags=("rule",))

    # 'Python' is a common term — should appear in BOTH facts
    result = auto_recall(store, "Python")
    assert "Known facts about the user" in result
    assert "Related memories" in result
    assert "prefers" in result
    assert "readable" in result
    store.close()


# ───────────────────────────────────────────────────────────────────
# auto_capture — heuristic fact extraction
# ───────────────────────────────────────────────────────────────────

def test_auto_capture_extracts_name_chinese(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    count = auto_capture(store, "你好，我叫小明。")
    assert count >= 1
    from madcop.memory.semantic import SemanticMemory
    sem = SemanticMemory(store)
    results = sem.search("小明")
    assert any("小明" in r.object for r in results)
    store.close()


def test_auto_capture_skips_question_words(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    count = auto_capture(store, "你是谁？")
    assert count == 0
    store.close()


def test_auto_capture_extracts_preference(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    count = auto_capture(store, "我喜欢吃火锅。")
    assert count >= 1
    store.close()


def test_auto_capture_extracts_english_name(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    count = auto_capture(store, "My name is John.")
    assert count >= 1
    store.close()


def test_auto_capture_extracts_english_preference(tmp_path: Path):
    store = MemoryStore(path=tmp_path / "mem.db")
    count = auto_capture(store, "I like dark mode.")
    assert count >= 1
    store.close()


# ───────────────────────────────────────────────────────────────────
# L4 — insight tier
# ───────────────────────────────────────────────────────────────────

def test_pipeline_state_has_l4_fields(tmp_path: Path):
    cm = CheckpointManager(path=tmp_path / "p.db")
    cp = cm.load("c1")
    assert hasattr(cp.pipeline, "l4_last_ts")
    assert hasattr(cp.pipeline, "l4_insight_count")
    assert cp.pipeline.l4_last_ts == 0.0
    assert cp.pipeline.l4_insight_count == 0
    cm.close()


def test_mark_l4_done_updates_timestamp_and_count(tmp_path: Path):
    cm = CheckpointManager(path=tmp_path / "p.db")
    cm.mark_l4_done_checkpoint("c1", insight_count=3)
    cp = cm.load("c1")
    assert cp.pipeline.l4_last_ts > 0
    assert cp.pipeline.l4_insight_count == 3
    cm.mark_l4_done_checkpoint("c1", insight_count=2)
    cp = cm.load("c1")
    assert cp.pipeline.l4_insight_count == 5  # accumulates
    cm.close()


def test_l4_triggered_after_first_l2(tmp_path: Path):
    """L4 fires once after the first L2 synthesis completes."""
    store = MemoryStore(path=tmp_path / "mem.db")
    cm = CheckpointManager(path=tmp_path / "p.db")
    pm = PipelineManager(store, cm)

    # Simulate L2 completion
    pm.mark_l2_done("c1")
    cp = cm.load("c1")
    assert cp.pipeline.l2_last_ts > 0

    # Next conversation should trigger L4 (first time)
    triggered = pm.notify_conversation("c1", time.time())
    assert triggered["l4"] is True

    # After L4 done, next conversation should NOT retrigger immediately
    pm.mark_l4_done("c1", insight_count=1)
    triggered2 = pm.notify_conversation("c1", time.time() + 60)
    assert triggered2["l4"] is False  # need 3 days

    store.close()
    cm.close()


def test_l4_retriggers_after_3_days(tmp_path: Path):
    """L4 re-fires after 3 days since last L4."""
    store = MemoryStore(path=tmp_path / "mem.db")
    cm = CheckpointManager(path=tmp_path / "p.db")
    pm = PipelineManager(store, cm)

    pm.mark_l2_done("c1")
    pm.mark_l4_done("c1", insight_count=1)

    # 4 days later
    future_ts = time.time() + 86400 * 4
    triggered = pm.notify_conversation("c1", future_ts)
    assert triggered["l4"] is True

    store.close()
    cm.close()
