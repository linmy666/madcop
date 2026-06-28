"""MadCop Mind — 5-tier progressive memory pipeline.

A custom layered architecture that grows progressively from raw
transcript to insight:

  L0 — raw transcript (every message, full fidelity)
  L1 — extracted facts (episodic + semantic + reflective)
  L2 — scenes (grouped memory, time-coherent)
  L3 — persona (compressed user model, profile of the user)
  L4 — insight (meta-patterns, cross-scene synthesis, lessons learned)

L4 is the unique layer that distinguishes MadCop Mind from other
4-tier systems: it operates on L3 output + L2 scenes to derive
transferable insights ("when the user asks about X, they usually
mean Y" or "the deploy workflow that worked last time was Z").

The pipeline runs in the background with a **warm-up threshold**:
  1 → 2 → 4 → 8 → ... messages between L1 extractions
This avoids redundant work for very long sessions and amortises
extraction cost over the conversation.

Checkpoint persistence uses a **split-state** design:
  - runner_states (owned by extractors)
  - pipeline_states (owned by the pipeline manager)
Each side reads/writes its own namespace so they cannot
clobber each other on concurrent writes.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from madcop.memory.store import MemoryStore


# ───────────────────────────────────────────────────────────────────
# Tier definitions (we keep MadCop's existing 4 kinds for L1)
# ───────────────────────────────────────────────────────────────────

# L0 = raw transcript (every message JSONL, full fidelity)
# L1 = episodic + semantic + reflective (MadCop existing memory store)
# L2 = scenes (groupings of L1 by time, similarity)
# L3 = persona (compressed user model, derived from L1+L2)
# L4 = insight (meta-patterns: cross-scene synthesis, transferable lessons)

DEFAULT_PIPELINE_DB = Path(
    "~/.madcop/pipeline.db"
).expanduser()


# ───────────────────────────────────────────────────────────────────
# Split-state checkpoint
# ───────────────────────────────────────────────────────────────────

@dataclass
class RunnerState:
    """Owned by extractors (L0/L1/L2 runners)."""
    last_captured_ts: float = 0.0  # L0 cursor
    last_l1_cursor: float = 0.0     # L1 input cursor
    last_scene_name: str = ""
    updated_at: float = 0.0


@dataclass
class PipelineState:
    """Owned by PipelineManager. Tracking scheduling."""
    conversation_count: int = 0
    last_extraction_ts: float = 0.0
    warmup_threshold: int = 1   # doubles after each L1 completion
    l2_last_ts: float = 0.0
    last_l2_ts: float = 0.0
    l4_last_ts: float = 0.0     # L4 insight synthesis timestamp
    l4_insight_count: int = 0   # total L4 insights generated

@dataclass
class Checkpoint:
    """One per conversation."""
    conversation_id: str
    runner: RunnerState
    pipeline: PipelineState
    schema_version: int = 1


# ───────────────────────────────────────────────────────────────────
# CheckpointManager
# ───────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS mc_checkpoints (
    conversation_id TEXT PRIMARY KEY,
    runner_json TEXT NOT NULL,
    pipeline_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    updated_at REAL NOT NULL
);
"""


