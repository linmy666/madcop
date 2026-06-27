"""Memory tools — let the LLM actively manage long-term memory.

Inspired by MemGPT: instead of only auto-injecting relevant memories
into the system prompt, we expose the memory store as tools the model
can call. This lets the LLM:

- store a fact it just learned about the user
- recall memories relevant to its current reasoning
- forget a fact that's no longer true

All operations hit the same MemoryStore that the auto-extract pipeline
uses, so manual + automatic + agentic memory writes share one source
of truth.

The store exposes flat MemoryRecord rows (id, kind, title, content,
tags, timestamps). We query via direct FTS5 to avoid layer-specific
dataclasses like Fact that only have subject/predicate/object.
"""

from __future__ import annotations

import json
from typing import Any

from .registry import Tool, ToolResult
from ..memory import MemoryStore, MemoryKind


def _query_memory(store: MemoryStore, query: str, limit: int = 5) -> list[dict]:
    """Run a FTS5 query over memory_records. Returns raw row dicts.

    Falls back to LIKE search if FTS5 query parsing fails (e.g. on
    queries with special characters).
    """
    try:
        # Sanitize query for FTS5: strip punctuation, take 5 longest words
        words = [w for w in query.split() if len(w) > 1][:5]
        if not words:
            return []
        fts_query = " OR ".join(f'"{w}"' for w in words)
        rows = store._conn.execute(
            "SELECT id, kind, title, content, tags, created_at FROM memory_fts "
            "WHERE memory_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        # Fallback: LIKE search
        try:
            rows = store._conn.execute(
                "SELECT id, kind, title, content, tags, created_at FROM memory_records "
                "WHERE content LIKE ? OR title LIKE ? OR tags LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


def _dedup_check(store: MemoryStore, fact: str) -> str | None:
    """Return memory id if a duplicate fact already exists, else None."""
    rows = _query_memory(store, fact, limit=3)
    for r in rows:
        if r.get("content") == fact:
            return r["id"]
    return None


class StoreMemoryTool(Tool):
    """Persist a new fact to long-term memory.

    The LLM calls this when it learns something about the user that
    should be remembered across sessions (preferences, name, job,
    projects, etc.). The fact is stored as a semantic memory with
    the `user-profile` tag so the next session's system prompt will
    surface it.
    """

    name = "store_memory"
    description = (
        "Save a fact about the user to long-term memory. Use this when "
        "the user tells you something about themselves that should be "
        "remembered in future sessions — name, job, preferences, "
        "ongoing projects, etc. Each call stores one fact."
    )

    def __init__(self, store: MemoryStore | None = None):
        self._store = store

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to remember, phrased as a complete statement. E.g. 'The user is a software engineer at Acme Corp.'",
                },
                "tags": {
                    "type": "string",
                    "description": "Optional comma-separated tags. Default 'user-profile,agent-stored'.",
                },
                "supersedes": {
                    "type": "string",
                    "description": "Optional memory_id. If set, the named memory is updated in place with this new fact (the old fact is replaced, audit trail preserved in metadata).",
                },
                "valid_for_days": {
                    "type": "string",
                    "description": "Optional number. If set, the memory is automatically excluded from the system prompt after this many days. Use for time-bound facts like 'the user is in Shanghai for the next 30 days'.",
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
        tags_str = kwargs.get("tags", "user-profile,agent-stored")
        tags = tuple(t.strip() for t in tags_str.split(",") if t.strip())
        if "user-profile" not in tags:
            tags = tags + ("user-profile",)

        supersedes = kwargs.get("supersedes", "").strip()
        valid_for_days_raw = kwargs.get("valid_for_days", "").strip()

        store = self._store
        if store is None:
            return ToolResult(
                tool_name=self.name, output="", error="Memory store not configured"
            ).to_message_content()

        # Build metadata_patch for temporal validity (Gap 4)
        import time as _t
        meta_patch: dict[str, Any] = {}
        if valid_for_days_raw:
            try:
                days = float(valid_for_days_raw)
                if days > 0:
                    meta_patch["valid_until"] = _t.time() + days * 86400
            except ValueError:
                return ToolResult(
                    tool_name=self.name, output="",
                    error=f"valid_for_days must be a number, got '{valid_for_days_raw}'",
                ).to_message_content()

        # Update path: if supersedes is set, update that record and return.
        if supersedes:
            meta_patch.setdefault("superseded_by", supersedes)
            meta_patch.setdefault("updated_fact", fact)
            updated = store.update(
                supersedes,
                title=fact[:60],
                content=fact,
                tags=tags,
                metadata_patch=meta_patch,
            )
            if updated:
                return ToolResult(
                    tool_name=self.name,
                    output=f"Updated memory {supersedes}: {fact}",
                ).to_message_content()
            return ToolResult(
                tool_name=self.name, output="",
                error=f"supersedes={supersedes} not found",
            ).to_message_content()

        # No-op path: identical fact already exists.
        existing_id = _dedup_check(store, fact)
        if existing_id:
            return ToolResult(
                tool_name=self.name,
                output=f"Memory already exists (id={existing_id}, noop).",
            ).to_message_content()

        rec = store.insert(
            kind=MemoryKind.SEMANTIC,
            title=fact[:60],
            content=fact,
            tags=tags,
            metadata=__import__("json").dumps(meta_patch) if meta_patch else "{}",
        )
        return ToolResult(
            tool_name=self.name,
            output=f"Stored memory id={rec.id}: {fact}",
        ).to_message_content()


class RecallMemoryTool(Tool):
    """Search long-term memory for facts relevant to a query.

    The LLM calls this when it needs to remember something but the
    auto-injected system prompt didn't surface it. Returns the top-K
    matching memory records.
    """

    name = "recall_memory"
    description = (
        "Search long-term memory for facts matching a query. Use this "
        "when you need to recall specific information about the user "
        "or past conversations that wasn't in your system prompt."
    )

    def __init__(self, store: MemoryStore | None = None, limit: int = 5):
        self._store = store
        self._limit = limit

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — keywords, names, or topics to look up.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5).",
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
        store = self._store
        if store is None:
            return ToolResult(
                tool_name=self.name, output="", error="Memory store not configured"
            ).to_message_content()
        limit = int(kwargs.get("limit", self._limit))
        limit = max(1, min(limit, 20))

        rows = _query_memory(store, query, limit=limit)
        if not rows:
            return ToolResult(
                tool_name=self.name,
                output=f"No memories found matching '{query}'.",
            ).to_message_content()

        lines = [f"Found {len(rows)} memories:"]
        for r in rows:
            tags = r.get("tags") or "no tags"
            lines.append(f"- [{r['kind']}] {r['title']} (tags: {tags})")
            lines.append(f"  id={r['id']}")
            lines.append(f"  {r['content']}")
        return ToolResult(tool_name=self.name, output="\n".join(lines)).to_message_content()


class ForgetMemoryTool(Tool):
    """Delete a fact from long-term memory by id or by content match.

    The LLM calls this when the user corrects an old fact or asks to
    forget something. Two modes:
    - exact id deletion (preferred when the LLM knows the id from
      recall_memory results)
    - content match: pass a query string and the most relevant fact
      matching it will be deleted
    """

    name = "forget_memory"
    description = (
        "Delete a fact from long-term memory. Use this when the user "
        "corrects an old fact or asks you to forget something. Either "
        "pass the memory_id (preferred) or a content_match query to "
        "delete the most relevant matching fact."
    )

    def __init__(self, store: MemoryStore | None = None):
        self._store = store

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "Exact memory id (from recall_memory results).",
                },
                "content_match": {
                    "type": "string",
                    "description": "Query string — the most relevant memory matching this will be deleted.",
                },
            },
        }

    def __call__(self, **kwargs: Any) -> str:
        store = self._store
        if store is None:
            return ToolResult(
                tool_name=self.name, output="", error="Memory store not configured"
            ).to_message_content()

        memory_id = kwargs.get("memory_id", "").strip()
        content_match = kwargs.get("content_match", "").strip()

        if memory_id:
            ok = store.delete(memory_id)
            if ok:
                return ToolResult(
                    tool_name=self.name,
                    output=f"Deleted memory {memory_id}.",
                ).to_message_content()
            return ToolResult(
                tool_name=self.name,
                output="",
                error=f"No memory with id {memory_id}",
            ).to_message_content()

        if content_match:
            rows = _query_memory(store, content_match, limit=1)
            if not rows:
                return ToolResult(
                    tool_name=self.name,
                    output=f"No memory found matching '{content_match}' — nothing to delete.",
                ).to_message_content()
            target = rows[0]
            store.delete(target["id"])
            return ToolResult(
                tool_name=self.name,
                output=f"Deleted memory {target['id']}: {target['content']}",
            ).to_message_content()

        return ToolResult(
            tool_name=self.name,
            output="",
            error="Provide either memory_id or content_match",
        ).to_message_content()


def default_memory_tools(store: MemoryStore) -> list[Tool]:
    """Return [StoreMemory, RecallMemory, ForgetMemory] bound to `store`."""
    return [
        StoreMemoryTool(store),
        RecallMemoryTool(store),
        ForgetMemoryTool(store),
    ]


__all__ = [
    "StoreMemoryTool",
    "RecallMemoryTool",
    "ForgetMemoryTool",
    "default_memory_tools",
]
