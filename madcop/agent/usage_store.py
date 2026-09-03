"""Process-wide per-session LLM usage store.

Single source of truth for "how much context is this session burning",
fed by the engine's DONE steps (provider-reported usage). Consumers:

  - chat_v4 compaction triggers (token ground truth)
  - the get_context_remaining tool the model can call to self-pace
    (codex parity: tools/handlers/get_context_remaining.rs)
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
# session_id → {"prompt_tokens": int, "completion_tokens": int,
#               "total_tokens": int}
SESSION_USAGE: dict[str, dict[str, int]] = {}


def record_usage(session_id: str, usage: dict[str, Any] | None) -> None:
    """Store the latest provider usage for a session (replaces prior)."""
    if not session_id or not isinstance(usage, dict):
        return
    clean = {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }
    clean["total_tokens"] = int(
        usage.get("total_tokens") or (clean["prompt_tokens"] + clean["completion_tokens"])
    )
    with _lock:
        SESSION_USAGE[session_id] = clean


def get_usage(session_id: str) -> dict[str, int] | None:
    if not session_id:
        return None
    with _lock:
        u = SESSION_USAGE.get(session_id)
        return dict(u) if u else None


def drop_session(session_id: str) -> None:
    with _lock:
        SESSION_USAGE.pop(session_id, None)


__all__ = ["SESSION_USAGE", "record_usage", "get_usage", "drop_session"]
