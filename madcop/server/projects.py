"""v2.6.0 — Project Workspace: long-running tasks + archival.

A Project is a stateful entity that:
  - tracks a multi-phase workflow (requirements → design → code)
  - stores artifacts (markdown documents, code snapshots)
  - links to chat sessions that have worked on it
  - survives across restarts (persisted to SQLite)

Use cases:
  - User says "I want to build a TMS" → agent creates a Project,
    generates Requirements.md, then Design.md, then code skeleton.
  - User opens a Project → sees all artifacts + can resume work.
  - User says "archive" → project status becomes "archived" but
    remains queryable.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / ".madcop" / "projects.db"

PHASE_TEMPLATE = {
    "requirement": {
        "name": "需求调研",
        "description": "与用户沟通确认项目需求",
        "output": "requirements.md",
        "next": "design",
    },
    "design": {
        "name": "产品设计",
        "description": "基于需求输出产品文档/技术方案",
        "output": "design.md",
        "next": "implementation",
    },
    "implementation": {
        "name": "前后端实现",
        "description": "根据设计文档生成代码骨架",
        "output": "code/",
        "next": "review",
    },
    "review": {
        "name": "代码审查",
        "description": "审查代码质量、安全、性能",
        "output": "review.md",
        "next": "deployment",
    },
    "deployment": {
        "name": "部署上线",
        "description": "打包、部署、运维文档",
        "output": "deployment.md",
        "next": None,  # terminal
    },
}

PHASE_ORDER = ["requirement", "design", "implementation", "review", "deployment"]


@dataclass
class Project:
    id: str
    name: str
    description: str
    status: str  # "draft" | "active" | "archived"
    current_phase: str  # one of PHASE_ORDER
    artifacts: dict[str, str] = field(default_factory=dict)  # phase -> markdown content
    session_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class ProjectStore:
    """SQLite-backed project storage with CRUD + workflow helpers."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            current_phase TEXT NOT NULL DEFAULT 'requirement',
            artifacts_json TEXT NOT NULL DEFAULT '{}',
            session_ids_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_projects_status
            ON projects(status, updated_at DESC);
        """)
        self._conn.commit()

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            status=row["status"],
            current_phase=row["current_phase"],
            artifacts=json.loads(row["artifacts_json"] or "{}"),
            session_ids=json.loads(row["session_ids_json"] or "[]"),
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ----- CRUD ----- #

    def create(self, name: str, description: str = "",
              metadata: dict[str, Any] | None = None) -> Project:
        pid = uuid.uuid4().hex[:12]
        now = self._now()
        proj = Project(
            id=pid, name=name, description=description,
            status="draft", current_phase="requirement",
            metadata=metadata or {},
            created_at=now, updated_at=now,
        )
        self._save(proj)
        return proj

    def _save(self, proj: Project) -> None:
        proj.updated_at = self._now()
        self._conn.execute("""
        INSERT OR REPLACE INTO projects
        (id, name, description, status, current_phase,
         artifacts_json, session_ids_json, metadata_json,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proj.id, proj.name, proj.description, proj.status,
            proj.current_phase,
            json.dumps(proj.artifacts, ensure_ascii=False),
            json.dumps(proj.session_ids, ensure_ascii=False),
            json.dumps(proj.metadata, ensure_ascii=False),
            proj.created_at, proj.updated_at,
        ))
        self._conn.commit()

    def get(self, project_id: str) -> Project | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return self._row_to_project(row) if row else None

    def list(self, status: str | None = None,
             limit: int = 50) -> list[Project]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM projects WHERE status = ? "
                "ORDER BY updated_at DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def delete(self, project_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ----- Workflow helpers ----- #

    def advance(self, project_id: str, next_phase: str | None = None,
                artifact_content: str | None = None) -> Project:
        """Move project to next phase, optionally saving current artifact."""
        proj = self.get(project_id)
        if not proj:
            raise ValueError(f"project {project_id} not found")
        # Save the current phase's artifact
        if artifact_content is not None:
            proj.artifacts[proj.current_phase] = artifact_content
        # Compute next phase
        if next_phase is None:
            current_idx = PHASE_ORDER.index(proj.current_phase)
            if current_idx + 1 >= len(PHASE_ORDER):
                proj.status = "archived"
            else:
                proj.current_phase = PHASE_ORDER[current_idx + 1]
                if proj.status == "draft":
                    proj.status = "active"
        else:
            proj.current_phase = next_phase
        self._save(proj)
        return proj

    def set_artifact(self, project_id: str, phase: str,
                     content: str) -> Project:
        proj = self.get(project_id)
        if not proj:
            raise ValueError(f"project {project_id} not found")
        proj.artifacts[phase] = content
        self._save(proj)
        return proj

    def attach_session(self, project_id: str,
                       session_id: str) -> Project:
        proj = self.get(project_id)
        if not proj:
            raise ValueError(f"project {project_id} not found")
        if session_id not in proj.session_ids:
            proj.session_ids.append(session_id)
        self._save(proj)
        return proj

    def archive(self, project_id: str) -> Project:
        proj = self.get(project_id)
        if not proj:
            raise ValueError(f"project {project_id} not found")
        proj.status = "archived"
        self._save(proj)
        return proj

    def activate(self, project_id: str) -> Project:
        proj = self.get(project_id)
        if not proj:
            raise ValueError(f"project {project_id} not found")
        proj.status = "active"
        self._save(proj)
        return proj

    def current_phase_info(self, proj: Project) -> dict[str, Any]:
        return {
            "phase": proj.current_phase,
            **PHASE_TEMPLATE.get(proj.current_phase, {}),
            "is_terminal": PHASE_TEMPLATE.get(
                proj.current_phase, {}).get("next") is None,
        }


_singleton: ProjectStore | None = None


def get_project_store() -> ProjectStore:
    global _singleton
    if _singleton is None:
        _singleton = ProjectStore()
    return _singleton
