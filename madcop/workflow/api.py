"""v2.7.0 — Workflow REST API: CRUD + run + status.

Mounted by app.py under /api/workflows/* prefix.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import persistence as p
from .engine import run_workflow_async


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# --------------------------------------------------------------------------- #
# Pydantic models
# --------------------------------------------------------------------------- #

class WorkflowNode(BaseModel):
    id: str
    type: str
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    nodes: list[WorkflowNode] | None = None
    edges: list[WorkflowEdge] | None = None


class RunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

@router.get("")
async def list_all() -> dict[str, Any]:
    return {"workflows": [w.to_dict() for w in p.list_workflows()]}


@router.post("")
async def create(body: WorkflowCreate) -> dict[str, Any]:
    wf = p.Workflow(
        id=uuid.uuid4().hex,
        name=body.name,
        description=body.description,
        nodes=[n.model_dump() for n in body.nodes],
        edges=[e.model_dump() for e in body.edges],
    )
    p.save_workflow(wf)
    return wf.to_dict()


@router.get("/{workflow_id}")
async def get_one(workflow_id: str) -> dict[str, Any]:
    wf = p.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf.to_dict()


@router.put("/{workflow_id}")
async def update_one(workflow_id: str, body: WorkflowUpdate) -> dict[str, Any]:
    wf = p.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if body.nodes is not None:
        wf.nodes = [n.model_dump() for n in body.nodes]
    if body.edges is not None:
        wf.edges = [e.model_dump() for e in body.edges]
    wf.version += 1
    p.save_workflow(wf)
    return wf.to_dict()


@router.delete("/{workflow_id}")
async def delete_one(workflow_id: str) -> dict[str, Any]:
    ok = p.delete_workflow(workflow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"deleted": workflow_id}


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, body: RunRequest) -> dict[str, Any]:
    """Run the workflow synchronously. Returns the final run + output.

    For Phase 1, we use a sync executor. Phase 2 will switch to
    async streaming via WebSocket for live progress.
    """
    wf = p.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        result = await run_workflow_async(workflow_id, body.input)
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/{workflow_id}/runs")
async def list_runs(workflow_id: str, limit: int = 50) -> dict[str, Any]:
    runs = p.list_runs(workflow_id, limit=limit)
    return {"runs": [r.to_dict() for r in runs]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = p.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    node_runs = p.list_node_runs(run_id)
    return {
        **run.to_dict(),
        "node_runs": [nr.to_dict() for nr in node_runs],
    }


# --------------------------------------------------------------------------- #
# Node types metadata (used by frontend for the component library)
# --------------------------------------------------------------------------- #

@router.get("/_meta/node-types")
async def get_node_types() -> dict[str, Any]:
    from .nodes.built_in import list_node_types
    return {"node_types": list_node_types()}


__all__ = ["router"]