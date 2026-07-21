"""Modular RAG tools — let the LLM actively query the modular retriever
and invoke the 3-tier router.

Three tools:
- `query_rag`  — semantic + episodic + reflective retrieval with
                 query rewriting, re-ranking, and web fallback. The
                 LLM calls this when it wants a context-grounded
                 answer from long-term memory.
- `remember`   — alias of `store_memory` that prefers the modular
                 retriever's record shape (with metadata patches).
                 Kept as a separate name so the LLM can decide
                 "remember this fact" vs "save structured memory".
- `route`      — invoke the 3-tier hybrid router (regex → embedding
                 → LLM) to choose a route key from the registry.
                 The LLM calls this when it wants to dispatch to a
                 specialist instead of answering itself.

The tools share a small `RagToolContext` object that bundles the
`MemoryStore`, the active `ModularRetriever`, the `RouterConfig`, and
an optional `call_llm` callback. The engine passes one shared
context so each tool is bound at boot.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .registry import Tool, ToolResult
from ..memory import MemoryStore, MemoryKind
from ..memory.retriever import (
    ModularRetriever,
    ModularConfig,
    ModularRetrievalResult,
)
from ..memory.router import (
    RouterConfig,
    RouteDecision,
    route as _route,
)


# --------------------------------------------------------------------------- #
# Context object — bundles everything the tools need
# --------------------------------------------------------------------------- #
@dataclass
class RagToolContext:
    """Shared context passed to each RAG tool at construction.

    Engine should build one per session and bind it to all three tools
    so they share the same `MemoryStore` and modular retriever.
    """

    store: MemoryStore
    retriever: ModularRetriever | None = None
    router_config: RouterConfig | None = None
    call_llm: Callable[[str], str] | None = None
    last_decision: RouteDecision | None = field(default=None, init=False)


# --------------------------------------------------------------------------- #
# query_rag — pull a context-grounded answer from memory
# --------------------------------------------------------------------------- #
class QueryRagTool(Tool):
    """Run the modular retriever on a natural-language query.

    Returns a JSON payload with:
    - `query_used`     — the (rewritten) query that was actually searched
    - `confidence`     — top score; if below the modular config's
                        threshold, web fallback was attempted
    - `items`          — list of {kind, title, content, score, id}
    - `web_hits`       — list of {title, snippet, url} if web fallback fired
    - `prompt_block`   — ready-to-paste context block for the LLM
    """

    name = "query_rag"
    description = (
        "Search long-term memory using the modular RAG pipeline "
        "(episodic + semantic + reflective, with query rewriting "
        "and confidence-gated web fallback). Returns structured "
        "context the assistant can cite. Use this when answering "
        "a question that may depend on prior conversations, the "
        "user's profile, or stored reflections."
    )

    def __init__(self, ctx: RagToolContext):
        self._ctx = ctx

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language question to search memory for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max local results to return (default 5, max 20).",
                },
                "include_web": {
                    "type": "boolean",
                    "description": "If true and local confidence is below the gate, attempt a web fallback. Default true.",
                },
            },
            "required": ["query"],
        }

    def __call__(self, **kwargs: Any) -> str:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return ToolResult(
                tool_name=self.name, output="", error="'query' is required"
            ).to_message_content()

        limit = int(kwargs.get("limit", 5))
        limit = max(1, min(limit, 20))
        include_web = bool(kwargs.get("include_web", True))

        retriever = self._ctx.retriever
        if retriever is None:
            return ToolResult(
                tool_name=self.name, output="",
                error="Modular retriever is not configured",
            ).to_message_content()

        # Build a per-call ModularConfig that honours the tool's limit /
        # include_web knobs without disturbing the cached retriever.
        # We pass it via the public `retriever.retrieve(query, config)`
        # signature. If the retriever doesn't accept a config object
        # we fall back to the no-arg form.
        config = ModularConfig(
            semantic_limit=limit,
            episodic_limit=limit,
            reflective_limit=limit,
            rewrite_query=True,
            always_search_web=include_web,
        )

        try:
            result: ModularRetrievalResult = retriever.retrieve(query, config=config)
        except TypeError:
            # Older signature: positional query only.
            try:
                result = retriever.retrieve(query=query)
            except Exception as exc:
                return ToolResult(
                    tool_name=self.name, output="",
                    error=f"retriever failed: {exc!r}",
                ).to_message_content()
        except Exception as exc:
            return ToolResult(
                tool_name=self.name, output="",
                error=f"retriever failed: {exc!r}",
            ).to_message_content()

        # ModularRetrievalResult.items is a list of (layer, score, text)
        # tuples. Serialise as a list of dicts so the LLM gets a clean
        # structured payload.
        items_payload = [
            {"layer": layer, "score": float(score), "text": text}
            for (layer, score, text) in result.items
        ]
        # prompt_block may not be set on the result object — call the
        # helper if present.
        prompt_block = getattr(result, "prompt_block", None) or ""
        if not prompt_block and hasattr(retriever, "format_prompt_block"):
            try:
                prompt_block = retriever.format_prompt_block(result) or ""
            except Exception:
                prompt_block = ""

        payload = {
            "query_used": getattr(result, "query_used", query),
            "rewrites": list(getattr(result, "rewrites", []) or []),
            "confidence": float(getattr(result, "confidence", 0.0) or 0.0),
            "items": items_payload,
            "web_hits": [list(t) for t in (getattr(result, "web_hits", []) or [])],
            "prompt_block": prompt_block,
        }
        return ToolResult(
            tool_name=self.name,
            output=json.dumps(payload, ensure_ascii=False, indent=2),
        ).to_message_content()


# --------------------------------------------------------------------------- #
# remember — store a fact with optional metadata
# --------------------------------------------------------------------------- #
class RememberTool(Tool):
    """Save a fact to long-term memory with optional metadata.

    Identical storage semantics to `store_memory` but exposes a flatter
    surface: just `fact`, optional `tags`, optional `metadata_json`,
    and optional `ttl_days`. Use this when the LLM wants to remember
    something but doesn't need the supersedes/audit machinery of the
    raw memory tool.
    """

    name = "remember"
    description = (
        "Save a fact to long-term memory. Use this when you want to "
        "remember a piece of information across sessions. Unlike "
        "`store_memory`, this tool takes a flat `fact` plus optional "
        "tags / metadata / TTL, and does not manage supersedes/audit "
        "chains — prefer it for simple 'remember this' writes."
    )

    def __init__(self, ctx: RagToolContext):
        self._ctx = ctx

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to remember, phrased as a complete statement.",
                },
                "tags": {
                    "type": "string",
                    "description": "Optional comma-separated tags.",
                },
                "metadata_json": {
                    "type": "string",
                    "description": "Optional JSON object merged into the record's metadata.",
                },
                "ttl_days": {
                    "type": "integer",
                    "description": "Optional TTL in days; the record is auto-excluded after this.",
                },
            },
            "required": ["fact"],
        }

    def __call__(self, **kwargs: Any) -> str:
        fact = str(kwargs.get("fact", "")).strip()
        if not fact:
            return ToolResult(
                tool_name=self.name, output="", error="'fact' is required"
            ).to_message_content()

        tags_raw = str(kwargs.get("tags", "") or "").strip()
        tags = tuple(t.strip() for t in tags_raw.split(",") if t.strip())
        if not tags:
            tags = ("user-profile", "agent-stored")

        meta_str = str(kwargs.get("metadata_json", "") or "").strip()
        meta: dict[str, Any] = {}
        if meta_str:
            try:
                meta = json.loads(meta_str)
            except Exception as exc:
                return ToolResult(
                    tool_name=self.name, output="",
                    error=f"metadata_json is not valid JSON: {exc}",
                ).to_message_content()

        ttl_raw = kwargs.get("ttl_days", None)
        if ttl_raw is not None and str(ttl_raw).strip():
            try:
                ttl = int(ttl_raw)
                if ttl > 0:
                    meta.setdefault("valid_until", time.time() + ttl * 86400)
            except (TypeError, ValueError):
                return ToolResult(
                    tool_name=self.name, output="",
                    error=f"ttl_days must be a positive integer, got {ttl_raw!r}",
                ).to_message_content()

        store = self._ctx.store
        # SemanticMemory expects JSON content with subject/predicate/object;
        # store the free-form fact as subject="fact", predicate="text",
        # object=fact so the retriever can read it back via the layer's
        # standard from_record path.
        fact_content = json.dumps(
            {"subject": "fact", "predicate": "text", "object": fact,
             "kind": "fact", "confidence": 1.0},
            ensure_ascii=False,
        )
        try:
            rec = store.insert(
                kind=MemoryKind.SEMANTIC,
                title=fact[:60],
                content=fact_content,
                tags=tags,
                metadata=json.dumps(meta) if meta else "{}",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name, output="",
                error=f"insert failed: {exc!r}",
            ).to_message_content()
        return ToolResult(
            tool_name=self.name,
            output=f"Stored memory id={rec.id}: {fact}",
        ).to_message_content()


# --------------------------------------------------------------------------- #
# route — invoke the 3-tier hybrid router
# --------------------------------------------------------------------------- #
class RouteTool(Tool):
    """Classify a user message into one of the registered routes.

    Returns a JSON payload with:
    - `target`     — the chosen route key (e.g. 'memory_retrieval')
    - `confidence` — 0..1 score for the chosen target
    - `tier`       — which tier matched: 'regex', 'embedding', 'llm', or 'default'
    - `rewrites`   — any rewrite hints the router applied
    - `all_scores` — full score map for transparency
    """

    name = "route"
    description = (
        "Decide which route the assistant should take for a user "
        "message. Returns the chosen route key and a 0..1 confidence "
        "score. Use this when the user's intent is ambiguous and you "
        "want to delegate dispatch to the router instead of guessing."
    )

    def __init__(self, ctx: RagToolContext):
        self._ctx = ctx

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user message (or summary) to route.",
                },
            },
            "required": ["query"],
        }

    def __call__(self, **kwargs: Any) -> str:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return ToolResult(
                tool_name=self.name, output="", error="'query' is required"
            ).to_message_content()

        try:
            decision = _route(query, config=self._ctx.router_config)
        except Exception as exc:
            return ToolResult(
                tool_name=self.name, output="",
                error=f"router failed: {exc!r}",
            ).to_message_content()

        # Cache for telemetry / debug panel
        self._ctx.last_decision = decision

        payload = {
            "target": decision.target,
            "confidence": float(decision.confidence or 0.0),
            "tier": decision.tier,
            "rewrites": list(decision.rewrites or []),
            "all_scores": {k: float(v) for k, v in (decision.all_scores or {}).items()},
        }
        return ToolResult(
            tool_name=self.name,
            output=json.dumps(payload, ensure_ascii=False, indent=2),
        ).to_message_content()


# --------------------------------------------------------------------------- #
# Bulk registration helper
# --------------------------------------------------------------------------- #
def default_rag_tools(ctx: RagToolContext) -> list[Tool]:
    """Return [QueryRag, Remember, Route] bound to a shared context."""
    return [
        QueryRagTool(ctx),
        RememberTool(ctx),
        RouteTool(ctx),
    ]


__all__ = [
    "RagToolContext",
    "QueryRagTool",
    "RememberTool",
    "RouteTool",
    "default_rag_tools",
]