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
            # Run engine in a thread (it's synchronous) and bridge to async
            q: queue.SimpleQueue = queue.SimpleQueue()
            sentinel = object()
            cancel_flag = threading.Event()

            def worker():
                try:
                    for step in engine.run(ctx):
                        if cancel_flag.is_set():
                            break
                        q.put(step)
                except Exception as e:
                    q.put(AgentStep(kind=StepKind.ERROR, content=str(e)))
                finally:
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
