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
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from madcop.agent.runtime import RunContext, EngineFactory, AgentStep, StepKind
from madcop.agent.tool_executor import build_default_registry
from madcop.server.sse_v4 import SSEEmitter
from madcop.llm.client import Message

logger = logging.getLogger(__name__)
router = APIRouter()


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

    # Create engine
    engine = EngineFactory.create(ctx)

    # SSE stream
    emitter = SSEEmitter()

    async def event_stream():
        thread = None
        try:
            # P3-A — memory_recall: emit before the engine starts so the
            # UI can show「基于 N 条记忆回答」. Mirrors the legacy /api/chat
            # handler (app.py:1884-1894). Runs in the main thread (fast, <50ms).
            _latest_user = ""
            for m in reversed(messages):
                if m.role == "user":
                    _latest_user = m.content or ""
                    break
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

            # Run engine in a thread (it's synchronous) and bridge to async
            q: queue.SimpleQueue = queue.SimpleQueue()
            sentinel = object()
            cancel_flag = threading.Event()
            _assistant_text_holder: list[str] = [""]

            def worker():
                try:
                    for step in engine.run(ctx):
                        if cancel_flag.is_set():
                            break
                        # Capture assistant text for skill distill after the run.
                        if step.kind == StepKind.TEXT_DELTA and step.content:
                            _assistant_text_holder[0] += step.content
                        q.put(step)
                except Exception as e:
                    q.put(AgentStep(kind=StepKind.ERROR, content=str(e)))
                finally:
                    # v4-1/2 — persist messages + generate title INSIDE the
                    # worker thread, before the sentinel. This runs even if
                    # the SSE client disconnects after receiving `done`,
                    # because the thread is joined in the finally block below.
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
                    import asyncio
                    item = await asyncio.get_running_loop().run_in_executor(
                        None, lambda: q.get(timeout=30.0)
                    )
                except Exception:
                    yield emitter.keepalive()
                    continue

                if item is sentinel:
                    break

                yield emitter.emit(item)

            # P3-A — skill_distilled: after the run, auto-distill if the
            # exchange looks valuable (mirrors legacy app.py:3037/3332/3526).
            # Note: message persistence + title generation now run inside the
            # worker thread (above) so they execute even if the SSE client
            # disconnects after `done`.
            _assistant_text = _assistant_text_holder[0].strip()
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
