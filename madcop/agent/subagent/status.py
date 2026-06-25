"""v0.7.0 — Sub-agent execution status + result holder.

The status state machine is the trickiest part of sub-agent execution:
the worker thread, a timeout watcher, and a cancellation signal can
all try to set a terminal status. The first one wins; late writes are
silently no-ops (the result is already finalised).

This is a simpler version of the same pattern used in many agent
frameworks. We use a `threading.Lock` because v0.7.0 doesn't yet use
asyncio for the executor — if/when we add async, this becomes an
asyncio.Lock.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SubagentStatus(str, Enum):
    """Lifecycle states for one sub-agent run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

    @property
    def is_terminal(self) -> bool:
        return self in {
            SubagentStatus.COMPLETED,
            SubagentStatus.FAILED,
            SubagentStatus.CANCELLED,
            SubagentStatus.TIMED_OUT,
        }


@dataclass
class SubagentResult:
    """Result of one sub-agent execution.

    Lifecycle: constructed in PENDING → moves to RUNNING when work
    starts → ends in one of {COMPLETED, FAILED, CANCELLED, TIMED_OUT}.
    The transition is one-way: once terminal, status cannot change.
    """

    task_id: str
    agent_name: str
    status: SubagentStatus = SubagentStatus.PENDING
    result: str | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    cost_usd: float = 0.0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _state_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def mark_running(self) -> None:
        """Mark the sub-agent as having started work."""
        with self._state_lock:
            if self.status == SubagentStatus.PENDING:
                self.status = SubagentStatus.RUNNING
                self.started_at = time.time()

    def try_set_terminal(
        self,
        status: SubagentStatus,
        *,
        result: str | None = None,
        error: str | None = None,
        cost_usd: float | None = None,
    ) -> bool:
        """Try to set a terminal status. Returns True if accepted.

        Late writes (after another caller already finalised) are
        no-ops returning False — this is the race-safe part.
        """
        if not status.is_terminal:
            raise ValueError(f"Status {status} is not terminal")
        with self._state_lock:
            if self.status.is_terminal:
                return False  # already done; late writer loses
            if result is not None:
                self.result = result
            if error is not None:
                self.error = error
            if cost_usd is not None:
                self.cost_usd = cost_usd
            self.completed_at = time.time()
            self.status = status
            return True

    @property
    def duration_s(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at

    def request_cancel(self) -> None:
        """Signal the worker to stop. Does NOT change status directly —
        the worker is responsible for calling try_set_terminal(CANCELLED)."""
        self.cancel_event.set()


__all__ = ["SubagentStatus", "SubagentResult"]
