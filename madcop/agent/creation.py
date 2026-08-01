"""Sprint 4 — Source-First CreationEngine skeleton.

Orchestrates: search (visitproject) → fetch (web_fetch) → extract
(semantic memory) → outline (LLM) → write (LLM with per-section
citations).

This is a SKELETON — wiring needs to be completed in a follow-up
PR. The shape is in place so the API surface is stable.

Public API (when complete):
  - CreationEngine.run(user_request, workspace) -> CreationResult
  - Each step emits SSE events for the frontend pipeline view.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Citation:
    """Source URL + title + quoted snippet for a single claim."""
    url: str
    title: str
    snippet: str = ""


@dataclass
class CreationResult:
    """Final output of a creation run."""
    title: str
    outline: list[str] = field(default_factory=list)
    body: str = ""
    citations: list[Citation] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    steps: list[dict] = field(default_factory=list)


class CreationEngine:
    """Sprint 4 skeleton — see /docs/innovation-roadmap.md."""

    def __init__(self, web_search=None, web_fetch=None, llm_client=None, memory_store=None) -> None:
        self.web_search = web_search
        self.web_fetch = web_fetch
        self.llm_client = llm_client
        self.memory_store = memory_store

    async def run(self, user_request: str, workspace: str = "") -> CreationResult:
        """Skeleton: 4-step pipeline. Real implementation requires
        wiring the web_search / web_fetch / llm_client / memory_store
        dependencies and LLM prompts for outline + section writing.
        """
        t0 = time.time()
        result = CreationResult(title="(skeleton) — wired implementation TODO")
        # Step 1: search (TODO: integrate visitproject / web_search)
        result.steps.append({"name": "search", "status": "skeleton"})
        # Step 2: fetch (TODO: web_fetch for top URLs)
        result.steps.append({"name": "fetch", "status": "skeleton"})
        # Step 3: outline (TODO: LLM call with prompt template)
        result.steps.append({"name": "outline", "status": "skeleton"})
        # Step 4: write (TODO: LLM per-section with citations)
        result.steps.append({"name": "write", "status": "skeleton"})
        result.elapsed_seconds = time.time() - t0
        return result
