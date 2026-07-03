"""v2.6.3.3 — ClarifyTool: ask the user a clarifying question with options.

This tool is special: when the LLM calls it, the backend forwards
the question + options to the UI as a `clarification_request` event,
and the LLM's turn is paused until the user clicks an option. The
user's response is then sent back as a `clarification_response`
message, and the LLM continues from where it left off.

The tool's __call__ never actually runs in the normal way — the
chat handler intercepts the call, sends the event, and returns a
ToolResult with a `__clarify__` marker that tells the synthesis
step to wait for the user's response.
"""
from __future__ import annotations

import json
from typing import Any

from .registry import Tool, ToolResult


class ClarifyTool(Tool):
    """Ask the user a clarifying question with up to N options.

    The LLM should call this when it can't proceed without more
    information from the user. Common cases:
    - Weather query: "Which city?"
    - File operation: "Which file?"
    - Code refactor: "What style?"
    """

    name = "ask_user"
    description = (
        "Ask the user a clarifying question with a list of options. "
        "Use this when you need more information from the user before "
        "you can answer. Provide 2-6 short options the user can pick. "
        "The user will see the question and click an option; their "
        "selection will be sent back to you as a regular user message."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "The question to show the user. Keep it short "
                        "(under 30 chars) and conversational. "
                        "Examples: 'Which city?', 'Which file?', 'What time period?'"
                    ),
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 6,
                    "description": (
                        "2-6 short options the user can choose from. "
                        "Each option should be under 20 chars. "
                        "The user's selection is sent back as plain text."
                    ),
                },
                "allow_free_text": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "If true, the user can also type a custom "
                        "response instead of picking an option."
                    ),
                },
            },
            "required": ["question", "options"],
        }

    def __call__(self, **kwargs: Any) -> ToolResult:
        """This is intercepted by the chat handler. We never actually
        run normally — the handler detects `name == "ask_user"` and
        pauses the loop, sends the clarification event, and waits
        for the user's response. This __call__ only runs as a
        safety fallback (and returns a marker that the synthesis
        step can interpret)."""
        return ToolResult(
            tool_name=self.name,
            output=json.dumps({
                "__clarify_pending__": True,
                "question": kwargs.get("question", ""),
                "options": kwargs.get("options", []),
            }, ensure_ascii=False),
        )


__all__ = ["ClarifyTool"]