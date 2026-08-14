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

from fastapi import APIRouter, Request
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
    """Get the active LLM client."""
    from madcop.config.settings import load_settings, get_active_client_config
    from madcop.llm.client import OpenAICompatClient
    settings = load_settings()
    cfg = get_active_client_config(settings)
    if not cfg:
        raise RuntimeError("No active LLM provider configured")
    from madcop.config.settings import _decrypt
    # Find the provider to decrypt key
    for p in settings.providers:
        if p.provider_id == settings.active_provider:
            key = _decrypt(p.api_key)
            return OpenAICompatClient(
                api_key=key,
                base_url=p.base_url,
                model=p.model,
            )
    raise RuntimeError(f"Active provider '{settings.active_provider}' not found")


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
    messages = [
        Message(role=m.get("role", "user"), content=m.get("content", ""))
        for m in body.get("messages", [])
    ]
    agent_mode = body.get("agent_mode") or "standard"
    model = body.get("model") or None
    work_dir = body.get("work_dir")
    session_id = body.get("conversation_id") or ""

    # v4-5 — context compaction: if the conversation is very long (>20
    # messages or >30k chars), keep the system prompt + last N messages
    # and summarize the middle into a compact block. This prevents token
    # overflow on long sessions. Mirrors legacy app.py:1939-1959.
    _total_chars = sum(len(m.content or "") for m in messages)
    if len(messages) > 20 or _total_chars > 30000:
        _keep_first = 2   # system + first user
        _keep_last = 12   # recent context
        if len(messages) > _keep_first + _keep_last:
            _head = messages[:_keep_first]
            _tail = messages[-_keep_last:]
            _middle = messages[_keep_first:-_keep_last]
            _summary_parts = []
            for m in _middle:
                role = m.role or "user"
                content = (m.content or "")[:200]
                _summary_parts.append(f"[{role}] {content}")
            _compact = Message(
                role="user",
                content=f"--- 对话摘要 (前 {len(_middle)} 条消息已压缩) ---\n"
                        + "\n".join(_summary_parts)
                        + "\n--- 最近对话 ---",
            )
            messages = [*_head, _compact, *_tail]

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

    # Build system prefix from memory (same as old handler)
    sys_prefix = ""
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
                    "ONE tool call only — for complex multi-step tasks, tell "
                    "the user to switch to standard mode."
                )
        except Exception:
            pass

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

    # Set up tool executor as a callable for ReActEngineV4.
    # Return the structured ToolResult so the engine can branch on
    # is_validation_error / is_timeout / needs_confirmation flags for
    # the SSE tool_end event metadata.
    def tool_call(name: str, raw_input: str, wd: str | None = None):
        return tool_executor.execute(name, raw_input, wd)

    ctx.tool_executor = tool_call

    # Meta-Harness: load active harness knobs and apply them. This connects
    # the ChatTaskHarness (memory budgets, tool policies, compaction threshold)
    # to the live chat path — previously the knobs existed but weren't wired in.
    try:
        from madcop.meta_harness.task_harness import load_active_harness
        _harness = load_active_harness()
        # Apply tool policy (allowlist / max_tools / enable)
        ctx.tool_schemas = _harness.filter_tool_schemas(ctx.tool_schemas)
        # Apply compaction threshold
        if _harness.compact_threshold_messages:
            _compact_threshold = _harness.compact_threshold_messages
        logger.info("meta-harness active: %s (tools=%d, compact=%d)",
                    _harness.name, len(ctx.tool_schemas), _harness.compact_threshold_messages)
    except Exception as _e:
        logger.debug("meta-harness not loaded: %s", _e)

    # HITL confirmation bridge: when the engine calls confirm_handler,
    # we register a concurrent.futures.Future in _PENDING_CONFIRMS, yield
    # a TOOL_CONFIRM_REQUEST event to the frontend, and block until the
    # user responds via POST /api/v4/chat/confirm (which sets the future).
    # We use concurrent.futures.Future (NOT asyncio.Future) because:
    #   1. The worker thread blocks on fut.result(timeout=120) — only
    #      concurrent.futures.Future supports the timeout param.
    #   2. The POST route runs in the event loop thread, so it uses
    #      fut.set_result() which is thread-safe on concurrent.futures.
    def confirm_handler(tool_name: str, tool_input: dict, tool_use_id: str) -> bool:
        """Block until the user responds to the confirmation card."""
        fut: concurrent.futures.Future = concurrent.futures.Future()
        _PENDING_CONFIRMS[tool_use_id] = fut
        try:
            return fut.result(timeout=120)
        except concurrent.futures.TimeoutError:
            return False  # timeout = reject
        finally:
            _PENDING_CONFIRMS.pop(tool_use_id, None)

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

                # v4-1: persist assistant text collected during plan.
                if session_id and _plan_thread_result:
                    # The last item should be the 'text' event. Persist it.
                    pass  # TODO: collect text from events

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
                        if _first_text:
                            _llm = ctx.client
                            if _llm and hasattr(_llm, "chat"):
                                _tp = (
                                    "Generate a concise 3-6 word title (same language "
                                    "as the conversation). Return ONLY the title.\n\n"
                                    f"User: {_latest_user[:300]}\n\n"
                                    f"Assistant: {_first_text[:300]}\n\nTitle:"
                                )
                                _tr = _llm.chat(
                                    [Message(role="system", content="Title generator."),
                                     Message(role="user", content=_tp)],
                                    model=model, temperature=0.3, max_tokens=30,
                                )
                                _title = (getattr(_tr, "content", "") or "").strip().strip('"').strip("'")
                                if _title and len(_title) <= 60:
                                    update_session_title(session_id, _title)
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
            cancel_flag = threading.Event()
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

            def worker():
                try:
                    for step in engine.run(ctx):
                        if cancel_flag.is_set():
                            break
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
                except Exception as e:
                    q.put(AgentStep(kind=StepKind.ERROR, content=str(e)))
                finally:
                    # v4-1/2/3 — persist messages + generate title + complete
                    # trace INSIDE the worker thread, before the sentinel.
                    # This runs even if the SSE client disconnects after
                    # receiving `done`, because the thread is joined in the
                    # finally block below.

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
                    if session_id and _latest_user and _at:
                        try:
                            _llm = ctx.client
                            if _llm and hasattr(_llm, "chat"):
                                from madcop.llm.client import Message as _Msg
                                _tp = (
                                    "Generate a concise 3-6 word title (same language as "
                                    "the conversation). Return ONLY the title.\n\n"
                                    f"User: {_latest_user[:300]}\n\n"
                                    f"Assistant: {_at[:300]}\n\nTitle:"
                                )
                                _tr = _llm.chat(
                                    [_Msg(role="system", content="Title generator."),
                                     _Msg(role="user", content=_tp)],
                                    model=model, temperature=0.3, max_tokens=30,
                                )
                                _title = (getattr(_tr, "content", "") or "").strip().strip('"').strip("'")
                                if _title and len(_title) <= 60:
                                    from madcop.server.session_persist import update_session_title
                                    update_session_title(session_id, _title)
                        except Exception:
                            pass
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
                            metadata={"citations": _deduped},
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


__all__ = ["router", "chat_v4"]
