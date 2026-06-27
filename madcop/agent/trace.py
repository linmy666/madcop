"""Flowtrace — trace DAG for visible, checkpointable agent execution.

Inspired by Flowtrace's file-as-state + downstream_of() model.

Each LLM call, tool call, and streaming chunk is a TraceNode:
  - id: unique node id
  - parent_id: the node that triggered this one (None for root)
  - conversation_id: which conversation this trace belongs to
  - type: "llm_call" | "tool_call" | "tool_result" | "stream_chunk" | "user_input"
  - status: "pending" | "running" | "done" | "error" | "superseded"
  - input: JSON string of the input (messages, tool args, etc.)
  - output: JSON string of the output (LLM response, tool result)
  - created_at / completed_at: timestamps

The DAG is stored in SQLite (trace.db). The key operation is
`downstream_of(node_id)` — topological sort to find all nodes
that depend on the given node. When the user fixes a node and
resumes, only the downstream nodes are re-run.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TRACE_DB = Path(
    "~/.madcop/trace.db"
).expanduser()


class TraceStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SUPERSEDED = "superseded"  # replaced by a re-run


SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_nodes (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    parent_id TEXT,
    node_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    label TEXT DEFAULT '',
    input TEXT DEFAULT '',
    output TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created_at REAL NOT NULL,
    completed_at REAL,
    depth INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_trace_conv ON trace_nodes(conversation_id);
CREATE INDEX IF NOT EXISTS idx_trace_parent ON trace_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_trace_status ON trace_nodes(status);
"""


@dataclass
class TraceNode:
    id: str
    conversation_id: str
    parent_id: str | None = None
    node_type: str = "llm_call"  # llm_call | tool_call | tool_result | user_input
    status: str = TraceStatus.PENDING
    label: str = ""
    input: str = ""
    output: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "parent_id": self.parent_id,
            "node_type": self.node_type,
            "status": self.status,
            "label": self.label,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "depth": self.depth,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TraceNode:
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            parent_id=row["parent_id"],
            node_type=row["node_type"],
            status=row["status"],
            label=row["label"] or "",
            input=row["input"] or "",
            output=row["output"] or "",
            error=row["error"] or "",
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            depth=row["depth"],
        )


class TraceStore:
    """SQLite-backed trace DAG store."""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else DEFAULT_TRACE_DB
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------ #
    # Write operations
    # ------------------------------------------------------------------ #

    def add(self, node: TraceNode) -> None:
        """Insert a new trace node."""
        with self._conn:
            self._conn.execute(
                """INSERT INTO trace_nodes
                   (id, conversation_id, parent_id, node_type, status,
                    label, input, output, error, created_at, completed_at, depth)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (node.id, node.conversation_id, node.parent_id, node.node_type,
                 node.status, node.label, node.input, node.output, node.error,
                 node.created_at, node.completed_at, node.depth),
            )

    def update(
        self,
        node_id: str,
        *,
        status: str | None = None,
        output: str | None = None,
        error: str | None = None,
        completed_at: float | None = None,
    ) -> bool:
        """Update fields of a trace node. Returns True if existed."""
        sets: list[str] = []
        vals: list[Any] = []
        if status is not None:
            sets.append("status = ?")
            vals.append(status)
        if output is not None:
            sets.append("output = ?")
            vals.append(output)
        if error is not None:
            sets.append("error = ?")
            vals.append(error)
        if completed_at is not None:
            sets.append("completed_at = ?")
            vals.append(completed_at)
        if not sets:
            return False
        vals.append(node_id)
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE trace_nodes SET {', '.join(sets)} WHERE id = ?",
                vals,
            )
            return cur.rowcount > 0

    def mark_running(self, node_id: str) -> None:
        self.update(node_id, status=TraceStatus.RUNNING)

    def mark_done(self, node_id: str, output: str = "") -> None:
        self.update(
            node_id,
            status=TraceStatus.DONE,
            output=output,
            completed_at=time.time(),
        )

    def mark_error(self, node_id: str, error: str = "") -> None:
        self.update(
            node_id,
            status=TraceStatus.ERROR,
            error=error,
            completed_at=time.time(),
        )

    # ------------------------------------------------------------------ #
    # Read operations
    # ------------------------------------------------------------------ #

    def get(self, node_id: str) -> TraceNode | None:
        row = self._conn.execute(
            "SELECT * FROM trace_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return TraceNode.from_row(row) if row else None

    def get_conversation_trace(self, conversation_id: str) -> list[TraceNode]:
        rows = self._conn.execute(
            "SELECT * FROM trace_nodes WHERE conversation_id = ? "
            "ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [TraceNode.from_row(r) for r in rows]

    def get_children(self, parent_id: str) -> list[TraceNode]:
        rows = self._conn.execute(
            "SELECT * FROM trace_nodes WHERE parent_id = ? "
            "ORDER BY created_at ASC",
            (parent_id,),
        ).fetchall()
        return [TraceNode.from_row(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Checkpoint / resume (Flowtrace's downstream_of)
    # ------------------------------------------------------------------ #

    def downstream_of(self, node_id: str) -> list[TraceNode]:
        """Return all nodes that transitively depend on `node_id`.

        Uses BFS from the given node's children, collecting all
        descendants. These are the nodes that need to be re-run
        when the given node's output changes.
        """
        result: list[TraceNode] = []
        seen: set[str] = set()
        queue: list[str] = [node_id]
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            children = self.get_children(current)
            for child in children:
                if child.id not in seen:
                    result.append(child)
                    queue.append(child.id)
        return result

    def reset_downstream(self, node_id: str) -> list[str]:
        """Mark all downstream nodes as 'superseded'. Return their ids.

        The caller can then re-execute them from the given node.
        """
        downstream = self.downstream_of(node_id)
        ids = [n.id for n in downstream]
        for n in downstream:
            self.update(n.id, status=TraceStatus.SUPERSEDED)
        return ids

    # ------------------------------------------------------------------ #
    # Convenience: create + return in one call
    # ------------------------------------------------------------------ #

    def create_node(
        self,
        *,
        conversation_id: str,
        parent_id: str | None = None,
        node_type: str = "llm_call",
        label: str = "",
        input_data: Any = None,
    ) -> TraceNode:
        """Create and insert a new trace node. Returns the node."""
        # Calculate depth based on parent
        depth = 0
        if parent_id:
            parent = self.get(parent_id)
            if parent:
                depth = parent.depth + 1

        node = TraceNode(
            id=uuid.uuid4().hex[:16],
            conversation_id=conversation_id,
            parent_id=parent_id,
            node_type=node_type,
            status=TraceStatus.PENDING,
            label=label,
            input=json.dumps(input_data, ensure_ascii=False, default=str)
            if input_data is not None else "",
            created_at=time.time(),
            depth=depth,
        )
        self.add(node)
        return node


# Module-level singleton (like MemoryStore)
_trace_store: TraceStore | None = None


def get_trace_store() -> TraceStore:
    global _trace_store
    if _trace_store is None:
        _trace_store = TraceStore()
    return _trace_store


def reset_trace_store(store: TraceStore | None) -> None:
    global _trace_store
    _trace_store = store


__all__ = [
    "TraceNode",
    "TraceStore",
    "TraceStatus",
    "DEFAULT_TRACE_DB",
    "get_trace_store",
    "reset_trace_store",
]
