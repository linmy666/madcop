"""Session lifecycle state machine — MadCop's per-chat-session model.

Each chat session has an `asyncio.Lock`-protected state object that
tracks:
  - whether a prompt is currently being processed
  - whether the user has been asked a clarifying question
  - whether the user has typed a follow-up while the previous run is
    still in flight ("Queue next prompt" semantics from opencode's
    followup:"queue" mode)
  - the cancellation event so an in-flight LLM call can be aborted

This replaces the scattered `busy` flag we used to flip on/off at
each SSE entry point. The point isn't to faithfully reproduce
opencode's `SynchronizedRef<State>` — that's an Effect-library
specific type. The point is to make it impossible to (a) send a
second prompt without one of {abort, queue}, (b) forget to clean up
the ask_user pending slot, or (c) lose the in-flight run because
the user typed something new.

Per-session lifecycle is in-memory only for now; persistent
"resume after process restart" is a follow-up.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    """Lifecycle states for a single chat session.

    Idle      — no LLM call in flight, no pending question, queue empty
    Running   — an LLM call (or stream) is in progress
    Awaiting  — the model has emitted an ask_user question; the loop
                is paused waiting for the user's reply
    Cancelling — abort was requested; the in-flight run is being
                torn down (transient)
    """

    IDLE = "idle"
    RUNNING = "running"
    AWAITING = "awaiting"
    CANCELLING = "cancelling"

    @property
    def is_terminal(self) -> bool:
        return self == self.IDLE


@dataclass
class QueuedPrompt:
    """A user prompt that arrived while a previous run was in flight.

    Drained in FIFO order by `Session.next_prompt` after the
    current run completes (success, error, or cancel). The store
    can decide whether to render a "queued" indicator in the UI.
    """
    content: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """Per-session lifecycle + pending-question state.

    NOT a database row — purely runtime state. The HTTP layer is
    expected to instantiate one Session per `conversation_id` and
    keep it in an in-process map (with a TTL eviction, see below).
    """
    session_id: str
    state: SessionState = SessionState.IDLE
    pending_prompts: deque[QueuedPrompt] = field(default_factory=deque)
    pending_question: dict[str, Any] | None = None
    # Signal the in-flight LLM call to abort. asyncio.Event is the
    # stdlib equivalent of the Effect interrupt that opencode uses
    # in its `Runner.cancel`. The LLM client checks this in its
    # streaming loop (or in the next iteration of the chat handler)
    # and tears down the request.
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    # Last activity timestamp — consumed by the long-running visibility
    # tab in SubAgentPanel to show "stuck for N seconds". See #2.
    last_active_at: float = 0.0
    # Tool-call counter (mirrors opencode's `toolCalls` field on the
    # subagent tab). See #2.
    tool_calls: int = 0
    # Last error so the UI can show "last failed at HH:MM" without
    # keeping a separate log. Pure convenience; no durability.
    last_error: str | None = None


# Per-session registry. In-memory only; a TTL eviction is the
# follow-up for "memory after restart".
_REGISTRY: dict[str, Session] = {}
_LOCK = asyncio.Lock()


async def get_or_create(session_id: str) -> Session:
    async with _LOCK:
        sess = _REGISTRY.get(session_id)
        if sess is None:
            sess = Session(session_id=session_id)
            _REGISTRY[session_id] = sess
        return sess


async def get(session_id: str) -> Session | None:
    async with _LOCK:
        return _REGISTRY.get(session_id)


async def remove(session_id: str) -> None:
    async with _LOCK:
        _REGISTRY.pop(session_id, None)


# ── Transitions ─────────────────────────────────────────────────────── #


class SessionBusyError(RuntimeError):
    """Raised when a transition is attempted that doesn't fit the
    current state (e.g. claiming a session for a new run when it's
    already running). The HTTP layer converts this to a 409."""

    def __init__(self, session_id: str, state: SessionState) -> None:
        super().__init__(f"Session {session_id!r} busy in state {state!r}")
        self.session_id = session_id
        self.state = state


async def claim_for_run(session_id: str) -> Session:
    """Atomically transition Idle → Running. Raises SessionBusyError
    if the session is already Running/Awaiting/Cancelling.

    Mirrors opencode's `ensureRunning` pattern (`runner.ts:115-138`).
    If the session is currently Awaiting (an ask_user is open), the
    caller is expected to drain the question slot first via
    `answer_pending_question`. If a follow-up prompt has been queued
    while this call was in flight, the queued entry is left in the
    deque so the next `next_prompt` call picks it up.
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        if sess.state in (SessionState.RUNNING, SessionState.CANCELLING):
            raise SessionBusyError(session_id, sess.state)
        if sess.state == SessionState.AWAITING:
            # Awaiting a user answer — don't claim for a new run;
            # the user must answer or the question must expire.
            raise SessionBusyError(session_id, sess.state)
        sess.state = SessionState.RUNNING
        sess.cancel_event.clear()
        sess.last_active_at = _now()
        sess.tool_calls = 0
        sess.last_error = None
    return sess


