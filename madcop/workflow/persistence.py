"""v2.7.0 — Workflow persistence: SQLite CRUD for workflow definitions + runs.

The data model:
  - workflows: visual workflow definition (nodes + edges JSON)
  - workflow_runs: each execution of a workflow (with state)
  - workflow_node_runs: each node's execution within a run (history)

Stored in ~/.madcop/workflow.db (separate from the main brain.db to
keep workflow data isolated from chat/memory data).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _workflow_db_path() -> Path:
    """Path to the workflow SQLite database (~/.madcop/workflow.db)."""
    return Path(os.path.expanduser("~/.madcop/workflow.db"))


def _connect() -> sqlite3.Connection:
    db = _workflow_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist. v2.7.0 schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            nodes_json TEXT NOT NULL DEFAULT '[]',
            edges_json TEXT NOT NULL DEFAULT '[]',
            variables_json TEXT DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending',
            input_json TEXT DEFAULT '{}',
            output_json TEXT DEFAULT '{}',
            current_node_id TEXT,
            error TEXT,
            started_at REAL,
            completed_at REAL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_node_runs (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
            node_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            input_json TEXT DEFAULT '{}',
            output_json TEXT DEFAULT '{}',
            duration_ms INTEGER,
            error TEXT,
            started_at REAL,
            completed_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_node_runs_run ON workflow_node_runs(run_id);
    """)


# --------------------------------------------------------------------------- #
# Domain dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class Workflow:
    id: str
    name: str
    description: str = ""
    version: int = 1
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    variables: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        # Auto-set timestamps if not provided
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.updated_at == 0.0:
            self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "nodes": self.nodes,
            "edges": self.edges,
            "variables": self.variables,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class WorkflowRun:
    id: str
    workflow_id: str
    status: str = "pending"   # pending / running / paused / completed / failed
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    current_node_id: str | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "input": self.input,
            "output": self.output,
            "current_node_id": self.current_node_id,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
        }


@dataclass
class NodeRun:
    id: str
    run_id: str
    node_id: str
    status: str = "pending"
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "status": self.status,
            "input": self.input,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# --------------------------------------------------------------------------- #
# Workflow CRUD
# --------------------------------------------------------------------------- #

def list_workflows() -> list[Workflow]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name, description, version, nodes_json, edges_json, "
            "variables_json, created_at, updated_at FROM workflows ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [
        Workflow(
            id=r[0], name=r[1], description=r[2] or "", version=r[3],
            nodes=json.loads(r[4] or "[]"),
            edges=json.loads(r[5] or "[]"),
            variables=json.loads(r[6] or "[]"),
            created_at=r[7], updated_at=r[8],
        )
        for r in rows
    ]


def get_workflow(workflow_id: str) -> Workflow | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, name, description, version, nodes_json, edges_json, "
            "variables_json, created_at, updated_at FROM workflows WHERE id=?",
            (workflow_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return Workflow(
        id=row[0], name=row[1], description=row[2] or "", version=row[3],
        nodes=json.loads(row[4] or "[]"),
        edges=json.loads(row[5] or "[]"),
        variables=json.loads(row[6] or "[]"),
        created_at=row[7], updated_at=row[8],
    )


def save_workflow(workflow: Workflow) -> Workflow:
    """Insert or update. Returns the saved workflow."""
    workflow.updated_at = time.time()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO workflows "
            "(id, name, description, version, nodes_json, edges_json, "
            "variables_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                workflow.id,
                workflow.name,
                workflow.description,
                workflow.version,
                json.dumps(workflow.nodes, ensure_ascii=False),
                json.dumps(workflow.edges, ensure_ascii=False),
                json.dumps(workflow.variables, ensure_ascii=False),
                workflow.created_at,
                workflow.updated_at,
            ),
        )
    finally:
        conn.close()
    return workflow


