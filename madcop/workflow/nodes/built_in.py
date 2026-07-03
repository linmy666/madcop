"""v2.7.0 — Built-in node types for Phase 1 MVP.

Three node types:
  - StartNode: workflow entry point, accepts initial input
  - LLMNode:   calls LLM with a prompt template
  - EndNode:   workflow exit, returns final output
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from .base import NodeBase, NodeContext, NodeResult, resolve_variables


# --------------------------------------------------------------------------- #
# StartNode
# --------------------------------------------------------------------------- #

class StartNode(NodeBase):
    """Workflow entry point. Passes workflow input through."""
    type = "start"
    label = "开始"
    description = "工作流入口, 接收用户输入"

    async def execute(self, context: NodeContext) -> NodeResult:
        return NodeResult(
            success=True,
            output={"input": context.workflow_input},
        )


# --------------------------------------------------------------------------- #
# LLMNode
# --------------------------------------------------------------------------- #

class LLMNode(NodeBase):
    """Call LLM with a prompt template.

    Data fields:
      - prompt: str (supports {{input}} / {{upstream_node}} refs)
      - system:  str (optional system prompt)
      - model:   str (optional override, otherwise use the active model)
    """
    type = "llm"
    label = "LLM 调用"
    description = "调用大语言模型, 支持变量引用"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        prompt_template = data.get("prompt", "")
        system_template = data.get("system", "")

        prompt = resolve_variables(prompt_template, context)
        system = resolve_variables(system_template, context) if system_template else ""

        # Use the active provider from settings
        try:
            from madcop.config import settings as settings_store
            from madcop.config.settings import get_active_client_config
            s = settings_store.load_settings()
            cfg = get_active_client_config(s)
            if not cfg:
                return NodeResult(
                    success=False,
                    error="No active provider configured. Open Settings to add one.",
                )
            model_name = data.get("model") or cfg.get("model") or ""
        except Exception as e:
            return NodeResult(success=False, error=f"Failed to load provider: {e}")

        # Use the LLM client
        try:
            from madcop.llm.client import OpenAICompatClient
            from madcop.llm import Message
            client = OpenAICompatClient(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model=model_name,
            )
            messages = []
            if system:
                messages.append(Message(role="system", content=system))
            messages.append(Message(role="user", content=prompt))
            resp = client.chat(
                messages=messages,
                model=model_name,
                temperature=0.7,
            )
            content = resp.content or ""
            return NodeResult(success=True, output={"text": content})
        except Exception as e:
            return NodeResult(success=False, error=f"LLM call failed: {e}")


# --------------------------------------------------------------------------- #
# EndNode
# --------------------------------------------------------------------------- #

class EndNode(NodeBase):
    """Workflow exit point. Returns the final output from upstream."""
    type = "end"
    label = "结束"
    description = "工作流出口, 返回上游节点输出"

    async def execute(self, context: NodeContext) -> NodeResult:
        # Return the last upstream node's output
        outputs = context.upstream_outputs
        if not outputs:
            return NodeResult(success=True, output=context.workflow_input)
        # Find the last node that produced output (the one connected to us)
        last_key = list(outputs.keys())[-1]
        last_output = outputs[last_key]
        return NodeResult(success=True, output=last_output)


# --------------------------------------------------------------------------- #
# ToolNode
# --------------------------------------------------------------------------- #

class ToolNode(NodeBase):
    """Call a registered tool from madcop/tools/registry.

    Data fields:
      - tool:     str (tool name, e.g. 'get_weather', 'web_search', 'echo')
      - params:   dict (tool parameters, supports {{var}} resolution)
    """
    type = "tool"
    label = "工具调用"
    description = "调用 MadCop 注册的工具 (天气 / 搜索 / 记忆 / 文件等)"
    category = "built-in"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        tool_name = data.get("tool", "")
        if not tool_name:
            return NodeResult(success=False, error="Missing 'tool' field in node data")
        raw_params = data.get("params", {})
        params = resolve_variables(raw_params, context)

        try:
            from madcop.tools import default_registry
            registry = default_registry()
            from madcop.llm import ToolCall
            call = ToolCall(
                id=f"wf_tool_{tool_name}",
                name=tool_name,
                arguments=params,
            )
            result = await asyncio.to_thread(registry.dispatch, call)
            result_str = result.to_message_content()
            return NodeResult(success=True, output={"result": result_str, "tool": tool_name})
        except Exception as e:
            return NodeResult(success=False, error=f"Tool {tool_name} failed: {e}")


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

_NODE_REGISTRY: dict[str, type[NodeBase]] = {
    "start": StartNode,
    "llm": LLMNode,
    "tool": ToolNode,
    "end": EndNode,
}


def get_node_class(node_type: str) -> type[NodeBase]:
    if node_type not in _NODE_REGISTRY:
        raise KeyError(f"Unknown node type: {node_type}. Available: {list(_NODE_REGISTRY)}")
    return _NODE_REGISTRY[node_type]


def list_node_types() -> list[dict[str, str]]:
    """Return metadata for all available node types (used by frontend)."""
    out = []
    for nt, cls in _NODE_REGISTRY.items():
        # Try to get icon / category from class attribute
        out.append({
            "type": nt,
            "label": cls.label,
            "description": cls.description,
            "category": getattr(cls, "category", "built-in"),
        })
    return out


__all__ = [
    "StartNode", "LLMNode", "EndNode",
    "get_node_class", "list_node_types",
]