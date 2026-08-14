"""
MadCop Harness — Core Types & Protocols.

Architectural design principles (adapted from production agent harness
patterns, not copied from any single source):

1. **Event log is the single source of truth.** All model-visible data
   must be reconstructable from the append-only event log. Messages,
   tool calls, and reasoning are derived from the log — not held in
   ad-hoc arrays that drift out of sync.

2. **Three event domains, structurally separated.**
   - Reasoning → thought_start/delta/end (the model's internal logic)
   - Tool calls → tool_start/end (side effects on the environment)
   - Answer → text_delta/end (what the user sees)
   These NEVER mix in a single text blob.

3. **Capability seams.** File system, shell, and search are Protocol
   interfaces — swappable backends without changing the agent loop.
   This enables sandboxing, remote execution, or mock testing.

4. **Turn/Step lifecycle.** A Turn spans user input → final answer.
   Each Step is one model request + its tool calls. The lifecycle is
   a formal state machine, not a while loop with break conditions.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

_HARNESS_ROOT = Path.home() / ".madcop" / "harness_runs"
from typing import Any, Callable, Iterator, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════════════
# Event Types — the three domains
# ═══════════════════════════════════════════════════════════════════════

class EventDomain(str, Enum):
    REASONING = "reasoning"
    TOOL = "tool"
    ANSWER = "answer"
    SYSTEM = "system"  # lifecycle events (turn/step start/end)


@dataclass
class HarnessEvent:
    """One event in the session log. Append-only, immutable after creation."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    domain: EventDomain = EventDomain.SYSTEM
    kind: str = ""  # thought_start, tool_call, text_delta, turn_start, etc.
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["timestamp_iso"] = datetime.fromtimestamp(self.timestamp).isoformat(timespec="seconds")
        return d


# ═══════════════════════════════════════════════════════════════════════
# Session Log — append-only, the single source of truth
# ═══════════════════════════════════════════════════════════════════════

