"""
v4.0 — Unified Chat Route.

Replaces the 1700-line chat() handler in app.py with a ~150-line
version that uses the new AgentEngine + SSEEmitter + ToolExecutor.

All three modes (quick/standard/deep) share one SSE output path.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import asyncio
import concurrent.futures
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from madcop.agent.runtime import RunContext, EngineFactory, AgentStep, StepKind
from madcop.agent.tool_executor import build_default_registry
from madcop.server.sse_v4 import SSEEmitter
from madcop.llm.client import Message
from madcop.workflow.planner import (
    StepStatus,
    generate_plan,
    execute_step,
    verify_step,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# HITL confirmation bridge: maps tool_use_id → Future. The worker thread
# creates a Future and blocks on it; the POST /api/v4/chat/confirm route
# resolves it when the user clicks Approve/Reject.
_PENDING_CONFIRMS: dict[str, asyncio.Future] = {}
# P0-4 — metadata for the pending-confirm GET endpoint (session-scoped
# rehydration of HITL cards). Keyed by tool_use_id, same lifecycle as
# the futures above.
_PENDING_META: dict[str, dict] = {}

# P1-6 — per-session live context signals: last provider usage (token
# ground truth, from DONE steps) and the latest compaction checkpoint
# (for incremental UPDATE summaries). In-process only; the durable
# record lives in the session log's compaction events.
_SESSION_LAST_USAGE: dict[str, dict] = {}
_SESSION_SUMMARIES: dict[str, str] = {}


@router.get("/api/v4/chat/confirm/pending")
async def pending_confirms(conversation_id: str = "") -> dict[str, Any]:
    """Live HITL confirmations for a session (P0-4 rehydration).

    The frontend polls this when a session becomes active so cards
    survive a tab switch or a UI refresh while the turn is still
    streaming in another connection. Server-restart durability is NOT
    covered here (the turn itself dies with the process) — that lands
    with session-tree/checkpoint work.
    """
    items = [
        {
            "tool_use_id": tid,
            "conversation_id": meta.get("conversation_id", ""),
            "tool_name": meta.get("tool_name", ""),
            "tool_input": meta.get("tool_input", {}),
        }
        for tid, meta in _PENDING_META.items()
        if not conversation_id or meta.get("conversation_id") == conversation_id
    ]
    return {"pending": items}


class ConfirmRequest(BaseModel):
    """Frontend payload for responding to a tool confirmation request."""
    session_id: str = ""
    tool_use_id: str
    approved: bool


@router.post("/api/v4/chat/confirm")
async def confirm_tool(body: ConfirmRequest) -> dict[str, Any]:
    """Resolve a pending tool confirmation. Called by the frontend when
    the user clicks Approve or Reject on an inline HITL card."""
    fut = _PENDING_CONFIRMS.get(body.tool_use_id)
    if fut is None or fut.done():
        return {"ok": False, "error": "no pending confirmation for this tool_use_id"}
    # concurrent.futures.Future.set_result is thread-safe — can be called
    # from the event loop thread while the worker thread blocks on result().
    fut.set_result(body.approved)
    return {"ok": True, "approved": body.approved}


def _get_client():
    """Get the active LLM client.

    Graceful degradation: when no provider/key is configured, fall back
    to MockClient (same policy the legacy handler had) so air-gapped
    demos and tests keep working instead of hard-failing.
    """
    from madcop.config.settings import load_settings, get_active_client_config
    from madcop.llm.client import OpenAICompatClient, MockClient
    settings = load_settings()
    cfg = get_active_client_config(settings)
    if not cfg:
        logger.warning("no active LLM provider — falling back to MockClient")
        return MockClient()
    from madcop.config.settings import _decrypt
    # Find the provider to decrypt key
    for p in settings.providers:
        if p.provider_id == settings.active_provider:
            key = _decrypt(p.api_key)
            return OpenAICompatClient(
                api_key=key,
                base_url=p.base_url,
                model=p.model,
                # 300s: build tasks stream one large artifact with long
                # inter-chunk thinking pauses — the 30s class default
                # killed those streams mid-generation ("The read
                # operation timed out").
                timeout=300.0,
            )
    logger.warning("active provider missing — falling back to MockClient")
    return MockClient()




def _gen_title(session_id: str, user_text: str, assistant_text: str,
               client: Any, model: str | None) -> None:
    """Generate a concise session title via the LLM and persist it.

    Shared by the plan path and the standard worker path (previously
    two copy-pasted blocks that drifted apart).
    """
    if not (session_id and user_text and assistant_text):
        return
    if not (client and hasattr(client, "chat")):
        return
    try:
        _tp = (
            "Generate a concise 3-6 word title (same language as "
            "the conversation). Return ONLY the title.\n\n"
            f"User: {user_text[:300]}\n\n"
            f"Assistant: {assistant_text[:300]}\n\nTitle:"
        )
        _tr = client.chat(
            [Message(role="system", content="Title generator."),
             Message(role="user", content=_tp)],
            model=model, temperature=0.3, max_tokens=30,
        )
        _title = (getattr(_tr, "content", "") or "").strip().strip('"').strip("'")
        if _title and len(_title) <= 60:
            from madcop.server.session_persist import update_session_title
            update_session_title(session_id, _title)
    except Exception as _e:
        logger.debug("title gen failed: %s", _e)


def _get_settings():
    """Get active settings."""
    try:
        from ..config.settings import load_settings
        return load_settings()
    except Exception:
        return None


@router.post("/api/v4/chat")
async def chat_v4(body: dict[str, Any]) -> StreamingResponse:
    """Unified chat endpoint using the v4 engine architecture.

    Accepts the same body format as /api/chat (messages, agent_mode,
    model, temperature, etc.) but outputs v4 SSE events (kind field
    instead of type field).
    """
    # Input limits — mirror the legacy ChatRequest pydantic caps so the
    # dict-typed body can't bypass them (oversized content previously
    # returned 422; without this check it streamed straight through).
    _MAX_CONTENT = 500_000
    _MAX_MESSAGES = 200
    _MAX_DATAURL = 2_500_000
    _msgs_in = body.get("messages") or []
    if not isinstance(_msgs_in, list):
        raise HTTPException(422, "messages must be a list")
    if len(_msgs_in) > _MAX_MESSAGES:
        raise HTTPException(422, f"too many messages ({len(_msgs_in)} > {_MAX_MESSAGES})")
    for _m in _msgs_in:
        _c = (_m or {}).get("content") or ""
        if len(_c) > _MAX_CONTENT:
            raise HTTPException(422, f"message content too large ({len(_c)} > {_MAX_CONTENT})")
    for _a in body.get("attachments") or []:
        _d = (_a or {}).get("dataUrl") or ""
        if len(_d) > _MAX_DATAURL:
            raise HTTPException(422, f"attachment dataUrl too large ({len(_d)} > {_MAX_DATAURL})")

    messages = [
        Message(role=m.get("role", "user"), content=m.get("content", ""))
        for m in body.get("messages", [])
        # The system prompt is owned by the backend (memory + workspace +
        # tool instructions). Frontend-sent system messages are dropped —
        # same policy the legacy handler enforced — so a client cannot
        # override the agent's instructions.
        if m.get("role") != "system"
    ]
    agent_mode = body.get("agent_mode") or "standard"
    model = body.get("model") or None
    work_dir = body.get("work_dir")
    session_id = body.get("conversation_id") or ""

    # Phase 2c — derive the conversation context from the session log
    # (single source of truth). The request body's history is treated as
    # a fallback for old sessions that predate logging. When a log with
    # prior turns exists, REPLACE the body history with log-derived
    # messages + this turn's fresh user message. This kills the
    # three-sources-of-truth drift: what the model sees is exactly what
    # the log recorded.
    if session_id:
        try:
            from madcop.harness.core import SessionLog
            _prior = SessionLog.for_session(session_id)
            _derived = _prior.derive_messages()
            if _derived:
                _fresh_user = next(
                    (m.content for m in reversed(messages) if m.role == "user"),
                    "",
                )
                messages = [
                    Message(role=d["role"], content=d["content"]) for d in _derived
                ]
                if _fresh_user:
                    messages.append(Message(role="user", content=_fresh_user))
                logger.info(
                    "ctx from session log: %d derived msgs (+fresh user turn)",
                    len(_derived),
                )
        except Exception as _e:
            logger.debug("log-derived context unavailable, using body: %s", _e)

    # P1-6 — token-driven compaction (pi-mono design). The old policy
    # (message-count trigger + 200-char truncation of the middle)
    # destroyed long-session context quality. Now: trigger on token
    # budget (provider usage when fresh, chars/4 otherwise), summarize
    # the head into a structured checkpoint via a dedicated LLM call,
    # cut ONLY at user-message boundaries, and persist the checkpoint
    # as a `compaction` event so future derives reuse it instead of
    # re-compacting every turn.
    try:
        from madcop.agent.compaction import (
            should_compact as _should_compact,
            compact_messages as _compact_messages,
        )
        _msgs_dicts = [{"role": m.role or "user", "content": m.content or ""}
                       for m in messages]
        _last_usage = _SESSION_LAST_USAGE.get(session_id) if session_id else None
        if _should_compact(_msgs_dicts, _last_usage):
            _prev_summary = _SESSION_SUMMARIES.get(session_id, "") if session_id else ""
            _new_dicts, _record = _compact_messages(
                _msgs_dicts, _get_client(), model,
                prev_summary=_prev_summary,
            )
            if _record.get("compacted"):
                messages = [Message(role=d["role"], content=d["content"])
                            for d in _new_dicts]
                if session_id:
                    _SESSION_SUMMARIES[session_id] = _record["summary"]
                    try:
                        from madcop.harness.core import SessionLog, EventDomain, HarnessEvent
                        SessionLog.for_session(session_id).append(HarnessEvent(
                            domain=EventDomain.SYSTEM, kind="compaction",
                            content=_record["summary"],
                            metadata={"keep_tail_n": _record.get("keep_tail_n", 0)},
                        ))
                    except Exception as _e:
                        logger.debug("compaction event persist failed: %s", _e)
                logger.info(
                    "context compacted: %d→%d msgs (head %d summarized)",
                    len(_msgs_dicts), len(_new_dicts), _record.get("head_turns", 0),
                )
    except Exception as _e:
        logger.debug("compaction skipped: %s", _e)

    # P3-G — attachment injection (parity with legacy app.py:1799-1858).
    # When the user attaches files, their text content is appended to
    # the last user message as an ATTACHMENT block so the LLM can see
    # the file without calling read_file.
    attachments = body.get("attachments") or []
    if attachments and messages and messages[-1].role == "user":
        extra_parts: list[str] = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            att_name = att.get("name", "attachment")
            att_type = att.get("type", "file")
            att_path = att.get("path", "")
            att_data = att.get("dataUrl") or att.get("data") or ""
            if att_path:
                try:
                    from pathlib import Path
                    p = Path(att_path).expanduser()
                    if p.is_file() and p.stat().st_size < 500_000:
                        content = p.read_text(errors="ignore")[:8000]
                        extra_parts.append(
                            f"--- ATTACHMENT: {att_name} ({att_type}) ---\n{content}\n--- END ---"
                        )
                        continue
                except Exception:
                    pass
            if att_data and isinstance(att_data, str) and len(att_data) < 500_000:
                # dataUrl format: data:<mime>;base64,<data>
                if "," in att_data:
                    import base64
                    try:
                        raw_b64 = att_data.split(",", 1)[1]
                        decoded = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")[:8000]
                        extra_parts.append(
                            f"--- ATTACHMENT: {att_name} ({att_type}) ---\n{decoded}\n--- END ---"
                        )
                    except Exception:
                        pass
        if extra_parts:
            original = messages[-1].content or ""
            messages[-1] = Message(
                role="user",
                content=original + "\n\n" + "\n\n".join(extra_parts),
            )

    # Build tool registry with memory store
    try:
        from madcop.server.deps import get_memory_store
        mem_store = get_memory_store()
    except Exception:
        mem_store = None

    reg, tool_executor = build_default_registry(
        workspace_dir=work_dir,
        store=mem_store,
    )

    # P1-7 — prompt-cache-friendly prefix split (Claude SDK
    # exclude_dynamic_sections). The SYSTEM prompt carries only
    # session-stable content (memory persona / output style / mode
    # directives) so providers can hit their prefix cache across turns.
    # Volatile context — date/time and per-turn directives — rides on
    # the LAST USER message instead.
    _user_ctx_parts: list[str] = []
    sys_prefix = ''
    # Time awareness still matters (without it the model's internal
    # date guess leaks as 'time confusion') — but it now lives on the
    # user turn, not the system prompt.
    from datetime import datetime as _dt
    _today = _dt.now()
    _user_ctx_parts.append(
        f"[Context] Today is {_today.strftime('%A, %B %d, %Y')}. "
        f"Current time: {_today.strftime('%H:%M')}. "
        "All 'today/recent/latest' references are relative to this date."
    )
    if mem_store:
        try:
            from madcop.server.app import _build_memory_system_prompt
            sys_prefix = _build_memory_system_prompt(mem_store) or ""
        except Exception:
            pass

    # P2-3 — outputStyle from settings (default 'Learning'). Each style
    # adds a small behavioral nudge so the chosen style actually changes
    # the model's voice / verbosity.
    _output_style = body.get("output_style") or "Learning"
    _style_hints = {
        "Learning": "\n\n[Output style: Learning] Explain your reasoning step by step. Use clear examples and highlight key takeaways at the end.",
        "Concise": "\n\n[Output style: Concise] Be brief. Skip preamble, give the answer in 1-3 sentences. No bullet lists unless asked.",
        "Detailed": "\n\n[Output style: Detailed] Provide comprehensive coverage: background, edge cases, and trade-offs. Use structure when it helps.",
    }
    if _output_style in _style_hints:
        sys_prefix = (sys_prefix + _style_hints[_output_style]).strip() + "\n"

    # P2-NS — quick mode tool awareness. Without this, the LLM doesn't
    # know web_search / web_fetch / weather / memory are available, so
    # it hallucinates "I can't search the web" for time-sensitive queries.
    # The actual tool execution is handled by QuickEngine (one step only).
    #
    # BUG-FIX: previous version only said "consider emitting" — models
    # still preferred to answer in prose ("I can't search the web, here
    # are alternative ways..."). Rewrote as a hard directive: "you MUST
    # call web_search whenever the user asks about something that could
    # have changed recently".
    if agent_mode == "quick" and reg.get_all_schemas():
        try:
            _tool_names = ", ".join(
                s.get("function", {}).get("name", "?")
                for s in reg.get_all_schemas()
            )
            if _tool_names:
                sys_prefix = (
                    sys_prefix
                    + "\n[Available tools] "
                    + _tool_names
                    + "\n[Tool-use directive] This is QUICK mode. You have tools. "
                    "If the user's question involves anything time-sensitive, "
                    "current events, weather, recent news, latest version, "
                    "today/now/this-week/this-month, or any fact that could have "
                    "changed after your training cutoff, you MUST emit a tool "
                    "call (web_search / web_fetch / weather) as your FIRST output "
                    "— do NOT answer in prose first. NEVER say 'I can't search "
                    "the web' or recommend external sites — you CAN search via "
                    "the tools. After the tool returns, summarise the result. "
                    "ONE tool call only. For web_search use SHORT queries "
                    "(2-4 Chinese words like '台风 最新', NOT long sentences "
                    "like '2026年最新台风消息 西北太平洋'). Long queries return "
                    "irrelevant results. For complex multi-step tasks, tell "
                    "the user to switch to standard mode."
                )
        except Exception:
            pass

    # Build-request action bias: "做个植物大战僵尸的游戏" previously
    # produced a wall of clarifying options and zero work — the model
    # treated a build order as a requirements interview. When the user
    # asks to CREATE something, mandate immediate action with sensible
    # defaults instead. (Routing to the tool-capable ReAct engine is
    # handled by EngineFactory.BUILD_SIGNALS; this directive fixes the
    # model's *behavior* once it's there.) P1-7: per-turn directive →
    # user message, not the system prefix.
    try:
        from madcop.agent.runtime import EngineFactory
        _last_user_lc = next(
            ((m.content or "").lower() for m in reversed(messages) if m.role == "user"),
            "",
        )
        if agent_mode in ("chat", "standard") and any(
            sig in _last_user_lc for sig in EngineFactory.BUILD_SIGNALS
        ):
            _user_ctx_parts.append(
                "[Build-request directive] The user asked you to CREATE "
                "something. Do NOT ask clarifying questions — they block all "
                "progress. Pick the smallest workable scope yourself "
                "(default: one self-contained HTML file, no build step, no "
                "dependencies), state your choice in ONE short line, then "
                "call write_file to produce it right away. A working minimal "
                "version now beats questions; iterate later if asked.\n"
                "[Markdown] Use GFM tables (`| col | col |`) for status/feature "
                "tables. NEVER put a GFM table INSIDE a ```mermaid code block — "
                "mermaid's parser reads `|` as a flow-arrow label and the "
                "diagram will fail to render. Mermaid blocks are ONLY for "
                "graph/flowchart/sequence diagrams; everything else uses "
                "regular Markdown. "
                "[No decorative emoji] Do NOT use emoji in headings, list "
                "bullets, or table cells (🌀✈️🌟 etc.) — the UI is a minimal "
                "thin-line design; plain text reads cleaner. Emoji inside "
                "actual game/chat content the user asked for is fine. "
                "[No plan-endings] NEVER end your reply with a promise of "
                "future action (『让我再搜一次』『我换个关键词试试』『Let me "
                "check...』). Either actually call the tool NOW, or give the "
                "user your final answer with the information you already "
                "have. A reply that only announces what you are ABOUT to do "
                "is a failure. "
                "[Office tasks] For Excel/PPT/Word/CSV/data work: prefer "
                "writing a short Python script via bash (pandas/openpyxl/"
                "python-docx/python-pptx/matplotlib are pre-installed) — "
                "code composes what fixed APIs cannot. For a STANDARD deck "
                "or spreadsheet use the write_pptx / write_xlsx tools "
                "directly. ALWAYS verify office output by calling "
                "read_office on the generated file before telling the user "
                "it is done, and report the real absolute path."
            )
    except Exception as _e:
        logger.debug("build-intent directive skipped: %s", _e)

    # P1-7: prepend the volatile context block to the last user message
    # (single injection point for ALL engines; keeps the system prompt
    # byte-stable within a session). The block is stripped back out
    # before the log/persist layer records the user turn.
    _user_ctx_block: str = ""
    if _user_ctx_parts and messages and messages[-1].role == "user":
        _user_ctx_block = "\n\n".join(_user_ctx_parts) + "\n\n"
        messages[-1] = Message(
            role="user",
            content=_user_ctx_block + (messages[-1].content or ""),
        )

    # Build run context
    ctx = RunContext(
        messages=messages,
        model=model,
        agent_mode=agent_mode,
        work_dir=work_dir,
        session_id=session_id,
        client=_get_client(),
        tool_schemas=reg.get_all_schemas(),
        system_prefix=sys_prefix,
    )

    # P2-12: ship the two demo hooks. A future plugin layer can swap
    # this for a settings-driven chain (per-session overrides, etc.).
    try:
        from madcop.agent.hooks import HookChain, Hook, SafetyHook, FormatterHook
        ctx.hooks = HookChain(hooks=[
            Hook(name="safety:dangerous-bash",
                 event="PreToolUse",
                 fn=SafetyHook(),
                 tool_filter="bash",
                 priority=0),
            Hook(name="fmt:notice",
                 event="PostToolUse",
                 fn=FormatterHook(),
                 tool_filter="write_file",
                 priority=10),
            Hook(name="fmt:notice",
                 event="PostToolUse",
                 fn=FormatterHook(),
                 tool_filter="edit_file",
                 priority=10),
        ])
    except Exception as _e:
        logger.debug("hook chain init failed (continuing without hooks): %s", _e)
        ctx.hooks = None

    # Set up tool executor as a callable for ReActEngineV4.
    # Return the structured ToolResult so the engine can branch on
    # is_validation_error / is_timeout / needs_confirmation flags for
    # the SSE tool_end event metadata. ``pre_approved`` passes the
    # engine's HITL approval through so the executor's destructive
    # gate doesn't reject an already-user-approved call.
    def tool_call(name: str, raw_input: str, wd: str | None = None,
                  pre_approved: bool = False):
        return tool_executor.execute(name, raw_input, wd, pre_approved=pre_approved)

    ctx.tool_executor = tool_call

    # Meta-Harness: apply tool-policy knobs. (Compaction threshold is
    # consumed earlier — before compaction runs — see _compact_threshold.)
    try:
        from madcop.meta_harness.task_harness import load_active_harness
        _harness = load_active_harness()
        # Apply tool policy (allowlist / max_tools / enable)
        ctx.tool_schemas = _harness.filter_tool_schemas(ctx.tool_schemas)
        logger.info("meta-harness active: %s (tools=%d, compact=%d)",
                    _harness.name, len(ctx.tool_schemas), _compact_threshold)
    except Exception as _e:
        logger.debug("meta-harness not loaded: %s", _e)

    # HITL confirmation bridge: when the engine calls confirm_handler,
    # we register a concurrent.futures.Future in _PENDING_CONFIRMS, yield
    # a TOOL_CONFIRM_REQUEST event to the frontend, and block until the
    # user responds via POST /api/v4/chat/confirm (which sets the future).
    # We use concurrent.futures.Future (NOT asyncio.Future) because:
    #   1. The worker thread blocks on fut.result(timeout=…) — only
    #      concurrent.futures.Future supports the timeout param.
    #   2. The POST route runs in the event loop thread, so it uses
    #      fut.set_result() which is thread-safe on concurrent.futures.
    #
    # P0-4: the old blind fut.result(timeout=120) auto-REJECTED after two
    # minutes — a user still reading a large write_file card would come
    # back to a silently-rejected turn. Now we wait as long as the SSE
    # connection is alive: the poll loop wakes every 5s to check
    # `turn_cancelled` (set when the stream aborts/disconnects), so an
    # aborted turn still rejects its pending confirm promptly and the
    # worker never leaks.
    turn_cancelled = threading.Event()

    def confirm_handler(tool_name: str, tool_input: dict, tool_use_id: str) -> bool:
        """Block until the user responds, or the turn is cancelled."""
        fut: concurrent.futures.Future = concurrent.futures.Future()
        _PENDING_CONFIRMS[tool_use_id] = fut
        _PENDING_META[tool_use_id] = {
            "conversation_id": session_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "created_at": time.time(),
        }
        try:
            while True:
                try:
                    return fut.result(timeout=5.0)
                except concurrent.futures.TimeoutError:
                    if turn_cancelled.is_set():
                        return False  # turn aborted while waiting
        finally:
            _PENDING_CONFIRMS.pop(tool_use_id, None)
            _PENDING_META.pop(tool_use_id, None)

    ctx.confirm_handler = confirm_handler

    # Create engine
    engine = EngineFactory.create(ctx)

    # v4-7 — Plan-and-Execute mode: a separate engine-like flow that runs
    # alongside the normal engine. emit_plan_events returns an async generator
    # of legacy SSE events (plan/plan_step/plan_done/text/done) paralleling
    # the standard engine lifecycle.
    async def emit_plan_events():
        """Run planner → step executor → verifier loop, yielding legacy
        plan events. Uses ctx.client for LLM calls and ctx.tool_executor
        for tool calls when a step is tool-based.
        """
        # Extract latest user task.
        _task = ""
        for _m in reversed(messages):
            if _m.role == "user" and (_m.content or "").strip():
                _task = _m.content
                break
        if not _task:
            yield {"type": "plan_done", "steps": []}
            return

        # Build a planner LLM callback that uses ctx.client.
        def _plan_llm_chat(msgs: list[dict]) -> str:
            try:
                _llm = ctx.client
                if _llm is None or not hasattr(_llm, "chat"):
                    return ""
                _resp = _llm.chat(
                    [Message(role=m.get("role", "user"), content=m.get("content", "")) for m in msgs],
                    model=ctx.model, temperature=0.5,
                )
                return getattr(_resp, "content", "") or str(_resp) or ""
            except Exception as _e:
                logger.warning("plan llm call failed: %s", _e)
                return ""

        # Phase 1: generate plan.
        _plan = generate_plan(_task, llm_complete=_plan_llm_chat, max_steps=6)
        yield {"type": "plan", "plan": _plan.to_dict()}

        # Phase 2: execute + verify each step.
        _plan_clarify_queue: list[dict] = []
        for _step in _plan.steps:
            _step.status = StepStatus.IN_PROGRESS
            yield {"type": "plan_step", "step": _step.to_dict()}

            # If the step expects a tool, try to invoke it via the executor.
            if _step.tool and ctx.tool_executor:
                try:
                    _raw = ctx.tool_executor(
                        _step.tool,
                        json.dumps({"input_hint": _step.input_hint}, ensure_ascii=False),
                        ctx.work_dir,
                    )
                    _content = getattr(_raw, "content", "") or (
                        _raw if isinstance(_raw, str) else json.dumps(_raw, ensure_ascii=False, default=str)
                    )
                    _step.result = _content[:2000]
                except Exception as _te:
                    _step.result = f"[tool error: {_te}]"
            else:
                # LLM-only step.
                _step.result = execute_step(
                    _step, _plan.goal, llm_complete=_plan_llm_chat,
                )[:2000]

            # Verify.
            passed, _reason = verify_step(_step, llm_complete=_plan_llm_chat)
            _step.status = StepStatus.COMPLETED if passed else StepStatus.FAILED
            yield {"type": "plan_step", "step": _step.to_dict()}

            # Handle ask_user / clarify surfaced by the executor.
            if _plan_clarify_queue:
                for _c in _plan_clarify_queue:
                    yield {
                        "type": "clarification_request",
                        "question": _c.get("question", ""),
                        "options": _c.get("options", []),
                        "allowFreeText": True,
                        "tool_use_id": f"plan-{_step.step}",
                    }
                _plan_clarify_queue.clear()

        # Phase 3: synthesize a final text from successful steps.
        _synth = (
            f"计划「{_plan.goal}」执行完成。\n\n"
            + "\n".join(
                f"**步骤 {_s.step} ({_s.action})**：\n{(_s.result or '').strip()[:800]}"
                for _s in _plan.steps
                if _s.status == StepStatus.COMPLETED
            )
        )
        yield {"type": "text", "content": _synth}
        yield {"type": "plan_done", "steps": [s.to_dict() for s in _plan.steps]}
        yield {"type": "done", "model": ctx.model or ""}

    # SSE stream
    emitter = SSEEmitter()

    async def event_stream():
        thread = None
        _trace_root_id: str | None = None  # initialized lazily in plan/standard
        try:
            # Capture last user message once (used by memory_recall +
            # plan branches below).
            _latest_user = ""
            for m in reversed(messages):
                if m.role == "user":
                    _latest_user = m.content or ""
                    break
            # P1-7: strip the volatile [Context]/directive block we
            # prepended to the user turn — the log (turn_start) and the
            # session store must record the user's actual words only.
            if _user_ctx_block and _latest_user.startswith(_user_ctx_block):
                _latest_user = _latest_user[len(_user_ctx_block):]

            # v4-7 — Plan-and-Execute mode: a separate flow that runs the
            # planner → step executor → verifier loop and emits legacy
            # plan/plan_step/plan_done SSE events. We don't run the normal
            # engine for this mode.

            if agent_mode == "plan":
                # Persist user message + start trace (run inside thread so
                # it survives SSE disconnect — see v4-1/3).
                # Run the planner in a thread for symmetry with the engine
                # path, but emit legacy SSE events directly.
                _plan_thread_result: list[Any] = []
                _plan_thread_error: list[Exception] = []

                def _plan_worker():
                    try:
                        # Drain the async generator into a list.
                        async def _drain():
                            async for _ev in emit_plan_events():
                                _plan_thread_result.append(_ev)
                        _loop_plan = asyncio.new_event_loop()
                        try:
                            _loop_plan.run_until_complete(_drain())
                        finally:
                            _loop_plan.close()
                    except Exception as _e:
                        _plan_thread_error.append(_e)

                _plan_thread = threading.Thread(target=_plan_worker, daemon=True)
                _plan_thread.start()

                # v4-1: persist user message
                if session_id and _latest_user:
                    try:
                        from madcop.server.session_persist import append_user_and_ensure
                        append_user_and_ensure(
                            session_id, _latest_user,
                            title_hint=_latest_user[:40],
                            work_dir=work_dir,
                        )
                    except Exception:
                        pass

                # Stream events from the worker thread.
                while True:
                    if _plan_thread_error:
                        logger.warning("v4 plan thread error: %s", _plan_thread_error[0])
                        yield f"data: {json.dumps({'type': 'error', 'message': str(_plan_thread_error[0])}, ensure_ascii=False)}\n\n"
                        break
                    if not _plan_thread_result and not _plan_thread.is_alive():
                        break
                    if _plan_thread_result:
                        _ev = _plan_thread_result.pop(0)
                        yield f"data: {json.dumps(_ev, ensure_ascii=False)}\n\n"
                    else:
                        # Yield keepalive while waiting.
                        yield ": keepalive\n\n"
                        await asyncio.sleep(0.1)

                _plan_thread.join(timeout=2.0)

                # v4-1: persist the plan-mode assistant reply. Previously a
                # bare `pass` TODO — plan answers vanished on reload (only
                # the title survived). Collect the final text event and
                # persist it like any other turn.
                if session_id and _plan_thread_result:
                    _plan_answer = ""
                    for _ev in _plan_thread_result:
                        if isinstance(_ev, dict) and _ev.get("type") == "text":
                            _plan_answer = _ev.get("content", "") or _plan_answer
                    if _plan_answer:
                        try:
                            from madcop.server.session_persist import append_assistant
                            append_assistant(session_id, _plan_answer, model=model or "")
                        except Exception:
                            pass

                # v4-2: auto-generate title (threaded path).
                if session_id and _latest_user:
                    try:
                        from madcop.server.session_persist import update_session_title
                        if _plan_thread_result:
                            _t = _plan_thread_result[-1] if isinstance(_plan_thread_result[-1], dict) else {}
                        else:
                            _t = {}
                        _first_text = ""
                        for _e in _plan_thread_result:
                            if isinstance(_e, dict) and _e.get("type") == "text":
                                _first_text = _e.get("content", "")
                                break
                        _gen_title(session_id, _latest_user, _first_text,
                                   ctx.client, model)
                    except Exception:
                        pass

                # v4-3: complete trace root.
                if _trace_root_id:
                    try:
                        from madcop.agent.trace import get_trace_store
                        get_trace_store().mark_done(_trace_root_id)
                    except Exception:
                        pass

                return

            # P3-A — memory_recall: emit before the engine starts so the
            # UI can show「基于 N 条记忆回答」. Mirrors the legacy /api/chat
            # handler (app.py:1884-1894). Runs in the main thread (fast, <50ms).
            # _latest_user is computed once at the top of event_stream.
            if _latest_user and mem_store:
                try:
                    from madcop.memory.retriever_5layer import FiveLayerRetriever
                    _fr = FiveLayerRetriever(mem_store)
                    _recalls = _fr.retrieve(_latest_user, top_k=5)
                    if _recalls:
                        yield emitter.emit(AgentStep(
                            kind=StepKind.MEMORY_RECALL,
                            metadata={"memories": [
                                {"id": str(r.item.get("id", "")),
                                 "kind": r.item.get("kind", ""),
                                 "title": r.item.get("title", ""),
                                 "preview": (r.item.get("content", "") or "")[:200],
                                 "layer": r.layer}
                                for r in _recalls
                            ]},
                        ))
                except Exception as _e:
                    logger.debug("v4 memory_recall skipped: %s", _e)

            # v4-1 — persist the user message to the session store so the
            # conversation survives reloads. Mirrors legacy app.py:2074-2080.
            if session_id and _latest_user:
                try:
                    from madcop.server.session_persist import append_user_and_ensure
                    append_user_and_ensure(
                        session_id, _latest_user,
                        title_hint=_latest_user[:40],
                        work_dir=work_dir,
                    )
                except Exception as _e:
                    logger.debug("v4 session persist (user) failed: %s", _e)

            # v4-3 — trace node: create a root user_input node so
            # /api/trace/{conversation_id} returns data. Full DAG (per-tool
            # nodes) is a follow-up; this at least makes the trace view
            # non-empty.
            _trace_root_id = None
            if session_id:
                try:
                    from madcop.agent.trace import get_trace_store, TraceStatus
                    _ts = get_trace_store()
                    _tn = _ts.create_node(
                        conversation_id=session_id,
                        node_type="user_input",
                        label=_latest_user[:60],
                        input_data={"messages": len(messages), "mode": agent_mode},
                    )
                    _ts.mark_running(_tn.id)
                    _trace_root_id = _tn.id
                except Exception:
                    pass

            # Run engine in a thread (it's synchronous) and bridge to async
            q: queue.SimpleQueue = queue.SimpleQueue()
            sentinel = object()
            # P0-4: reuse the route-scoped cancel event so the HITL
            # confirm_handler's poll loop also wakes on abort/disconnect
            # (it used to be a blind 120s future timeout that silently
            # rejected cards while the user was still reading them).
            cancel_flag = turn_cancelled
            _assistant_text_holder: list[str] = [""]
            # D2 fix: in task (MEA) mode, the executor's inner TEXT_DELTAs
            # must NOT be accumulated as the turn's assistant message —
            # they're per-step fragments. Only text emitted AFTER the last
            # inner DONE is the MEA outer answer. We track the last-done
            # offset and slice when persisting.
            _last_done_len: list[int] = [0]
            _saw_done: list[bool] = [False]
            # Resume-Claim-4: collect web_search/web_fetch tool results so we
            # can attach them as citations on the DONE event — not just in
            # create mode, but in ANY mode that used web tools. This makes
            # "every conclusion carries citation traceability" true.
            _citations_holder: list[dict] = []

            # Phase 2a: SessionLog is now the persistent record of the MAIN
            # chat path (not just MEA). run_id == session_id so all turns of
            # one conversation share one log — enabling resume/fork later.
            # "model-visible ⟺ logged": every AgentStep sent over SSE is
            # also appended here.
            from madcop.harness.core import (
                SessionLog, EventDomain, HarnessEvent,
            )

            def _step_to_event(step: AgentStep) -> HarnessEvent:
                kind_val = step.kind.value if hasattr(step.kind, "value") else str(step.kind)
                # Vocabulary unification: the log's reader (derive_messages)
                # speaks MEA vocabulary (tool_call/tool_result). The engine
                # emits tool_start/tool_end. Map them so tool usage actually
                # reconstructs into derived context — previously the
                # mismatch silently voided 'model-visible ⟺ logged'.
                if kind_val.startswith("thought_"):
                    domain = EventDomain.REASONING
                elif kind_val.startswith("tool_"):
                    domain = EventDomain.TOOL
                    if kind_val == "tool_start":
                        kind_val = "tool_call"
                    elif kind_val == "tool_end":
                        kind_val = "tool_result"
                elif kind_val.startswith("text_") or kind_val == "done":
                    domain = EventDomain.ANSWER
                else:
                    domain = EventDomain.SYSTEM
                meta: dict = {}
                if getattr(step, "tool_name", None):
                    meta["tool_name"] = step.tool_name
                if getattr(step, "tool_use_id", None):
                    meta["tool_use_id"] = step.tool_use_id
                if getattr(step, "is_error", None):
                    meta["is_error"] = True
                # tool_end carries the result in tool_result — persist it
                # as the event content so derive_messages/replay can see it.
                content = step.content or ""
                if domain == EventDomain.TOOL and kind_val == "tool_result":
                    content = str(getattr(step, "tool_result", "") or "")[:2000]
                elif domain == EventDomain.TOOL and kind_val == "tool_call":
                    try:
                        import json as _json
                        content = _json.dumps(step.tool_input, ensure_ascii=False)[:500]
                    except Exception:
                        content = ""
                return HarnessEvent(
                    domain=domain,
                    kind=kind_val,
                    content=content,
                    metadata=meta,
                )

            _session_log = (
                SessionLog.for_session(session_id) if session_id else None
            )
            # Hand the log to engines via ctx so MEA reuses it instead of
            # creating a duplicate orphan log (double-write fix).
            ctx._shared_session_log = _session_log
            # P2-9: engines parent their llm/tool spans to this turn's
            # user_input root node.
            ctx._trace_root_id = _trace_root_id

            def worker():
                # P1-6: the overflow-retry path below REBINDS `engine`
                # (fresh factory after compaction) — declare it nonlocal
                # or the rebind silently makes it an unbound local.
                nonlocal engine
                try:
                    # Log the user's input as the turn's opening event so
                    # derive_messages can reconstruct the user turn.
                    if _session_log:
                        _session_log.append(HarnessEvent(
                            domain=EventDomain.SYSTEM, kind="turn_start",
                            content=_latest_user or "",
                        ))
                    # P1-6 — overflow retry: a provider context-length
                    # ERROR force-compacts the context and reruns the
                    # engine ONCE (pi's overflow recovery path).
                    _overflow_attempted = False
                    while True:
                        _overflowed = False
                        for step in engine.run(ctx):
                            if cancel_flag.is_set():
                                break
                            # Phase 2a: persist every emitted step to the log.
                            if _session_log:
                                _session_log.append(_step_to_event(step))
                            # Capture assistant text for skill distill after the run.
                            if step.kind == StepKind.TEXT_DELTA and step.content:
                                _assistant_text_holder[0] += step.content
                            elif step.kind == StepKind.DONE:
                                # D2: MEA executor emits inner DONEs (now filtered
                                # at the harness layer, but guard here too for any
                                # engine that terminates mid-run). Text after the
                                # last DONE is the authoritative outer answer.
                                _last_done_len[0] = len(_assistant_text_holder[0])
                                _saw_done[0] = True
                                # P1-6: remember the run's usage as the session's
                                # live token ground truth for compaction triggers.
                                if session_id and step.metadata.get("usage"):
                                    _SESSION_LAST_USAGE[session_id] = dict(step.metadata["usage"])
                            if step.kind == StepKind.ERROR:
                                from madcop.agent.compaction import is_overflow_error as _is_ovf
                                if _is_ovf(Exception(step.content or "")):
                                    _overflowed = True
                            # Resume-Claim-4: capture web tool results as citations
                            if step.kind == StepKind.TOOL_END and step.tool_name in ("web_search", "web_fetch"):
                                try:
                                    _raw_result = step.tool_result
                                    if isinstance(_raw_result, str):
                                        import json as _json
                                        try:
                                            _parsed = _json.loads(_raw_result)
                                        except Exception:
                                            _parsed = None
                                    else:
                                        _parsed = _raw_result
                                    # web_search returns a list of {title,url,snippet}
                                    if isinstance(_parsed, list):
                                        for _hit in _parsed:
                                            if isinstance(_hit, dict) and _hit.get("url"):
                                                _citations_holder.append({
                                                    "url": str(_hit.get("url", "")),
                                                    "title": str(_hit.get("title", "") or _hit.get("url", ""))[:120],
                                                    "snippet": str(_hit.get("snippet", ""))[:200],
                                                })
                                    # web_fetch returns {url, content}
                                    elif isinstance(_parsed, dict) and _parsed.get("url") and not _parsed.get("is_spa"):
                                        _citations_holder.append({
                                            "url": str(_parsed.get("url", "")),
                                            "title": str(_parsed.get("title", "") or _parsed.get("url", ""))[:120],
                                            "snippet": str(_parsed.get("content", ""))[:200],
                                        })
                                except Exception:
                                    pass
                            q.put(step)
                        # end of `for step in engine.run(ctx)` — overflow
                        # retry decision at the while-body level.
                        if _overflowed and not _overflow_attempted and session_id:
                            _overflow_attempted = True
                            try:
                                from madcop.agent.compaction import compact_messages as _cm
                                _dmsgs = [{"role": m.role or "user", "content": m.content or ""}
                                          for m in ctx.messages]
                                _cmsgs, _crec = _cm(
                                    _dmsgs, ctx.client, ctx.model,
                                    prev_summary=_SESSION_SUMMARIES.get(session_id, ""),
                                )
                                if _crec.get("compacted"):
                                    ctx.messages = [Message(role=d["role"], content=d["content"])
                                                    for d in _cmsgs]
                                    _SESSION_SUMMARIES[session_id] = _crec["summary"]
                                    if _session_log:
                                        _session_log.append(HarnessEvent(
                                            domain=EventDomain.SYSTEM, kind="compaction",
                                            content=_crec["summary"],
                                            metadata={"keep_tail_n": _crec.get("keep_tail_n", 0)},
                                        ))
                                    engine = EngineFactory.create(ctx)
                                    logger.info("overflow: compacted %d→%d msgs, retrying",
                                                len(_dmsgs), len(_cmsgs))
                                    continue  # retry once with the compacted ctx
                            except Exception as _oe:
                                logger.warning("overflow compaction failed: %s", _oe)
                        break  # normal exit of the retry loop
                except Exception as e:
                    q.put(AgentStep(kind=StepKind.ERROR, content=str(e)))
                finally:
                    # v4-1/2/3 — persist messages + generate title + complete
                    # trace INSIDE the worker thread, before the sentinel.
                    # This runs even if the SSE client disconnects after
                    # receiving `done`, because the thread is joined in the
                    # finally block below.

                    # Phase 2a: close the turn in the session log.
                    if _session_log:
                        try:
                            _session_log.append(HarnessEvent(
                                domain=EventDomain.SYSTEM, kind="turn_end",
                                content="",
                            ))
                        except Exception:
                            pass

                    # v4-3 — mark trace root as done.
                    if _trace_root_id:
                        try:
                            from madcop.agent.trace import get_trace_store
                            get_trace_store().mark_done(_trace_root_id)
                        except Exception:
                            pass

                    _at = _assistant_text_holder[0].strip()
                    if session_id and _at:
                        try:
                            from madcop.server.session_persist import append_assistant
                            append_assistant(session_id, _at, model=model or "")
                        except Exception:
                            pass
                    # Auto-generate title (persist to session store).
                    _gen_title(session_id, _latest_user, _at, ctx.client, model)
                    q.put(sentinel)

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()

            while True:
                try:
                    item = await asyncio.get_running_loop().run_in_executor(
                        None, lambda: q.get(timeout=30.0)
                    )
                except Exception:
                    yield emitter.keepalive()
                    continue

                if item is sentinel:
                    break

                # Resume-Claim-4: if this is the DONE event AND we collected
                # web tool results during the run, attach them as citations
                # so the user sees source traceability for search-based
                # answers (not just create mode). Dedup by URL, cap at 8.
                if isinstance(item, AgentStep) and item.kind == StepKind.DONE and _citations_holder:
                    _seen_urls = set()
                    _deduped = []
                    for _c in _citations_holder:
                        if _c["url"] and _c["url"] not in _seen_urls:
                            _seen_urls.add(_c["url"])
                            _deduped.append(_c)
                        if len(_deduped) >= 8:
                            break
                    if _deduped:
                        item = AgentStep(
                            kind=StepKind.DONE,
                            model=item.model,
                            # Keep the run's token usage (P1-5) alongside
                            # the citations we're attaching.
                            metadata={
                                "citations": _deduped,
                                **({"usage": item.metadata["usage"]}
                                   if item.metadata.get("usage") else {}),
                            },
                        )

                yield emitter.emit(item)

            # P3-A — skill_distilled: after the run, auto-distill if the
            # exchange looks valuable (mirrors legacy app.py:3037/3332/3526).
            # Note: message persistence + title generation now run inside the
            # worker thread (above) so they execute even if the SSE client
            # disconnects after `done`.
            # D2: if an inner DONE was seen (MEA mode), only the text after
            # it is the outer authoritative answer.
            _full_text = _assistant_text_holder[0]
            _assistant_text = (
                _full_text[_last_done_len[0]:].strip() if _saw_done[0]
                else _full_text.strip()
            )
            if _assistant_text and len(_assistant_text) >= 400:
                try:
                    from madcop.memory.skill_distill import auto_distill_if_valuable
                    _skill_name = auto_distill_if_valuable(_latest_user, _assistant_text)
                    if _skill_name:
                        yield emitter.emit(AgentStep(
                            kind=StepKind.SKILL_DISTILLED,
                            metadata={"skillName": _skill_name},
                        ))
                except Exception as _e:
                    logger.debug("v4 skill_distill skipped: %s", _e)

            # Resume-Claim-5: auto-grow the knowledge graph. After a
            # substantive turn, extract the topic + answer into a brain
            # node so the Knowledge Canvas literally grows with use. This
            # is what makes "understanding you better over time" true.
            if _assistant_text and len(_assistant_text) >= 600:
                try:
                    from madcop.brain.auto_extract import auto_extract_to_brain
                    _brain_slug = auto_extract_to_brain(_latest_user, _assistant_text)
                    if _brain_slug:
                        logger.info("brain graph auto-grew: slug=%s", _brain_slug)
                except Exception as _e:
                    logger.debug("brain_auto skipped: %s", _e)

        except Exception as e:
            logger.error("chat_v4 stream error: %s", e)
            yield emitter.error(str(e))
        finally:
            # Signal the worker to stop and wait briefly so tool
            # side-effects don't continue after the client disconnects.
            if thread is not None:
                cancel_flag.set()
                thread.join(timeout=2.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/v4/sessions/{session_id}/events")
async def session_events(session_id: str) -> dict[str, Any]:
    """Replay the session's event log (dsh-style trajectory).

    Returns the full JSONL event stream for the UI: thoughts, tool
    calls, and answers in temporal order. This is what history loading
    should consume — it survives reloads (unlike text-only session
    persistence, which dropped tools/thoughts).
    """
    from madcop.harness.core import SessionLog
    log = SessionLog.for_session(session_id)
    events = [
        {
            "id": e.id,
            "domain": e.domain.value,
            "kind": e.kind,
            "content": e.content,
            "metadata": e.metadata,
            "timestamp": e.timestamp,
            "parent_id": e.parent_id,
        }
        for e in log.events()
    ]
    # P2-10 — crash-recovery hint: the last turn that never closed
    # (process died mid-turn). The UI can offer "resume this turn".
    return {
        "session_id": session_id,
        "events": events,
        "unclosed_turn": log.unclosed_turn(),
    }


class ForkBody(BaseModel):
    """Fork a session: copy the log up to a boundary into a new session."""
    until_event_id: str | None = None  # None = up to the last turn_end
    new_session_id: str | None = None  # caller may pin the target id


@router.post("/api/v4/sessions/{session_id}/fork")
async def session_fork(session_id: str, body: ForkBody | None = None) -> dict[str, Any]:
    """Fork the conversation at an event boundary.

    Copies the log prefix (up to `until_event_id`, or the last complete
    turn when omitted) into a NEW session's log. The new session's
    context derives entirely from that prefix — the dsh fork primitive.
    P2-10: delegates to SessionLog.fork_session, which SNAPS the cut
    back to the last complete turn (never forks mid-turn), preserves
    event ids + the parent chain verbatim (stable replay), and records
    a forked_from lineage marker.
    """
    from madcop.harness.core import SessionLog

    body = body or ForkBody()
    src = SessionLog.for_session(session_id)
    if not src.events():
        raise HTTPException(404, f"no event log for session '{session_id}'")

    dst = SessionLog.fork_session(session_id, body.until_event_id)
    copied = len(dst.events()) - 1  # minus the forked_from marker
    if copied <= 0:
        raise HTTPException(400, "fork boundary produced an empty prefix")

    return {
        "ok": True,
        "source_session": session_id,
        "new_session_id": dst.run_id,
        "events_copied": copied,
    }


__all__ = ["router", "chat_v4"]
