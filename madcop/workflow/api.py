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
# Workflow templates (MUST come before {workflow_id} routes)
# --------------------------------------------------------------------------- #

_TEMPLATES: dict[str, dict[str, Any]] = {
    "research_report": {
        "name": "调查报告",
        "description": "自动搜索资料 → 分析整理 → 生成本地 Markdown 报告",
        "nodes": [
            {"id": "start-1", "type": "start", "position": {"x": 50, "y": 200}, "data": {"label": "开始"}},
            {"id": "search-1", "type": "web_search", "position": {"x": 280, "y": 200}, "data": {"label": "搜索资料", "query": "{{input}}"}},
            {"id": "llm-1", "type": "llm", "position": {"x": 510, "y": 200}, "data": {"label": "分析整理", "prompt": "请根据以下搜索结果, 写一份详细的分析报告(中文):\n\n{{search-1.output.results}}", "system": "你是专业的行业分析师, 擅长从信息中提炼洞察。"}},
            {"id": "tool-write", "type": "tool", "position": {"x": 740, "y": 200}, "data": {"label": "写入文件", "tool": "write_file", "params": {"path": "/Users/linruihan/Desktop/{{input}}_报告.md", "content": "{{llm-1.output.text}}"}}},
            {"id": "end-1", "type": "end", "position": {"x": 970, "y": 200}, "data": {"label": "完成"}},
        ],
        "edges": [
            {"id": "e1", "source": "start-1", "target": "search-1"},
            {"id": "e2", "source": "search-1", "target": "llm-1"},
            {"id": "e3", "source": "llm-1", "target": "tool-write"},
            {"id": "e4", "source": "tool-write", "target": "end-1"},
        ],
    },
    "bi_analysis": {
        "name": "BI 数据分析",
        "description": "搜索行业数据 → 生成 BI 分析报告 → 保存 Markdown",
        "nodes": [
            {"id": "start-1", "type": "start", "position": {"x": 50, "y": 200}, "data": {"label": "开始"}},
            {"id": "search-1", "type": "web_search", "position": {"x": 280, "y": 200}, "data": {"label": "搜索行业数据", "query": "{{input}} 行业数据 2025 2026 市场规模 增长率"}},
            {"id": "search-2", "type": "web_search", "position": {"x": 280, "y": 350}, "data": {"label": "搜索竞品分析", "query": "{{input}} 竞争格局 市场份额 头部企业"}},
            {"id": "agg-1", "type": "aggregator", "position": {"x": 510, "y": 275}, "data": {"label": "合并搜索结果", "mode": "merge"}},
            {"id": "llm-bi", "type": "llm", "position": {"x": 740, "y": 275}, "data": {"label": "BI 分析", "prompt": "请根据以下数据, 写一份专业的BI分析报告(中文Markdown格式):\n\n搜索数据: {{agg-1.output.combined}}\n\n报告结构要求:\n1. 行业概览 (市场规模、增速)\n2. 竞争格局 (头部玩家、市场份额)\n3. 趋势分析 (增长点、风险)\n4. 数据可视化建议 (什么图表适合展示什么数据)\n5. 结论与建议", "system": "你是资深的BI分析师, 擅长从数据中提取商业洞察。"}},
            {"id": "tool-write", "type": "tool", "position": {"x": 970, "y": 275}, "data": {"label": "保存报告", "tool": "write_file", "params": {"path": "/Users/linruihan/Desktop/BI_分析_{{input}}_2026.md", "content": "{{llm-bi.output.text}}"}}},
            {"id": "end-1", "type": "end", "position": {"x": 1200, "y": 275}, "data": {"label": "完成"}},
        ],
        "edges": [
            {"id": "e1", "source": "start-1", "target": "search-1"},
            {"id": "e2", "source": "start-1", "target": "search-2"},
            {"id": "e3", "source": "search-1", "target": "agg-1"},
            {"id": "e4", "source": "search-2", "target": "agg-1"},
            {"id": "e5", "source": "agg-1", "target": "llm-bi"},
            {"id": "e6", "source": "llm-bi", "target": "tool-write"},
            {"id": "e7", "source": "tool-write", "target": "end-1"},
        ],
    },
}


@router.get("/templates")
async def list_templates() -> dict[str, Any]:
    out = []
    for tid, tmpl in _TEMPLATES.items():
        out.append({
            "id": tid,
            "name": tmpl["name"],
            "description": tmpl["description"],
            "node_count": len(tmpl["nodes"]),
            "edge_count": len(tmpl["edges"]),
        })
    return {"templates": out}


@router.get("/templates/{template_id}")
async def get_template(template_id: str) -> dict[str, Any]:
    if template_id not in _TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"id": template_id, **_TEMPLATES[template_id]}


@router.post("/templates/{template_id}/instantiate")
async def instantiate_template(template_id: str) -> dict[str, Any]:
    if template_id not in _TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")
    tmpl = _TEMPLATES[template_id]
    wf = p.Workflow(
        id=uuid.uuid4().hex,
        name=tmpl["name"],
        description=tmpl["description"],
        nodes=tmpl["nodes"],
        edges=tmpl["edges"],
    )
    p.save_workflow(wf)
    return wf.to_dict()


# === Everything below here is the original CRUD API ===

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


@router.get("/_meta/node-types")
async def get_node_types() -> dict[str, Any]:
    from .nodes.built_in import list_node_types
    return {"node_types": list_node_types()}


__all__ = ["router"]