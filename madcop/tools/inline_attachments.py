"""v1.0.0 — Module-level in-memory store for inline attachments sent from
the chat composer. Keyed by attachment id. Allows the Read tool to
look up an attachment's bytes when the LLM calls read_file with a
virtual "attachment://<id>" path.

Lifespan: the most recent set of attachments is kept in a ring buffer
(limit: 32). Older attachments are dropped to bound memory.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Optional


_STORE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_LIMIT = 32


def put(attachment: dict[str, Any]) -> None:
    """Register an attachment for in-memory lookup.

    Expected keys: id, name, mimeType, data (base64 dataURL or raw text).
    """
    if "id" not in attachment:
        return
    att_id = attachment["id"]
    _STORE[att_id] = attachment
    if len(_STORE) > _LIMIT:
        # Drop the oldest entry
        _STORE.popitem(last=False)


def get(att_id: str) -> Optional[dict[str, Any]]:
    """Look up an attachment by id, or None if not found."""
    return _STORE.get(att_id)


def clear() -> None:
    """Clear all stored attachments (call on session start)."""
    _STORE.clear()


def all() -> list[dict[str, Any]]:
    """Return all stored attachments (most recent first)."""
    return list(reversed(_STORE.values()))


__all__ = ["put", "get", "clear", "all"]