def delete_workflow(workflow_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
        return cur.rowcount > 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Run CRUD
# --------------------------------------------------------------------------- #

def create_run(workflow_id: str, input: dict[str, Any] | None = None) -> WorkflowRun:
    run = WorkflowRun(
        id=uuid.uuid4().hex,
        workflow_id=workflow_id,
        status="pending",
        input=input or {},
    )
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO workflow_runs "
            "(id, workflow_id, status, input_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run.id, run.workflow_id, run.status,
             json.dumps(run.input, ensure_ascii=False), run.created_at),
        )
    finally:
        conn.close()
    return run


def update_run(run: WorkflowRun) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE workflow_runs SET status=?, output_json=?, current_node_id=?, "
            "error=?, started_at=?, completed_at=? WHERE id=?",
            (
                run.status,
                json.dumps(run.output, ensure_ascii=False),
                run.current_node_id,
                run.error,
                run.started_at,
                run.completed_at,
                run.id,
            ),
        )
    finally:
        conn.close()


def get_run(run_id: str) -> WorkflowRun | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, workflow_id, status, input_json, output_json, "
            "current_node_id, error, started_at, completed_at, created_at "
            "FROM workflow_runs WHERE id=?",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return WorkflowRun(
        id=row[0], workflow_id=row[1], status=row[2],
        input=json.loads(row[3] or "{}"),
        output=json.loads(row[4] or "{}"),
        current_node_id=row[5], error=row[6],
        started_at=row[7], completed_at=row[8], created_at=row[9],
    )


def list_runs(workflow_id: str, limit: int = 50) -> list[WorkflowRun]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, workflow_id, status, input_json, output_json, "
            "current_node_id, error, started_at, completed_at, created_at "
            "FROM workflow_runs WHERE workflow_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (workflow_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        WorkflowRun(
            id=r[0], workflow_id=r[1], status=r[2],
            input=json.loads(r[3] or "{}"),
            output=json.loads(r[4] or "{}"),
            current_node_id=r[5], error=r[6],
            started_at=r[7], completed_at=r[8], created_at=r[9],
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Node run history
# --------------------------------------------------------------------------- #

def create_node_run(run_id: str, node_id: str) -> NodeRun:
    nr = NodeRun(
        id=uuid.uuid4().hex,
        run_id=run_id,
        node_id=node_id,
        status="pending",
    )
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO workflow_node_runs "
            "(id, run_id, node_id, status) VALUES (?, ?, ?, ?)",
            (nr.id, nr.run_id, nr.node_id, nr.status),
        )
    finally:
        conn.close()
    return nr


def update_node_run(nr: NodeRun) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE workflow_node_runs SET status=?, input_json=?, output_json=?, "
            "duration_ms=?, error=?, started_at=?, completed_at=? WHERE id=?",
            (
                nr.status,
                json.dumps(nr.input, ensure_ascii=False),
                json.dumps(nr.output, ensure_ascii=False),
                nr.duration_ms,
                nr.error,
                nr.started_at,
                nr.completed_at,
                nr.id,
            ),
        )
    finally:
        conn.close()


def list_node_runs(run_id: str) -> list[NodeRun]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, run_id, node_id, status, input_json, output_json, "
            "duration_ms, error, started_at, completed_at "
            "FROM workflow_node_runs WHERE run_id=? ORDER BY started_at",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        NodeRun(
            id=r[0], run_id=r[1], node_id=r[2], status=r[3],
            input=json.loads(r[4] or "{}"),
            output=json.loads(r[5] or "{}"),
            duration_ms=r[6], error=r[7],
            started_at=r[8], completed_at=r[9],
        )
        for r in rows
    ]


__all__ = [
    "Workflow", "WorkflowRun", "NodeRun",
    "list_workflows", "get_workflow", "save_workflow", "delete_workflow",
    "create_run", "get_run", "update_run", "list_runs",
    "create_node_run", "update_node_run", "list_node_runs",
]