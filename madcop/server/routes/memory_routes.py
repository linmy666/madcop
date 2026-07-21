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


# --------------------------------------------------------------------------- #
# /api/rag/retrieve — the modular RAG endpoint
# --------------------------------------------------------------------------- #
# The previous /api/memory/* routes are flat CRUD. /api/rag/retrieve is
# the real RAG pipeline: query rewrite → fan-out → confidence-gated
# web fallback → grouping → prompt-block rendering. Mirrors opencode's
# pattern of stringifying the catalog for the LLM to pick, but here
# we expose the result as a structured JSON the agent (or the UI) can
# consume.
#
# This route is independent of the agent path. The chat handler
# already calls Retriever directly during planning; this endpoint
# exists so:
#   1. The agent runtime can pull a structured retrieval result as
#      a tool side-effect.
#   2. The UI can show "what I remembered" as a debug surface.
#   3. Tests can call it without going through the chat loop.
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from madcop.memory.episodic import EpisodicMemory
from madcop.memory.query_rewriter import expand
from madcop.memory.reflective import ReflectiveMemory
from madcop.memory.retriever import (
    ModularConfig,
    ModularRetriever,
    RetrievalConfig,
    Retriever,
)
from madcop.memory.semantic import SemanticMemory

from madcop.server.deps import get_memory_store

logger = logging.getLogger(__name__)


def _build_modular_retriever() -> ModularRetriever | None:
    store = get_memory_store()
    # A MemoryStore is usable when it exposes a sqlite connection and
    # the canonical memory_records table. Probe with a SELECT 1 against
    # that table; if it fails the store isn't initialised yet.
    try:
        conn = getattr(store, "_conn", None)
        if conn is None:
            return None
        conn.execute("SELECT 1 FROM memory_records LIMIT 1").fetchone()
    except Exception:
        return None
    try:
        episodic = EpisodicMemory(store)
        semantic = SemanticMemory(store)
        reflective = ReflectiveMemory(store)
    except Exception:
        return None
    base = Retriever(episodic, semantic, reflective)
    return ModularRetriever(base, web_fallback=None)


# Reuse the existing router so the route sits in the memory group.
# A second router is not necessary; the prefix /api/rag/ is unique
# to this file and the parent `router` is already included by
# include_all_routers.
_memory_router = router  # alias for clarity below


@_memory_router.post("/api/rag/retrieve")
async def post_rag_retrieve(body: dict[str, Any]) -> dict[str, Any]:
    """Modular RAG query → ranked hits + rendered prompt block.

    Request body::

        {
          "query": "natural-language question",
          "limit": 5,            // optional
          "rewrite": true,       // optional, default true
          "call_llm": null,      // optional fn for LLM rewriter
          "format": "json" | "prompt"  // default "json"
        }

    Response body::

        {
          "query_used": "...", "rewrites": [...], "rewrote": bool,
          "confidence": 0.0..1.0,
          "items": [{"layer": "L2|L3|L4", "score": float, "text": str}],
          "web_hits": [{"title", "snippet", "url"}],
          "prompt_block": "## Memory context ..."  // if format=prompt
        }
    """
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(400, "query is required")
    limit = body.get("limit") or 5
    if not isinstance(limit, int) or limit <= 0 or limit > 50:
        raise HTTPException(400, "limit must be 1..50")
    rewrite = body.get("rewrite", True)
    if not isinstance(rewrite, bool):
        raise HTTPException(400, "rewrite must be a bool")
    call_llm = body.get("call_llm")
    fmt = body.get("format", "json")
    if fmt not in ("json", "prompt"):
        raise HTTPException(400, "format must be 'json' or 'prompt'")

    mret = _build_modular_retriever()
    if mret is None:
        raise HTTPException(500, "memory store unavailable")

    cfg = ModularConfig(
        episodic_limit=limit,
        semantic_limit=limit * 2,
        reflective_limit=limit,
    )
    variants = expand(query, call_llm) if rewrite else [query]
    if not variants:
        variants = [query]

    # Run the modular pipeline once per rewrite variant; merge
    # results across variants by score so the most-relevant item
    # wins regardless of which variant surfaced it.
    merged: list = []
    seen_texts: set = set()
    for v in variants:
        result = mret.retrieve(v, cfg)
        for layer, score, text in result.items:
            key = (layer, text)
            if key in seen_texts:
                continue
            seen_texts.add(key)
            merged.append((layer, score, text))
    merged.sort(key=lambda x: x[1], reverse=True)
    final_items = merged[:limit]

    if fmt == "prompt":
        result_obj = mret.retrieve(query, cfg)
        prompt_block = mret.format_prompt_block(result_obj)
    else:
        prompt_block = ""

    return {
        "query_used": variants[0] if variants else query,
        "rewrites": variants,
        "rewrote": len(variants) > 1 or (variants and variants[0] != query),
        "confidence": max((s for _, s, _ in final_items), default=0.0),
        "items": [
            {"layer": layer, "score": score, "text": text}
            for layer, score, text in final_items
        ],
        "web_hits": [],
        "prompt_block": prompt_block,
    }


# --------------------------------------------------------------------------- #
# /api/rag/route — exposes the 3-tier router for the debug panel
# --------------------------------------------------------------------------- #
@_memory_router.post("/api/rag/route")
async def post_rag_route(body: dict[str, Any]) -> dict[str, Any]:
    """Classify a user message into a registry route key.

    Request body::

        {"query": "what do you remember about my project?"}

    Response body::

        {
          "target": "memory_retrieval",
          "confidence": 0.85,
          "tier": 1,                  # 1=regex, 2=embedding, 3=llm, 0=fallback
          "rewrites": [...],          # if applicable
          "all_scores": {...}         # full score map
        }
    """
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(400, "query is required")

    from madcop.memory.router import RouterConfig, route

    try:
        decision = route(query, config=RouterConfig())
    except Exception as exc:
        raise HTTPException(500, f"router failed: {exc!r}")

    return {
        "target": decision.target,
        "confidence": float(decision.confidence or 0.0),
        "tier": int(decision.tier),
        "rewrites": list(decision.rewrites or []),
        "all_scores": {k: float(v) for k, v in (decision.all_scores or {}).items()},
    }
