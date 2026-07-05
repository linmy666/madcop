"""
MadCop Agent Network API — agent registry, knowledge base, and orchestration.
"""

from __future__ import annotations
import json, time, uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["agents"])

# ── Storage (SQLite-like JSON files for simplicity) ────────────────── #
# In production, replace with a proper database.

_DATA_DIR = Path.home() / ".madcop" / "agent_network"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_AGENTS_FILE = _DATA_DIR / "agents.json"
_KB_FILE = _DATA_DIR / "knowledge.json"

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
    {"id": "reviewer", "name": "审查员", "description": "代码审查、安全审计、质量检查。", "icon": "rate_review", "model": "deepseek-v4-flash", "status": "offline", "capabilities": ["代码审查", "安全审计", "性能分析"], "source": "builtin"},
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
        "status": "offline",
        "capabilities": body.capabilities,
        "source": "custom",
        "createdAt": int(time.time()),
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


# ── Knowledge Base ─────────────────────────────────────────────────── #

class KBCreate(BaseModel):
    title: str
    type: str = "note"  # document | url | note | code
    content: str = ""
    tags: list[str] = []

@router.get("/knowledge")
async def list_knowledge():
    """List all knowledge items."""
    return _load(_KB_FILE)

@router.post("/knowledge")
async def create_knowledge(body: KBCreate):
    """Add a knowledge item."""
    items = _load(_KB_FILE)
    item = {
        "id": str(uuid.uuid4())[:8],
        "title": body.title,
        "type": body.type,
        "content": body.content,
        "tags": body.tags,
        "size": f"{len(body.content)}B",
        "updatedAt": time.strftime("%Y-%m-%d"),
        "pinned": False,
    }
    items.insert(0, item)
    _save(_KB_FILE, items)
    return item

@router.delete("/knowledge/{item_id}")
async def delete_knowledge(item_id: str):
    """Delete a knowledge item."""
    items = _load(_KB_FILE)
    items = [i for i in items if i["id"] != item_id]
    _save(_KB_FILE, items)
    return {"ok": True}

@router.patch("/knowledge/{item_id}")
async def update_knowledge(item_id: str, body: dict):
    """Update a knowledge item (pin/unpin, edit content)."""
    items = _load(_KB_FILE)
    for item in items:
        if item["id"] == item_id:
            item.update(body)
            _save(_KB_FILE, items)
            return item
    raise HTTPException(404, "Knowledge item not found")


# ── Agent Network Orchestration ────────────────────────────────────── #

class NetworkConfig(BaseModel):
    name: str = "Untitled Network"
    nodes: list[dict] = []
    edges: list[dict] = []

_NETWORKS_FILE = _DATA_DIR / "networks.json"

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

@router.post("/networks/{network_id}/run")
async def run_network(network_id: str, body: dict = None):
    """Execute an agent network (stub — returns execution plan)."""
    networks = _load(_NETWORKS_FILE)
    net = next((n for n in networks if n["id"] == network_id), None)
    if not net:
        raise HTTPException(404, "Network not found")
    
    # Build execution plan from nodes + edges
    user_input = (body or {}).get("input", "")
    plan = []
    for edge in net.get("edges", []):
        plan.append({
            "from": edge.get("from"),
            "to": edge.get("to"),
            "label": edge.get("label", "delegate"),
            "status": "queued",
        })
    
    return {
        "network_id": network_id,
        "status": "planned",
        "input": user_input,
        "steps": plan,
        "message": f"Network '{net['name']}' queued with {len(plan)} steps. Connect agents to backend LLM to execute.",
    }