class SessionLog:
    """Append-only event log. The single source of truth for a task run.

    Design invariant: "model-visible ⟺ logged." Any data the model sees
    in its context must be reconstructable from this log. Messages are
    derived from the log stream, not stored separately.

    Persistence: JSONL file under ~/.madcop/harness_runs/<run_id>/log.jsonl
    """

    def __init__(self, run_id: str | None = None, persist_dir: Path | None = None):
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self._events: list[HarnessEvent] = []
        self._persist_path: Path | None = None

        if persist_dir:
            self._persist_dir = persist_dir / self.run_id
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._persist_path = self._persist_dir / "log.jsonl"

    @classmethod
    def for_session(cls, session_id: str) -> "SessionLog":
        """Open (or create) the persistent log for a chat session.

        run_id == session_id so every turn of one conversation lands in
        the same directory and resume/fork/replay become possible.
        Reloads prior events from disk into memory so derive_messages()
        reflects the full conversation, not just this turn.
        """
        log = cls(run_id=session_id, persist_dir=_HARNESS_ROOT)
        if log._persist_path and log._persist_path.exists():
            try:
                for line in log._persist_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    ev = HarnessEvent(
                        id=data.get("id") or uuid.uuid4().hex[:12],
                        domain=EventDomain(data.get("domain", "system")),
                        kind=data.get("kind", ""),
                        content=data.get("content", ""),
                        metadata=data.get("metadata", {}) or {},
                        timestamp=data.get("timestamp", time.time()),
                    )
                    log._events.append(ev)
            except Exception:
                # Corrupted log line — keep what we parsed; never crash chat.
                pass
        return log

    def append(self, event: HarnessEvent) -> HarnessEvent:
        """Append an event. Also persists to JSONL if a path is set."""
        self._events.append(event)
        if self._persist_path:
            with open(self._persist_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def events(self, domain: EventDomain | None = None) -> list[HarnessEvent]:
        """Return events, optionally filtered by domain."""
        if domain:
            return [e for e in self._events if e.domain == domain]
        return list(self._events)

    def derive_messages(self) -> list[dict[str, str]]:
        """Derive model-visible messages from the log.

        This is the key method — model context is ALWAYS derived from
        the log, never stored separately. This prevents drift between
        what the model saw and what the log records.

        Rules (aligned with how chat_v4/mea_loop actually write events):
        - ``turn_start`` (content = user query) opens a user message.
        - ANSWER-domain events (text deltas + done) fold into one
          assistant message per turn.
        - REASONING events are EXCLUDED — execution trajectories are
          discarded; only the verified answer survives (the principle).
        - TOOL tool_call/tool_result pairs render as an assistant
          narration ("Used <tool>") followed by a user-role observation,
          keeping the message sequence valid for OpenAI-compatible APIs
          (a bare role:"tool" without tool_calls would be rejected).
        - ``turn_end`` closes the current message.
        """
        messages: list[dict[str, str]] = []
        current_role: str | None = None
        current_content: list[str] = []

        def _flush() -> None:
            nonlocal current_role, current_content
            if current_role:
                text = "".join(current_content).strip()
                if text:
                    messages.append({"role": current_role, "content": text})
            current_role = None
            current_content = []

        def _start(role: str, content: str) -> None:
            nonlocal current_role, current_content
            if current_role != role:
                _flush()
                current_role = role
                current_content = []
            current_content.append(content)

        for ev in self._events:
            if ev.domain == EventDomain.SYSTEM:
                if ev.kind == "turn_start":
                    _flush()
                    _start("user", ev.content)
                elif ev.kind == "turn_end":
                    _flush()
            elif ev.domain == EventDomain.ANSWER:
                if ev.kind in ("text_delta", "done") and ev.content:
                    _start("assistant", ev.content)
            elif ev.domain == EventDomain.TOOL:
                if ev.kind == "tool_call":
                    name = ev.metadata.get("tool_name") or ev.content or "tool"
                    _start("assistant", f"[used tool: {name}]")
                elif ev.kind == "tool_result":
                    _start("user", f"[tool result] {ev.content[:500]}")
            # REASONING domain: deliberately ignored (trajectory discard).

        _flush()
        return messages

    def reasoning_summary(self) -> str:
        """Concatenate all reasoning events — for audit/review."""
        return "\n".join(e.content for e in self.events(EventDomain.REASONING) if e.content)

    def tool_calls_summary(self) -> list[dict]:
        """Summary of all tool calls — for the trajectory UI."""
        calls = []
        for ev in self._events:
            if ev.domain == EventDomain.TOOL:
                calls.append({
                    "kind": ev.kind,
                    "content": ev.content[:100],
                    "metadata": ev.metadata,
                    "timestamp": ev.timestamp,
                })
        return calls

    def answer_text(self) -> str:
        """Concatenate all answer events — the final user-visible output."""
        return "".join(e.content for e in self.events(EventDomain.ANSWER))


# ═══════════════════════════════════════════════════════════════════════
# Capability Protocols — swappable backends (plugin seams)
# ═══════════════════════════════════════════════════════════════════════

@runtime_checkable
class FileSystemCapability(Protocol):
    """File system operations. Swappable: local FS, sandbox, remote."""
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> bool: ...
    def list_dir(self, path: str) -> list[str]: ...


@runtime_checkable
class ShellCapability(Protocol):
    """Shell command execution. Swappable: local, sandbox, remote."""
    def exec(self, command: str, timeout: int = 30) -> tuple[str, int]: ...


@runtime_checkable
class SearchCapability(Protocol):
    """Web search. Swappable: Bing, SearXNG, Tavily."""
    def search(self, query: str, max_results: int = 5) -> list[dict]: ...


@dataclass
class LocalFileSystem:
    """Default local filesystem implementation."""
    root: Path = field(default_factory=lambda: Path.cwd())

    def read_file(self, path: str) -> str:
        p = self.root / path if not Path(path).is_absolute() else Path(path)
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"[read error: {e}]"

    def write_file(self, path: str, content: str) -> bool:
        p = self.root / path if not Path(path).is_absolute() else Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def list_dir(self, path: str) -> list[str]:
        p = self.root / path if not Path(path).is_absolute() else Path(path)
        try:
            return [str(f.name) for f in p.iterdir()]
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# Turn/Step State Machine
# ═══════════════════════════════════════════════════════════════════════

class TurnState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"      # Manager is thinking
    EXECUTING = "executing"    # Executor is running
    AUDITING = "auditing"      # Auditor is verifying
    WAITING_HUMAN = "waiting_human"  # HITL confirmation
    DONE = "done"
    BLOCKED = "blocked"
    ERROR = "error"


# Legal state-machine transitions. Anything not listed is a bug —
# assert_transition() logs loudly instead of failing the turn.
_TRANSITIONS: dict[TurnState, frozenset[TurnState]] = {
    TurnState.IDLE: frozenset({TurnState.PLANNING, TurnState.ERROR}),
    TurnState.PLANNING: frozenset({TurnState.EXECUTING, TurnState.WAITING_HUMAN,
                                   TurnState.BLOCKED, TurnState.DONE, TurnState.ERROR}),
    TurnState.EXECUTING: frozenset({TurnState.AUDITING, TurnState.WAITING_HUMAN,
                                    TurnState.BLOCKED, TurnState.ERROR}),
    TurnState.WAITING_HUMAN: frozenset({TurnState.EXECUTING, TurnState.AUDITING,
                                        TurnState.BLOCKED, TurnState.DONE, TurnState.ERROR}),
    TurnState.AUDITING: frozenset({TurnState.PLANNING, TurnState.DONE,
                                   TurnState.BLOCKED, TurnState.ERROR}),
    TurnState.DONE: frozenset({TurnState.PLANNING}),   # next step
    TurnState.BLOCKED: frozenset(),
    TurnState.ERROR: frozenset(),
}


def assert_transition(step: "Step", to: TurnState) -> bool:
    """Validate a state change on a Step. Returns False (and logs) on an
    illegal transition rather than raising — a bookkeeping bug must not
    kill an in-flight agent turn."""
    from_current = _TRANSITIONS.get(step.state, frozenset())
    if to not in from_current:
        logging.getLogger(__name__).warning(
            "illegal turn-state transition %s → %s on step %d",
            step.state.value, to.value, step.index,
        )
        return False
    return True


@dataclass
class Step:
    """One step in the MEA loop."""
    index: int
    state: TurnState = TurnState.IDLE
    contract_description: str = ""
    executor_summary: str = ""
    audit_status: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    @property
    def duration_ms(self) -> int:
        end = self.completed_at or time.time()
        return int((end - self.started_at) * 1000)

    def transition(self, to: TurnState) -> bool:
        """Validated state change (see assert_transition).

        Returns True when legal; on an illegal transition the state is
        NOT mutated (an in-flight loop would corrupt itself otherwise) and
        a warning is logged so bookkeeping bugs surface in ops.
        """
        legal = assert_transition(self, to)
        if legal:
            self.state = to
        return legal

    def to_dict(self) -> dict:
        return {
            "step": self.index,
            "state": self.state.value,
            "contract": self.contract_description[:200],
            "audit": self.audit_status,
            "duration_ms": self.duration_ms,
        }


# ═══════════════════════════════════════════════════════════════════════
# Event Factory — convenient constructors for each domain
# ═══════════════════════════════════════════════════════════════════════

def reasoning_event(kind: str, content: str, **meta) -> HarnessEvent:
    return HarnessEvent(domain=EventDomain.REASONING, kind=kind, content=content, metadata=meta)

def tool_event(kind: str, content: str, **meta) -> HarnessEvent:
    return HarnessEvent(domain=EventDomain.TOOL, kind=kind, content=content, metadata=meta)

def answer_event(kind: str, content: str, **meta) -> HarnessEvent:
    return HarnessEvent(domain=EventDomain.ANSWER, kind=kind, content=content, metadata=meta)

def system_event(kind: str, content: str = "", **meta) -> HarnessEvent:
    return HarnessEvent(domain=EventDomain.SYSTEM, kind=kind, content=content, metadata=meta)
