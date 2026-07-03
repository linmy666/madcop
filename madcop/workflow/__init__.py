"""v2.7.0 — Visual workflow orchestration.

Modules:
  - persistence: SQLite CRUD for workflow definitions + runs
  - nodes.base: NodeBase / NodeContext / NodeResult + variable resolution
  - nodes.built_in: StartNode / LLMNode / EndNode (Phase 1 MVP)
  - engine: linear workflow executor
  - api: FastAPI router for /api/workflows/*
"""
from __future__ import annotations

from . import persistence, engine, api
from .persistence import Workflow, WorkflowRun, NodeRun
from .engine import run_workflow, run_workflow_async
from .nodes.built_in import (
    StartNode, LLMNode, EndNode,
    get_node_class, list_node_types,
)
from .nodes.base import NodeBase, NodeContext, NodeResult, resolve_variables

__all__ = [
    "persistence", "engine", "api",
    "Workflow", "WorkflowRun", "NodeRun",
    "run_workflow", "run_workflow_async",
    "StartNode", "LLMNode", "EndNode",
    "get_node_class", "list_node_types",
    "NodeBase", "NodeContext", "NodeResult", "resolve_variables",
]