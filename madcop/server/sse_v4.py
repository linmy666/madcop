"""
v4.0 — Unified SSE emitter.

The single point where AgentStep objects become SSE `data:` lines.
No mode-specific logic here — all three engines output AgentStep,
and this class just serialises them.
"""

from __future__ import annotations

import json
from typing import Any

from ..agent.runtime import AgentStep


class SSEEmitter:
    """Convert AgentStep → SSE string. Adds event IDs and keepalives."""

    def __init__(self):
        self._event_id = 0

    def emit(self, step: AgentStep) -> str:
        """Serialise one step to an SSE data line."""
        self._event_id += 1
        return step.to_sse(event_id=self._event_id)

    def keepalive(self) -> str:
        """SSE comment line (no data, just keeps connection alive)."""
        return ": keepalive\n\n"

    def error(self, message: str) -> str:
        """Emit a terminal error event."""
        self._event_id += 1
        data = {"kind": "error", "content": message, "id": self._event_id}
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def done(self, model: str = "") -> str:
        """Emit a terminal done event."""
        self._event_id += 1
        data = {"kind": "done", "model": model, "id": self._event_id}
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


__all__ = ["SSEEmitter"]
