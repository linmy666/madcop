"""v1.1.0 — DeferredToolCatalog: load tools on demand, not all at once.

When you have 100+ tools, naively putting them all in the
`ToolRegistry` and passing every `openai_schemas()` to the LLM
is wasteful: the prompt balloons, the LLM gets confused, and you
pay for every token of every tool description on every call.

DeerFlow's `DeferredToolCatalog` solves this with a "tool_search"
pattern: the LLM starts with just a few meta-tools (`tool_search`,
`tool_load`), and asks to load specific categories of tools as
needed. We do the same.

Three concepts:
1. **Category** — a logical group of tools (e.g. "filesystem",
   "network", "data"). Each tool belongs to exactly one category.
2. **Search** — given a query string, return matching categories
   and tool names. Cheap (string match on names + descriptions).
3. **Load** — actually add the tools in a category to the live
   ToolRegistry. After loading, the LLM can call them.

Qian invariants:
- **稳定性**: prompt size stays small regardless of total tool count
- **可控性**: every load is logged so you can see what the agent
  actually used
- **早纠偏**: if the LLM keeps loading the same category, that's
  a signal something's wrong (handled by LoopDetection, not here)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from .registry import Tool, ToolRegistry

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# ToolEntry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ToolEntry:
    """One tool in the catalog, with its category."""
    tool: Tool
    category: str
    description: str  # short description for the LLM to see in search


# --------------------------------------------------------------------------- #
# DeferredToolCatalog
# --------------------------------------------------------------------------- #


class DeferredToolCatalog:
    """A searchable catalog of tools that get loaded on demand.

    The catalog has a `ToolRegistry` for the currently-loaded tools.
    New categories are added to the registry via `load_category()`.

    Usage:
        catalog = DeferredToolCatalog()

        catalog.register(EchoTool(), category="demo", description="echoes text")
        catalog.register(ReadFileTool(), category="filesystem", description="read a file")

        # Registry is empty by default. The LLM sees only meta-tools
        # (search + load) until it asks for specific categories.
        registry = catalog.registry

        # Search for what to load:
        matches = catalog.search("read a file from disk")
        # → [("filesystem", ["ReadFileTool"])]

        # Load the category:
        catalog.load_category("filesystem")
        # Now registry contains ReadFileTool.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list[ToolEntry]] = {}  # category -> entries
        self._registry = ToolRegistry()

    # ----- public properties -------------------------------------------

    @property
    def registry(self) -> ToolRegistry:
        """The currently-loaded tools."""
        return self._registry

    @property
    def categories(self) -> list[str]:
        """All registered categories (regardless of whether they're loaded)."""
        return sorted(self._entries.keys())

    @property
    def loaded_categories(self) -> list[str]:
        """Categories whose tools are currently in the registry."""
        return sorted({
            cat for cat, entries in self._entries.items()
            if any(e.tool.name in self._registry for e in entries)
        })

    # ----- registration -------------------------------------------------

    def register(
        self,
        tool: Tool,
        *,
        category: str,
        description: str = "",
    ) -> None:
        """Add a tool to the catalog. Does NOT add it to the live registry."""
        desc = description or (tool.description or "")
        entry = ToolEntry(tool=tool, category=category, description=desc)
        self._entries.setdefault(category, []).append(entry)

    def register_many(
        self,
        tools_with_meta: Iterable[tuple[Tool, str, str]],
    ) -> None:
        """Bulk-register. Each item is (tool, category, description)."""
        for tool, cat, desc in tools_with_meta:
            self.register(tool, category=cat, description=desc)

    # ----- search -------------------------------------------------------

    def search(self, query: str) -> list[tuple[str, list[str]]]:
        """Search the catalog. Returns [(category, [tool_name, ...]), ...].

        Match logic (cheap — no LLM call):
        - Tool name contains query (case-insensitive)
        - Tool description contains query
        - Category name contains query
        - Tool is already in the live registry (no need to load)

        Results are sorted by relevance: exact name match > description
        match > category match.
        """
        q = query.lower().strip()
        if not q:
            return []

        results: dict[str, set[str]] = {}

        for cat, entries in self._entries.items():
            for entry in entries:
                score = self._match_score(q, entry, cat)
                if score > 0:
                    results.setdefault(cat, set()).add(entry.tool.name)

        # Sort categories by sum of scores
        scored = sorted(
            results.items(),
            key=lambda kv: -sum(
                self._match_score(q, e, kv[0]) for e in self._entries[kv[0]]
            ),
        )
        return [(cat, sorted(names)) for cat, names in scored]

    @staticmethod
    def _match_score(query: str, entry: "ToolEntry", category: str) -> int:
        name = entry.tool.name.lower()
        desc = entry.description.lower()
        cat = category.lower()
        if query == name:
            return 10
        if query in name:
            return 5
        if query in desc:
            return 3
        if query in cat:
            return 2
        return 0

    # ----- load ---------------------------------------------------------

    def load_category(self, category: str) -> list[str]:
        """Add all tools in `category` to the live registry.

        Returns the list of tool names that were added. If the
        category is unknown, returns an empty list.
        """
        if category not in self._entries:
            logger.warning("[catalog] unknown category: %r", category)
            return []
        added: list[str] = []
        for entry in self._entries[category]:
            if entry.tool.name in self._registry:
                continue  # already loaded
            try:
                self._registry.register(entry.tool)
                added.append(entry.tool.name)
            except ValueError:
                # duplicate name — skip silently
                pass
        logger.info("[catalog] loaded %d tool(s) from %r: %s", len(added), category, added)
        return added

    def load_search_results(self, matches: list[tuple[str, list[str]]]) -> dict[str, list[str]]:
        """Load every category in a search result. Returns a mapping
        of category -> tools loaded."""
        return {cat: self.load_category(cat) for cat, _ in matches}


__all__ = ["DeferredToolCatalog", "ToolEntry"]
