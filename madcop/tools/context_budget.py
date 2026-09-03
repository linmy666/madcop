"""get_context_remaining — codex parity (tools/handlers/get_context_remaining.rs).

A tiny self-pacing tool: the model can ask how much of the context
window is left and decide to wrap up, stop starting new subtasks, or
tell the user to continue in a fresh session — instead of running into
a provider overflow mid-artifact. Reads the usage the engine already
records per session (madcop.agent.usage_store).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000


class GetContextRemainingTool:
    """Report remaining context tokens for the current session."""

    name = "get_context_remaining"
    description = (
        "Get the remaining tokens in the current context window. "
        "Call this before starting a large subtask (e.g. writing a long "
        "file) when the conversation is already long; if few tokens "
        "remain, wrap up and hand off to the user instead of starting "
        "new work."
    )

    def __init__(
        self,
        session_id: str = "",
        context_window: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
        usage_getter: Callable[[str], dict[str, int] | None] | None = None,
    ) -> None:
        self._session_id = session_id or ""
        self._window = int(context_window)
        self._usage_getter = usage_getter or self._default_getter

    @staticmethod
    def _default_getter(session_id: str) -> dict[str, int] | None:
        try:
            from madcop.agent.usage_store import get_usage
            return get_usage(session_id)
        except Exception:  # noqa: BLE001
            return None

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def __call__(self, **_kwargs: Any) -> dict[str, Any]:
        usage = self._usage_getter(self._session_id) or {}
        prompt = int(usage.get("prompt_tokens") or 0)
        left = max(0, self._window - prompt)
        return {
            "tokens_left": left,
            "context_window": self._window,
            "prompt_tokens": prompt,
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "note": (
                "tokens_left 为估算（上次调用 prompt_tokens 与窗口上限之差）。"
                "偏小时应收敛任务，不要开启新的子任务。"
                if left < self._window * 0.25
                else ""
            ),
        }

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


__all__ = ["GetContextRemainingTool", "DEFAULT_CONTEXT_WINDOW_TOKENS"]