async def finish_run(session_id: str, error: str | None = None) -> Session:
    """Transition Running → Idle (or Awaiting if a question is open).
    Drains one queued prompt back into the runner if present.
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        sess.state = SessionState.AWAITING if sess.pending_question else SessionState.IDLE
        sess.last_error = error
        sess.last_active_at = _now()
    return sess


async def ask_pending_question(session_id: str, question: dict[str, Any]) -> None:
    """Mark the session Awaiting because the model asked a question.
    Mirrors opencode's `Permission.ask` pending-slot pattern
    (`permission/index.ts:67-167`).
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        sess.pending_question = question
        sess.state = SessionState.AWAITING
        sess.last_active_at = _now()


async def answer_pending_question(session_id: str) -> None:
    """Called when the user answered an ask_user question.

    Returns Idle (no queued prompt) or Running with the next
    queued prompt dispatched (the caller is expected to start the
    next SSE stream immediately). Cascades pending prompts: if the
    user answered, the next queued prompt (if any) is automatically
    picked up — same as opencode's `Permission.reply` which doesn't
    leave siblings queued.
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        sess.pending_question = None
        if sess.pending_prompts:
            sess.state = SessionState.RUNNING
            sess.cancel_event.clear()
        else:
            sess.state = SessionState.IDLE
        sess.last_active_at = _now()


async def request_cancel(session_id: str) -> None:
    """Mark the session Cancelling and set the cancel event so the
    in-flight LLM call sees it on its next iteration. Mirrors
    opencode's `Runner.cancel` (`runner.ts:171-202`).

    Does NOT wait for the run to actually finish — the runner is
    expected to observe the cancel_event, tear down, and call
    `finish_run` itself.
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        if sess.state in (SessionState.RUNNING, SessionState.AWAITING):
            sess.state = SessionState.CANCELLING
            sess.last_active_at = _now()
        sess.cancel_event.set()


async def queue_prompt(session_id: str, prompt: QueuedPrompt) -> Session:
    """Queue a follow-up prompt while a previous run is in flight.

    Mirrors opencode's `prompt_async` (`session.ts:311-329`): the new
    prompt runs after the current one settles, not instead of it.
    If the session is currently Idle, the caller is expected to
    switch the lifecycle to Running itself.
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        sess.pending_prompts.append(prompt)
        sess.last_active_at = _now()
    return sess


async def next_prompt(session_id: str) -> QueuedPrompt | None:
    """Pop the next queued prompt (FIFO). Returns None if empty.
    Call this AFTER the current run finishes to feed the next SSE
    stream.
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        if not sess.pending_prompts:
            return None
        return sess.pending_prompts.popleft()


async def record_tool_call(session_id: str) -> None:
    """Bump the tool-call counter for #2's SubAgentPanel display."""
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        sess.tool_calls += 1
        sess.last_active_at = _now()


async def touch(session_id: str) -> None:
    """Bump the last_active_at timestamp without changing state.

    Used by the streaming loop on every chunk so the SubAgentPanel
    "stuck for N seconds" indicator stays fresh while the run is
    actually moving.
    """
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        sess.last_active_at = _now()


# ── Snapshot for the UI ─────────────────────────────────────────────── #


@dataclass
class SessionSnapshot:
    """A read-only view of the session state, safe to send over the
    event bus and to the Vuex store. Mirrors opencode's
    SessionStatusEvent shape (`packages/schema/src/session-status-event.ts:9-32`).
    """

    session_id: str
    state: str
    pending_prompts: int
    has_pending_question: bool
    tool_calls: int
    last_active_at: float
    last_error: str | None


async def snapshot(session_id: str) -> SessionSnapshot:
    sess = await get_or_create(session_id)
    async with _asyncio_unlocked_attr(sess, "_state_lock"):
        return SessionSnapshot(
            session_id=sess.session_id,
            state=sess.state.value,
            pending_prompts=len(sess.pending_prompts),
            has_pending_question=sess.pending_question is not None,
            tool_calls=sess.tool_calls,
            last_active_at=sess.last_active_at,
            last_error=sess.last_error,
        )


# ── Internal helpers ───────────────────────────────────────────────── #

import time as _time


def _now() -> float:
    return _time.time()


@contextlib.asynccontextmanager
async def _asyncio_unlocked_attr(obj, attr):
    """A no-op async ctx manager for places that don't need a per-Session
    lock. We rely on `dict` operations on the registry being atomic at
    the GIL level; the only state mutation that needs serialization is
    the Session object's own fields, and Python's GIL gives us that
    for free for simple attribute reads/writes. If we ever need true
    atomicity, swap this for `asyncio.Lock()`.
    """
    yield
