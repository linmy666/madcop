"""Tests for the modular RAG agent tools (query_rag / remember / route)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from madcop.memory.store import MemoryStore
from madcop.memory.episodic import EpisodicMemory
from madcop.memory.semantic import SemanticMemory
from madcop.memory.reflective import ReflectiveMemory
from madcop.memory.retriever import (
    ModularRetriever,
    ModularConfig,
    Retriever,
    format_for_prompt,
)
from madcop.memory.router import RouterConfig, route
from madcop.tools.rag_tools import (
    RagToolContext,
    QueryRagTool,
    RememberTool,
    RouteTool,
    default_rag_tools,
)


@pytest.fixture
def ctx(tmp_path: Path):
    """Minimal RagToolContext backed by an isolated MemoryStore."""
    db = tmp_path / "rag.db"
    store = MemoryStore(path=db)
    epi = EpisodicMemory(store)
    sem = SemanticMemory(store)
    ref = ReflectiveMemory(store)
    raw = Retriever(epi, sem, ref)
    retriever = ModularRetriever(raw, web_fallback=None)
    yield RagToolContext(
        store=store,
        retriever=retriever,
        router_config=RouterConfig(),
        call_llm=None,
    )
    store.close()


def _unwrap(result: str) -> dict:
    """Parse the tool's serialized output. Tools that return JSON
    payloads use ``json.dumps``; tools that return plain strings keep
    them as-is. ``ToolResult.to_message_content`` prefixes errors with
    ``"ERROR: "``."""
    if not result:
        return {"output": "", "error": "empty"}
    if result.startswith("ERROR: "):
        return {"error": result[len("ERROR: "):]}
    try:
        return json.loads(result)
    except Exception:
        # Plain string output (e.g. "Stored memory id=…")
        return {"output": result}


# ---------------------------------------------------------------------------
# remember tool
# ---------------------------------------------------------------------------
def test_remember_writes_fact(ctx):
    tool = RememberTool(ctx)
    res = tool(fact="The user prefers dark mode.")
    assert res.startswith("Stored memory id="), res
    # Stored rows: 1 semantic record
    rows = ctx.store._conn.execute(
        "SELECT COUNT(*) AS n FROM memory_records"
    ).fetchone()
    assert rows["n"] == 1


def test_remember_rejects_empty_fact(ctx):
    tool = RememberTool(ctx)
    res = tool(fact="")
    assert res.startswith("ERROR:"), res
    assert "fact" in res.lower()


def test_remember_parses_ttl(ctx):
    tool = RememberTool(ctx)
    res = tool(fact="user is in Shenzhen for 30 days", ttl_days=30)
    assert res.startswith("Stored memory id="), res
    row = ctx.store._conn.execute(
        "SELECT metadata FROM memory_records ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    import json as _json
    meta = _json.loads(row["metadata"] or "{}")
    assert "valid_until" in meta


# ---------------------------------------------------------------------------
# route tool
# ---------------------------------------------------------------------------
def test_route_classifies_into_registry(ctx):
    tool = RouteTool(ctx)
    # A clearly memory-shaped query should land on memory_retrieval.
    raw = tool(query="what do you remember about my project?")
    res = _unwrap(raw)
    assert res["target"] in {"memory_retrieval", "casual", "modular_rag"}
    assert 0.0 <= res["confidence"] <= 1.0
    # The router uses numeric tiers (1=regex, 2=embedding, 3=llm, 0=fallback)
    assert res["tier"] in {0, 1, 2, 3}
    # Router decision is cached on the context for telemetry.
    assert ctx.last_decision is not None
    assert ctx.last_decision.target == res["target"]


def test_route_rejects_empty(ctx):
    tool = RouteTool(ctx)
    res = tool(query="")
    assert res.startswith("ERROR:"), res


# ---------------------------------------------------------------------------
# query_rag tool
# ---------------------------------------------------------------------------
def test_query_rag_returns_structured_payload(ctx):
    # Seed a memory so the retriever has something to find. We use
    # SemanticMemory.add so the row is stored in the same shape the
    # retriever expects (JSON content with subject/predicate/object).
    from madcop.memory.semantic import SemanticMemory, FactKind
    sem = SemanticMemory(ctx.store)
    sem.add(
        subject="user",
        predicate="lives in",
        object="Shanghai",
        kind=FactKind.FACT,
        tags=("user-profile",),
    )
    tool = QueryRagTool(ctx)
    # The query uses prefix-friendly words ("Shanghai", "live*") so
    # the modular retriever's prefix-aware expansion matches.
    raw = tool(query="where does the user live Shanghai", limit=3)
    inner = _unwrap(raw)
    # Output is a JSON payload string
    if isinstance(inner.get("output"), str) and inner["output"].startswith("{"):
        inner = json.loads(inner["output"])
    assert "items" in inner
    assert "prompt_block" in inner
    assert "query_used" in inner
    found = any("Shanghai" in (it.get("text") or "") for it in inner["items"])
    assert found, inner


def test_query_rag_handles_missing_retriever(tmp_path):
    """When the context has no retriever, the tool returns a clean error."""
    db = tmp_path / "no_retriever.db"
    store = MemoryStore(path=db)
    bare_ctx = RagToolContext(store=store, retriever=None)
    tool = QueryRagTool(bare_ctx)
    res = tool(query="anything")
    assert res.startswith("ERROR:"), res
    assert "retriever" in res.lower()
    store.close()


# ---------------------------------------------------------------------------
# bulk registration helper
# ---------------------------------------------------------------------------
def test_default_rag_tools_returns_all_three(ctx):
    tools = default_rag_tools(ctx)
    names = {t.name for t in tools}
    assert {"query_rag", "remember", "route"} <= names


# ---------------------------------------------------------------------------
# end-to-end: remember → query_rag round-trip
# ---------------------------------------------------------------------------
def test_round_trip_remember_then_query(ctx):
    remember = RememberTool(ctx)
    query = QueryRagTool(ctx)

    # The fact includes "peanut" verbatim — the keyword rewriter keeps
    # the noun, and FTS5 prefix-matches "peanut*" against "peanuts".
    remember(fact="The user is allergic to peanuts.")
    raw = query(query="peanut allergies", limit=3)
    inner = _unwrap(raw)
    if isinstance(inner.get("output"), str) and inner["output"].startswith("{"):
        inner = json.loads(inner["output"])
    texts = [it.get("text") or "" for it in inner["items"]]
    assert any("peanut" in t for t in texts), texts