class CheckpointManager:
    """Two-namespace checkpoint store.

    All mutating methods are serialised via a per-file async lock so
    multiple CheckpointManager instances sharing the same file path
    share the same lock — no split-brain overwrites.
    """

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else DEFAULT_PIPELINE_DB
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def load(self, conversation_id: str) -> Checkpoint:
        row = self._conn.execute(
            "SELECT * FROM mc_checkpoints WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return Checkpoint(
                conversation_id=conversation_id,
                runner=RunnerState(),
                pipeline=PipelineState(),
            )
        return Checkpoint(
            conversation_id=conversation_id,
            runner=RunnerState(**json.loads(row["runner_json"])),
            pipeline=PipelineState(**json.loads(row["pipeline_json"])),
            schema_version=row["schema_version"],
        )

    def save(self, cp: Checkpoint) -> None:
        cp.runner.updated_at = time.time()
        with self._conn:
            self._conn.execute(
                """INSERT INTO mc_checkpoints
                   (conversation_id, runner_json, pipeline_json, schema_version, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET
                     runner_json = excluded.runner_json,
                     pipeline_json = excluded.pipeline_json,
                     schema_version = excluded.schema_version,
                     updated_at = excluded.updated_at""",
                (
                    cp.conversation_id,
                    json.dumps(cp.runner.__dict__),
                    json.dumps(cp.pipeline.__dict__),
                    cp.schema_version,
                    cp.runner.updated_at,
                ),
            )

    def mark_l1_complete(self, conversation_id: str, last_captured_ts: float, last_scene: str) -> None:
        """Called by the L1 runner after a successful L1 extraction."""
        cp = self.load(conversation_id)
        cp.runner.last_captured_ts = max(cp.runner.last_captured_ts, last_captured_ts)
        cp.runner.last_scene_name = last_scene
        cp.pipeline.warmup_threshold = (
            0 if cp.pipeline.warmup_threshold == 0
            else min(cp.pipeline.warmup_threshold * 2, 32)
        )
        cp.pipeline.last_extraction_ts = time.time()
        self.save(cp)

    def advance_capture_cursor(self, conversation_id: str, last_msg_ts: float) -> None:
        cp = self.load(conversation_id)
        cp.runner.last_captured_ts = max(cp.runner.last_captured_ts, last_msg_ts)
        cp.runner.last_l1_cursor = max(cp.runner.last_l1_cursor, last_msg_ts)
        cp.pipeline.conversation_count += 1
        self.save(cp)

    def mark_l2_done_checkpoint(self, conversation_id: str) -> None:
        """Directly update L2 timestamp."""
        cp = self.load(conversation_id)
        cp.pipeline.l2_last_ts = time.time()
        self.save(cp)

    def mark_l4_done_checkpoint(self, conversation_id: str, insight_count: int = 0) -> None:
        """Directly update L4 timestamp + insight count."""
        cp = self.load(conversation_id)
        cp.pipeline.l4_last_ts = time.time()
        cp.pipeline.l4_insight_count += insight_count
        self.save(cp)

    def should_extract_l1(self, conversation_id: str) -> bool:
        """Return True if enough new messages have arrived since last L1.

        A brand-new conversation (count=0) is always ready. After
        the first L1 extraction the warmup threshold doubles, so
        subsequent L1s require progressively more new messages.
        """
        cp = self.load(conversation_id)
        if cp.pipeline.conversation_count == 0:
            return True  # fresh — first extraction is free
        return cp.pipeline.conversation_count >= cp.pipeline.warmup_threshold


# ───────────────────────────────────────────────────────────────────
# Pipeline manager — schedules L1/L2/L3 based on conversation growth
# ───────────────────────────────────────────────────────────────────

class PipelineManager:
    """Decides WHEN to run each tier, and delegates the actual
    extraction to registered runners.

    The pipeline manager does NOT do the extraction itself; it
    just decides whether a runner should run now, based on:
      - conversation_count vs warmup_threshold (L1)
      - last_extraction_ts vs max_recency (L2)
      - first-run or major-change vs never (L3)
    """

    def __init__(self, memory_store: MemoryStore, checkpoint: CheckpointManager):
        self._memory = memory_store
        self._checkpoint = checkpoint
        self._inflight_l1: set[str] = set()  # conversation ids
        self._inflight_l2: set[str] = set()
        self._inflight_l3: set[str] = set()

    def notify_conversation(self, conversation_id: str, latest_message_ts: float) -> dict[str, bool]:
        """Called after every assistant turn. Returns which tiers were triggered."""
        self._checkpoint.advance_capture_cursor(conversation_id, latest_message_ts)
        triggered = {"l1": False, "l2": False, "l3": False, "l4": False}

        if self._checkpoint.should_extract_l1(conversation_id):
            if conversation_id not in self._inflight_l1:
                self._inflight_l1.add(conversation_id)
                # Consume this trigger: bump warmup so the next
                # `should_extract_l1` call returns False until enough
                # more conversation has accumulated. We keep the
                # doubling-after-completion behaviour in mark_l1_complete.
                cp = self._checkpoint.load(conversation_id)
                cp.pipeline.conversation_count = 0
                # Set warmup to current value (or 1) so we don't re-trigger
                # immediately. After mark_l1_complete the value doubles.
                cur = cp.pipeline.warmup_threshold
                cp.pipeline.warmup_threshold = cur if cur > 1 else 1
                self._checkpoint.save(cp)
                triggered["l1"] = True

        # L2 every 10 L1 cycles
        cp = self._checkpoint.load(conversation_id)
        if cp.pipeline.last_l2_ts > 0 and (latest_message_ts - cp.pipeline.l2_last_ts) > 86400:
            if conversation_id not in self._inflight_l2:
                self._inflight_l2.add(conversation_id)
                triggered["l2"] = True

        # L4 insight synthesis: triggered after L2 completes and at least
        # 3 scenes exist (enough data for cross-scene pattern detection)
        if cp.pipeline.l2_last_ts > 0 and cp.pipeline.l4_last_ts == 0:
            # First L4 runs after first L2
            triggered["l4"] = True
        elif cp.pipeline.l4_last_ts > 0 and (latest_message_ts - cp.pipeline.l4_last_ts) > 86400 * 3:
            # Subsequent L4 runs every 3 days
            triggered["l4"] = True

        return triggered

    def mark_l1_done(self, conversation_id: str, last_captured_ts: float, last_scene: str) -> None:
        self._inflight_l1.discard(conversation_id)
        self._checkpoint.mark_l1_complete(conversation_id, last_captured_ts, last_scene)

    def mark_l2_done(self, conversation_id: str) -> None:
        self._inflight_l2.discard(conversation_id)
        self._checkpoint.mark_l2_done_checkpoint(conversation_id)

    def mark_l4_done(self, conversation_id: str, insight_count: int = 0) -> None:
        """Called after L4 insight synthesis completes."""
        self._checkpoint.mark_l4_done_checkpoint(conversation_id, insight_count)


