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

    # Build tool registry
    _, tool_executor = build_default_registry(
        workspace_dir=work_dir,
        store=None,  # TODO: pass memory store
    )

    # Build run context
    ctx = RunContext(
        messages=messages,
        model=model,
        agent_mode=agent_mode,
        work_dir=work_dir,
        session_id=session_id,
        client=_get_client(),
        tool_schemas=[],  # filled by executor
    )

    # Set up tool executor as a callable for ReActEngineV4
    def tool_call(name: str, raw_input: str, wd: str | None = None) -> str:
        result = tool_executor.execute(name, raw_input, wd)
        return result.to_observation()

    ctx.tool_executor = tool_call

    # Create engine
    engine = EngineFactory.create(ctx)

    # SSE stream
    emitter = SSEEmitter()

    async def event_stream():
        try:
            # Run engine in a thread (it's synchronous) and bridge to async
            q: queue.SimpleQueue = queue.SimpleQueue()
            sentinel = object()

            def worker():
                try:
                    for step in engine.run(ctx):
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
                    item = await asyncio.get_event_loop().run_in_executor(
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
