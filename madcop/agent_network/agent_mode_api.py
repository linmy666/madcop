"""Agent mode API — exposes ReAct engine + task router to frontend.

Endpoints:
  GET  /api/agent/modes          — list available modes + descriptions
  POST /api/agent/route           — auto-route a task (preview, no execution)
  POST /api/agent/run             — execute a task with a given mode (SSE stream)
  POST /api/agent/run-sync        — execute and return full result (no stream)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .task_router import (
    route_task, get_mode_config,
    QUICK, STANDARD, DEEP, AUTO,
    MODE_LABELS, MODE_DESCRIPTIONS,
)

router = APIRouter(prefix="/api/agent", tags=["agent-mode"])


# ── Models ─────────────────────────────────────────────────────────── #

class RouteRequest(BaseModel):
    input: str
    context: str = ""


class RunRequest(BaseModel):
    input: str
    agent_mode: str = "auto"    # auto | quick | standard | deep
    work_dir: str | None = None
    context: str = ""
    model: str | None = None
    max_steps: int = 10


# ── Endpoints ──────────────────────────────────────────────────────── #

@router.get("/modes")
async def list_modes():
    """List all agent modes with their configurations."""
    modes = []
    for mode in [QUICK, STANDARD, DEEP]:
        modes.append(get_mode_config(mode))
    return {
        "modes": modes,
        "default": STANDARD,
        "auto_routing": True,
    }


@router.post("/route")
async def route(req: RouteRequest):
    """Preview which mode the task router would choose (no execution)."""
    decision = route_task(req.input, req.context)
    return {
        "mode": decision.mode,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "label": MODE_LABELS.get(decision.mode, decision.mode),
        "config": get_mode_config(decision.mode),
    }


@router.post("/run-sync")
async def run_sync(req: RunRequest):
    """Execute a task and return the full result (non-streaming).

    For "auto" mode, the task router decides quick/standard/deep.
    For explicit modes, uses the requested one.
    """
    # Resolve mode
    if req.agent_mode == AUTO:
        decision = route_task(req.input, req.context)
        mode = decision.mode
        route_reason = decision.reason
        route_confidence = decision.confidence
    else:
        mode = req.agent_mode
        route_reason = "user-selected"
        route_confidence = 1.0

    config = get_mode_config(mode)

    # Execute based on workflow type
    if config["workflow"] == "direct":
        result = await _run_direct(req, config)
    elif config["workflow"] == "react":
        result = await _run_react(req, config)
    else:
        result = await _run_multi_agent(req, config)

    result["agent_mode"] = mode
    result["route_reason"] = route_reason
    result["route_confidence"] = route_confidence
    return result


@router.post("/run")
async def run_stream(req: RunRequest):
    """Execute a task with SSE streaming of intermediate steps.

    Emits 'step' events for each ReAct step, then a 'done' event.
    """
    from fastapi.responses import StreamingResponse

    # Resolve mode
    if req.agent_mode == AUTO:
        decision = route_task(req.input, req.context)
        mode = decision.mode
    else:
        mode = req.agent_mode

    config = get_mode_config(mode)

    async def event_stream():
        # Send route info
        yield _sse("route", {
            "mode": mode,
            "label": config["label"],
            "workflow": config["workflow"],
        })

        if config["workflow"] == "direct":
            # Quick mode — single call, stream tokens
            result = await _run_direct(req, config)
            yield _sse("answer", {"content": result["answer"]})
            yield _sse("done", result)
            return

        if config["workflow"] == "react":
            try:
                from .react_engine import build_react_engine
                engine = build_react_engine(
                    model=req.model,
                    max_steps=req.max_steps,
                )
                for step in engine.run_stream(req.input, req.work_dir, req.context):
                    yield _sse("step", {
                        "step_num": step.step_num,
                        "thought": step.thought,
                        "action": step.action,
                        "action_input": step.action_input,
                        "observation": step.observation,
                        "error": step.error,
                        "elapsed_ms": step.elapsed_ms,
                    })
                yield _sse("done", {"status": "completed"})
            except Exception as e:
                yield _sse("error", {"message": str(e)})
            return

        # Multi-agent mode
        result = await _run_multi_agent(req, config)
        yield _sse("answer", {"content": result.get("answer", "")})
        yield _sse("done", result)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


# ── Internal executors ─────────────────────────────────────────────── #

async def _run_direct(req: RunRequest, config: dict) -> dict:
    """Quick mode — single LLM call, no loop."""
    from madcop.config import settings as settings_store
    from madcop.llm import Message
    from madcop.llm.factory import build_client_from_config

    started = time.time()
    s = settings_store.load_settings()
    cfg = settings_store.get_active_client_config(s)
    if cfg and req.model:
        cfg = {**cfg, "model": req.model}
    client = build_client_from_config(cfg, timeout=120.0)

    messages = [
        Message(role="system", content="You are a helpful coding assistant. Answer concisely."),
        Message(role="user", content=req.input),
    ]

    resp = await asyncio.to_thread(
        client.chat, messages,
        model=req.model or (cfg.get("model") if cfg else None),
        temperature=0.3,
        effort=config["effort"],
    )

    return {
        "answer": getattr(resp, "content", str(resp)),
        "status": "completed",
        "workflow": "direct",
        "elapsed_ms": round((time.time() - started) * 1000, 1),
    }


async def _run_react(req: RunRequest, config: dict) -> dict:
    """Standard mode — ReAct loop."""
    from .react_engine import build_react_engine

    started = time.time()
    engine = build_react_engine(
        model=req.model,
        max_steps=req.max_steps,
    )
    result = await asyncio.to_thread(
        engine.run, req.input, req.work_dir, req.context,
    )

    return {
        "answer": result.final_answer,
        "status": result.status,
        "workflow": "react",
        "steps": [
            {
                "step_num": s.step_num,
                "thought": s.thought,
                "action": s.action,
                "action_input": s.action_input,
                "observation": s.observation,
                "error": s.error,
            }
            for s in result.steps
        ],
        "tool_calls": result.tool_calls,
        "elapsed_ms": result.total_elapsed_ms,
    }


async def _run_multi_agent(req: RunRequest, config: dict) -> dict:
    """Deep mode — multi-agent DAG (plan → code → review)."""
    from .engine import build_engine

    started = time.time()
    engine = build_engine()

    # Build the chain topology: planner → coder → reviewer
    network = {
        "name": "Plan-Code-Review Chain",
        "nodes": [
            {"id": "input", "agentId": "input", "name": "用户输入"},
            {"id": "planner", "agentId": "planner", "name": "规划师"},
            {"id": "coder", "agentId": "coder", "name": "编码专家"},
            {"id": "reviewer", "agentId": "reviewer", "name": "审查员"},
            {"id": "output", "agentId": "output", "name": "最终结果"},
        ],
        "edges": [
            {"from": "input", "to": "planner"},
            {"from": "planner", "to": "coder"},
            {"from": "coder", "to": "reviewer"},
            {"from": "reviewer", "to": "output"},
        ],
    }

    result = await engine.run(network, user_input=req.input)

    # The output node has the final combined result
    final = result.outputs.get("output", result.outputs.get("reviewer", ""))

    return {
        "answer": final,
        "status": result.status,
        "workflow": "multi_agent",
        "steps": [
            {
                "node_id": s.node_id,
                "agent_name": s.agent_name,
                "output": s.output,
                "status": s.status,
            }
            for s in result.steps
        ],
        "elapsed_ms": result.elapsed_ms,
    }


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
