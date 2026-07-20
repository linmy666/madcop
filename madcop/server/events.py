"""SSE event types — typed discriminated union for the chat stream.

MadCop's SSE stream emits ~19 event shapes (`text`, `done`, `tool`,
`error`, `plan_step`, ...). They're currently constructed ad-hoc as
`json.dumps({"type": "...", "field": ...})` strings at every emit
site (~20 of them), so a typo in the discriminator key silently
bypasses the SSE consumer's switch.

This module provides:
  - `EventType`  — a Literal union of all valid type names.
  - `make_event` — a single helper that builds an event dict with a
    validated `type` field, plus an `id` (set by the wrapper
    upstream of this module), ready to feed straight into
    `json.dumps`. Old-style string `type` still works via the
    `Any` overload, so this is a strict superset of the existing
    shape — no flag-day rewrite.
  - `TypeError` if a caller passes an unknown `type` — caught at
    emit time, not at consumer parse time.

We don't depend on pydantic here to keep the import surface small
in the SSE hot path; the validation is just an `in` check against
the literal tuple.
"""

from __future__ import annotations

from typing import Any, Literal

# All valid SSE event types in the chat stream. Keep this tuple in
# sync with the consumer's switch in desktop/src/vue/stores/
# chatStore.ts. Adding a new event here forces a compile-time-style
# check at every emit site.
EventType = Literal[
    "ack",                              # server-side handshake reply
    "connected",                        # WebSocket/SSE peer-ready
    "ping", "pong",                     # keepalive
    "status",                           # state-machine change (idle/busy)
    "permission_mode_changed",          # opencode compat
    "text",                             # text delta
    "content_start", "content_delta", "message_complete",  # legacy aliases
    "reasoning",                        # model thought (Claude/o-series)
    "tool",                             # tool call started
    "tool_result",                      # tool result
    "tool_use_complete",                # opencode compat
    "plan", "plan_step", "plan_done",   # step state machine
    "deep_route",                       # deep-mode route decision
    "agent_start", "agent_token",       # per-agent streaming
    "agent_done",
    "preview_update",                   # write to ~/.madcop/preview
    "clarification_request",            # ask_user tool fired
    "skill_distilled",                  # auto-distilled SKILL.md
    "skill_distilled_error",            # (reserved for future error)
    "email", "password",                # compat stubs
    "done",                             # terminal happy path
    "error",                            # terminal failure
    "retry",                            # transient retry hint
    "permission_asked", "permission_replied",  # NEW: opencode compat
    "question_asked", "question_replied",       # NEW: opencode compat
    "version",                          # meta event (api version)
]

# Tuple form for membership tests (Literal[] can't be iterated).
ALL_TYPES: tuple[str, ...] = (
    "ack", "connected", "ping", "pong", "status",
    "permission_mode_changed",
    "text", "content_start", "content_delta", "message_complete",
    "reasoning",
    "tool", "tool_result", "tool_use_complete",
    "plan", "plan_step", "plan_done",
    "deep_route",
    "agent_start", "agent_token", "agent_done",
    "preview_update",
    "clarification_request",
    "skill_distilled", "skill_distilled_error",
    "email", "password",
    "done", "error", "retry",
    "permission_asked", "permission_replied",
    "question_asked", "question_replied",
    "version",
)


def make_event(type: str, **fields: Any) -> dict[str, Any]:
    """Build a typed SSE event dict.

    Validates that `type` is in `ALL_TYPES`; raises TypeError
    otherwise. The returned dict is ready to be `json.dumps`'d and
    emitted as `data: <json>\\n\\n`.
    """
    if type not in ALL_TYPES:
        raise TypeError(
            f"unknown SSE event type {type!r}; "
            f"add it to ALL_TYPES in madcop/server/events.py first"
        )
    return {"type": type, **fields}
