"""Memory CRUD routes."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from madcop.server.deps import get_memory_store
from madcop.server.models import MemoryCreateRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memory"])


@router.get("/api/memory")
async def list_memory() -> dict[str, Any]:
    from madcop.memory import (
        MemoryKind,
        ScenarioMemory, PersonaMemory, InsightMemory,
    )
    store = get_memory_store()
    result: dict[str, Any] = {
        "episodic": [], "semantic": [], "reflective": [],
        "scenario": [], "persona": [], "insight": [],
    }
    for kind_label, mk in [
        ("episodic", MemoryKind.EPISODIC),
        ("semantic", MemoryKind.SEMANTIC),
        ("reflective", MemoryKind.REFLECTIVE),
    ]:
        for r in store.list_by_kind(mk, limit=200):
            result[kind_label].append({
                "id": r.id, "kind": r.kind.value, "title": r.title,
                "content": r.content, "tags": list(r.tags),
                "created_at": r.created_at, "updated_at": r.updated_at,
            })
    try:
        scm = ScenarioMemory(store)
        for sc in scm.list_recent(limit=50):
            result["scenario"].append(scm.to_public_dict(sc))
    except Exception as e:
        logger.debug("memory scenario list: %s", e)
    try:
        pm = PersonaMemory(store)
        for t in pm.traits():
            result["persona"].append({
                "key": t.key, "value": t.value, "confidence": t.confidence,
            })
    except Exception as e:
        logger.debug("memory persona list: %s", e)
    try:
        im = InsightMemory(store)
        for ins in im.list(limit=50):
            result["insight"].append({
                "id": ins.id, "title": ins.title,
                "description": ins.description,
                "confidence": ins.confidence,
                "occurrences": ins.occurrences, "tags": ins.tags,
            })
    except Exception as e:
        logger.debug("memory insight list: %s", e)
    result["total"] = sum(len(v) for v in result.values() if isinstance(v, list))
    return result


@router.post("/api/memory")
async def add_memory(body: MemoryCreateRequest) -> dict[str, Any]:
    from madcop.memory import MemoryKind
    kind_map = {
        "episodic": MemoryKind.EPISODIC,
        "semantic": MemoryKind.SEMANTIC,
        "reflective": MemoryKind.REFLECTIVE,
    }
    mk = kind_map.get(body.kind)
    if mk is None:
        raise HTTPException(400, f"Invalid kind '{body.kind}'. Must be one of: {list(kind_map)}")
    store = get_memory_store()
    rec = store.insert(
        kind=mk, title=body.title, content=body.content, tags=tuple(body.tags),
    )
    return {
        "id": rec.id, "kind": rec.kind.value, "title": rec.title,
        "content": rec.content, "tags": list(rec.tags), "created_at": rec.created_at,
    }


@router.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str) -> dict[str, Any]:
    store = get_memory_store()
    deleted = store.delete(memory_id)
    if not deleted:
        raise HTTPException(404, f"Memory '{memory_id}' not found")
    return {"deleted": True, "id": memory_id}


@router.get("/api/memory/search")
async def search_memory(q: str = Query(..., description="Search query")) -> dict[str, Any]:
    store = get_memory_store()
    safe_q = q.replace('"', '""')
    records = store.search_fts(f'"{safe_q}"', limit=50)
    return {
        "query": q,
        "count": len(records),
        "results": [
            {
                "id": r.id, "kind": r.kind.value, "title": r.title,
                "content": r.content, "tags": list(r.tags),
                "created_at": r.created_at,
            }
            for r in records
        ],
    }
