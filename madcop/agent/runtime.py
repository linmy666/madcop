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

from madcop.llm.client import Message


# ─── Step Types ──────────────────────────────────────────────────────────────


class StepKind(str, Enum):
    """The unified event kinds. Maps 1:1 to frontend SSE handlers."""

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

    # P3-A — memory/skill side-channel events (parity with legacy /api/chat).
    # These carry structured metadata in `metadata` rather than `content`.
    MEMORY_RECALL = "memory_recall"
    SKILL_DISTILLED = "skill_distilled"
    # v4-2 — auto-generated session title after the first exchange.
    SESSION_TITLE = "session_title"

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
    agent_mode: str = "standard"  # quick | standard | deep | create
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
    """Direct LLM call with optional single tool invocation.

    P2-NS — quick mode (without this fix) called the LLM without any
    tools, so users got hallucinated responses like "I can't search the
    web" for time-sensitive queries. Now we pass tool_schemas to the LLM
    so it knows what's available, and if the model chooses to call a
    tool, we execute it once and feed the result back. One-step only —
    anything complex should switch to standard mode.
    """

    def run(self, ctx: RunContext) -> Iterator[AgentStep]:
        try:
            # 1) First call: stream with tools. The LLM client may emit
            # tool_call_deltas (incremental) during streaming rather than
            # a complete tool_call object at the end, so we accumulate.
            raw_text = ""
            tc_args_acc = ""
            tc_name: str | None = None
            tc_id: str | None = None
            if hasattr(ctx.client, "stream"):
                for chunk in ctx.client.stream(
                    ctx.messages,
                    model=ctx.model,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                    tools=ctx.tool_schemas or None,
                ):
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        raw_text += text
                        yield AgentStep(kind=StepKind.TEXT_DELTA, content=text)
                    # Process streaming tool-call deltas (Anthropic-style).
                    for d in (getattr(chunk, "tool_call_deltas", None) or ()):
                        if not isinstance(d, dict):
                            continue
                        if d.get("id"):
                            tc_id = d["id"]
                        if d.get("name"):
                            tc_name = d["name"]
                        if d.get("arguments"):
                            tc_args_acc += d["arguments"]
                    # Non-streaming fallback (some clients only emit at the end).
                    end_tc = getattr(chunk, "tool_call", None)
                    if end_tc is not None:
                        if hasattr(end_tc, "name"):
                            tc_name = end_tc.name
                            tc_args_acc = (
                                json.dumps(end_tc.arguments, ensure_ascii=False)
                                if not isinstance(end_tc.arguments, str)
                                else end_tc.arguments
                            )
                        elif isinstance(end_tc, dict):
                            tc_name = end_tc.get("function", {}).get("name") or tc_name
                            a = end_tc.get("function", {}).get("arguments")
                            if a:
                                tc_args_acc = a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)
                    fr = getattr(chunk, "finish_reason", None)
                    if fr:
                        break
            else:
                resp = ctx.client.chat(
                    ctx.messages,
                    model=ctx.model,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                    tools=ctx.tool_schemas or None,
                )
                raw_text = getattr(resp, "content", "") or str(resp)
                if raw_text:
                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=raw_text)
                # Some non-streaming clients return a list of tool_calls.
                tcs = getattr(resp, "tool_calls", None) or []
                if tcs:
                    first = tcs[0]
                    tc_name = getattr(first, "name", None) or first.get("function", {}).get("name")
                    a = getattr(first, "arguments", None) or first.get("function", {}).get("arguments")
                    tc_args_acc = a if isinstance(a, str) else json.dumps(a or {}, ensure_ascii=False)

            # 2) If the LLM requested a tool and we have a tool_executor,
            # run it once and feed the result back.
            if tc_name and ctx.tool_executor:
                tool_use_id = tc_id or f"qtool-{uuid.uuid4().hex[:8]}"
                try:
                    args_dict = json.loads(tc_args_acc) if tc_args_acc else {}
                except Exception:
                    args_dict = {"raw": tc_args_acc or ""}
                yield AgentStep(
                    kind=StepKind.TOOL_START,
                    tool_name=tc_name,
                    tool_input=args_dict,
                    tool_use_id=tool_use_id,
                )
                try:
                    tool_result = ctx.tool_executor(
                        tc_name, json.dumps(args_dict, ensure_ascii=False), ctx.work_dir
                    )
                    result_text = (
                        getattr(tool_result, "content", None)
                        or (tool_result if isinstance(tool_result, str) else json.dumps(tool_result, ensure_ascii=False, default=str))
                    )
                except Exception as _te:
                    result_text = f"[tool error: {_te}]"
                yield AgentStep(
                    kind=StepKind.TOOL_END,
                    tool_name=tc_name,
                    tool_use_id=tool_use_id,
                    tool_result=result_text[:2000],
                )
                # 3) Follow-up call: stream final answer with the tool
                # result in the conversation so the LLM can use it.
                follow_up = list(ctx.messages) + [
                    Message(role="user", content=(
                        f"Tool `{tc_name}` returned:\n\n{result_text[:2000]}\n\n"
                        "Respond based on this data. If the tool didn't help, "
                        "answer with what you know."
                    )),
                ]
                if hasattr(ctx.client, "stream"):
                    for chunk in ctx.client.stream(
                        follow_up,
                        model=ctx.model,
                        temperature=ctx.temperature,
                        max_tokens=ctx.max_tokens,
                    ):
                        text = getattr(chunk, "text", "") or ""
                        if text:
                            yield AgentStep(kind=StepKind.TEXT_DELTA, content=text)
                else:
                    resp2 = ctx.client.chat(
                        follow_up,
                        model=ctx.model,
                        temperature=ctx.temperature,
                        max_tokens=ctx.max_tokens,
                    )
                    text = getattr(resp2, "content", "") or str(resp2)
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
        elif mode == "create":
            from .creation import CreationEngine
            return CreationEngine()
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
