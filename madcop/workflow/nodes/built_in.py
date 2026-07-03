"""v2.7.0 — Built-in node types for Phase 1 MVP.

Three node types:
  - StartNode: workflow entry point, accepts initial input
  - LLMNode:   calls LLM with a prompt template
  - EndNode:   workflow exit, returns final output
"""
from __future__ import annotations

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
    """Workflow exit point. Returns the final output."""
    type = "end"
    label = "结束"
    description = "工作流出口, 返回最终结果"

    async def execute(self, context: NodeContext) -> NodeResult:
        # The end node's output is the upstream's output
        return NodeResult(success=True, output=context.workflow_input)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

_NODE_REGISTRY: dict[str, type[NodeBase]] = {
    "start": StartNode,
    "llm": LLMNode,
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