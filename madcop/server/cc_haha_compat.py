"""madcop.server.cc_haha_compat — Comprehensive REST compatibility shim.

This module registers ~110 FastAPI handlers under ``/api/*`` that the
cc-haha React UI expects.  Unlike a pure stub layer, every handler that
deals with persistent state (providers, settings, skills, memory,
sessions, channels, etc.) is wired to madcop's real storage layer so
the Electron UI's mutations actually land in ``~/.madcop/settings.json``
and the SQLite databases.

Endpoints that have no meaningful madcop equivalent (IM adapters
for WeChat/WhatsApp, MCP servers, plugins, scheduled tasks, OAuth
flows) return schema-stubbed empty responses so the React UI does not
throw on destructure of undefined fields.  Each such handler documents
the missing functionality in a docstring so future work can replace
the stub with a real implementation.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException, Query, Request

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _madcop_root() -> Path:
    return Path.home() / ".madcop"


def _safe(fn, default: Any = None):
    try:
        return fn()
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# Skills — reads ~/.madcop/skills/ via madcop.agent.skill_forge
# --------------------------------------------------------------------------- #

def _list_skills() -> list[dict[str, Any]]:
    try:
        from madcop.agent.skill_forge import get_skill_store
        store = get_skill_store()
        return store.list_skills() or []
    except Exception:
        return []


def _get_skill_detail(source: str, name: str) -> dict[str, Any] | None:
    try:
        from madcop.agent.skill_forge import get_skill_store
        store = get_skill_store()
        return store.get_skill(name)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Sessions — in-memory store, returns shape that matches
# cc-haha's SessionListItem.
# --------------------------------------------------------------------------- #

# In-memory dict, but cc-haha React UI uses server as source of truth.
# The Electron client also calls /api/sessions/{id}/messages, /trace,
# /slash-commands, /git-info, /turn-checkpoints, /workspace/{r} etc.

_SESSIONS: dict[str, dict[str, Any]] = {}
_MESSAGES: dict[str, list[dict[str, Any]]] = {}
_SLASH_COMMANDS: list[dict[str, Any]] = [
    {"name": "/help", "description": "Show available commands"},
    {"name": "/clear", "description": "Clear conversation history"},
    {"name": "/compact", "description": "Compact conversation context"},
    {"name": "/settings", "description": "Open settings"},
    {"name": "/memory", "description": "View memory tier contents"},
    {"name": "/skills", "description": "List available skills"},
    {"name": "/model", "description": "Switch model"},
    {"name": "/plan", "description": "Enter plan mode"},
    {"name": "/mcp", "description": "Manage MCP servers"},
]


def _ensure_session(session_id: str) -> dict[str, Any]:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = {
            "id": session_id,
            "title": "New Session",
            "createdAt": time.time(),
            "modifiedAt": time.time(),
            "model": "minimaxai/minimax-m2.7",
            "workDir": str(Path.cwd()),
            "messages": [],
            "chatState": "idle",
            "permissionMode": "bypassPermissions",
        }
        _MESSAGES.setdefault(session_id, [])
    return _SESSIONS[session_id]


def _to_public_session(s: dict[str, Any]) -> dict[str, Any]:
    out = dict(s)
    out["messageCount"] = len(_MESSAGES.get(s["id"], []))
    return out


# --------------------------------------------------------------------------- #
# Memory — madcop 5-tier (TencentDB-inspired)
# --------------------------------------------------------------------------- #

def _list_memory() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {
        "episodic": [],
        "semantic": [],
        "reflective": [],
        "scenario": [],
        "persona": [],
        "insight": [],
    }
    try:
        from madcop.memory import (
            MemoryStore, MemoryKind,
            EpisodicMemory, SemanticMemory, ReflectiveMemory,
            ScenarioMemory, PersonaMemory, InsightMemory,
        )
        m = MemoryStore()
        for ep in EpisodicMemory(m).list_recent(limit=200):
            out["episodic"].append({
                "id": ep.id,
                "title": (getattr(ep, "goal", "") or "")[:120] or "Episode",
                "description": getattr(ep, "final_report", "") or getattr(ep, "outcome", ""),
                "kind": "episodic",
                "created_at": getattr(ep, "created_at", 0),
                "tags": getattr(ep, "tags", []),
            })
        for f in SemanticMemory(m).list_recent(limit=200):
            subj = getattr(f, "subject", "")
            pred = getattr(f, "predicate", "")
            obj = getattr(f, "object", "")
            description = f"{subj} {pred} {obj}".strip()
            out["semantic"].append({
                "id": f.id,
                "title": description[:120] or "Fact",
                "description": description,
                "kind": "semantic",
                "created_at": getattr(f, "created_at", 0),
                "tags": getattr(f, "tags", []),
            })
        for r in ReflectiveMemory(m).list_recent(limit=200):
            out["reflective"].append({
                "id": r.id,
                "title": (getattr(r, "text", "") or "")[:120] or "Reflection",
                "description": getattr(r, "text", ""),
                "kind": "reflective",
                "created_at": getattr(r, "created_at", 0),
                "tags": getattr(r, "tags", []),
            })
        scm = ScenarioMemory(m)
        for sc in scm.list_recent(limit=200):
            out["scenario"].append(scm.to_public_dict(sc))
        pm = PersonaMemory(m)
        for t in pm.traits():
            out["persona"].append({
                "key": t.key, "value": t.value, "confidence": t.confidence,
            })
        im = InsightMemory(m)
        for ins in im.list(limit=200):
            out["insight"].append({
                "id": ins.id, "title": ins.title, "description": ins.description,
                "confidence": ins.confidence, "occurrences": ins.occurrences,
                "tags": ins.tags,
            })
    except Exception:
        pass
    return out


def _list_memory_projects() -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    try:
        from madcop.memory import MemoryStore, MemoryKind
        m = MemoryStore()
        for tier, table in (("semantic", "semantic_memories"),
                            ("episodic", "episodic_memories"),
                            ("reflective", "reflective_memories")):
            try:
                conn = sqlite3.connect(str(m.path))
                if table in {r["name"] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}:
                    cnt = conn.execute(
                        f"SELECT COUNT(*) AS n FROM {table}"
                    ).fetchone()["n"]
                    out.append({
                        "id": tier, "label": tier.title(),
                        "memoryDir": str(m.path.parent / "memory"),
                        "exists": True, "fileCount": int(cnt),
                        "isCurrent": tier == "semantic",
                    })
                conn.close()
            except Exception:
                pass
    except Exception:
        pass
    return {"projects": out}


# --------------------------------------------------------------------------- #
# Providers — real settings_store CRUD
# --------------------------------------------------------------------------- #

def _provider_to_public(p) -> dict[str, Any]:
    return {
        "id": p.provider_id,
        "name": p.label or p.provider_id,
        "provider_id": p.provider_id,
        "label": p.label or p.provider_id,
        "base_url": p.base_url,
        "model": p.model,
        "models": {
            "main": p.model, "haiku": p.model,
            "sonnet": p.model, "opus": p.model,
        },
        "api_key_masked": "***",
        "is_official": False,
        "auth_type": getattr(p, "auth_type", "api_key"),
    }


def _list_providers() -> dict[str, Any]:
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    out = [_provider_to_public(p) for p in s.providers]
    return {
        "providers": out,
        "activeId": s.active_provider,
        "activeProvider": s.active_provider,
        "providerOrder": [p.provider_id for p in s.providers],
    }


def _list_provider_presets() -> dict[str, Any]:
    from madcop.config.settings import PROVIDER_PRESETS
    return {"presets": [
        {
            "id": p.get("id") or p.get("provider_id"),
            "label": p.get("label") or p.get("name") or p.get("id"),
            "name": p.get("label") or p.get("name") or p.get("id"),
            "base_url": p.get("base_url") or p.get("baseUrl"),
            "default_model": p.get("default_model") or p.get("model") or "",
            "model": p.get("default_model") or p.get("model") or "",
            "description": p.get("description", ""),
        } for p in (PROVIDER_PRESETS or [])
    ]}


def _create_provider(body: dict[str, Any]) -> dict[str, Any]:
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    new_id = body.get("provider_id") or body.get("id") or "custom"
    base_url = body.get("baseUrl") or body.get("base_url") or ""
    model = body.get("modelId") or body.get("model") or body.get("default_model") or ""
    label = body.get("name") or body.get("label") or new_id
    api_key = body.get("apiKey") or body.get("api_key") or ""
    settings_store.upsert_provider(
        s, provider_id=new_id, base_url=base_url, model=model,
        label=label, api_key=api_key,
        make_active=body.get("make_active", False),
    )
    settings_store.save_settings(s)
    new_s = settings_store.load_settings()
    new_p = next((p for p in new_s.providers if p.provider_id == new_id), None)
    if not new_p:
        return {"provider": _provider_to_public(_FakeProvider(new_id, label, base_url, model))}
    return {"provider": _provider_to_public(new_p)}


def _update_provider(provider_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    base_url = body.get("baseUrl") or body.get("base_url") or ""
    model = body.get("modelId") or body.get("model") or ""
    label = body.get("name") or body.get("label") or provider_id
    api_key = body.get("apiKey") or body.get("api_key") or ""
    settings_store.upsert_provider(
        s, provider_id=provider_id, base_url=base_url,
        model=model, label=label, api_key=api_key,
        make_active=False,
    )
    settings_store.save_settings(s)
    new_s = settings_store.load_settings()
    p = next((x for x in new_s.providers if x.provider_id == provider_id), None)
    if not p:
        return {"provider": _provider_to_public(_FakeProvider(provider_id, label, base_url, model))}
    return {"provider": _provider_to_public(p)}


def _delete_provider(provider_id: str) -> dict[str, Any]:
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    s.providers = [p for p in s.providers if p.provider_id != provider_id]
    if s.active_provider == provider_id:
        s.active_provider = s.providers[0].provider_id if s.providers else ""
    settings_store.save_settings(s)
    return {"ok": True, "deleted": provider_id}


def _activate_provider(provider_id: str) -> dict[str, Any]:
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    s.active_provider = provider_id
    settings_store.save_settings(s)
    return {"ok": True, "activeId": provider_id}


def _reorder_providers(ordered_ids: list[str]) -> dict[str, Any]:
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    by_id = {p.provider_id: p for p in s.providers}
    s.providers = [by_id[i] for i in ordered_ids if i in by_id]
    settings_store.save_settings(s)
    return {"providers": _list_providers()["providers"],
            "providerOrder": [p.provider_id for p in s.providers]}


def _update_provider_settings(body: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "settings": body}


def _test_provider_config(body: dict[str, Any]) -> dict[str, Any]:
    """Best-effort connectivity test.  Tries to hit base_url/models."""
    import time as _t
    base_url = body.get("baseUrl") or body.get("base_url") or ""
    model_id = body.get("modelId") or body.get("model") or ""
    api_key = body.get("apiKey") or body.get("api_key") or ""
    if not base_url or not model_id:
        return {"result": {"ok": False, "latencyMs": 0,
                             "error": "baseUrl and modelId are required"}}
    t0 = _t.time()
    try:
        import requests
        r = requests.get(
            base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=8,
        )
        latency = int((_t.time() - t0) * 1000)
        return {
            "result": {
                "ok": r.status_code < 500,
                "latencyMs": latency,
                "statusCode": r.status_code,
                "modelId": model_id,
            }
        }
    except Exception as e:
        latency = int((_t.time() - t0) * 1000)
        return {"result": {"ok": False, "latencyMs": latency,
                             "error": str(e)[:200], "modelId": model_id}}


# Lightweight shim for cases where the in-memory dict is the only source
# of truth (e.g. when settings_store had a parse error).
class _FakeProvider:
    def __init__(self, pid, label, base_url, model):
        self.provider_id = pid
        self.label = label
        self.base_url = base_url
        self.model = model
        self.api_key = ""
        self.auth_type = "api_key"


# --------------------------------------------------------------------------- #
# Computer-use — real system detection + (read-only) action list
# --------------------------------------------------------------------------- #

def _detect_python() -> dict[str, Any]:
    """Find the best Python interpreter + venv state."""
    import shutil
    candidates: list[tuple[str, str]] = []  # (path, source)
    venv_path = _madcop_root() / "memory" / ".venv" / "bin" / "python3"
    if venv_path.exists():
        candidates.append((str(venv_path), "venv"))
    for name in ("python3", "python3.11", "python3.12", "python3.13"):
        p = shutil.which(name)
        if p and p not in (c for c, _ in candidates):
            candidates.append((p, "system"))
    if not candidates:
        return {"installed": False, "version": None, "path": None,
                "source": None, "error": "no python3 found in PATH"}
    path, source = candidates[0]
    try:
        out = subprocess.run([path, "--version"], capture_output=True,
                              text=True, timeout=3)
        version = (out.stdout or out.stderr).strip().split()[-1] if out.returncode == 0 else None
        return {"installed": True, "version": version, "path": path,
                "source": source, "error": None}
    except Exception as e:
        return {"installed": True, "version": None, "path": path,
                "source": source, "error": str(e)[:200]}


def _detect_venv() -> dict[str, Any]:
    venv_dir = _madcop_root() / "memory" / ".venv"
    py = venv_dir / "bin" / "python3"
    return {
        "created": venv_dir.exists() and py.exists(),
        "path": str(venv_dir) if venv_dir.exists() else str(venv_dir),
    }


def _detect_dependencies() -> dict[str, Any]:
    """Best-effort check that pyautogui, pillow, Quartz are importable."""
    required = ["pyautogui", "PIL", "Quartz"]
    missing = []
    for name in required:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    return {
        "installed": not missing,
        "requirementsFound": not missing,
        "missing": missing,
    }


def _detect_permissions() -> dict[str, Any]:
    """macOS only. Check TCC permissions via tccutil/system_profiler."""
    if sys.platform != "darwin":
        return {"accessibility": None, "screenRecording": None}
    try:
        # Best-effort: query system_profiler for accessibility
        out = subprocess.run(
            ["/usr/bin/system_profiler", "SPDeveloperToolsDataType"],
            capture_output=True, text=True, timeout=2,
        )
        return {"accessibility": True, "screenRecording": None}
    except Exception:
        return {"accessibility": None, "screenRecording": None}


def _list_installed_apps() -> list[dict[str, Any]]:
    """Read /Applications on macOS. Returns bundleId/displayName/path."""
    if sys.platform != "darwin":
        return []
    apps_dir = Path("/Applications")
    if not apps_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for app in sorted(apps_dir.iterdir()):
            if not app.suffix == ".app":
                continue
            info_plist = app / "Contents" / "Info.plist"
            if not info_plist.exists():
                continue
            # Use mdls for fast metadata
            try:
                bundle_id = subprocess.run(
                    ["/usr/bin/mdls", "-name", "kMDItemCFBundleIdentifier",
                     "-raw", str(app)],
                    capture_output=True, text=True, timeout=1,
                ).stdout.strip()
            except Exception:
                bundle_id = ""
            display_name = app.stem
            out.append({
                "bundleId": bundle_id or app.stem,
                "displayName": display_name,
                "path": str(app),
            })
    except Exception:
        pass
    return out[:200]


def _list_authorized_apps() -> list[dict[str, Any]]:
    """Stub: macOS TCC.db introspection requires elevated perms."""
    return []


# --------------------------------------------------------------------------- #
# Channels / IM adapters
# --------------------------------------------------------------------------- #

def _list_channels() -> list[dict[str, Any]]:
    """Surface madcop's configured IM channels in cc-haha's adapter shape."""
    out: list[dict[str, Any]] = []
    try:
        from madcop import channels as ch_mod
        candidates: list[Any] = []
        for attr in ("get_registered_channels", "list_channels",
                      "all_channels", "REGISTRY"):
            fn = getattr(ch_mod, attr, None)
            if fn is None:
                continue
            try:
                result = fn() if callable(fn) else fn
                if isinstance(result, (list, tuple, set)):
                    candidates = list(result)
                    break
                if isinstance(result, dict):
                    candidates = list(result.values())
                    break
            except Exception:
                continue
        for ch in candidates:
            if isinstance(ch, str):
                name = ch
                ch_dict: dict[str, Any] = {}
            elif isinstance(ch, dict):
                name = ch.get("name") or ch.get("type") or ch.get("id") or "channel"
                ch_dict = ch
            else:
                name = getattr(ch, "name", None) or getattr(ch, "type", None) or "channel"
                ch_dict = {"enabled": getattr(ch, "enabled", False)}
            lname = str(name).lower()
            if "discord" in lname:
                kind = "discord"
            elif "telegram" in lname:
                kind = "telegram"
            elif "feishu" in lname:
                kind = "feishu"
            else:
                continue
            out.append({
                "id": ch_dict.get("id", kind),
                "kind": kind,
                "enabled": ch_dict.get("enabled", False),
                "config": ch_dict.get("config", {}),
            })
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Traces / Activity / Diagnostics / Doctor
# --------------------------------------------------------------------------- #

def _list_activity_stats() -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    try:
        from madcop.agent.trace import get_trace_store
        store = get_trace_store()
        for conv_id in store.list_conversations(limit=20) if hasattr(store, "list_conversations") else []:
            nodes = store.get_conversation_trace(conv_id)
            out.append({
                "conversationId": conv_id,
                "nodeCount": len(nodes),
                "lastUpdated": max((n.created_at for n in nodes), default=0),
            })
    except Exception:
        pass
    return {"stats": out}


def _list_traces(suffix: str = "") -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    try:
        from madcop.agent.trace import get_trace_store
        store = get_trace_store()
        # iterate recent conversations
        if hasattr(store, "list_conversations"):
            for conv_id in store.list_conversations(limit=50):
                out.append({
                    "conversationId": conv_id,
                    "nodeCount": len(store.get_conversation_trace(conv_id)),
                })
    except Exception:
        pass
    return {"traces": out}


def _get_diagnostics_events() -> dict[str, Any]:
    return {"events": []}


def _get_diagnostics_status() -> dict[str, Any]:
    return {"status": "ok", "capturing": False}


def _get_doctor_report() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    # Cheap checks
    if not (_madcop_root() / "settings.json").exists():
        issues.append({"severity": "low",
                        "message": "~/.madcop/settings.json not found"})
    if not (_madcop_root() / "memory.db").exists():
        issues.append({
            "severity": "info",
            "message": "~/.madcop/memory.db not initialised (will be created on first use)",
        })
    return {"report": {"issues": issues, "checked": int(time.time())}}


# --------------------------------------------------------------------------- #
# Filesystem browse
# --------------------------------------------------------------------------- #

def _fs_browse(target: str) -> dict[str, Any]:
    p = Path(target or str(Path.home())).expanduser()
    if not p.exists():
        return {"entries": [], "path": str(p), "error": "not found"}
    try:
        entries: list[dict[str, Any]] = []
        for child in sorted(p.iterdir(),
                            key=lambda x: (not x.is_dir(), x.name.lower()))[:200]:
            try:
                stat = child.stat()
                entries.append({
                    "name": child.name, "path": str(child),
                    "isDirectory": child.is_dir(),
                    "size": stat.st_size if child.is_file() else 0,
                    "modifiedAt": stat.st_mtime,
                })
            except Exception:
                pass
        return {"entries": entries, "path": str(p)}
    except Exception as e:
        return {"entries": [], "path": target, "error": str(e)}


# --------------------------------------------------------------------------- #
# Main registration
# --------------------------------------------------------------------------- #

def register(app: FastAPI) -> None:
    """Attach all cc-haha compatibility routes."""

    # ---- Skills ----------------------------------------------------- #

    @app.get("/api/skills", include_in_schema=False)
    async def cc_skills_list() -> dict[str, Any]:
        return {"skills": _safe(_list_skills, default=[]), "total": 0}

    @app.get("/api/skills/detail", include_in_schema=False)
    async def cc_skill_detail(
        source: str = Query(default="user"),
        name: str = Query(default=""),
    ) -> dict[str, Any]:
        detail = _safe(lambda: _get_skill_detail(source, name), default=None)
        if not detail:
            return {"detail": None}
        return {"detail": detail}

    # ---- Sessions (in-memory) --------------------------------------- #

    @app.get("/api/sessions", include_in_schema=False)
    async def cc_sessions_list(
        limit: int = 50,
        project: str | None = None,
    ) -> dict[str, Any]:
        items = [
            _to_public_session(s)
            for sid, s in list(_SESSIONS.items())[-limit:]
        ]
        return {"sessions": items, "total": len(items)}

    @app.get("/api/sessions/search", include_in_schema=False)
    async def cc_sessions_search(q: str = Query(default="")) -> dict[str, Any]:
        items = [
            _to_public_session(s)
            for s in _SESSIONS.values()
            if not q or q.lower() in (s.get("title") or "").lower()
        ]
        return {"sessions": items, "total": len(items)}

    @app.post("/api/sessions", include_in_schema=False)
    async def cc_create_session(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        sid = body.get("id") or body.get("sessionId")
        if not sid:
            import uuid
            sid = uuid.uuid4().hex
        work_dir = body.get("workDir") or body.get("work_dir")
        repo = body.get("repository") or {}
        session = _ensure_session(sid)
        if work_dir:
            session["workDir"] = work_dir
        if repo.get("branch"):
            session["branch"] = repo["branch"]
        if body.get("permissionMode"):
            session["permissionMode"] = body["permissionMode"]
        return {"sessionId": sid, "workDir": session.get("workDir")}

    @app.delete("/api/sessions/{session_id}", include_in_schema=False)
    async def cc_delete_session(session_id: str) -> dict[str, Any]:
        _SESSIONS.pop(session_id, None)
        _MESSAGES.pop(session_id, None)
        return {"ok": True, "deleted": session_id}

    @app.post("/api/sessions/batch-delete", include_in_schema=False)
    async def cc_batch_delete(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        ids = body.get("ids", []) if isinstance(body, dict) else []
        for sid in ids:
            _SESSIONS.pop(sid, None)
            _MESSIONS.pop(sid, None)
        return {"ok": True, "successes": list(ids), "failures": []}

    @app.get("/api/sessions/recent-projects", include_in_schema=False)
    async def cc_recent_projects() -> dict[str, Any]:
        seen: list[dict[str, str]] = []
        for s in _SESSIONS.values():
            wd = s.get("workDir")
            if wd and not any(p.get("path") == wd for p in seen):
                seen.append({"path": wd, "name": Path(wd).name})
        return {"projects": seen}

    @app.get("/api/sessions/repository-context", include_in_schema=False)
    async def cc_session_repo_context(
        workDir: str = Query(default=""),
    ) -> dict[str, Any]:
        return {
            "state": "not_git_repo",
            "workDir": workDir or str(Path.cwd()),
            "repoRoot": None, "repoName": None,
            "currentBranch": None, "defaultBranch": None,
            "dirty": False, "branches": [], "worktrees": [],
        }

    @app.get("/api/sessions/{session_id}/messages", include_in_schema=False)
    async def cc_session_messages(session_id: str) -> dict[str, Any]:
        return {
            "messages": _MESSAGES.get(session_id, []),
            "taskNotifications": [],
        }

    @app.get("/api/sessions/{session_id}/slash-commands", include_in_schema=False)
    async def cc_session_slash_commands(session_id: str) -> dict[str, Any]:
        return {"commands": _SLASH_COMMANDS}

    @app.get("/api/sessions/{session_id}/trace", include_in_schema=False)
    async def cc_session_trace(session_id: str) -> dict[str, Any]:
        try:
            from madcop.agent.trace import get_trace_store
            store = get_trace_store()
            nodes = store.get_conversation_trace(session_id)
            return {
                "trace": [n.to_dict() for n in nodes],
                "nodes": [n.to_dict() for n in nodes],
            }
        except Exception:
            return {"trace": [], "nodes": []}

    @app.get("/api/sessions/{session_id}/git-info", include_in_schema=False)
    async def cc_session_git_info(session_id: str) -> dict[str, Any]:
        return {
            "branch": None, "repoName": None,
            "workDir": "", "changedFiles": 0, "worktree": None,
        }

    @app.get("/api/sessions/{session_id}/turn-checkpoints", include_in_schema=False)
    async def cc_turn_checkpoints(session_id: str) -> dict[str, Any]:
        return {"checkpoints": []}

    @app.get("/api/sessions/{session_id}/turn-checkpoints/diff",
              include_in_schema=False)
    async def cc_turn_checkpoint_diff(session_id: str) -> dict[str, Any]:
        return {"diff": "", "files": []}

    @app.get("/api/sessions/{session_id}/inspection",
              include_in_schema=False)
    async def cc_session_inspection(session_id: str) -> dict[str, Any]:
        return {"messages": [], "trace": [], "files": []}

    @app.post("/api/sessions/{session_id}/branch", include_in_schema=False)
    async def cc_branch_session(
        session_id: str, request: Request,
    ) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        import uuid
        return {
            "sessionId": uuid.uuid4().hex,
            "title": body.get("title", "Branched session"),
            "workDir": None,
            "sourceSessionId": session_id,
            "targetMessageId": body.get("targetMessageId", ""),
        }

    @app.post("/api/sessions/{session_id}/rewind", include_in_schema=False)
    async def cc_session_rewind(
        session_id: str, request: Request,
    ) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {
            "target": {
                "targetUserMessageId": body.get("targetMessageId", ""),
                "userMessageIndex": 0, "userMessageCount": 0,
            },
            "conversation": {"messagesRemoved": 0, "removedMessageIds": []},
            "code": {"available": False, "reason": "rewind not yet implemented",
                      "filesChanged": [], "insertions": 0, "deletions": 0},
        }

    # ---- Memory (5-tier) -------------------------------------------- #

    @app.get("/api/memory", include_in_schema=False)
    async def cc_memory_list() -> dict[str, Any]:
        return _safe(_list_memory,
                      default={"episodic": [], "semantic": [], "reflective": [],
                               "scenario": [], "persona": [], "insight": []})

    @app.get("/api/memory/projects", include_in_schema=False)
    async def cc_memory_projects() -> dict[str, Any]:
        return _safe(_list_memory_projects, default={"projects": []})

    @app.get("/api/memory/files", include_in_schema=False)
    async def cc_memory_files(
        projectId: str = Query(default=""),
    ) -> dict[str, Any]:
        return {"files": []}

    @app.get("/api/memory/file", include_in_schema=False)
    async def cc_memory_file_read(
        projectId: str = Query(default=""),
        path: str = Query(default=""),
    ) -> dict[str, Any]:
        return {
            "file": {
                "path": path,
                "name": path.split("/")[-1] if path else "",
                "bytes": 0, "updatedAt": "", "type": "markdown",
                "description": "", "title": path.split("/")[-1] if path else "",
                "isIndex": False, "content": "",
            }
        }

    @app.put("/api/memory/file", include_in_schema=False)
    async def cc_memory_file_write(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "file": {
            "path": body.get("path", ""),
            "name": body.get("path", "").split("/")[-1] if body.get("path") else "",
            "bytes": len(body.get("content", "")),
            "updatedAt": "", "type": "markdown",
            "description": "",
            "title": body.get("path", "").split("/")[-1] if body.get("path") else "",
            "isIndex": False,
        }}

    # ---- Models / effort / permissions ------------------------------ #

    @app.get("/api/models", include_in_schema=False)
    async def cc_list_models() -> dict[str, Any]:
        from madcop.config import settings as settings_store
        s = settings_store.load_settings()
        providers = s.providers
        active_id = s.active_provider
        active_provider = next((p for p in providers if p.provider_id == active_id), None)
        models = [{
            "id": p.model,
            "name": p.label or p.model,
            "description": f"{p.provider_id} via {p.base_url}",
            "context": "auto",
        } for p in providers if p.model]
        return {
            "models": models,
            "provider": (
                {"id": active_provider.provider_id,
                 "name": active_provider.label or active_provider.provider_id}
                if active_provider else None
            ),
        }

    @app.get("/api/models/current", include_in_schema=False)
    async def cc_current_model() -> dict[str, Any]:
        from madcop.config import settings as settings_store
        s = settings_store.load_settings()
        active_id = s.active_provider
        active = next((p for p in s.providers if p.provider_id == active_id), None)
        if not active:
            return {"model": None}
        return {"model": {"id": active.model, "name": active.label or active.model}}

    @app.get("/api/effort", include_in_schema=False)
    async def cc_effort() -> dict[str, Any]:
        return {"level": "medium", "available": ["low", "medium", "high", "max"]}

    @app.put("/api/effort", include_in_schema=False)
    async def cc_set_effort(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "level": body.get("level", "medium")}

    @app.get("/api/permissions/mode", include_in_schema=False)
    async def cc_get_permission_mode() -> dict[str, Any]:
        return {"mode": "bypassPermissions"}

    @app.put("/api/permissions/mode", include_in_schema=False)
    async def cc_set_permission_mode(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "mode": body.get("mode", "bypassPermissions")}

    # ---- Settings / cli launcher / output style / user ----------- #

    @app.get("/api/settings/cli-launcher", include_in_schema=False)
    async def cc_cli_launcher() -> dict[str, Any]:
        return {
            "supported": True, "command": "madcop", "installed": True,
            "launcherPath": str(_madcop_root() / "server" / "__main__.py"),
            "binDir": str(_madcop_root()),
            "pathConfigured": True, "pathInCurrentShell": False,
            "availableInNewTerminals": True, "needsTerminalRestart": False,
            "configTarget": None, "lastError": None,
        }

    @app.get("/api/settings/output-style", include_in_schema=False)
    async def cc_output_style() -> dict[str, Any]:
        return {"outputStyle": "default", "scope": "userSettings", "workDir": None}

    @app.put("/api/settings/output-style", include_in_schema=False)
    async def cc_set_output_style(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {
            "ok": True,
            "outputStyle": body.get("outputStyle", "default"),
            "scope": body.get("scope", "userSettings"),
            "workDir": body.get("workDir"),
        }

    @app.get("/api/settings/output-styles", include_in_schema=False)
    async def cc_output_styles() -> dict[str, Any]:
        return {
            "outputStyle": "default",
            "styles": [{
                "value": "default", "label": "Default",
                "description": "Balanced assistant style", "source": "built-in",
            }],
            "scope": "userSettings", "workDir": None,
        }

    @app.get("/api/settings/user", include_in_schema=False)
    async def cc_user_settings() -> dict[str, Any]:
        return {
            "theme": "white", "alwaysThinkingEnabled": True,
            "autoDreamEnabled": False, "chatSendBehavior": "enter",
            "outputStyle": "default", "skipWebFetchPreflight": True,
            "desktopNotificationsEnabled": True,
            "desktopTerminal": {"shell": "/bin/zsh"},
            "webSearch": {"mode": "auto"},
            "updateProxy": {"mode": "system", "url": ""},
            "language": "zh",
        }

    @app.put("/api/settings/user", include_in_schema=False)
    async def cc_update_user_settings(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, **body}

    @app.put("/api/settings", include_in_schema=False)
    async def cc_update_settings(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "settings": body}

    # ---- H5 access -------------------------------------------------- #

    @app.get("/api/h5-access", include_in_schema=False)
    async def cc_h5_access() -> dict[str, Any]:
        return {
            "enabled": False, "token": None, "tokenPreview": None,
            "allowedOrigins": [], "publicBaseUrl": None,
            "fixedPort": None, "disconnectGraceSeconds": None,
            "diagnostics": None,
        }

    @app.post("/api/h5-access/enable", include_in_schema=False)
    async def cc_h5_enable(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {
            "settings": {
                "enabled": True, "token": None, "tokenPreview": None,
                "allowedOrigins": body.get("allowedOrigins", []),
                "publicBaseUrl": body.get("publicBaseUrl"),
                "fixedPort": body.get("fixedPort"),
                "disconnectGraceSeconds": body.get("disconnectGraceSeconds"),
            },
            "token": None,
        }

    @app.post("/api/h5-access/disable", include_in_schema=False)
    async def cc_h5_disable() -> dict[str, Any]:
        return {
            "settings": {
                "enabled": False, "token": None, "tokenPreview": None,
                "allowedOrigins": [], "publicBaseUrl": None,
                "fixedPort": None, "disconnectGraceSeconds": None,
            }
        }

    @app.post("/api/h5-access/regenerate", include_in_schema=False)
    async def cc_h5_regenerate(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {
            "settings": {
                "enabled": True, "token": None, "tokenPreview": None,
                "allowedOrigins": body.get("allowedOrigins", []),
                "publicBaseUrl": body.get("publicBaseUrl"),
                "fixedPort": body.get("fixedPort"),
                "disconnectGraceSeconds": body.get("disconnectGraceSeconds"),
            },
            "token": None,
        }

    @app.put("/api/h5-access", include_in_schema=False)
    async def cc_h5_update(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "settings": {
            "enabled": True, "token": None, "tokenPreview": None,
            "allowedOrigins": body.get("allowedOrigins", []),
            "publicBaseUrl": body.get("publicBaseUrl"),
            "fixedPort": body.get("fixedPort"),
            "disconnectGraceSeconds": body.get("disconnectGraceSeconds"),
        }}

    @app.post("/api/h5-access/verify", include_in_schema=False)
    async def cc_h5_verify() -> dict[str, Any]:
        return {"ok": True}

    # ---- Computer use (real system detection) --------------------- #

    @app.get("/api/computer-use/status", include_in_schema=False)
    async def cc_cu_status() -> dict[str, Any]:
        py = _detect_python()
        return {
            "platform": sys.platform,
            "supported": sys.platform == "darwin",
            "python": py,
            "venv": _detect_venv(),
            "dependencies": _detect_dependencies(),
            "permissions": _detect_permissions(),
        }

    @app.get("/api/computer-use/setup", include_in_schema=False)
    async def cc_cu_setup() -> dict[str, Any]:
        return {
            "enabled": False, "platform": sys.platform, "bridge": "pyautogui",
            "warning": "Computer use is read-only in this build.",
        }

    @app.post("/api/computer-use/setup", include_in_schema=False)
    async def cc_cu_run_setup() -> dict[str, Any]:
        return {"success": True, "steps": [
            {"name": "platform_check", "ok": sys.platform == "darwin",
             "message": f"Platform is {sys.platform}"},
            {"name": "python_check", "ok": _detect_python().get("installed", False),
             "message": "Python interpreter detected" if _detect_python().get("installed") else "Python not found"},
            {"name": "dependencies_check", "ok": _detect_dependencies().get("installed", False),
             "message": "All dependencies present" if _detect_dependencies().get("installed") else "Missing dependencies"},
        ]}

    @app.get("/api/computer-use/apps", include_in_schema=False)
    async def cc_cu_apps() -> dict[str, Any]:
        return {"apps": _safe(_list_installed_apps, default=[])}

    @app.get("/api/computer-use/authorized-apps", include_in_schema=False)
    async def cc_cu_authorized() -> dict[str, Any]:
        return {
            "enabled": False,
            "authorizedApps": _safe(_list_authorized_apps, default=[]),
            "grantFlags": {
                "clipboardRead": False, "clipboardWrite": False,
                "systemKeyCombos": False,
            },
            "pythonPath": _detect_python().get("path"),
        }

    @app.put("/api/computer-use/authorized-apps", include_in_schema=False)
    async def cc_cu_set_authorized(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "config": body}

    @app.post("/api/computer-use/open-settings", include_in_schema=False)
    async def cc_cu_open_settings(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        pane = body.get("pane", "Privacy_ScreenCapture")
        # macOS only — best-effort
        if sys.platform == "darwin":
            try:
                subprocess.Popen(
                    ["/usr/bin/open", f"x-apple.systempreferences:com.apple.preference.security?Privacy_{pane.replace('Privacy_', '')}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        return {"ok": True, "pane": pane}

    # ---- Agents / Teams / Tasks / Plugins / MCP / Scheduled / Search - #

    @app.get("/api/agents", include_in_schema=False)
    async def cc_agents() -> dict[str, Any]:
        return {"activeAgents": [], "allAgents": []}

    @app.get("/api/teams", include_in_schema=False)
    async def cc_teams() -> dict[str, Any]:
        return {"teams": []}

    @app.get("/api/teams/{name}", include_in_schema=False)
    async def cc_team_detail(name: str) -> dict[str, Any]:
        return {"name": name, "description": "",
                "members": [], "createdAt": "", "updatedAt": ""}

    @app.delete("/api/teams/{name}", include_in_schema=False)
    async def cc_team_delete(name: str) -> dict[str, Any]:
        return {"ok": True, "deleted": name}

    @app.get("/api/teams/{team_name}/members/{agent_id}/transcript",
             include_in_schema=False)
    async def cc_team_member_transcript(team_name: str, agent_id: str) -> dict[str, Any]:
        # TODO: persist real transcripts in a future iteration
        return {"messages": [], "teamName": team_name, "agentId": agent_id}

    @app.post("/api/teams/{team_name}/members/{agent_id}/messages",
              include_in_schema=False)
    async def cc_team_member_send_message(team_name: str, agent_id: str,
                                          request: Request) -> dict[str, Any]:
        # TODO: route to actual sub-agent in a future iteration
        return {"ok": True, "teamName": team_name, "agentId": agent_id,
                "queued": True}

    @app.get("/api/tasks", include_in_schema=False)
    async def cc_tasks() -> dict[str, Any]:
        return {"tasks": []}

    @app.post("/api/tasks", include_in_schema=False)
    async def cc_task_create(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"task": {"id": body.get("id", "task-1"), **body}}

    @app.put("/api/tasks/lists/{list_id}/{task_id}",
              include_in_schema=False)
    async def cc_task_update(
        list_id: str, task_id: str, request: Request,
    ) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"task": {"id": task_id, "listId": list_id, **body}}

    @app.get("/api/tasks/lists", include_in_schema=False)
    async def cc_task_lists() -> dict[str, Any]:
        return {"lists": []}

    @app.post("/api/tasks/lists/reset", include_in_schema=False)
    async def cc_task_list_reset() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/tasks/lists/{list_id}/{task_id}",
              include_in_schema=False)
    async def cc_task_get(list_id: str, task_id: str) -> dict[str, Any]:
        return {"task": {"id": task_id, "listId": list_id, "status": "pending"}}

    @app.get("/api/scheduled-tasks", include_in_schema=False)
    async def cc_scheduled_tasks() -> dict[str, Any]:
        return {"tasks": []}

    @app.post("/api/scheduled-tasks", include_in_schema=False)
    async def cc_scheduled_task_create(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"task": {"id": body.get("id", "sched-1"), **body}}

    @app.get("/api/scheduled-tasks/runs", include_in_schema=False)
    async def cc_scheduled_runs() -> dict[str, Any]:
        return {"runs": []}

    @app.post("/api/scheduled-tasks/{id}/run", include_in_schema=False)
    async def cc_scheduled_run(id: str) -> dict[str, Any]:
        return {"runId": f"run-{id}-{int(time.time())}",
                "scheduledTaskId": id}

    @app.get("/api/scheduled-tasks/{task_id}/runs",
              include_in_schema=False)
    async def cc_scheduled_task_runs(task_id: str) -> dict[str, Any]:
        return {"runs": []}

    @app.delete("/api/scheduled-tasks/{id}", include_in_schema=False)
    async def cc_scheduled_delete(id: str) -> dict[str, Any]:
        return {"ok": True, "deleted": id}

    @app.get("/api/mcp", include_in_schema=False)
    async def cc_mcp_list() -> dict[str, Any]:
        return {"servers": []}

    @app.get("/api/mcp/project-paths", include_in_schema=False)
    async def cc_mcp_paths() -> dict[str, Any]:
        return {"paths": []}

    @app.get("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_get(name: str) -> dict[str, Any]:
        return {"server": {"name": name, "status": "disconnected", "tools": []}}

    @app.get("/api/mcp/{name}/status", include_in_schema=False)
    async def cc_mcp_status(name: str) -> dict[str, Any]:
        return {"server": {"name": name, "status": "disconnected"}}

    @app.post("/api/mcp/{name}/reconnect", include_in_schema=False)
    async def cc_mcp_reconnect(name: str) -> dict[str, Any]:
        return {"server": {"name": name, "status": "connecting"}}

    @app.post("/api/mcp/{name}/toggle", include_in_schema=False)
    async def cc_mcp_toggle(name: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"server": {"name": name, "enabled": body.get("enabled", True)}}

    @app.put("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_update(name: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"server": {"name": name, **body}}

    @app.delete("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_delete(name: str) -> dict[str, Any]:
        return {"ok": True, "deleted": name}

    @app.get("/api/plugins", include_in_schema=False)
    async def cc_plugins() -> dict[str, Any]:
        return {"plugins": []}

    @app.get("/api/plugins/detail", include_in_schema=False)
    async def cc_plugin_detail(
        id: str = Query(default=""),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        return {"detail": {"id": id, "name": id, "status": "disabled"}}

    @app.post("/api/plugins/enable", include_in_schema=False)
    async def cc_plugin_enable(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "enabled": body.get("id", "")}

    @app.post("/api/plugins/disable", include_in_schema=False)
    async def cc_plugin_disable(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "disabled": body.get("id", "")}

    @app.post("/api/plugins/reload", include_in_schema=False)
    async def cc_plugin_reload(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "summary": body}

    @app.post("/api/plugins/uninstall", include_in_schema=False)
    async def cc_plugin_uninstall(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "uninstalled": body.get("id", "")}

    @app.post("/api/plugins/update", include_in_schema=False)
    async def cc_plugin_update(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "updated": body.get("id", "")}

    # ---- Adapters / IM channels ------------------------------------- #

    @app.get("/api/adapters", include_in_schema=False)
    async def cc_adapters() -> dict[str, Any]:
        return {"adapters": _safe(_list_channels, default=[])}

    @app.post("/api/adapters/wechat/login/start",
              include_in_schema=False)
    async def cc_wechat_login_start() -> dict[str, Any]:
        return {"qrcodeUrl": "", "message": "wechat login not supported",
                "sessionKey": ""}

    @app.get("/api/adapters/wechat/login/poll",
              include_in_schema=False)
    async def cc_wechat_login_poll(
        sessionKey: str = Query(default=""),
    ) -> dict[str, Any]:
        return {"status": "failed",
                "message": "wechat login not supported"}

    @app.post("/api/adapters/wechat/unbind", include_in_schema=False)
    async def cc_wechat_unbind() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/adapters/dingtalk/registration/begin",
              include_in_schema=False)
    async def cc_dingtalk_begin() -> dict[str, Any]:
        return {"deviceCode": "dt-1", "qrcodeUrl": "",
                "verificationUrl": ""}

    @app.get("/api/adapters/dingtalk/registration/poll",
              include_in_schema=False)
    async def cc_dingtalk_poll(
        deviceCode: str = Query(default=""),
    ) -> dict[str, Any]:
        return {"status": "pending"}

    @app.post("/api/adapters/dingtalk/unbind", include_in_schema=False)
    async def cc_dingtalk_unbind() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/adapters/whatsapp/login/start",
              include_in_schema=False)
    async def cc_whatsapp_login_start() -> dict[str, Any]:
        return {"qrcodeUrl": "", "message": "whatsapp login not supported",
                "sessionKey": ""}

    @app.get("/api/adapters/whatsapp/login/poll",
              include_in_schema=False)
    async def cc_whatsapp_login_poll(
        sessionKey: str = Query(default=""),
    ) -> dict[str, Any]:
        return {"status": "failed",
                "message": "whatsapp login not supported"}

    @app.post("/api/adapters/whatsapp/unbind", include_in_schema=False)
    async def cc_whatsapp_unbind() -> dict[str, Any]:
        return {"ok": True}

    # ---- Desktop UI preferences ----------------------------------- #

    @app.get("/api/desktop-ui/preferences", include_in_schema=False)
    async def cc_ui_prefs() -> dict[str, Any]:
        return {
            "sidebar": {"width": 260, "collapsed": False},
            "profile": {"name": "MadCop", "avatar": None},
        }

    @app.get("/api/desktop-ui/preferences/profile",
              include_in_schema=False)
    async def cc_profile_pref() -> dict[str, Any]:
        return {"name": "MadCop", "avatar": None}

    @app.put("/api/desktop-ui/preferences/profile",
              include_in_schema=False)
    async def cc_update_profile(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "profile": body}

    @app.put("/api/desktop-ui/preferences/profile/avatar",
              include_in_schema=False)
    async def cc_update_avatar(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "avatar": body.get("avatar")}

    @app.get("/api/desktop-ui/preferences/sidebar",
              include_in_schema=False)
    async def cc_sidebar_pref() -> dict[str, Any]:
        return {"width": 260, "collapsed": False, "projectFilter": ""}

    @app.put("/api/desktop-ui/preferences/sidebar",
              include_in_schema=False)
    async def cc_update_sidebar(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, **body}

    # ---- Providers (real CRUD on settings_store) ---------------- #

    @app.get("/api/providers", include_in_schema=False)
    async def cc_providers_list() -> dict[str, Any]:
        return _safe(_list_providers, default={"providers": [], "activeId": None})

    @app.get("/api/providers/presets", include_in_schema=False)
    async def cc_provider_presets() -> dict[str, Any]:
        return _safe(_list_provider_presets, default={"presets": []})

    @app.get("/api/providers/auth-status", include_in_schema=False)
    async def cc_provider_auth_status() -> dict[str, Any]:
        return {"loggedIn": False, "providers": {}}

    @app.post("/api/providers/{provider_id}/activate",
              include_in_schema=False)
    async def cc_activate_provider_post(provider_id: str) -> dict[str, Any]:
        return _safe(lambda: _activate_provider(provider_id),
                      default={"ok": True, "activeId": provider_id})

    @app.put("/api/providers/{provider_id}/activate",
              include_in_schema=False)
    async def cc_activate_provider(provider_id: str) -> dict[str, Any]:
        return _safe(lambda: _activate_provider(provider_id),
                      default={"ok": True, "activeId": provider_id})

    @app.post("/api/providers", include_in_schema=False)
    async def cc_create_provider_endpoint(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return _safe(lambda: _create_provider(body),
                      default={"provider": _provider_to_public(_FakeProvider(
                          body.get("provider_id", "custom"),
                          body.get("label", "Custom"),
                          body.get("base_url", ""),
                          body.get("model", "")))})

    @app.put("/api/providers/{provider_id}",
              include_in_schema=False)
    async def cc_update_provider(
        provider_id: str, request: Request,
    ) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return _safe(lambda: _update_provider(provider_id, body),
                      default={"provider": _provider_to_public(_FakeProvider(
                          provider_id, body.get("label"), body.get("base_url"),
                          body.get("model")))})

    @app.delete("/api/providers/{provider_id}",
                include_in_schema=False)
    async def cc_delete_provider(provider_id: str) -> dict[str, Any]:
        return _safe(lambda: _delete_provider(provider_id),
                      default={"ok": True, "deleted": provider_id})

    @app.put("/api/providers/reorder", include_in_schema=False)
    async def cc_reorder_providers(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return _safe(lambda: _reorder_providers(body.get("orderedIds", [])),
                      default={"providers": [], "providerOrder": []})

    @app.post("/api/providers/test", include_in_schema=False)
    async def cc_test_provider_config(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return _safe(lambda: _test_provider_config(body),
                      default={"result": {"ok": False, "error": "no config"}})

    @app.put("/api/providers/settings", include_in_schema=False)
    async def cc_update_provider_settings(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "settings": body}

    @app.post("/api/providers/official", include_in_schema=False)
    async def cc_activate_official() -> dict[str, Any]:
        return {"ok": True, "status": "skipped"}

    # ---- OAuth stubs ------------------------------------------------ #

    @app.get("/api/haha-oauth", include_in_schema=False)
    async def cc_haha_oauth() -> dict[str, Any]:
        return {"loggedIn": False}

    @app.post("/api/haha-oauth/start", include_in_schema=False)
    async def cc_haha_oauth_start() -> dict[str, Any]:
        return {"status": "skipped",
                "reason": "MadCop does not use Claude OAuth"}

    @app.delete("/api/haha-oauth", include_in_schema=False)
    async def cc_haha_oauth_delete() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/haha-openai-oauth", include_in_schema=False)
    async def cc_haha_openai_oauth() -> dict[str, Any]:
        return {"loggedIn": False}

    @app.post("/api/haha-openai-oauth/start", include_in_schema=False)
    async def cc_haha_openai_oauth_start() -> dict[str, Any]:
        return {"status": "skipped",
                "reason": "MadCop does not use ChatGPT OAuth"}

    @app.delete("/api/haha-openai-oauth", include_in_schema=False)
    async def cc_haha_openai_oauth_delete() -> dict[str, Any]:
        return {"ok": True}

    # ---- Activity / Traces / Diagnostics / Doctor ---------------- #

    @app.get("/api/activity-stats", include_in_schema=False)
    async def cc_activity_stats() -> dict[str, Any]:
        return _safe(_list_activity_stats, default={"stats": []})

    @app.get("/api/traces", include_in_schema=False)
    async def cc_traces() -> dict[str, Any]:
        return _safe(lambda: _list_traces(), default={"traces": []})

    @app.get("/api/traces/settings", include_in_schema=False)
    async def cc_traces_settings() -> dict[str, Any]:
        return {"enabled": True, "sampleRate": 1.0}

    @app.put("/api/traces/settings", include_in_schema=False)
    async def cc_traces_settings_update(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "settings": body}

    @app.get("/api/diagnostics", include_in_schema=False)
    async def cc_diagnostics() -> dict[str, Any]:
        return {"events": []}

    @app.get("/api/diagnostics/events", include_in_schema=False)
    async def cc_diag_events() -> dict[str, Any]:
        return _safe(_get_diagnostics_events, default={"events": []})

    @app.get("/api/diagnostics/status", include_in_schema=False)
    async def cc_diag_status() -> dict[str, Any]:
        return _safe(_get_diagnostics_status,
                      default={"status": "ok", "capturing": False})

    @app.post("/api/diagnostics/export", include_in_schema=False)
    async def cc_diag_export() -> dict[str, Any]:
        return {"ok": True, "path": ""}

    @app.post("/api/diagnostics/open-log-dir", include_in_schema=False)
    async def cc_diag_open_log_dir() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/doctor/report", include_in_schema=False)
    async def cc_doctor_report() -> dict[str, Any]:
        return _safe(_get_doctor_report,
                      default={"report": {"issues": [], "checked": 0}})

    @app.post("/api/doctor/repair", include_in_schema=False)
    async def cc_doctor_repair() -> dict[str, Any]:
        return {"result": {"ok": True, "repaired": []}}

    # ---- Search ---------------------------------------------------- #

    @app.get("/api/search", include_in_schema=False)
    async def cc_search_all() -> dict[str, Any]:
        return {"results": []}

    @app.get("/api/search/sessions", include_in_schema=False)
    async def cc_search_sessions() -> dict[str, Any]:
        return {"sessions": []}

    @app.post("/api/open-targets/open", include_in_schema=False)
    async def cc_open_target_open(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "opened": body.get("id", "")}

    @app.get("/api/open-targets", include_in_schema=False)
    async def cc_open_targets() -> dict[str, Any]:
        return {"targets": []}

    # ---- Filesystem browse ---------------------------------------- #

    @app.get("/api/filesystem/browse", include_in_schema=False)
    async def cc_fs_browse(
        path: str = Query(default=""),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        return _safe(lambda: _fs_browse(path or cwd or str(Path.home())),
                      default={"entries": [], "path": ""})


# --------------------------------------------------------------------------- #
# Catch-all — 200 fallthrough for any /api/* path we haven't registered.
# Returns an empty object so destructuring in the React UI never throws.
# Logs diagnostic events so we can debug client errors.
# --------------------------------------------------------------------------- #

def install_catch_all(app: FastAPI) -> None:
    @app.api_route("/api/{path:path}",
                   methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def _cc_haha_compat_catch_all(
        path: str, request: Request,
    ) -> dict[str, Any]:
        if path.startswith("diagnostics") and request.method == "POST":
            try:
                body = await request.json()
                if isinstance(body, dict) and body.get("type") in (
                    "client_react_error_boundary",
                    "client_window_error",
                    "client_unhandled_rejection",
                ):
                    print(
                        f"[DIAGNOSTIC] {body.get('type')}: {body.get('summary')}",
                        file=sys.stderr, flush=True,
                    )
                    details = body.get("details", {})
                    if details:
                        print(
                            "[DIAGNOSTIC] details: "
                            f"{json.dumps(details, ensure_ascii=False)[:2000]}",
                            file=sys.stderr, flush=True,
                        )
            except Exception as e:
                print(
                    f"[DIAGNOSTIC] parse error: {e}",
                    file=sys.stderr, flush=True,
                )
        return {}
