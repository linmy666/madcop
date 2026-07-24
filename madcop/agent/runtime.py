"""
v4.0 — Unified Agent Runtime.

Inspired by Grok Build's architecture:
- Channel separation (text vs reasoning vs tool calls)
- Independent thought blocks with lifecycle events
- Unified step iterator → single SSE emission path

Three engine modes share the same AgentStep output type:
- QuickEngine: direct LLM call, no tool loop
- ReActEngine: Thought→Action→Observation loop with COT enforcement
- DeepEngine: multi-specialist DAG (each specialist runs a mini-ReAct)
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Iterator, Optional


# ─── Step Types ──────────────────────────────────────────────────────────────


class StepKind(str, Enum):
    """The 10 unified event kinds. Maps 1:1 to frontend SSE handlers."""

    # Thought lifecycle (Grok-Build-style independent blocks)
    THOUGHT_START = "thought_start"
    THOUGHT_DELTA = "thought_delta"
    THOUGHT_END = "thought_end"

    # Tool lifecycle
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"

    # Answer text
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"

    # Clarification
    CLARIFY = "clarify"

    # Terminal
    ERROR = "error"
    DONE = "done"


@dataclass
class AgentStep:
    """One output unit from any engine. Serialised to one SSE event."""

    kind: StepKind
    # Thought fields
    thought_id: str = ""
    # Content (for thought_delta / text_delta / clarify)
    content: str = ""
    # Tool fields
    tool_name: str = ""
    tool_input: dict[str, Any] | None = None
    tool_result: Any = None
    tool_use_id: str = ""
    is_error: bool = False
    # Clarify fields
    question: str = ""
    options: list[str] = field(default_factory=list)
    # Metadata
    elapsed_ms: int = 0
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sse(self, event_id: int = 0) -> str:
        """Serialise to an SSE `data:` line."""
        data: dict[str, Any] = {"kind": self.kind.value}
        if self.thought_id:
            data["thought_id"] = self.thought_id
        if self.content:
            data["content"] = self.content
        if self.tool_name:
            data["tool_name"] = self.tool_name
        if self.tool_input is not None:
            data["tool_input"] = self.tool_input
        if self.tool_result is not None:
            data["tool_result"] = self.tool_result
        if self.tool_use_id:
            data["tool_use_id"] = self.tool_use_id
        if self.is_error:
            data["is_error"] = True
        if self.question:
            data["question"] = self.question
        if self.options:
            data["options"] = self.options
        if self.elapsed_ms:
            data["elapsed_ms"] = self.elapsed_ms
        if self.model:
            data["model"] = self.model
        if self.metadata:
            data["metadata"] = self.metadata
        if event_id:
            data["id"] = event_id
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─── Run Context ─────────────────────────────────────────────────────────────


@dataclass
class RunContext:
    """Everything an engine needs to execute a turn."""

    # Input
    messages: list  # list of Message objects
    model: str | None = None
    agent_mode: str = "standard"  # quick | standard | deep
    temperature: float = 0.7
    max_tokens: int = 8192
    work_dir: str | None = None
    session_id: str = ""
    conversation_id: str = ""

    # LLM client (set by factory)
    client: Any = None

    # Tool registry (set by factory)
    tool_executor: Callable[..., str] | None = None
    tool_schemas: list[dict] = field(default_factory=list)

    # System prompt prefix (extra rules injected by chat handler)
    system_prefix: str = ""

    # Conversation history as context text
    context: str = ""

    # Max ReAct steps
    max_steps: int = 12


# ─── Engine Interface ────────────────────────────────────────────────────────


class AgentEngine(ABC):
    """Base class for all execution modes. Each mode implements run()."""

    @abstractmethod
    def run(self, ctx: RunContext) -> Iterator[AgentStep]:
        """Execute one turn, yielding AgentSteps.

        This is a synchronous iterator (not async) because the
        underlying LLM client (ChatClient.chat/stream) is synchronous.
        The chat handler wraps it in run_in_executor + queue bridge.
        """
        ...


# ─── Quick Engine ────────────────────────────────────────────────────────────


class QuickEngine(AgentEngine):
    """Direct single-shot LLM call. No tool loop."""

    def run(self, ctx: RunContext) -> Iterator[AgentStep]:
        try:
            if hasattr(ctx.client, "stream"):
                for chunk in ctx.client.stream(
                    ctx.messages,
                    model=ctx.model,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                ):
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        yield AgentStep(kind=StepKind.TEXT_DELTA, content=text)
            else:
                resp = ctx.client.chat(
                    ctx.messages,
                    model=ctx.model,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                )
                text = getattr(resp, "content", "") or str(resp)
                if text:
                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=text)

            yield AgentStep(kind=StepKind.TEXT_END)
            yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")
        except Exception as e:
            yield AgentStep(kind=StepKind.ERROR, content=str(e))


# ─── Engine Factory ──────────────────────────────────────────────────────────


class EngineFactory:
    """Create the right engine based on agent_mode."""

    @staticmethod
    def create(ctx: RunContext) -> AgentEngine:
        mode = (ctx.agent_mode or "standard").lower()
        if mode == "quick":
            return QuickEngine()
        elif mode == "standard":
            from .react_v4 import ReActEngineV4
            return ReActEngineV4()
        elif mode == "deep":
            from .deep_v4 import DeepEngineV4
            return DeepEngineV4()
        else:
            return QuickEngine()


__all__ = [
    "StepKind",
    "AgentStep",
    "RunContext",
    "AgentEngine",
    "QuickEngine",
    "EngineFactory",
]
