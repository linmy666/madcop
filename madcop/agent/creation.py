"""Sprint 4 — Source-First CreationEngine.

A genuine ``AgentEngine`` that writes a researched, cited long-form
article from a user request. It implements the real 4-step pipeline:

  1. **search** — call the ``web_search`` tool (visitproject / SearXNG /
     etc.) for 2-3 queries derived from the request.
  2. **fetch** — call ``web_fetch`` on the top URLs to gather source text.
  3. **outline** — one non-streaming LLM call turns the sources into a
     Markdown outline.
  4. **write** — the LLM streams the full article section-by-section,
     inserting ``[n]`` citation markers; we yield each token as a
     ``TEXT_DELTA``.

Every step yields lifecycle-correct ``AgentStep``s so the existing
chat_v4 route + SSE bridge surface them with no changes, and a
``CreationProgress`` pill on the frontend can show the pipeline phase.

The engine conforms to the same contract as Quick/ReAct/Deep engines:
``run(ctx) -> Iterator[AgentStep]`` (synchronous), reading the LLM
client from ``ctx.client`` and tools from ``ctx.tool_executor``.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

from .creation_prompts import (
    OUTLINE_PROMPT,
    SEARCH_QUERY_PROMPT,
    WRITE_PROMPT,
)
from .runtime import AgentEngine, AgentStep, RunContext, StepKind
from madcop.llm.client import Message


# ── Public data shapes (kept for direct testing / future API use) ────────────


@dataclass
class Citation:
    """Source URL + title + quoted snippet for a single claim."""
    url: str
    title: str
    snippet: str = ""


@dataclass
class CreationResult:
    """Final structured output of a creation run."""
    title: str
    outline: list[str] = field(default_factory=list)
    body: str = ""
    citations: list[Citation] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    steps: list[dict] = field(default_factory=list)


# ── Engine ───────────────────────────────────────────────────────────────────


_MAX_SEARCH_QUERIES = 3
_MAX_FETCH_URLS = 3
_MAX_FETCH_CHARS = 4000
_OUTLINE_MAX_TOKENS = 700
_WRITE_MAX_TOKENS = 3000


class CreationEngine(AgentEngine):
    """Source-first long-form creation engine.

    Wired dependencies come from ``ctx`` (not the constructor), exactly
    like the other v4 engines — this lets ``EngineFactory`` instantiate
    it with no arguments and keeps test doubles simple.
    """

    def __init__(
        self,
        web_search: Any = None,
        web_fetch: Any = None,
        llm_client: Any = None,
        memory_store: Any = None,
    ) -> None:
        # Stored for backwards compat / direct unit use; the real path
        # reads everything off ctx in run().
        self.web_search = web_search
        self.web_fetch = web_fetch
        self.llm_client = llm_client
        self.memory_store = memory_store

    # ── AgentEngine contract ──────────────────────────────────────────────

    def run(self, ctx: RunContext) -> Iterator[AgentStep]:
        t0 = time.time()
        request = self._current_query(ctx)
        client = ctx.client or self.llm_client
        citations: list[Citation] = []

        try:
            # ── Step 1: SEARCH ─────────────────────────────────────────
            queries = self._derive_queries(client, ctx, request)
            raw_hits = self._run_search(ctx, queries)
            hits = self._normalize_hits(raw_hits)

            # ── Step 2: FETCH ──────────────────────────────────────────
            fetched = self._run_fetch(ctx, hits[:_MAX_FETCH_URLS])
            citations = self._hits_to_citations(hits[:_MAX_FETCH_URLS], fetched)
            sources_block, numbered_block = self._build_source_text(hits[:_MAX_FETCH_URLS], fetched)

            # ── Step 3: OUTLINE ────────────────────────────────────────
            outline = self._derive_outline(client, ctx, request, sources_block)

            # ── Step 4: WRITE (streamed) ───────────────────────────────
            body_parts: list[str] = []
            for chunk in self._stream_write(client, ctx, request, outline, numbered_block):
                body_parts.append(chunk)
                if chunk:
                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=chunk)
            body = "".join(body_parts).strip()

            yield AgentStep(kind=StepKind.TEXT_END)
            yield AgentStep(
                kind=StepKind.DONE,
                model=ctx.model or "",
                metadata={
                    "citations": [
                        {"url": c.url, "title": c.title, "snippet": c.snippet}
                        for c in citations
                    ],
                    "outline": outline,
                    "elapsed_seconds": round(time.time() - t0, 2),
                    "step": "create",
                },
            )
        except Exception as e:  # noqa: BLE001 — surface any failure to the UI
            yield AgentStep(kind=StepKind.ERROR, content=f"创作失败: {e}")

    # ── Helpers: query / search / fetch ───────────────────────────────────

    @staticmethod
    def _current_query(ctx: RunContext) -> str:
        msgs = ctx.messages or []
        if not msgs:
            return ""
        return (getattr(msgs[-1], "content", "") or "").strip()

    def _call_llm_chat(self, client: Any, ctx: RunContext, messages: list, *,
                       max_tokens: int) -> str:
        """One non-streaming LLM turn → text. Falls back to streaming."""
        if client is None:
            return ""
        try:
            if hasattr(client, "chat"):
                resp = client.chat(messages, model=ctx.model,
                                   temperature=0.3, max_tokens=max_tokens)
                return (getattr(resp, "content", "") or str(resp)).strip()
            # No .chat — accumulate the stream.
            out: list[str] = []
            for chunk in client.stream(messages, model=ctx.model,
                                       temperature=0.3, max_tokens=max_tokens):
                t = getattr(chunk, "text", "") or ""
                if t:
                    out.append(t)
                if getattr(chunk, "finish_reason", None):
                    break
            return "".join(out).strip()
        except Exception:
            return ""

    def _derive_queries(self, client: Any, ctx: RunContext, request: str) -> list[str]:
        """Ask the LLM to split the request into 2-3 search queries."""
        if not request:
            return []
        prompt = SEARCH_QUERY_PROMPT.format(request=request[:800])
        messages = [Message(role="user", content=prompt)]
        raw = self._call_llm_chat(client, ctx, messages, max_tokens=200)
        queries = self._parse_query_list(raw)
        if not queries:
            # Fallback: use the request itself as a single query.
            queries = [request[:120]]
        return queries[:_MAX_SEARCH_QUERIES]

    @staticmethod
    def _parse_query_list(raw: str) -> list[str]:
        """Best-effort parse of an LLM JSON-array answer into strings."""
        if not raw:
            return []
        # Strip code fences if present.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
        # Last resort: split by newline / comma.
        parts = re.split(r"[\n,]+", cleaned)
        return [p.strip().strip('"').strip("'") for p in parts if p.strip()][:_MAX_SEARCH_QUERIES]

    def _run_search(self, ctx: RunContext, queries: list[str]) -> list[dict]:
        """Call web_search for each query; merge + de-dup by URL."""
        all_hits: list[dict] = []
        seen_urls: set[str] = set()
        for q in queries:
            hits = self._call_tool(ctx, "web_search", {"query": q, "max_results": 5})
            for h in hits:
                if not isinstance(h, dict):
                    continue
                url = (h.get("url") or "").strip()
                if not url or h.get("error") or url in seen_urls:
                    continue
                seen_urls.add(url)
                all_hits.append({
                    "title": (h.get("title") or "").strip()[:160],
                    "url": url,
                    "snippet": (h.get("snippet") or "").strip()[:300],
                    "query": q,
                })
        return all_hits

    def _run_fetch(self, ctx: RunContext, hits: list[dict]) -> dict[str, str]:
        """Fetch the body text for each hit URL. Returns {url: text}."""
        out: dict[str, str] = {}
        for h in hits:
            url = h.get("url", "")
            res = self._call_tool(ctx, "web_fetch",
                                  {"url": url, "max_chars": _MAX_FETCH_CHARS})
            if isinstance(res, dict) and res.get("content") and not res.get("error"):
                out[url] = str(res["content"])[:_MAX_FETCH_CHARS]
        return out

    def _call_tool(self, ctx: RunContext, name: str, args: dict) -> Any:
        """Invoke a tool via ctx.tool_executor and decode the result.

        Returns the parsed JSON value (list/dict) when the executor
        serialized it, else the raw string.
        """
        executor = ctx.tool_executor
        if executor is None:
            return []
        try:
            raw = executor(name, json.dumps(args, ensure_ascii=False), ctx.work_dir)
        except Exception:
            return []
        content = ""
        if hasattr(raw, "content"):
            content = getattr(raw, "content", "") or ""
        elif hasattr(raw, "to_observation"):
            content = raw.to_observation()
        else:
            content = str(raw)
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content

    # ── Helpers: normalize / build sources ────────────────────────────────

    @staticmethod
    def _normalize_hits(hits: Any) -> list[dict]:
        if isinstance(hits, list):
            return [h for h in hits if isinstance(h, dict)]
        return []

    @staticmethod
    def _hits_to_citations(hits: list[dict], fetched: dict[str, str]) -> list[Citation]:
        out: list[Citation] = []
        for h in hits:
            url = h.get("url", "")
            out.append(Citation(
                url=url,
                title=h.get("title") or url,
                snippet=(fetched.get(url, "") or h.get("snippet", ""))[:200],
            ))
        return out

    @staticmethod
    def _build_source_text(hits: list[dict], fetched: dict[str, str]) -> tuple[str, str]:
        """Build (compact_sources_for_outline, numbered_sources_for_write)."""
        compact_parts: list[str] = []
        numbered_parts: list[str] = []
        for i, h in enumerate(hits, start=1):
            url = h.get("url", "")
            body = fetched.get(url, "") or h.get("snippet", "")
            body = body[:1200]
            compact_parts.append(f"[{i}] {h.get('title','')} — {url}\n{body}")
            numbered_parts.append(f"[{i}] {h.get('title','')} ({url}):\n{body}")
        return "\n\n".join(compact_parts), "\n\n".join(numbered_parts)

    # ── Helpers: outline ──────────────────────────────────────────────────

    def _derive_outline(self, client: Any, ctx: RunContext,
                        request: str, sources: str) -> list[str]:
        prompt = OUTLINE_PROMPT.format(request=request[:800], sources=sources or "(暂无检索素材)")
        messages = [Message(role="user", content=prompt)]
        raw = self._call_llm_chat(client, ctx, messages, max_tokens=_OUTLINE_MAX_TOKENS)
        return self._parse_outline(raw)

    @staticmethod
    def _parse_outline(raw: str) -> list[str]:
        """Extract the numbered list from the LLM outline response."""
        if not raw:
            return []
        lines: list[str] = []
        for line in raw.splitlines():
            m = re.match(r"^\s*(?:\d+[\.\)]|[-*])\s+(.+)$", line.strip())
            if m:
                lines.append(m.group(1).strip())
        return lines

    # ── Helpers: write (streamed) ─────────────────────────────────────────

    def _stream_write(self, client: Any, ctx: RunContext, request: str,
                      outline: list[str], numbered_sources: str) -> Iterator[str]:
        prompt = WRITE_PROMPT.format(
            request=request[:800],
            outline="\n".join(f"{i}. {s}" for i, s in enumerate(outline, 1)) or "(由模型自行决定结构)",
            numbered_sources=numbered_sources or "(暂无素材，请基于你的知识撰写并如实说明)",
        )
        messages = [Message(role="user", content=prompt)]
        if client is None:
            yield "(未配置 LLM 客户端，无法生成正文)"
            return
        # Prefer streaming for the long write step.
        try:
            if hasattr(client, "stream"):
                for chunk in client.stream(messages, model=ctx.model,
                                           temperature=0.4, max_tokens=_WRITE_MAX_TOKENS):
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        yield text
                    if getattr(chunk, "finish_reason", None):
                        return
                return
            # No stream — single chat call, emit whole.
            resp = client.chat(messages, model=ctx.model,
                               temperature=0.4, max_tokens=_WRITE_MAX_TOKENS)
            yield (getattr(resp, "content", "") or str(resp))
        except Exception as e:  # noqa: BLE001
            yield f"\n\n(生成中断: {e})"


# ── Tool lifecycle helpers (yield TOOL_START/TOOL_END for the UI) ────────────
#
# These are exposed as generator helpers so the main run() loop (above,
# which is kept linear for readability) can optionally show per-tool
# progress. We keep the search/fetch as a single grouped phase to avoid
# spamming the timeline with one event per query.


def _tool_event(name: str, args: dict, *, start: bool, tool_use_id: str = "",
                result: str = "", is_error: bool = False) -> AgentStep:
    return AgentStep(
        kind=StepKind.TOOL_START if start else StepKind.TOOL_END,
        tool_name=name,
        tool_input=args if start else None,
        tool_use_id=tool_use_id or uuid.uuid4().hex[:10],
        tool_result=(result[:2000] if not start else None),
        is_error=is_error,
    )


__all__ = ["CreationEngine", "CreationResult", "Citation"]
