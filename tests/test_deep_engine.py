"""Tests for the task-typed deep engine: synthesizer DAG, retry, error isolation.

Run: cd /Users/linruihan/PycharmProjects/madcop && python -m pytest tests/test_deep_engine.py -v
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

import pytest
from madcop.agent_network.engine import (
    AgentEngine,
    build_network_for_task,
    classify_task,
    SYNTHESIZER_NODE_ID,
)
from madcop.agent_network.api import BUILTIN_AGENTS
from madcop.llm.client import StreamChunk


# ── Task classification ───────────────────────────────────────────── #

class TestClassifyTask:
    def test_research_no_coder_no_reviewer(self):
        """A research report should use researcher specialists only."""
        _cat, specs = classify_task("帮我写快递行业调研报告")
        assert "coder" not in specs, "调研任务不该有编码专家"
        assert "reviewer" not in specs, "调研任务不需要审查员拖慢流程"

    def test_coding_has_coder(self):
        _cat, specs = classify_task("帮我做一个植物大战僵尸游戏")
        assert "coder" in specs

    def test_design_has_designer(self):
        _cat, specs = classify_task("帮我设计登录页面 UI 原型")
        assert "designer" in specs

    def test_general_falls_back_to_researcher(self):
        _cat, specs = classify_task("写一首关于秋天的诗")
        assert "researcher" in specs
        assert "coder" not in specs


# ── DAG structure with synthesizer ────────────────────────────────── #

class TestBuildNetwork:
    def test_synthesizer_node_present(self):
        net = build_network_for_task("调研报告")
        node_ids = [n["id"] for n in net["nodes"]]
        assert SYNTHESIZER_NODE_ID in node_ids, "必须有综合节点"

    def test_synthesizer_is_real_agent_not_merge(self):
        """synthesizer must have an agentId so the engine calls the LLM,
        rather than treating it as a passthrough/merge node."""
        net = build_network_for_task("调研报告")
        synth = next(n for n in net["nodes"] if n["id"] == SYNTHESIZER_NODE_ID)
        assert synth.get("agentId"), "综合节点必须是真实 agent（有 agentId）"

    def test_edges_flow_through_synthesizer(self):
        net = build_network_for_task("调研报告")
        edges = [(e["from"], e["to"]) for e in net["edges"]]
        # specialist → synthesizer → output
        assert ("researcher", SYNTHESIZER_NODE_ID) in edges
        assert (SYNTHESIZER_NODE_ID, "output") in edges

    def test_output_only_receives_synthesizer(self):
        """The output merge node should have ONLY synthesizer as upstream,
        so the final answer is the synthesis, not a raw concatenation."""
        net = build_network_for_task("调研报告")
        ups = [e["from"] for e in net["edges"] if e["to"] == "output"]
        assert ups == [SYNTHESIZER_NODE_ID], f"output 上游应只有 synthesizer，实际: {ups}"


# ── End-to-end execution ──────────────────────────────────────────── #

class _RecordingClient:
    """Fake client that records calls and returns canned text."""

    def __init__(self, response: str = "模拟输出内容"):
        self._response = response
        self.call_count = 0
        self.calls: list = []

    def chat(self, *a, **kw):
        raise RuntimeError("chat() should not be called in stream mode")

    def stream(self, messages, **kw):
        self.call_count += 1
        self.calls.append(list(messages))
        yield StreamChunk(text=self._response, model="test")
        yield StreamChunk(finish_reason="stop", model="test")


class TestExecution:
    def test_research_dag_completes(self):
        async def run():
            client = _RecordingClient("报告内容")
            engine = AgentEngine(client, BUILTIN_AGENTS)
            net = build_network_for_task("帮我写快递行业调研报告")
            result = await engine.run(net, user_input="帮我写快递行业调研报告")
            return result

        result = asyncio.run(run())
        assert result.status == "completed"
        # All non-input/output nodes should have produced output.
        for step in result.steps:
            if step.node_id in ("input", "output"):
                continue
            assert step.status == "done", f"{step.node_id} failed: {step.error}"

    def test_synthesizer_output_is_final_answer(self):
        """The synthesizer's output should be what becomes the final answer."""
        async def run():
            client = _RecordingClient("综合报告最终内容")
            engine = AgentEngine(client, BUILTIN_AGENTS)
            net = build_network_for_task("调研报告")
            result = await engine.run(net, user_input="调研报告")
            return result

        result = asyncio.run(run())
        synth_out = result.outputs.get(SYNTHESIZER_NODE_ID, "")
        assert synth_out, "综合节点必须有输出"

    def test_on_token_callback_fires(self):
        """Token streaming callback should fire for each specialist."""
        events = []

        async def run():
            client = _RecordingClient("内容")
            engine = AgentEngine(client, BUILTIN_AGENTS)
            net = build_network_for_task("调研报告")

            def on_token(node_id, agent_name, agent_id, text):
                events.append((node_id, text))

            await engine.run(net, user_input="调研报告", on_token=on_token)

        asyncio.run(run())
        assert len(events) > 0, "应该有 token 流式事件"


# ── Retry + error isolation ───────────────────────────────────────── #

class _FailOnceClient:
    """Fails the first stream call, succeeds afterwards — tests retry."""

    def __init__(self):
        self.calls = 0

    def chat(self, *a, **kw):
        raise RuntimeError("no")

    def stream(self, messages, **kw):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("Connection timed out")
        yield StreamChunk(text="重试后成功", model="test")


class TestRetry:
    def test_transient_failure_retried(self):
        """A connection timeout on the first call should be retried."""
        async def run():
            client = _FailOnceClient()
            engine = AgentEngine(client, BUILTIN_AGENTS)
            net = build_network_for_task("调研报告")
            result = await engine.run(net, user_input="调研报告")
            return client, result

        client, result = asyncio.run(run())
        # First agent (planner) failed once then retried → total calls > 1
        assert client.calls > 1, "应该发生重试"
        # At least planner should have succeeded after retry
        planner = next(s for s in result.steps if s.node_id == "planner")
        assert planner.status == "done", f"planner 重试后应成功: {planner.error}"


class _PermanentFailClient:
    """All stream calls raise a 401 — not retryable."""

    def chat(self, *a, **kw):
        raise RuntimeError("no")

    def stream(self, messages, **kw):
        err = RuntimeError("401 Unauthorized")
        err.status_code = 401
        raise err


class TestErrorIsolation:
    def test_failed_agent_has_empty_output(self):
        """A failed agent stores empty output, not an error string."""
        async def run():
            client = _PermanentFailClient()
            engine = AgentEngine(client, BUILTIN_AGENTS)
            net = build_network_for_task("调研报告")
            result = await engine.run(net, user_input="调研报告")
            return result

        result = asyncio.run(run())
        for step in result.steps:
            if step.status == "error":
                assert step.output == "", (
                    f"失败的 {step.node_id} 输出应为空串，实际: {step.output!r}"
                )

    def test_error_does_not_leak_as_content(self):
        """Error messages must not appear in successful agents' outputs."""
        async def run():
            client = _PermanentFailClient()
            engine = AgentEngine(client, BUILTIN_AGENTS)
            net = build_network_for_task("调研报告")
            result = await engine.run(net, user_input="调研报告")
            return result

        result = asyncio.run(run())
        # Even if everything fails, no output should contain the raw
        # "[Agent X 执行失败...]" error marker.
        for step in result.steps:
            assert "执行失败" not in step.output, (
                f"{step.node_id} 输出含错误标记串: {step.output!r}"
            )
