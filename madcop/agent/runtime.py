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


# ─── <think> tag separator ──────────────────────────────────────────────────
# Models like MiniMax-M3, DeepSeek-R1, Qwen-QwQ put their reasoning inside
# <think>...</think> tags in the CONTENT stream (not in a separate
# reasoning_content field). This separator splits incoming text deltas into
# reasoning (inside <think>) vs answer (outside), so the frontend can show
# the reasoning process in a collapsible "thinking" block — exactly like
# Claude / Cursor / Co-Work do — instead of hiding it or dumping it raw.
#
# Usage: create one ThinkSeparator per engine run, feed each text chunk via
# .feed(text), and route the returned (reasoning, answer) to THOUGHT_DELTA /
# TEXT_DELTA respectively. The separator buffers across chunk boundaries so
# a split "</thi" + "nk>" is handled correctly.

class ThinkSeparator:
    """Stateful <think> tag splitter for streaming text.

    feed(chunk) → (reasoning_text, answer_text)
    Both may be empty. Call flush() at the end to drain the buffer.
    Manages thought block lifecycle: emits nothing itself (the caller does
    yield THOUGHT_START/END based on _in_think transitions).
    """

    def __init__(self):
        self._buf = ""
        self._in_think = False  # currently inside <think> block?
        self._thought_started = False  # have we emitted thought_start?

    @property
    def in_think(self) -> bool:
        return self._in_think

    def feed(self, chunk: str) -> tuple[str, str]:
        """Process a text chunk. Returns (reasoning, answer) strings."""
        self._buf += chunk
        reasoning_parts: list[str] = []
        answer_parts: list[str] = []

        while self._buf:
            if self._in_think:
                # Look for closing </think>
                idx = self._buf.find("</think>")
                if idx != -1:
                    # Found closing tag
                    reasoning_parts.append(self._buf[:idx])
                    self._buf = self._buf[idx + 8:]  # skip past </think>
                    self._in_think = False
                    continue
                # No closing tag found. Check if the buffer ENDS with a
                # partial "</think>" prefix — if so, hold those chars back
                # and output the rest immediately. This keeps reasoning
                # streaming live instead of buffering everything.
                hold = 0
                close_tag = "</think>"
                for n in range(min(len(close_tag) - 1, len(self._buf)), 0, -1):
                    if self._buf.endswith(close_tag[:n]):
                        hold = n
                        break
                safe = self._buf[:len(self._buf) - hold] if hold < len(self._buf) else ""
                if safe:
                    reasoning_parts.append(safe)
                    self._buf = self._buf[len(safe):]
                break  # wait for more data
            else:
                # Look for opening <think>
                idx = self._buf.find("<think>")
                if idx != -1:
                    # Found opening tag
                    before = self._buf[:idx]
                    if before:
                        answer_parts.append(before)
                    self._buf = self._buf[idx + 7:]  # skip past <think>
                    self._in_think = True
                    self._thought_started = True
                    continue
                # No opening tag. Check for partial "<think>" prefix at end.
                hold = 0
                open_tag = "<think>"
                for n in range(min(len(open_tag) - 1, len(self._buf)), 0, -1):
                    if self._buf.endswith(open_tag[:n]):
                        hold = n
                        break
                safe = self._buf[:len(self._buf) - hold] if hold < len(self._buf) else ""
                if safe:
                    # Strip leading whitespace/newlines right after </think>
                    if self._thought_started:
                        stripped = safe.lstrip("\n\r")
                        if stripped:
                            answer_parts.append(stripped)
                            self._thought_started = False
                    else:
                        answer_parts.append(safe)
                    self._buf = self._buf[len(safe):]
                break

        return ("".join(reasoning_parts), "".join(answer_parts))

    def flush(self) -> tuple[str, str]:
        """Drain any remaining buffer (call at end of stream)."""
        remaining = self._buf
        self._buf = ""
        if self._in_think:
            # Stream ended inside <think> — treat the rest as reasoning
            return (remaining, "")
        # Outside think — might have trailing answer text (e.g. model ended
        # without closing tag, or leftover whitespace after </think>)
        if remaining and self._thought_started:
            remaining = remaining.lstrip("\n\r")
            self._thought_started = False
        return ("", remaining)


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
    # HITL: request user confirmation before executing a mutating tool.
    # Frontend shows an inline approval card; user responds via
    # POST /api/v4/chat/confirm → confirm_handler returns True/False.
    TOOL_CONFIRM_REQUEST = "tool_confirm_request"
    # Real-time preview: emitted after a successful write_file/edit_file
    # whose target lives in ~/.madcop/preview/ (or is an HTML file).
    # Frontend auto-opens the workbench panel in browser mode and
    # debounce-reloads the preview iframe.
    PREVIEW_UPDATE = "preview_update"
    # Long-task liveness: emitted while the model is still STREAMING
    # tool-call arguments (e.g. a 20KB write_file payload takes minutes
    # to compose). Frontend shows "composing… N KB" on the pending
    # card so the user sees forward motion instead of a frozen spinner.
    TOOL_PROGRESS = "tool_progress"

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
    # MEA task mode: plan stepper updates for the task monitor panel.
    # Carries the full plan object in `metadata.plan` + step status in
    # `metadata.step` so the frontend's existing plan/plan_step handlers
    # can render the Step N/M progress UI.
    PLAN = "plan"

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

    # HITL confirmation: when set, mutating tools (write_file/edit_file/
    # bash etc.) will call this BEFORE executing. Returns True=approved,
    # False=rejected. When None, all tools execute immediately (yolo).
    # The handler is called from the worker thread and should BLOCK until
    # the user responds (the SSE bridge handles async fan-out).
    confirm_handler: Callable[[str, dict, str], bool] | None = None

    # System prompt prefix (extra rules injected by chat handler)
    system_prefix: str = ""

    # Conversation history as context text
    context: str = ""

    # P2-12: optional HookChain (Pre/PostToolUse veto / rewrite /
    # observe). None = no hooks = identical baseline behavior.
    hooks: Any = None

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

    @staticmethod
    def _with_system_prefix(ctx: RunContext) -> list:
        """Return ctx.messages with ctx.system_prefix merged in.

        Behavior:
          - If there is no system_prefix: return the original list unchanged.
          - If the first message is already a system role: prepend the prefix
            to its content (so we don't clobber any existing instructions).
          - Otherwise: insert a new system message at index 0.
        This mirrors what ReActEngineV4._build_messages does, so quick
        and standard modes get the same prompt prefix treatment.
        """
        prefix = (ctx.system_prefix or "").strip()
        if not prefix:
            return ctx.messages
        msgs = list(ctx.messages)  # don't mutate the caller's list
        if msgs and getattr(msgs[0], "role", None) == "system":
            existing = getattr(msgs[0], "content", "") or ""
            msgs[0] = Message(
                role="system",
                content=f"{prefix}\n\n{existing}".strip(),
            )
        else:
            msgs.insert(0, Message(role="system", content=prefix))
        return msgs

    def run(self, ctx: RunContext) -> Iterator[AgentStep]:
        try:
            # BUG-FIX: previously QuickEngine called client.stream(ctx.messages)
            # without ever using ctx.system_prefix — so the chat handler's
            # quick-mode tool awareness prompt (injected in chat_v4.py) was
            # never delivered to the LLM. The model had no idea web_search
            # / weather / memory were available, so it just hallucinated
            # "I can't search the web" for time-sensitive queries.
            #
            # Now we prepend ctx.system_prefix as a system message (or merge
            # into the first existing system message) before streaming.
            messages = self._with_system_prefix(ctx)
            raw_text = ""
            tc_args_acc = ""
            tc_name: str | None = None
            tc_id: str | None = None
            # Think-separator: splits <think>...</think> reasoning from the
            # answer so the frontend can show the reasoning process live
            # (like Claude/Cursor/Co-Work) instead of hiding it or dumping
            # it raw into the answer bubble.
            _think = ThinkSeparator()
            _thought_block_open = False
            if hasattr(ctx.client, "stream"):
                for chunk in ctx.client.stream(
                    messages,
                    model=ctx.model,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                    tools=ctx.tool_schemas or None,
                ):
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        raw_text += text
                        reasoning, answer = _think.feed(text)
                        # Route reasoning → THOUGHT_DELTA (visible thinking)
                        if reasoning:
                            if not _thought_block_open:
                                _thought_block_open = True
                                yield AgentStep(kind=StepKind.THOUGHT_START, thought_id="think-1")
                            yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id="think-1", content=reasoning)
                        # If we transitioned out of <think>, close the block
                        if answer and _thought_block_open and not _think.in_think:
                            yield AgentStep(kind=StepKind.THOUGHT_END, thought_id="think-1")
                            _thought_block_open = False
                        # Route answer → TEXT_DELTA
                        if answer:
                            yield AgentStep(kind=StepKind.TEXT_DELTA, content=answer)
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
                # Flush any remaining buffered text from the think separator
                r_rem, a_rem = _think.flush()
                if r_rem:
                    if not _thought_block_open:
                        _thought_block_open = True
                        yield AgentStep(kind=StepKind.THOUGHT_START, thought_id="think-1")
                    yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id="think-1", content=r_rem)
                if _thought_block_open:
                    yield AgentStep(kind=StepKind.THOUGHT_END, thought_id="think-1")
                    _thought_block_open = False
                if a_rem:
                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=a_rem)
            else:
                resp = ctx.client.chat(
                    messages,
                    model=ctx.model,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                    tools=ctx.tool_schemas or None,
                )
                raw_text = getattr(resp, "content", "") or str(resp)
                # Non-streaming: still split <think> tags for consistency.
                _think2 = ThinkSeparator()
                _tb2 = False
                reasoning, answer = _think2.feed(raw_text)
                r2, a2 = _think2.flush()
                reasoning += r2
                answer += a2
                if reasoning:
                    yield AgentStep(kind=StepKind.THOUGHT_START, thought_id="think-1")
                    yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id="think-1", content=reasoning)
                    yield AgentStep(kind=StepKind.THOUGHT_END, thought_id="think-1")
                if answer:
                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=answer)
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
                    # Models sometimes emit MULTIPLE JSON objects concatenated
                    # (parallel tool calls as text). Extract the FIRST valid
                    # {...} block — the old {"raw": ...} fallback broke
                    # web_search ("query: Field required").
                    import re as _re
                    _m = _re.search(r'\{[^{}]*\}', tc_args_acc or '', _re.DOTALL)
                    if _m:
                        try:
                            args_dict = json.loads(_m.group(0))
                        except Exception:
                            args_dict = {"query": (tc_args_acc or "")[:200]}
                    else:
                        args_dict = {"query": (tc_args_acc or "")[:200]}
                yield AgentStep(
                    kind=StepKind.TOOL_START,
                    tool_name=tc_name,
                    tool_input=args_dict,
                    tool_use_id=tool_use_id,
                )
                # HITL: if the tool is mutating AND a confirm_handler is
                # set, ask the user before executing. This lets the
                # frontend show an Accept/Reject card (with diff preview
                # for file edits) before the change is applied.
                _approved = True
                if ctx.confirm_handler:
                    try:
                        from madcop.tools.safety import needs_confirmation
                        if needs_confirmation(tc_name):
                            yield AgentStep(
                                kind=StepKind.TOOL_CONFIRM_REQUEST,
                                tool_name=tc_name,
                                tool_input=args_dict,
                                tool_use_id=tool_use_id,
                            )
                            _approved = ctx.confirm_handler(tc_name, args_dict, tool_use_id)
                    except Exception:
                        _approved = True  # on error, proceed (don't block)

                if not _approved:
                    yield AgentStep(
                        kind=StepKind.TOOL_END,
                        tool_name=tc_name,
                        tool_use_id=tool_use_id,
                        tool_result="[用户拒绝了此操作]",
                        is_error=True,
                    )
                else:
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
                # Route through ThinkSeparator — the follow-up response
                # also contains <think> blocks that must go to THOUGHT_*
                # not TEXT_DELTA.
                _fu_sep = ThinkSeparator()
                _fu_think_open = False
                _fu_tid = "fu-think"
                if hasattr(ctx.client, "stream"):
                    for chunk in ctx.client.stream(
                        follow_up,
                        model=ctx.model,
                        temperature=ctx.temperature,
                        max_tokens=ctx.max_tokens,
                    ):
                        text = getattr(chunk, "text", "") or ""
                        if not text:
                            continue
                        reasoning, answer = _fu_sep.feed(text)
                        if reasoning:
                            if not _fu_think_open:
                                _fu_think_open = True
                                yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=_fu_tid)
                            yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=_fu_tid, content=reasoning)
                        if answer:
                            if _fu_think_open and not _fu_sep.in_think:
                                yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=_fu_tid)
                                _fu_think_open = False
                            yield AgentStep(kind=StepKind.TEXT_DELTA, content=answer)
                else:
                    resp2 = ctx.client.chat(
                        follow_up,
                        model=ctx.model,
                        temperature=ctx.temperature,
                        max_tokens=ctx.max_tokens,
                    )
                    text = getattr(resp2, "content", "") or str(resp2)
                    if text:
                        # Non-streaming: feed whole response through separator
                        r, a = _fu_sep.feed(text)
                        r2, a2 = _fu_sep.flush()
                        clean_answer = (a + a2).strip()
                        if clean_answer:
                            yield AgentStep(kind=StepKind.TEXT_DELTA, content=clean_answer)
                if _fu_think_open:
                    yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=_fu_tid)

            yield AgentStep(kind=StepKind.TEXT_END)
            yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")
        except Exception as e:
            yield AgentStep(kind=StepKind.ERROR, content=str(e))


