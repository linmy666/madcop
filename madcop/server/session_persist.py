"""Shared session/message persistence helpers for SSE + WebSocket chat paths.

Keeps message IDs stable across frontend ↔ backend so branch/rewind can
locate transcript rows by the same id the UI already holds.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Re-export caps from compat when available; fall back to safe defaults.
try:
    from madcop.server.madcop_compat import (
        _MAX_SESSION_MESSAGES,
        _MAX_MESSAGE_CONTENT_CHARS,
        _MESSAGES,
        _SESSIONS,
        _PERSIST_LOCK,
    )
except Exception:  # pragma: no cover — import cycle during early boot
    _MAX_SESSION_MESSAGES = 2_000
    _MAX_MESSAGE_CONTENT_CHARS = 500_000
    _MESSAGES: dict[str, list[dict[str, Any]]] = {}
    _SESSIONS: dict[str, dict[str, Any]] = {}
    import threading
    _PERSIST_LOCK = threading.RLock()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cap_content(content: str | None) -> str:
    text = content or ""
    if len(text) > _MAX_MESSAGE_CONTENT_CHARS:
        return text[:_MAX_MESSAGE_CONTENT_CHARS]
    return text


def _bound_session(session_id: str) -> None:
    msgs = _MESSAGES.get(session_id)
    if msgs is not None and len(msgs) > _MAX_SESSION_MESSAGES:
        _MESSAGES[session_id] = msgs[-_MAX_SESSION_MESSAGES:]


def ensure_session(
    session_id: str,
    *,
    title: str = "New Session",
    work_dir: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """Create or refresh an in-memory session record."""
    now = _now_iso()
    with _PERSIST_LOCK:
        if session_id not in _SESSIONS:
            _SESSIONS[session_id] = {
                "id": session_id,
                "title": title or "New Session",
                "createdAt": now,
                "modifiedAt": now,
                "messageCount": 0,
                "projectPath": project_path or work_dir or "",
                "workDir": work_dir,
                "workDirExists": bool(work_dir),
            }
        sess = _SESSIONS[session_id]
        sess["modifiedAt"] = now
        if work_dir:
            sess["workDir"] = work_dir
            sess["projectPath"] = project_path or work_dir
        if title and (not sess.get("title") or sess.get("title") in ("New Session", "新对话", "")):
            sess["title"] = title
        _MESSAGES.setdefault(session_id, [])
        return sess


def append_message(
    session_id: str,
    *,
    msg_type: str,
    content: str,
    msg_id: str | None = None,
    model: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one message, preferring a client-supplied ``msg_id``.

    Returns the stored entry (including the final id).
    """
    entry: dict[str, Any] = {
        "id": (msg_id or "").strip() or uuid.uuid4().hex,
        "type": msg_type,
        "content": _cap_content(content),
        "timestamp": _now_iso(),
    }
    if model:
        entry["model"] = model
    if extra:
        for k, v in extra.items():
            if k not in entry and v is not None:
                entry[k] = v

    with _PERSIST_LOCK:
        ensure_session(session_id)
        _MESSAGES.setdefault(session_id, []).append(entry)
        _bound_session(session_id)
        if session_id in _SESSIONS:
            _SESSIONS[session_id]["messageCount"] = len(_MESSAGES[session_id])
            _SESSIONS[session_id]["modifiedAt"] = entry["timestamp"]
    return entry


def append_user_and_ensure(
    session_id: str,
    content: str,
    *,
    msg_id: str | None = None,
    title_hint: str = "",
    work_dir: str | None = None,
) -> dict[str, Any]:
    title = (title_hint or content or "New Session")[:40]
    ensure_session(session_id, title=title, work_dir=work_dir)
    return append_message(
        session_id,
        msg_type="user",
        content=content,
        msg_id=msg_id,
    )


def append_assistant(
    session_id: str,
    content: str,
    *,
    msg_id: str | None = None,
    model: str = "",
) -> dict[str, Any]:
    return append_message(
        session_id,
        msg_type="assistant",
        content=content,
        msg_id=msg_id,
        model=model,
    )
