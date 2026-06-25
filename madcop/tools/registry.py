"""L7 — Tool registry.

A `Tool` is a JSON-schema-described function the LLM can request to
call. The `ToolRegistry` collects tools and dispatches `ToolCall`s
to the matching implementation.

This is the minimum viable tool-use surface — enough for an agent to
do useful things like "lookup SKU info" or "send Slack alert". MCP
servers plug in by mapping their tool list into this format.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from ..llm import ToolCall


# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ToolResult:
    """The result of executing a tool."""
    tool_name: str
    output: Any
    error: str | None = None

    def to_message_content(self) -> str:
        """Format for LLM tool-result message."""
        if self.error is not None:
            return f"ERROR: {self.error}"
        if isinstance(self.output, str):
            return self.output
        return json.dumps(self.output, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------- #
# Tool ABC
# --------------------------------------------------------------------------- #

class Tool(ABC):
    """A callable tool the LLM can invoke."""

    name: str
    description: str

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON schema for the tool's parameters."""
        raise NotImplementedError

    @abstractmethod
    def __call__(self, **kwargs: Any) -> Any:
        """Execute the tool with the given arguments."""
        raise NotImplementedError

    def to_openai_schema(self) -> dict[str, Any]:
        """Format as an OpenAI tool descriptor."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


# --------------------------------------------------------------------------- #
# Function-tool helper
# --------------------------------------------------------------------------- #

class FunctionTool(Tool):
    """Wrap a plain Python function as a Tool. Args are introspected from
    the function signature. No automatic schema generation (we keep it
    explicit) — pass schema dict at construction.
    """

    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[..., Any],
        parameters_schema: dict[str, Any],
    ):
        self.name = name
        self.description = description
        self._fn = fn
        self._schema = parameters_schema

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return self._schema

    def __call__(self, **kwargs: Any) -> Any:
        return self._fn(**kwargs)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class ToolRegistry:
    """Holds a set of tools and dispatches LLM tool calls to them."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def dispatch(self, call: ToolCall) -> ToolResult:
        try:
            tool = self.get(call.name)
        except KeyError as e:
            return ToolResult(tool_name=call.name, output=None, error=str(e))
        try:
            output = tool(**call.arguments)
        except Exception as e:  # noqa: BLE001
            return ToolResult(tool_name=call.name, output=None, error=f"{type(e).__name__}: {e}")
        return ToolResult(tool_name=call.name, output=output)


# --------------------------------------------------------------------------- #
# Built-in tools (so demos work out-of-the-box)
# --------------------------------------------------------------------------- #

class EchoTool(Tool):
    """A toy tool that echoes its input. Useful for demos + tests."""

    name = "echo"
    description = "Echoes the input string back."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
            },
            "required": ["text"],
        }

    def __call__(self, **kwargs: Any) -> str:
        return str(kwargs.get("text", ""))


class GetTimeTool(Tool):
    """Return the current UTC time. Pure, no side effects."""

    name = "get_current_time"
    description = "Returns the current UTC timestamp in ISO 8601 format."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def __call__(self, **kwargs: Any) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "EchoTool",
    "FunctionTool",
    "GetTimeTool",
    "Tool",
    "ToolRegistry",
    "ToolResult",
]