"""Sprint 4 — tests for the source-first CreationEngine.

Uses fake LLM client + fake tool executor so the test does not depend
on an API key or network. Verifies the engine:
  - derives search queries,
  - calls web_search + web_fetch,
  - builds an outline,
  - streams a cited article,
  - emits the right AgentStep lifecycle (TEXT_DELTA / TEXT_END / DONE).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from madcop.agent.creation import CreationEngine
from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeChunk:
    def __init__(self, text: str = "", finish_reason: str | None = None) -> None:
        self.text = text
        self.finish_reason = finish_reason


class FakeLLM:
    """Returns canned answers keyed by which prompt phase is calling.

    - chat(): the outline + query phases both use chat. We distinguish
      by inspecting the last user message: contains '检索词' → queries;
      contains '大纲' → outline.
    - stream(): the write phase. Returns a fixed article with a [1]
      citation marker, delivered in 3 chunks.
    """

    def chat(self, messages, model=None, temperature=0.3, max_tokens=700):
        last = messages[-1].content if messages else ""
        if "检索词" in last:
            return SimpleNamespace(content='["RAG 检索增强", "retrieval augmented generation", "RAG 架构"]')
        if "大纲" in last:
            return SimpleNamespace(
                content=(
                    "1. 什么是 RAG — 定义与动机\n"
                    "2. 核心架构 — 索引、检索、生成\n"
                    "3. 实践方法 — 如何落地"
                )
            )
        return SimpleNamespace(content="(unexpected chat)")

    def stream(self, messages, model=None, temperature=0.4, max_tokens=3000):
        article = (
            "## 什么是 RAG\n"
            "RAG 是检索增强生成的缩写，结合检索与生成 [1]。\n\n"
            "## 核心架构\n"
            "它由索引、检索和生成三部分组成。\n\n"
            "## 参考\n- [1] RAG 概述 — https://example.com/rag"
        )
        # Deliver in 3 chunks, last one carries finish_reason.
        third = len(article) // 3
        yield FakeChunk(article[:third])
        yield FakeChunk(article[third:third * 2])
        yield FakeChunk(article[third * 2:], finish_reason="stop")


def make_fake_executor():
    """Returns a tool_executor closure returning ToolResult-shaped
    objects whose .content is a JSON string (matching the real
    executor's serialization)."""

    @dataclass
    class FakeResult:
        content: str = ""
        is_error: bool = False

        def to_observation(self) -> str:
            return self.content

    def executor(name, raw_input, work_dir=None):
        if name == "web_search":
            hits = [
                {"title": "RAG 概述", "url": "https://example.com/rag",
                 "snippet": "RAG 结合检索与生成。"},
                {"title": "RAG 架构详解", "url": "https://example.com/arch",
                 "snippet": "索引检索生成三段式。"},
            ]
            return FakeResult(content=json.dumps(hits, ensure_ascii=False))
        if name == "web_fetch":
            args = json.loads(raw_input) if raw_input else {}
            return FakeResult(content=json.dumps({
                "url": args.get("url", ""),
                "content": "RAG (检索增强生成) 把外部知识注入 LLM。"
                           "索引→检索→生成是其核心流程。",
            }, ensure_ascii=False))
        return FakeResult(content="[]")

    return executor


def _make_ctx() -> RunContext:
    ctx = RunContext(
        messages=[Message(role="user", content="帮我写一篇关于 RAG 的长文")],
        model="fake-model",
        agent_mode="create",
        client=FakeLLM(),
    )
    ctx.tool_executor = make_fake_executor()
    return ctx


# ── Tests ────────────────────────────────────────────────────────────────────


def _collect(ctx):
    engine = CreationEngine()
    return list(engine.run(ctx))


def test_emits_text_delta_then_end_then_done():
    ctx = _make_ctx()
    steps = _collect(ctx)
    kinds = [s.kind for s in steps]
    assert StepKind.TEXT_DELTA in kinds, f"missing TEXT_DELTA: {kinds}"
    assert kinds[-2] == StepKind.TEXT_END, f"second-to-last should be TEXT_END: {kinds}"
    assert kinds[-1] == StepKind.DONE, f"last should be DONE: {kinds}"


def test_body_contains_citation_marker():
    ctx = _make_ctx()
    steps = _collect(ctx)
    body = "".join(s.content for s in steps if s.kind == StepKind.TEXT_DELTA)
    assert "[1]" in body, f"article should cite source [1]:\n{body}"
    assert "RAG" in body


def test_done_metadata_carries_citations_and_outline():
    ctx = _make_ctx()
    steps = _collect(ctx)
    done = [s for s in steps if s.kind == StepKind.DONE]
    assert done, "no DONE step"
    meta = done[-1].metadata
    assert meta["step"] == "create"
    cits = meta["citations"]
    assert isinstance(cits, list) and cits, "should carry at least one citation"
    assert cits[0]["url"].startswith("http")
    outline = meta["outline"]
    assert isinstance(outline, list) and len(outline) == 3


def test_search_and_fetch_tools_were_called():
    """The fake executor is stateful-free; verify indirectly by checking
    that citations came from the fetched content (proves fetch ran)."""
    ctx = _make_ctx()
    steps = _collect(ctx)
    done = [s for s in steps if s.kind == StepKind.DONE][0]
    # The citation snippet should contain fetched text, not just the
    # raw search snippet — proving web_fetch executed.
    cits = done.metadata["citations"]
    snippets = " ".join(c["snippet"] for c in cits)
    assert "核心流程" in snippets or "检索增强生成" in snippets, (
        f"citation snippets should reflect fetched content: {snippets}"
    )


def test_no_errors_when_client_missing():
    """Engine should not raise if ctx.client is None — it degrades
    gracefully (no queries derived → search uses raw request)."""
    ctx = RunContext(
        messages=[Message(role="user", content="写一篇关于 X 的文章")],
        agent_mode="create",
        client=None,
    )
    ctx.tool_executor = make_fake_executor()
    steps = list(CreationEngine().run(ctx))
    kinds = [s.kind for s in steps]
    # Should still complete the lifecycle (possibly with an empty/error body).
    assert StepKind.DONE in kinds or StepKind.ERROR in kinds, kinds


def test_engine_factory_routes_create_mode():
    """EngineFactory.create should return a CreationEngine for create mode."""
    from madcop.agent.runtime import EngineFactory
    from madcop.agent.creation import CreationEngine as CE
    ctx = RunContext(messages=[], agent_mode="create")
    engine = EngineFactory.create(ctx)
    assert isinstance(engine, CE)
