"""
MadCop Agent Network API — agent registry, knowledge base, and orchestration.
"""

from __future__ import annotations
import json, time, uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["agents"])

# ── Storage ────────────────────────────────────────────────────────── #

_DATA_DIR = Path.home() / ".madcop" / "agent_network"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_AGENTS_FILE = _DATA_DIR / "agents.json"
_KB_FILE = _DATA_DIR / "knowledge.json"
_NETWORKS_FILE = _DATA_DIR / "networks.json"

def _load(path: Path) -> list[dict]:
    if not path.exists(): return []
    try: return json.loads(path.read_text())
    except: return []

def _save(path: Path, data: list[dict]):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ── Builtin agents ─────────────────────────────────────────────────── #

BUILTIN_AGENTS = [
    {"id": "assistant", "name": "通用助手", "description": "全能型对话 agent，适合日常问题、代码编写和一般任务。", "icon": "smart_toy", "model": "glm-5.2", "status": "online", "capabilities": ["对话", "代码", "工具调用", "文件读写"], "source": "builtin"},
    {"id": "coder", "name": "编码专家", "description": "专注于代码生成、审查和调试。多文件编辑能力强。", "icon": "code", "model": "deepseek-v4-flash", "status": "online", "capabilities": ["代码生成", "代码审查", "调试", "重构"], "source": "builtin"},
    {"id": "designer", "name": "设计助手", "description": "生成 UI 原型和设计稿。集成 DesignCanvas。", "icon": "palette", "model": "glm-5.2", "status": "online", "capabilities": ["UI 设计", "原型生成", "CSS 编写"], "source": "builtin"},
    {"id": "researcher", "name": "研究员", "description": "联网搜索、资料整理、报告生成。", "icon": "travel_explore", "model": "qwen3-80b", "status": "online", "capabilities": ["网页搜索", "信息提取", "报告生成"], "source": "builtin"},
    {"id": "planner", "name": "规划师", "description": "将复杂任务分解为多步骤计划，协调其他 agent。", "icon": "account_tree", "model": "glm-5.2", "status": "online", "capabilities": ["任务分解", "协调", "调度"], "source": "builtin"},
    {"id": "reviewer", "name": "审查员", "description": "代码审查、安全审计、质量检查。", "icon": "rate_review", "model": "deepseek-v4-flash", "status": "online", "capabilities": ["代码审查", "安全审计", "性能分析"], "source": "builtin"},
]


# ── Agent Registry ─────────────────────────────────────────────────── #

class AgentCreate(BaseModel):
    name: str
    description: str = ""
    icon: str = "smart_toy"
    model: str = "glm-5.2"
    capabilities: list[str] = []

@router.get("")
async def list_agents():
    """List all agents (builtin + installed)."""
    installed = _load(_AGENTS_FILE)
    return {"builtin": BUILTIN_AGENTS, "installed": installed}

@router.post("")
async def create_agent(body: AgentCreate):
    """Create a custom agent."""
    agents = _load(_AGENTS_FILE)
    agent = {
        "id": str(uuid.uuid4())[:8],
        "name": body.name,
        "description": body.description,
        "icon": body.icon,
        "model": body.model,
        "capabilities": body.capabilities,
        "status": "online",
        "source": "installed",
    }
    agents.append(agent)
    _save(_AGENTS_FILE, agents)
    return agent

