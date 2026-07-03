"""v2.7.0 — Workflow engine: simple linear executor (Phase 1 MVP).

Walks nodes following edges, in order. No DAG/parallel yet — that's
Phase 2 work. For Phase 1, we just need to execute start → llm → end
in sequence and return the final output.

Each node execution:
  1. Build NodeContext with input + upstream outputs + workflow input
  2. Call node.execute(context) -> NodeResult
  3. Record a node_run row in workflow_node_runs
  4. Pass output to downstream nodes as upstream_output[node_id]

Sends WebSocket events for live status (status, current_node_id).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from . import persistence as p
from .nodes.base import NodeContext, NodeResult
from .nodes.built_in import get_node_class


def _build_adjacency(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    """source_node_id -> [target_node_id, ...]"""
    out: dict[str, list[str]] = {}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s and t:
            out.setdefault(s, []).append(t)
    return out


def _find_starts(nodes: list[dict[str, Any]]) -> list[str]:
    """Nodes of type 'start' OR nodes with no incoming edges."""
    return [n["id"] for n in nodes if n.get("type") == "start"]


def _resolve_input_for_node(
    node: dict[str, Any],
    upstream_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """A node's input = its own data.input + upstream outputs."""
    base = dict(node.get("data", {}).get("input", {}) or {})
    base["upstream"] = upstream_outputs
    return base


async def run_workflow_async(
    workflow_id: str,
    workflow_input: dict[str, Any] | None = None,
    on_event=None,
) -> p.WorkflowRun:
    """Execute a workflow. Returns the final WorkflowRun.

    on_event: optional async callback(event_dict) for live status updates.
    """
    wf = p.get_workflow(workflow_id)
    if not wf:
        raise ValueError(f"Workflow not found: {workflow_id}")

    run = p.create_run(workflow_id, workflow_input)
    # Mutate the same run object so we don't accidentally reset fields
    run.status = "running"
    run.started_at = time.time()
    p.update_run(run)

    nodes_by_id = {n["id"]: n for n in wf.nodes}
    adjacency = _build_adjacency(wf.edges)

    upstream_outputs: dict[str, dict[str, Any]] = {}

    async def emit(event: dict[str, Any]) -> None:
        if on_event:
            try:
                await on_event(event)
            except Exception:
                pass

    await emit({
        "type": "workflow_run_started",
        "run_id": run.id,
        "workflow_id": workflow_id,
        "workflow_name": wf.name,
        "total_nodes": len(wf.nodes),
    })

    # Find entry points (start nodes). For Phase 1, just walk from them.
    starts = _find_starts(wf.nodes)
    if not starts:
        run.status = "failed"
        run.error = "No start node found"
        run.completed_at = time.time()
        p.update_run(run)
        return run

    # Phase 1: linear walk from start nodes, BFS following edges.
    # We support a single start node; for multi-start we'd need DAG.
    queue = list(starts)
    visited = set()
    final_output: Any = None

    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        node = nodes_by_id.get(node_id)
        if not node:
            continue

        run.current_node_id = node_id
        p.update_run(run)
        await emit({
            "type": "workflow_node_started",
            "run_id": run.id,
            "node_id": node_id,
            "node_type": node.get("type"),
        })

        # Build context for this node
        ctx = NodeContext(
            node=node,
            input=_resolve_input_for_node(node, upstream_outputs),
            upstream_outputs=upstream_outputs,
            workflow_input=workflow_input or {},
            workflow_id=workflow_id,
            run_id=run.id,
        )

        # Resolve any {{var}} in data fields before passing
        # (the node's own execute() will do the final string substitution)
        node_run = p.create_node_run(run.id, node_id)
        node_run.started_at = time.time()
        p.update_node_run(node_run)
        try:
            cls = get_node_class(node.get("type", ""))
            instance = cls()
            result: NodeResult = await instance.execute(ctx)
        except KeyError as e:
            result = NodeResult(success=False, error=str(e))
        except Exception as e:
            result = NodeResult(success=False, error=f"{type(e).__name__}: {e}")

        node_run.completed_at = time.time()
        node_run.duration_ms = int((node_run.completed_at - node_run.started_at) * 1000)
        node_run.status = "success" if result.success else "failed"
        node_run.output = result.output if result.output is not None else {}
        node_run.error = result.error
        p.update_node_run(node_run)

        await emit({
            "type": "workflow_node_completed",
            "run_id": run.id,
            "node_id": node_id,
            "node_type": node.get("type"),
            "status": node_run.status,
            "output": node_run.output,
            "error": node_run.error,
            "duration_ms": node_run.duration_ms,
        })

        if not result.success:
            run.status = "failed"
            run.error = f"Node {node_id} failed: {result.error}"
            break

        # Store output for downstream nodes
        upstream_outputs[node_id] = result.output if result.output is not None else {}
        final_output = result.output

        # Schedule downstream nodes
        for nxt in adjacency.get(node_id, []):
            if nxt not in visited:
                queue.append(nxt)

    if run.status == "running":
        run.status = "completed"
    run.output = final_output if final_output is not None else {}
    run.completed_at = time.time()
    p.update_run(run)

    await emit({
        "type": "workflow_run_completed",
        "run_id": run.id,
        "workflow_id": workflow_id,
        "status": run.status,
        "output": run.output,
        "error": run.error,
    })
    return run


def run_workflow(workflow_id: str, workflow_input: dict[str, Any] | None = None) -> p.WorkflowRun:
    """Synchronous wrapper for run_workflow_async."""
    return asyncio.run(run_workflow_async(workflow_id, workflow_input))


__all__ = ["run_workflow", "run_workflow_async"]