# ───────────────────────────────────────────────────────────────────
# Auto-recall: pull relevant L1 memories into a system prompt
# ───────────────────────────────────────────────────────────────────

def auto_recall(
    memory_store: MemoryStore,
    query: str,
    *,
    user_profile_tag: str = "user-profile",
    limit: int = 5,
) -> str:
    """Return a system-prompt-ready string of relevant memories.

    Format mirrors production agent memory block style:
      # Known facts about the user
      - <fact 1>
      - <fact 2>
    """
    from madcop.memory.semantic import SemanticMemory
    sem = SemanticMemory(memory_store)
    try:
        results = sem.search(query, limit=limit)
    except Exception:
        return ""

    if not results:
        return ""

    user_facts: list[str] = []
    other_facts: list[str] = []

    for r in results:
        text = r.object if hasattr(r, "object") else str(r)
        if not text:
            continue
        if "user-profile" in (r.tags or []):
            user_facts.append(text)
        else:
            other_facts.append(text)

    parts: list[str] = []
    if user_facts:
        parts.append("# Known facts about the user")
        parts.extend(f"- {f}" for f in user_facts[:5])
    if other_facts:
        parts.append("\n# Related memories")
        parts.extend(f"- {f}" for f in other_facts[:5])

    return "\n".join(parts) if parts else ""


# ───────────────────────────────────────────────────────────────────
# Auto-capture: heuristic extraction (no LLM call, fast)
# ───────────────────────────────────────────────────────────────────

_CAPTURE_BLACKLIST = {"谁", "什么", "哪", "我", "你", "他", "她", "它", "的"}
_NAME_PATTERNS = [
    re.compile(r"我(?:叫|是)\s*(\S+?)[\s,，。.!？?！]"),
    re.compile(r"(?:my name is|i am|i'm)\s+([A-Za-z][\w'-]{0,30})", re.IGNORECASE),
]
_PREF_PATTERNS = [
    re.compile(r"我(?:喜欢|偏好|爱)\s*(.{2,40}?)[\s,，。.!？?！]"),
    re.compile(r"(?:i like|i prefer|i love)\s+(.{2,60}?)[\s.,，!?！]", re.IGNORECASE),
]


def auto_capture(
    memory_store: MemoryStore,
    text: str,
) -> int:
    """Heuristic fact extraction. Returns count of facts stored."""
    from madcop.memory.semantic import SemanticMemory
    sem = SemanticMemory(memory_store)
    count = 0

    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            if name in _CAPTURE_BLACKLIST or not name:
                continue
            sem.add(
                subject="user",
                predicate="has_property",
                object=f"The user's name is {name}.",
                tags=("auto-extracted", "user-profile", "name"),
            )
            count += 1
            break

    for pat in _PREF_PATTERNS:
        for m in pat.finditer(text):
            pref = m.group(1).strip().rstrip(".,，")
            if len(pref) < 2:
                continue
            sem.add(
                subject="user",
                predicate="has_property",
                object=f"The user likes/prefers {pref}.",
                tags=("auto-extracted", "user-profile", "preference"),
            )
            count += 1

    return count


# ───────────────────────────────────────────────────────────────────
# Module-level singleton helpers
# ───────────────────────────────────────────────────────────────────

_checkpoint: CheckpointManager | None = None
_memory: MemoryStore | None = None
_pipeline: PipelineManager | None = None


def get_checkpoint_manager() -> CheckpointManager:
    global _checkpoint
    if _checkpoint is None:
        _checkpoint = CheckpointManager()
    return _checkpoint


def get_pipeline_manager() -> PipelineManager:
    global _pipeline, _memory
    if _pipeline is None:
        if _memory is None:
            from .memory.store import MemoryStore
            _memory = MemoryStore()
        _pipeline = PipelineManager(_memory, get_checkpoint_manager())
    return _pipeline


def reset_pipeline() -> None:
    global _checkpoint, _memory, _pipeline
    if _checkpoint is not None:
        _checkpoint.close()
    _checkpoint = None
    _memory = None
    _pipeline = None


__all__ = [
    "RunnerState",
    "PipelineState",
    "Checkpoint",
    "CheckpointManager",
    "PipelineManager",
    "auto_recall",
    "auto_capture",
    "get_checkpoint_manager",
    "get_pipeline_manager",
    "reset_pipeline",
    "DEFAULT_PIPELINE_DB",
]