@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete a custom agent."""
    agents = _load(_AGENTS_FILE)
    agents = [a for a in agents if a["id"] != agent_id]
    _save(_AGENTS_FILE, agents)
    return {"ok": True}

@router.get("/knowledge")
async def list_knowledge():
    """List all knowledge base entries."""
    return {"items": _load(_KB_FILE)}

@router.post("/knowledge")
async def add_knowledge(body: dict):
    """Add a knowledge base entry."""
    items = _load(_KB_FILE)
    item = {
        "id": str(uuid.uuid4())[:8],
        "agent_id": body.get("agent_id", ""),
        "title": body.get("title", ""),
        "content": body.get("content", ""),
        "type": body.get("type", "text"),
        "tags": body.get("tags", []),
        "pinned": bool(body.get("pinned", False)),
        "createdAt": int(time.time()),
    }
    items.insert(0, item)
    _save(_KB_FILE, items)
    return item

@router.delete("/knowledge/{item_id}")
async def delete_knowledge(item_id: str):
    """Delete a knowledge base entry."""
    items = _load(_KB_FILE)
    items = [i for i in items if i["id"] != item_id]
    _save(_KB_FILE, items)
    return {"ok": True}

@router.patch("/knowledge/{item_id}")
async def update_knowledge(item_id: str, body: dict):
    """Update a knowledge base entry."""
    items = _load(_KB_FILE)
    for item in items:
        if item["id"] == item_id:
            for key in ("content", "type", "agent_id", "title", "tags", "pinned"):
                if key in body:
                    item[key] = body[key]
            _save(_KB_FILE, items)
            return item
    raise HTTPException(404, "Knowledge item not found")


# ── Network configuration ──────────────────────────────────────────── #

class NetworkConfig(BaseModel):
    name: str = "Untitled Network"
    nodes: list[dict] = []
    edges: list[dict] = []

@router.get("/networks")
async def list_networks():
    """List saved agent networks."""
    return _load(_NETWORKS_FILE)

@router.post("/networks")
async def save_network(body: NetworkConfig):
    """Save an agent network configuration."""
    networks = _load(_NETWORKS_FILE)
    net = {
        "id": str(uuid.uuid4())[:8],
        "name": body.name,
        "nodes": body.nodes,
        "edges": body.edges,
        "createdAt": int(time.time()),
    }
    networks.append(net)
    _save(_NETWORKS_FILE, networks)
    return net

@router.delete("/networks/{network_id}")
async def delete_network(network_id: str):
    """Delete a saved network."""
    networks = _load(_NETWORKS_FILE)
    networks = [n for n in networks if n["id"] != network_id]
    _save(_NETWORKS_FILE, networks)
    return {"ok": True}

@router.post("/networks/{network_id}/run")
async def run_network(network_id: str, body: dict = None):
    """Execute a saved agent network with the real execution engine."""
    from madcop.agent_network.engine import build_engine

    networks = _load(_NETWORKS_FILE)
    net = next((n for n in networks if n["id"] == network_id), None)
    if not net:
        raise HTTPException(404, "Network not found")

    user_input = (body or {}).get("input", "")
    if not user_input:
        raise HTTPException(400, "input is required")

    engine = build_engine()
    result = await engine.run(net, user_input=user_input)

    return {
        "network_id": network_id,
        "network_name": result.network_name,
        "status": result.status,
        "outputs": result.outputs,
        "steps": [
            {
                "node_id": s.node_id,
                "agent_id": s.agent_id,
                "agent_name": s.agent_name,
                "output": s.output,
                "status": s.status,
                "error": s.error,
                "elapsed_ms": s.elapsed_ms,
                "upstream": s.upstream,
            }
            for s in result.steps
        ],
        "elapsed_ms": result.elapsed_ms,
        "started_at": result.started_at,
    }

@router.post("/networks/run-adhoc")
async def run_adhoc_network(body: dict):
    """Execute an ad-hoc network (not saved) — used by the canvas Run button."""
    from madcop.agent_network.engine import build_engine

    user_input = body.get("input", "")
    if not user_input:
        raise HTTPException(400, "input is required")

    net = {
        "name": body.get("name", "Ad-hoc"),
        "nodes": body.get("nodes", []),
        "edges": body.get("edges", []),
    }

    engine = build_engine()
    result = await engine.run(net, user_input=user_input)

    return {
        "status": result.status,
        "outputs": result.outputs,
        "steps": [
            {
                "node_id": s.node_id,
                "agent_id": s.agent_id,
                "agent_name": s.agent_name,
                "output": s.output,
                "status": s.status,
                "error": s.error,
                "elapsed_ms": s.elapsed_ms,
                "upstream": s.upstream,
            }
            for s in result.steps
        ],
        "elapsed_ms": result.elapsed_ms,
    }
