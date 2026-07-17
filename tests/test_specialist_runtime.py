"""Tests for transparent specialist tools + single-LLM defaults.

Run: python -m pytest tests/test_specialist_runtime.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from madcop.agent_network.specialist_runtime import (
    build_role_tool_schemas,
    filter_tool_schemas,
    max_steps_for_role,
    role_should_use_tools,
    tools_for_role,
)
from madcop.agent_network.engine import AgentEngine, build_network_for_task
from madcop.llm.client import MockClient, StreamChunk
import asyncio


def test_coder_has_write_tools_researcher_does_not():
    coder = set(tools_for_role("coder"))
    researcher = set(tools_for_role("researcher"))
    assert "write_file" in coder
    assert "read_file" in coder
    assert "write_file" not in researcher
    assert "web_search" in researcher
    assert "web_search" not in coder


def test_reviewer_is_read_only():
    rev = set(tools_for_role("reviewer"))
    assert "read_file" in rev
    assert "write_file" not in rev
    assert "edit_file" not in rev


def test_synthesizer_never_uses_tools():
    assert role_should_use_tools("assistant", node_id="synthesizer") is False
    assert role_should_use_tools("coder", node_id="coder") is True


def test_max_steps_bounded():
    assert max_steps_for_role("coder") <= 8
    assert max_steps_for_role("planner") <= 4


def test_filter_tool_schemas():
    schemas = [
        {"name": "read_file", "description": "r"},
        {"name": "write_file", "description": "w"},
        {"name": "web_search", "description": "s"},
    ]
    filtered = filter_tool_schemas(schemas, ["read_file", "web_search"])
    names = {s["name"] for s in filtered}
    assert names == {"read_file", "web_search"}


def test_build_role_schemas_subset():
    schemas = build_role_tool_schemas("researcher")
    # Registry may or may not load depending on env; if present, only allowlist.
    if schemas:
        names = {
            s.get("name") or (s.get("function") or {}).get("name")
            for s in schemas
        }
        assert names <= set(tools_for_role("researcher"))
        assert "write_file" not in names


def test_single_llm_engine_runs_without_routing():
    """Same MockClient for all roles — no multi-model config required."""
    # Force pure completion path (no tools) so MockClient stream is enough.
    client = MockClient(default_response="ok from specialist")
    # MockClient may use chat not stream — check interface
    agents = [
        {"id": "planner", "name": "规划", "description": "plan", "model": "only-model"},
        {"id": "researcher", "name": "调研", "description": "research", "model": "only-model"},
        {"id": "assistant", "name": "综合", "description": "synth", "model": "only-model"},
    ]

    class _StreamClient:
        def stream(self, messages, **kw):
            yield StreamChunk(text="单模型输出", model=kw.get("model") or "only-model")
            yield StreamChunk(finish_reason="stop", model="only-model")

        def chat(self, *a, **kw):
            raise RuntimeError("chat not used in pure path")

    engine = AgentEngine(
        _StreamClient(),
        agents,
        enable_specialist_tools=False,  # pure path for unit test speed
    )
    net = build_network_for_task("写一份行业调研报告")

    async def run():
        return await engine.run(net, user_input="写一份行业调研报告")

    result = asyncio.run(run())
    assert result.status in ("completed", "partial")
    # All agents share the same model id on the agent dicts
    assert agents[0]["model"] == agents[1]["model"] == "only-model"


def test_mini_react_path_with_mock_final():
    """Coder role with tools: ReAct FINAL_ANSWER becomes node output."""
    from madcop.agent_network.react_engine import ReActEngine

    mock = MockClient(scripted=[
        "Thought: done\nAction: FINAL_ANSWER\nAction Input: 代码已就绪",
    ])
    eng = ReActEngine(
        client=mock,
        tools=[{"name": "read_file", "description": "read"}],
        max_steps=3,
        system_prefix="你是编码专家",
    )
    res = eng.run("实现 hello")
    assert res.final_answer == "代码已就绪"
