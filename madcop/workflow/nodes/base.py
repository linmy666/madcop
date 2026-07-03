"""v2.7.0 — Workflow node base class.

Each node type (Start, LLM, Tool, Code, MCP, etc.) subclasses NodeBase
and implements `execute(context) -> NodeResult`.

The `context` provides:
  - input: dict (the node's own input, including references like {{upstream.output}})
  - upstream_outputs: dict[node_id, output] — outputs from upstream nodes
  - workflow_input: dict — initial input to the whole workflow
  - node_runs: list — for appending node-level run history
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeContext:
    """Context passed to each node's execute()."""
    node: dict[str, Any]                    # The node definition itself
    input: dict[str, Any] = field(default_factory=dict)
    upstream_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    workflow_input: dict[str, Any] = field(default_factory=dict)
    workflow_id: str = ""
    run_id: str = ""


@dataclass
class NodeResult:
    """Result of executing a single node."""
    success: bool = True
    output: Any = None
    error: str | None = None
    # For if_else nodes: which branch to take ('true' / 'false')
    branch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "branch": self.branch,
        }


_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.\-]+)\s*\}\}")


def resolve_variables(template: Any, context: NodeContext) -> Any:
    """Replace {{var}} placeholders in string/recursive structures.

    Supported paths:
      {{input}}              → workflow_input['input']
      {{node_id}}            → upstream_outputs[node_id]
      {{node_id.output}}     → upstream_outputs[node_id]['output']
    """
    if isinstance(template, str):
        return _VAR_PATTERN.sub(lambda m: _resolve_var(m.group(1), context), template)
    if isinstance(template, list):
        return [resolve_variables(item, context) for item in template]
    if isinstance(template, dict):
        return {k: resolve_variables(v, context) for k, v in template.items()}
    return template


def _resolve_var(path: str, context: NodeContext) -> str:
    """Resolve a single {{path}} reference to its string value."""
    if path == "input":
        return json.dumps(context.workflow_input, ensure_ascii=False)
    parts = path.split(".", 1)
    head = parts[0]
    tail = parts[1] if len(parts) > 1 else None
    if head in context.upstream_outputs:
        if tail is None:
            return json.dumps(context.upstream_outputs[head], ensure_ascii=False)
        return _resolve_var_path(context.upstream_outputs[head], tail)
    # Fallback: return the literal placeholder
    return f"{{{{{path}}}}}"


def _resolve_var_path(obj: Any, path: str) -> str:
    """Drill into a nested dict using a dotted path."""
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return json.dumps(cur, ensure_ascii=False)
    return json.dumps(cur, ensure_ascii=False)


class NodeBase:
    """Base class for all node types."""
    type: str = "base"
    label: str = "Node"
    description: str = ""

    async def execute(self, context: NodeContext) -> NodeResult:
        raise NotImplementedError


__all__ = ["NodeBase", "NodeContext", "NodeResult", "resolve_variables"]