# ─── Engine Factory ──────────────────────────────────────────────────────────


class EngineFactory:
    """Create the right engine based on agent_mode.

    Mode design (product-oriented):
    - chat:    Auto-routes to Quick (simple Q&A) or ReAct (needs tools/search)
    - task:    MEA Harness loop (Manager→Executor→Auditor) for long-horizon work
    - create:  CreationEngine (search→fetch→outline→write with citations)

    Legacy modes (quick/standard/deep) are mapped for backward compat:
    - quick → QuickEngine directly
    - standard → ReActEngineV4
    - deep → ReActEngineV4 with max_steps=20
    """

    # Build-intent signals: requests to CREATE an artifact (game/site/
    # script/app). These must route to the tool-capable ReAct engine —
    # previously "做个植物大战僵尸的游戏" matched nothing and fell to
    # QuickEngine, which answered with clarifying questions and no
    # tool timeline (the single most-complained demo failure).
    BUILD_SIGNALS = [
        "做个", "做一个", "写一个", "写个", "生成一个", "生成个",
        "实现一个", "实现个", "开发一个", "开发个", "搭建", "搭一个",
        "帮我做个", "帮我写个", "做一个", "新建一个",
        "build a", "make a", "make me", "create a", "implement a",
        "write a ", "write me",
    ]

    @staticmethod
    def _should_use_tools(ctx: RunContext) -> bool:
        """Heuristic: does this query need tools (search/file/etc)?"""
        last_msg = ""
        if ctx.messages:
            last_msg = (ctx.messages[-1].content or "").lower()
        # Tool-needed signals: questions about current events, files, data
        tool_signals = [
            "最新", "搜索", "搜一下", "查一下", "今天", "现在", "当前",
            "天气", "新闻", "价格", "汇率", "latest", "search", "current",
            "文件", "读取", "修改", "创建", "file", "read", "write",
            "帮我写", "帮我做", "帮我创建", "帮我分析",
        ]
        return any(sig in last_msg for sig in tool_signals + EngineFactory.BUILD_SIGNALS)

    @staticmethod
    def create(ctx: RunContext) -> AgentEngine:
        mode = (ctx.agent_mode or "chat").lower()

        # ── New product modes ──
        if mode == "chat":
            # Auto-route: simple Q&A → Quick, needs tools → ReAct
            if EngineFactory._should_use_tools(ctx):
                from .react_v4 import ReActEngineV4
                return ReActEngineV4()
            return QuickEngine()

        elif mode == "task":
            # MEA Harness: Manager→Executor→Auditor loop for long tasks.
            # Returns AgentStep events like a normal engine.
            from madcop.harness import MadCopHarness

            class _HarnessEngineWrapper(AgentEngine):
                def __init__(self):
                    self._harness = None

                def run(self, ctx: RunContext):
                    # Pass the chat worker's session log so MEA doesn't
                    # create a duplicate orphan log (double-write fix).
                    self._harness = MadCopHarness(
                        ctx, max_steps=8,
                        shared_log=getattr(ctx, "_shared_session_log", None),
                    )
                    yield from self._harness.run()

            return _HarnessEngineWrapper()

        elif mode == "create":
            from .creation import CreationEngine
            return CreationEngine()

        # ── Legacy modes (backward compat) ──
        elif mode == "quick":
            return QuickEngine()
        elif mode == "standard":
            from .react_v4 import ReActEngineV4
            return ReActEngineV4()
        elif mode == "deep":
            from .react_v4 import ReActEngineV4
            ctx.max_steps = 20
            return ReActEngineV4()
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
