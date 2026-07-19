"""Per-session mid-run steer queue (Codex-style guidance).

While quick / standard / deep is running, the UI can POST a steer text.
Engines poll ``drain_steers(session_id)`` between steps / waves and inject
the text as cooperative guidance — without aborting the whole run.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SteerItem:
    text: str
    created_at: float = field(default_factory=time.time)


_lock = threading.Lock()
# session_id -> FIFO list
_queues: dict[str, list[SteerItem]] = {}
# cap per session to avoid abuse
_MAX_PENDING = 20
_MAX_TEXT = 4000


def push_steer(session_id: str, text: str) -> dict[str, Any]:
    """Enqueue a steer for a live session. Returns status payload."""
    sid = (session_id or "").strip()
    body = (text or "").strip()
    if not sid:
        return {"ok": False, "error": "session_id required"}
    if not body:
        return {"ok": False, "error": "text required"}
    if len(body) > _MAX_TEXT:
        body = body[:_MAX_TEXT] + "\n…(截断)"
    with _lock:
        q = _queues.setdefault(sid, [])
        if len(q) >= _MAX_PENDING:
            return {
                "ok": False,
                "error": f"too many pending steers (max {_MAX_PENDING})",
                "pending": len(q),
            }
        q.append(SteerItem(text=body))
        pending = len(q)
    return {
        "ok": True,
        "session_id": sid,
        "pending": pending,
        "preview": body[:120],
        "note": "Steer queued — injected at next ReAct step / deep wave / after quick turn.",
    }


def drain_steers(session_id: str) -> list[str]:
    """Pop all pending steers for a session (oldest first)."""
    sid = (session_id or "").strip()
    if not sid:
        return []
    with _lock:
        items = _queues.pop(sid, [])
    return [i.text for i in items]


def pending_count(session_id: str) -> int:
    sid = (session_id or "").strip()
    if not sid:
        return 0
    with _lock:
        return len(_queues.get(sid, []))


def clear_steers(session_id: str) -> None:
    sid = (session_id or "").strip()
    if not sid:
        return
    with _lock:
        _queues.pop(sid, None)


def format_steer_block(steers: list[str]) -> str:
    """Format drained steers for injection into agent context."""
    if not steers:
        return ""
    if len(steers) == 1:
        body = steers[0]
    else:
        body = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(steers))
    return (
        "【用户中途指引 / Steer】\n"
        "用户在本轮任务执行过程中追加了以下指引。请立即调整方向，"
        "优先遵循这些指引，不要忽略。这不是新开对话。\n\n"
        f"{body}"
    )


__all__ = [
    "push_steer",
    "drain_steers",
    "pending_count",
    "clear_steers",
    "format_steer_block",
]
