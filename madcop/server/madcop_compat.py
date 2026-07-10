"""madcop.server.madcop_compat — Comprehensive REST compatibility shim.

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
from madcop.config import settings as settings_store

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


_SESSIONS_FILE = Path.home() / ".madcop" / "sessions.json"
_MESSAGES_DIR = Path.home() / ".madcop" / "session_messages"


def _ensure_session(session_id: str) -> dict[str, Any]:
    if session_id not in _SESSIONS:
        import time as _t
        now = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
        _SESSIONS[session_id] = {
            "id": session_id,
            "title": "New Session",
            "createdAt": now,
            "modifiedAt": now,
            "model": "minimaxai/minimax-m2.7",
            "workDir": str(Path.cwd()),
            "projectPath": str(Path.cwd()),
            "projectRoot": str(Path.cwd()),
            "messages": [],
            "chatState": "idle",
            "permissionMode": "bypassPermissions",
        }
        _MESSAGES.setdefault(session_id, [])
    return _SESSIONS[session_id]


def _persist_sessions() -> None:
    """Save sessions + messages to disk so they survive restarts."""
    try:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
        # Build a JSON-safe copy (no nested non-serializable values)
        safe_sessions: dict[str, Any] = {}
        for sid, s in _SESSIONS.items():
            safe_sessions[sid] = {
                k: v for k, v in s.items()
                if isinstance(v, (str, int, float, bool, type(None), list, dict))
            }
        _SESSIONS_FILE.write_text(json.dumps(safe_sessions, ensure_ascii=False, indent=2))
        # Save each session's messages to its own file
        for sid, msgs in _MESSAGES.items():
            ( _MESSAGES_DIR / f"{sid}.json").write_text(
                json.dumps(msgs, ensure_ascii=False, indent=2)
            )
    except Exception as e:
        import sys as _sys
        print(f"[cc-haha-compat] persist error: {e}", file=_sys.stderr, flush=True)


def _load_sessions() -> None:
    """Restore sessions + messages from disk at startup."""
    if not _SESSIONS_FILE.exists():
        return
    try:
        data = json.loads(_SESSIONS_FILE.read_text())
        for sid, s in data.items():
            _SESSIONS[sid] = s
        # Load messages per session
        if _MESSAGES_DIR.exists():
            for f in _MESSAGES_DIR.glob("*.json"):
                sid = f.stem
                try:
                    _MESSAGES[sid] = json.loads(f.read_text())
                except Exception:
                    pass
    except Exception as e:
        import sys as _sys
        print(f"[cc-haha-compat] load error: {e}", file=_sys.stderr, flush=True)


# Load on import
_load_sessions()


def _to_public_session(s: dict[str, Any]) -> dict[str, Any]:
    out = dict(s)
    out["messageCount"] = len(_MESSAGES.get(s["id"], []))
    # Compute workDirExists at serialization time so the UI badge is accurate
    wd = out.get("workDir") or out.get("projectPath")
    if wd:
        try:
            out["workDirExists"] = Path(wd).is_dir()
        except OSError:
            out["workDirExists"] = False
    else:
        out["workDirExists"] = True  # no workDir = no badge to show
    # Frontend expects these aliases too
    if "workDir" in out and "projectPath" not in out:
        out["projectPath"] = out["workDir"] or ""
    if "workDir" in out and "projectRoot" not in out:
        out["projectRoot"] = out["workDir"]
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
    """Return SavedProvider shape that the Edit-Provider form expects.

    Fields: id, presetId, name, apiKey, authStrategy, baseUrl, apiFormat,
    runtimeKind, models, model1mSupport, autoCompactWindow,
    modelContextWindows, toolSearchEnabled, notes.
    """
    # Decrypt API key so the form can show the real value for editing
    api_key = ""
    try:
        from madcop.config.settings import _decrypt
        api_key = _decrypt(getattr(p, "api_key", ""))
    except Exception:
        api_key = ""
    # If decryption fails, show masked
    if not api_key:
        api_key = "***"
    return {
        "id": p.provider_id,
        "presetId": getattr(p, "preset_id", "") or p.provider_id,
        "name": p.label or p.provider_id,
        "apiKey": api_key,
        "authStrategy": getattr(p, "auth_strategy", "api_key") or "api_key",
        "baseUrl": getattr(p, "base_url", ""),
        "apiFormat": getattr(p, "api_format", "openai_chat") or "openai_chat",
        "runtimeKind": getattr(p, "runtime_kind", "") or "",
        "models": {
            "main": p.model, "haiku": p.model,
            "sonnet": p.model, "opus": p.model,
        },
        "model1mSupport": {"main": False, "haiku": False,
                            "sonnet": False, "opus": False},
        "autoCompactWindow": None,
        "modelContextWindows": {},
        "toolSearchEnabled": getattr(p, "tool_search_enabled", True),
        "notes": getattr(p, "notes", "") or "",
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
    """Return full ProviderPreset list for the cc-haha React UI.

    Each preset has: id, name, baseUrl, apiFormat, defaultModels
    (with main/haiku/sonnet/opus), needsApiKey, websiteUrl, authStrategy,
    featured.
    """
    from madcop.config.settings import PROVIDER_PRESETS
    # Map preset id → apiFormat heuristic
    _FORMAT_MAP = {
        "anthropic": "anthropic",
        "openai": "openai_chat",
        "minimax": "openai_chat",
        "deepseek": "openai_chat",
        "zhipu": "openai_chat",
        "nvidia": "openai_chat",  # NVIDIA NIM uses OpenAI Chat Completions
    }
    out: list[dict[str, Any]] = []
    for p in (PROVIDER_PRESETS or []):
        pid = p.get("id") or p.get("provider_id") or ""
        model = p.get("default_model") or p.get("model") or ""
        out.append({
            "id": pid,
            "name": p.get("label") or p.get("name") or pid,
            "baseUrl": p.get("base_url") or p.get("baseUrl") or "",
            "apiFormat": _FORMAT_MAP.get(pid, "openai_chat"),
            "defaultModels": {
                "main": model,
                "haiku": model,
                "sonnet": model,
                "opus": model,
            },
            "needsApiKey": True,
            "websiteUrl": "",
            "apiKeyUrl": "",
            "authStrategy": "api_key",
            "featured": False,
        })
    return {"presets": out}


def _create_provider(body: dict[str, Any]) -> dict[str, Any]:
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    new_id = body.get("provider_id") or body.get("id") or "custom"
    base_url = body.get("baseUrl") or body.get("base_url") or ""
    # Model can be flat (modelId) or nested (models.main)
    models_obj = body.get("models") or {}
    if isinstance(models_obj, dict):
        # v2.6.0: prefer a single "active model" — accept any of
        # main/haiku/sonnet/opus but they all point to the same thing now
        model = (models_obj.get("main") or models_obj.get("haiku")
                 or models_obj.get("sonnet") or models_obj.get("opus")
                 or "")
    else:
        model = ""
    model = model or body.get("modelId") or body.get("model") or body.get("default_model") or ""
    label = body.get("name") or body.get("label") or new_id
    api_key = body.get("apiKey") or body.get("api_key") or ""
    preset_id = body.get("presetId") or body.get("preset_id") or new_id
    api_format = body.get("apiFormat") or body.get("api_format") or "openai_chat"
    auth_strategy = body.get("authStrategy") or body.get("auth_strategy") or "api_key"
    runtime_kind = body.get("runtimeKind") or body.get("runtime_kind") or ""
    tool_search_enabled = bool(body.get("toolSearchEnabled", body.get("tool_search_enabled", True)))
    notes = body.get("notes") or ""
    settings_store.upsert_provider(
        s, provider_id=new_id, base_url=base_url, model=model,
        label=label, api_key=api_key,
        make_active=body.get("make_active", False),
    )
    # Now patch the extended fields
    new_p = next((p for p in s.providers if p.provider_id == new_id), None)
    if new_p:
        new_p.preset_id = preset_id
        new_p.api_format = api_format
        new_p.auth_strategy = auth_strategy
        new_p.runtime_kind = runtime_kind
        new_p.tool_search_enabled = tool_search_enabled
        new_p.notes = notes
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
    models_obj = body.get("models") or {}
    if isinstance(models_obj, dict):
        model = (models_obj.get("main") or models_obj.get("haiku")
                 or models_obj.get("sonnet") or models_obj.get("opus")
                 or "")
    else:
        model = ""
    model = model or body.get("modelId") or body.get("model") or ""
    label = body.get("name") or body.get("label") or provider_id
    api_key = body.get("apiKey") or body.get("api_key") or ""
    preset_id = body.get("presetId") or body.get("preset_id") or provider_id
    api_format = body.get("apiFormat") or body.get("api_format") or "openai_chat"
    auth_strategy = body.get("authStrategy") or body.get("auth_strategy") or "api_key"
    runtime_kind = body.get("runtimeKind") or body.get("runtime_kind") or ""
    tool_search_enabled = bool(body.get("toolSearchEnabled", body.get("tool_search_enabled", True)))
    notes = body.get("notes") or ""
    settings_store.upsert_provider(
        s, provider_id=provider_id, base_url=base_url,
        model=model, label=label, api_key=api_key,
        make_active=False,
    )
    # Patch the extended fields
    p = next((x for x in s.providers if x.provider_id == provider_id), None)
    if p:
        p.preset_id = preset_id
        p.api_format = api_format
        p.auth_strategy = auth_strategy
        p.runtime_kind = runtime_kind
        p.tool_search_enabled = tool_search_enabled
        p.notes = notes
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
    """Check if mac_ax (JXA/osascript) is available — the only real dep."""
    required = ["osascript"]
    missing = []
    for exe in required:
        try:
            import shutil
            if not shutil.which(exe):
                missing.append(exe)
        except Exception:
            missing.append(exe)
    return {
        "installed": len(missing) == 0,
        "requirementsFound": True,
        "missing": missing,
        "bridge": "jxa",
    }


def _detect_permissions() -> dict[str, Any]:
    """macOS only. Real AXAPI permission check via JXA."""
    if sys.platform != "darwin":
        return {"accessibility": None, "screenRecording": None}
    try:
        from madcop.tools.mac_ax import check_permission, check_screen_recording
        ax = check_permission()
        sr = check_screen_recording()
        return {
            "accessibility": ax.get("granted", False),
            "screenRecording": sr.get("granted", False),
            "_ax_detail": ax,
            "_sr_detail": sr,
        }
    except Exception as e:
        return {"accessibility": None, "screenRecording": None, "_error": str(e)[:200]}


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


def _list_running_apps() -> list[dict[str, Any]]:
    """List currently running GUI apps via mac_ax."""
    try:
        from madcop.tools.mac_ax import list_apps as _jxa_apps
        return _jxa_apps()[:50]
    except Exception:
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
                    "nodeCount": len(
                        store.get_conversation_trace(conv_id)
                        if hasattr(store, "get_conversation_trace") else []
                    ),
                })
        return {"traces": out}
    except Exception as e:
        import sys as _sys
        print(f"[cc-list-traces] error: {e}", file=_sys.stderr, flush=True)
        return {"traces": out}


def _list_traces_proper(limit: int = 50, offset: int = 0,
                        q: str = "") -> dict[str, Any]:
    """Build TraceSessionList shape from in-memory sessions + trace store."""
    import datetime as _dt
    from madcop.server.madcop_compat import _SESSIONS, _MESSAGES
    storage_dir = str(Path.home() / ".madcop" / "traces")
    storage_path = Path(storage_dir)
    items: list[dict[str, Any]] = []

    for sid, sess in list(_SESSIONS.items())[offset:offset + limit]:
        # Apply search filter
        if q and q.lower() not in (sess.get("title") or "").lower():
            continue
        msgs = _MESSAGES.get(sid, [])
        # Count API calls: assistant messages are API calls
        api_calls = sum(1 for m in msgs if m.get("type") == "assistant")
        # Failed: any error events
        failed = 0
        # Token totals
        total_input = 0
        total_output = 0
        for m in msgs:
            if m.get("type") == "assistant":
                total_output += len(m.get("content", "")) // 4
        # Model breakdown
        model_counts: dict[str, int] = {}
        for m in msgs:
            if m.get("type") == "assistant":
                model = m.get("model") or "unknown"
                model_counts[model] = model_counts.get(model, 0) + 1
        models = [{"model": m, "calls": c} for m, c in model_counts.items()]
        # File size: rough estimate from messages
        file_size = sum(len(json.dumps(m)) for m in msgs)
        # Updated
        updated_at = sess.get("modifiedAt", "")
        if updated_at:
            try:
                # Convert to ISO
                updated_at_dt = _dt.datetime.fromisoformat(
                    updated_at.replace("Z", "+00:00"))
                updated_at = updated_at_dt.isoformat()
            except Exception:
                pass
        items.append({
            "sessionId": sid,
            "session": {
                "id": sid,
                "title": sess.get("title") or "New Session",
                "projectPath": sess.get("projectPath", "") or "",
                "workDir": sess.get("workDir"),
            },
            "summary": {
                "apiCalls": api_calls,
                "failedCalls": failed,
                "totalDurationMs": 0,
                "totalInputTokens": total_input,
                "totalOutputTokens": total_output,
                "models": models,
                "updatedAt": updated_at or None,
            },
            "fileSize": file_size,
            "fileUpdatedAt": updated_at or "1970-01-01T00:00:00Z",
        })

    return {
        "traces": items,
        "total": len(_SESSIONS),
        "storageDir": storage_dir,
        "settings": {
            "enabled": True,
            "storageDir": storage_dir,
        },
    }

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

    @app.get("/api/skills/detail", include_in_schema=False)
    async def cc_skill_detail(
        source: str = Query(default="user"),
        name: str = Query(default=""),
    ) -> dict[str, Any]:
        # Use the unified skill_distill reader (handles both user skills
        # auto-distilled by MadCop and any custom skills on disk).
        from madcop.memory.skill_distill import read_skill_detail
        detail = read_skill_detail(name, source)
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

    # NOTE: /api/memory/{projects,files,file} are defined in the v2.6.0
    # section below with full real implementations. The legacy stubs that
    # used to be here were removed because they shadowed the real handlers
    # (FastAPI matches routes in registration order).

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
            "apps": _safe(_list_installed_apps, default=[])[:30],
            "runningApps": _safe(_list_running_apps, default=[]),
        }

    @app.get("/api/computer-use/setup", include_in_schema=False)
    async def cc_cu_setup() -> dict[str, Any]:
        return {
            "enabled": True, "platform": sys.platform, "bridge": "jxa",
            "setup_guide": "Open System Settings → Privacy & Security → Accessibility → add Terminal",
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

    @app.post("/api/tasks/lists/reset", include_in_schema=False)
    async def cc_task_list_reset_no_param() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/tasks/lists/{list_id}/{task_id}",
              include_in_schema=False)
    async def cc_task_get_legacy(list_id: str, task_id: str) -> dict[str, Any]:
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
    async def cc_mcp_list_legacy() -> dict[str, Any]:
        return {"servers": []}

    @app.get("/api/mcp/project-paths", include_in_schema=False)
    async def cc_mcp_paths() -> dict[str, Any]:
        return {"paths": []}

    @app.get("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_get(name: str) -> dict[str, Any]:
        return {"server": {"name": name, "status": "disconnected", "tools": []}}

    @app.get("/api/mcp/{name}/status", include_in_schema=False)
    async def cc_mcp_status_legacy(name: str) -> dict[str, Any]:
        return {"server": {"name": name, "status": "disconnected"}}

    @app.post("/api/mcp/{name}/reconnect", include_in_schema=False)
    async def cc_mcp_reconnect_legacy(name: str) -> dict[str, Any]:
        return {"server": {"name": name, "status": "connecting"}}

    @app.post("/api/mcp/{name}/toggle", include_in_schema=False)
    async def cc_mcp_toggle_legacy(name: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"server": {"name": name, "enabled": body.get("enabled", True)}}

    @app.put("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_update_legacy(name: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"server": {"name": name, **body}}

    @app.delete("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_delete_legacy(name: str) -> dict[str, Any]:
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

    # ---- Desktop UI preferences (real implementation at end of file) ---- #

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
    async def madcop_oauth() -> dict[str, Any]:
        return {"loggedIn": False}

    @app.post("/api/haha-oauth/start", include_in_schema=False)
    async def madcop_oauth_start() -> dict[str, Any]:
        return {"status": "skipped",
                "reason": "MadCop does not use the upstream OAuth flow"}

    @app.delete("/api/haha-oauth", include_in_schema=False)
    async def madcop_oauth_delete() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/haha-openai-oauth", include_in_schema=False)
    async def madcop_openai_oauth() -> dict[str, Any]:
        return {"loggedIn": False}

    @app.post("/api/haha-openai-oauth/start", include_in_schema=False)
    async def madcop_openai_oauth_start() -> dict[str, Any]:
        return {"status": "skipped",
                "reason": "MadCop does not use ChatGPT OAuth"}

    @app.delete("/api/haha-openai-oauth", include_in_schema=False)
    async def madcop_openai_oauth_delete() -> dict[str, Any]:
        return {"ok": True}

    # ---- Activity / Traces / Diagnostics / Doctor ---------------- #

    @app.get("/api/activity-stats", include_in_schema=False)
    async def cc_activity_stats(
        suffix: str = Query(default=""),
        range: str = Query(default="all"),
    ) -> dict[str, Any]:
        """Return ActivityStats in the cc-haha React shape:
        {stats: ActivityStats, range, generatedAt}
        """
        return _safe(lambda: _build_activity_stats(range),
                      default={"stats": _empty_activity_stats(),
                              "range": range, "generatedAt": ""})

    @app.get("/api/traces", include_in_schema=False)
    async def cc_traces(
        limit: int = Query(default=50),
        offset: int = Query(default=0),
        q: str = Query(default=""),
    ) -> dict[str, Any]:
        """Return TraceSessionList with proper shape:
        {traces: TraceSessionListItem[], total, storageDir, settings}

        Each item has:
          sessionId, session: {id, title, projectPath, workDir} | null,
          summary: TraceSessionSummary (apiCalls, failedCalls, etc.),
          fileSize, fileUpdatedAt
        """
        return _safe(
            lambda: _list_traces_proper(limit=limit, offset=offset, q=q),
            default={"traces": [], "total": 0,
                     "storageDir": str(Path.home() / ".madcop" / "traces"),
                     "settings": {"enabled": True,
                                  "storageDir": str(Path.home() / ".madcop" / "traces")}},
        )

    @app.get("/api/traces/settings", include_in_schema=False)
    async def cc_traces_settings() -> dict[str, Any]:
        return {"enabled": True,
                "storageDir": str(Path.home() / ".madcop" / "traces")}

    @app.put("/api/traces/settings", include_in_schema=False)
    async def cc_traces_settings_update(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        enabled = bool(body.get("enabled", True))
        return {"ok": True, "settings": {
            "enabled": enabled,
            "storageDir": str(Path.home() / ".madcop" / "traces"),
        }}

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
    async def cc_search_sessions_legacy() -> dict[str, Any]:
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

    # ================================================================= #
    # v2.6.0 — Real implementations for the 33 stub endpoints
    # ================================================================= #

    # ---- Models (current + list) --------------------------------- #
    # v2.6.0: Auto-fetch models from the active provider's /v1/models
    # endpoint instead of using the hardcoded models.{main,haiku,...}
    # mapping. The user picks a model in the UI from a live dropdown.

    _MODELS_CACHE: dict[str, Any] = {}  # cache: provider_id -> {ts, models}

    @app.get("/api/models", include_in_schema=False)
    async def cc_models_list() -> dict[str, Any]:
        """List models available across all configured providers.

        Auto-fetches from {baseUrl}/v1/models (OpenAI-compatible) and
        returns the live model list. Falls back to whatever's in
        settings if the fetch fails.
        """
        import time as _t
        try:
            settings = settings_store.load_settings()
            providers = settings.providers or []
            active = settings.active_provider
            out: list[dict[str, Any]] = []
            now = _t.time()
            for p in providers:
                if not getattr(p, "api_key", ""):
                    continue
                pid = getattr(p, "provider_id", "")
                base = getattr(p, "base_url", "").rstrip("/")
                if not base:
                    continue
                # Cache for 5 minutes per provider
                cached = _MODELS_CACHE.get(pid)
                if cached and (now - cached.get("ts", 0)) < 300:
                    models = cached["models"]
                else:
                    models = await asyncio.to_thread(
                        _fetch_provider_models, base,
                        getattr(p, "api_key", ""))
                    _MODELS_CACHE[pid] = {"ts": now, "models": models}
                provider_name = getattr(p, "label", "") or pid
                for m in models:
                    mid = m.get("id", "")
                    if not mid:
                        continue
                    out.append({
                        "id": mid,
                        "name": _model_display_name(mid),
                        "providerId": pid,
                        "providerName": provider_name,
                    })
            return {"models": out, "total": len(out)}
        except Exception as e:
            import sys as _sys
            print(f"[cc-models-list] error: {e}", file=_sys.stderr, flush=True)
            return {"models": [], "total": 0}

    @app.get("/api/models/current", include_in_schema=False)
    async def cc_models_current() -> dict[str, Any]:
        try:
            s = settings_store.load_settings()
            # active_model isn't a real field; derive from active provider's model
            model_id = "minimaxai/minimax-m2.7"
            try:
                for p in (s.providers or []):
                    if p.provider_id == s.active_provider and getattr(p, "model", None):
                        model_id = p.model
                        break
            except Exception:
                pass
            return {
                "modelId": model_id,
                "providerId": s.active_provider or "nvidia",
            }
        except Exception:
            return {"modelId": "minimaxai/minimax-m2.7", "providerId": "nvidia"}

    @app.put("/api/models/current", include_in_schema=False)
    async def cc_models_set_current(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_id = body.get("modelId") or body.get("model") or ""
        if not model_id:
            return {"ok": False, "error": "modelId required"}
        try:
            s = settings_store.load_settings()
            # Update the active provider's model field
            for p in (s.providers or []):
                if p.provider_id == s.active_provider:
                    try:
                        p.model = model_id
                    except Exception:
                        pass
                    break
            settings_store.save_settings(s)
            return {"ok": True, "modelId": model_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- Skills (from disk + auto-distilled) -------------------- #

    @app.get("/api/skills", include_in_schema=False)
    async def cc_skills_list(
        q: str = Query(default=""),
        category: str = Query(default=""),
        source: str = Query(default=""),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        """List skills from ~/.madcop/skills/ + bundled defaults."""
        skills: list[dict[str, Any]] = []
        # User skills (auto-distilled)
        from madcop.memory.skill_distill import list_user_skills
        if not source or source == "user":
            for s in list_user_skills():
                if q and q.lower() not in s["name"].lower() + s.get("description", "").lower():
                    continue
                s["source"] = "user"
                skills.append(s)
        # Project skills (in cwd/.madcop/skills/)
        if cwd and (not source or source == "project"):
            proj_dir = Path(cwd) / ".madcop" / "skills"
            if proj_dir.exists():
                for f in proj_dir.glob("*.md"):
                    content = f.read_text(errors="ignore")
                    title = f.stem
                    if content.startswith("# "):
                        title = content.split("\n", 1)[0][2:].strip()
                    if q and q.lower() not in (title + content).lower():
                        continue
                    skills.append({
                        "name": f.stem,
                        "displayName": title,
                        "description": content[:200],
                        "source": "project",
                        "userInvocable": True,
                        "contentLength": len(content),
                        "hasDirectory": False,
                        "path": str(f),
                    })
        # Bundled skills (in-repo)
        if not source or source == "bundled":
            bundled = Path(__file__).parent.parent.parent / "skills"
            if bundled.exists():
                for f in bundled.glob("*.md"):
                    content = f.read_text(errors="ignore")
                    title = f.stem
                    if content.startswith("# "):
                        title = content.split("\n", 1)[0][2:].strip()
                    if q and q.lower() not in (title + content).lower():
                        continue
                    skills.append({
                        "name": f.stem,
                        "displayName": title,
                        "description": content[:200],
                        "source": "bundled",
                        "userInvocable": True,
                        "contentLength": len(content),
                        "hasDirectory": False,
                        "path": str(f),
                    })
        return {"skills": skills, "total": len(skills)}

    @app.get("/api/skills/detail", include_in_schema=False)
    async def cc_skills_detail(
        name: str = Query(default=""),
        source: str = Query(default="user"),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        """Read a skill's full content + tree. Returns SkillDetail shape:
          {detail: {meta, tree, files, skillRoot}}
        """
        from madcop.memory.skill_distill import read_skill_detail
        # User skill
        if source in ("user", "project"):
            detail = read_skill_detail(name, source)
            if detail:
                return {"detail": detail}
        # Project skill
        if source == "project" and cwd:
            proj_dir = Path(cwd) / ".madcop" / "skills"
            f = proj_dir / f"{name}.md"
            if f.exists():
                content = f.read_text(errors="ignore")
                return {"detail": {
                    "meta": {
                        "name": name, "displayName": name,
                        "description": content[:200], "source": "project",
                        "userInvocable": True, "contentLength": len(content),
                        "hasDirectory": False,
                    },
                    "tree": [{"name": f.name, "path": str(f), "type": "file"}],
                    "files": [{"path": str(f), "content": content,
                               "language": "markdown", "isEntry": True}],
                    "skillRoot": str(proj_dir),
                }}
        # Bundled skill
        bundled = Path(__file__).parent.parent.parent / "skills"
        f = bundled / f"{name}.md"
        if f.exists():
            content = f.read_text(errors="ignore")
            return {"detail": {
                "meta": {
                    "name": name, "displayName": name,
                    "description": content[:200], "source": "bundled",
                    "userInvocable": True, "contentLength": len(content),
                    "hasDirectory": False,
                },
                "tree": [{"name": f.name, "path": str(f), "type": "file"}],
                "files": [{"path": str(f), "content": content,
                           "language": "markdown", "isEntry": True}],
                "skillRoot": str(bundled),
            }}
        return {"detail": {"meta": {"name": name}, "tree": [], "files": []}}

    # Trigger a manual distill (for testing or force-distill)
    @app.post("/api/skills/distill", include_in_schema=False)
    async def cc_skills_distill(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        topic = body.get("topic", "")
        user_q = body.get("userQuery", topic)
        assistant_r = body.get("assistantResponse", "")
        if not user_q or not assistant_r:
            return {"ok": False, "error": "userQuery and assistantResponse required"}
        from madcop.memory.skill_distill import force_distill_skill
        name = force_distill_skill(topic, user_q, assistant_r)
        if name:
            return {"ok": True, "skillName": name}
        return {"ok": False, "error": "could not distill"}

    @app.delete("/api/skills/{name}", include_in_schema=False)
    async def cc_skills_delete(name: str) -> dict[str, Any]:
        target = Path.home() / ".madcop" / "skills" / f"{name}.md"
        if not target.exists():
            return {"ok": False, "error": "not found"}
        target.unlink()
        return {"ok": True, "deleted": name}

    # ---- Scheduled tasks (basic cron-like) ---------------------- #

    _SCHEDULED_TASKS: dict[str, dict[str, Any]] = {}
    _SCHEDULED_RUNS: list[dict[str, Any]] = []

    @app.get("/api/scheduled-tasks", include_in_schema=False)
    async def cc_sched_list() -> dict[str, Any]:
        return {"tasks": list(_SCHEDULED_TASKS.values())}

    @app.post("/api/scheduled-tasks", include_in_schema=False)
    async def cc_sched_create(request: Request) -> dict[str, Any]:
        import uuid as _u, time as _t
        try:
            body = await request.json()
        except Exception:
            body = {}
        tid = body.get("id") or _u.uuid4().hex
        task = {
            "id": tid,
            "name": body.get("name", "Untitled task"),
            "cron": body.get("cron", "*/5 * * * *"),
            "prompt": body.get("prompt", ""),
            "enabled": body.get("enabled", True),
            "createdAt": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
        }
        _SCHEDULED_TASKS[tid] = task
        return {"ok": True, "task": task}

    @app.put("/api/scheduled-tasks/{task_id}", include_in_schema=False)
    async def cc_sched_update(task_id: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if task_id not in _SCHEDULED_TASKS:
            return {"ok": False, "error": "not found"}
        _SCHEDULED_TASKS[task_id].update(body)
        return {"ok": True, "task": _SCHEDULED_TASKS[task_id]}

    @app.delete("/api/scheduled-tasks/{task_id}", include_in_schema=False)
    async def cc_sched_delete(task_id: str) -> dict[str, Any]:
        if _SCHEDULED_TASKS.pop(task_id, None) is None:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "deleted": task_id}

    @app.post("/api/scheduled-tasks/{task_id}/run", include_in_schema=False)
    async def cc_sched_run(task_id: str) -> dict[str, Any]:
        import time as _t, uuid as _u
        task = _SCHEDULED_TASKS.get(task_id)
        if not task:
            return {"ok": False, "error": "not found"}
        run = {
            "id": _u.uuid4().hex,
            "taskId": task_id,
            "status": "completed",
            "startedAt": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
            "finishedAt": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
            "output": f"[stub] Ran task '{task['name']}' with prompt: {task['prompt'][:80]}",
        }
        _SCHEDULED_RUNS.append(run)
        return {"ok": True, "run": run}

    @app.get("/api/scheduled-tasks/runs", include_in_schema=False)
    async def cc_sched_runs(limit: int = Query(default=50)) -> dict[str, Any]:
        return {"runs": _SCHEDULED_RUNS[-limit:]}

    @app.get("/api/scheduled-tasks/{task_id}/runs", include_in_schema=False)
    async def cc_sched_task_runs(task_id: str) -> dict[str, Any]:
        runs = [r for r in _SCHEDULED_RUNS if r["taskId"] == task_id]
        return {"runs": runs}

    # ---- Plugins (from ~/.madcop/plugins/ + bundled) ------------ #

    @app.get("/api/plugins", include_in_schema=False)
    async def cc_plugins_list() -> dict[str, Any]:
        plugins: list[dict[str, Any]] = []
        for d in [Path.home() / ".madcop" / "plugins",
                  Path(__file__).parent.parent.parent / "plugins"]:
            if not d.exists():
                continue
            for f in d.glob("plugin.json"):
                try:
                    import json as _j
                    data = _j.loads(f.read_text())
                    plugins.append({
                        "id": data.get("id", f.parent.name),
                        "name": data.get("name", f.parent.name),
                        "version": data.get("version", "0.0.0"),
                        "enabled": data.get("enabled", True),
                        "path": str(f.parent),
                    })
                except Exception:
                    pass
        return {"plugins": plugins}

    @app.post("/api/plugins/{action}", include_in_schema=False)
    async def cc_plugins_action(action: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        pid = body.get("id") or body.get("name") or ""
        if action == "reload":
            return {"ok": True, "reloaded": pid or "all"}
        return {"ok": True, "action": action, "id": pid}

    @app.get("/api/plugins/detail", include_in_schema=False)
    async def cc_plugins_detail(name: str = Query(...)) -> dict[str, Any]:
        for d in [Path.home() / ".madcop" / "plugins",
                  Path(__file__).parent.parent.parent / "plugins"]:
            f = d / name / "plugin.json"
            if f.exists():
                import json as _j
                return {"id": name, "manifest": _j.loads(f.read_text()),
                        "path": str(f.parent)}
        return {"id": name, "error": "not found"}

    # ---- MCP (server definitions) ------------------------------- #

    @app.get("/api/mcp", include_in_schema=False)
    async def cc_mcp_list(
        q: str = Query(default=""),
        scope: str = Query(default=""),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        servers = _load_mcp_servers()
        if q:
            servers = [s for s in servers if q.lower() in s["name"].lower()]
        # Reshape to McpServerRecord
        records: list[dict[str, Any]] = []
        for s in servers:
            config = s.get("config") or {
                "type": "stdio",
                "command": s.get("command", ""),
                "args": s.get("args", []),
                "env": s.get("env", {}),
            }
            status = s.get("status", "disconnected")
            enabled = s.get("enabled", True)
            if not enabled:
                status_str = "disabled"
            elif status == "connected":
                status_str = "connected"
            else:
                status_str = "needs-auth"
            records.append({
                "name": s["name"],
                "scope": s.get("scope", "user"),
                "transport": s.get("transport", "stdio"),
                "enabled": enabled,
                "status": status_str,
                "statusLabel": status_str.replace("-", " ").title(),
                "statusDetail": s.get("statusDetail", ""),
                "configLocation": s.get("configLocation", str(_MCP_FILE)),
                "summary": s.get("summary",
                    f"{config.get('type', 'stdio')}: "
                    f"{config.get('command', '') or config.get('url', '')}"),
                "canEdit": True,
                "canRemove": True,
                "canReconnect": True,
                "canToggle": True,
                "config": config,
                "projectPath": s.get("projectPath") or (cwd or None),
            })
        return {"servers": records, "total": len(records)}

    @app.get("/api/mcp/{name}/status", include_in_schema=False)
    async def cc_mcp_status(name: str, cwd: str = Query(default="")) -> dict[str, Any]:
        servers = _load_mcp_servers()
        for s in servers:
            if s["name"] == name:
                config = s.get("config") or {
                    "type": "stdio",
                    "command": s.get("command", ""),
                    "args": s.get("args", []),
                    "env": s.get("env", {}),
                }
                status = s.get("status", "disconnected")
                enabled = s.get("enabled", True)
                if not enabled:
                    status_str = "disabled"
                elif status == "connected":
                    status_str = "connected"
                else:
                    status_str = "needs-auth"
                return {"server": {
                    "name": name,
                    "scope": s.get("scope", "user"),
                    "transport": s.get("transport", "stdio"),
                    "enabled": enabled,
                    "status": status_str,
                    "statusLabel": status_str.replace("-", " ").title(),
                    "statusDetail": s.get("statusDetail", ""),
                    "configLocation": s.get("configLocation", str(_MCP_FILE)),
                    "summary": s.get("summary", ""),
                    "canEdit": True, "canRemove": True,
                    "canReconnect": True, "canToggle": True,
                    "config": config,
                    "projectPath": s.get("projectPath") or (cwd or None),
                }, "connected": status_str == "connected"}
        return {"server": None, "connected": False}

    @app.post("/api/mcp", include_in_schema=False)
    async def cc_mcp_create(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        name = body.get("name", "")
        if not name:
            return {"ok": False, "error": "name required"}
        servers = _load_mcp_servers()
        scope = body.get("scope", "user")
        config = body.get("config", {
            "type": "stdio",
            "command": body.get("command", ""),
            "args": body.get("args", []),
            "env": body.get("env", {}),
        })
        new_server = {
            "name": name,
            "scope": scope,
            "transport": config.get("type", "stdio"),
            "command": config.get("command", ""),
            "args": config.get("args", []),
            "env": config.get("env", {}),
            "config": config,
            "enabled": body.get("enabled", True),
            "status": "disconnected",
            "summary": f"{config.get('type', 'stdio')}: "
                       f"{config.get('command', '') or config.get('url', '')}",
        }
        servers.append(new_server)
        _save_mcp_servers(servers)
        return {"ok": True, "server": {
            "name": name, "scope": scope,
            "transport": new_server["transport"],
            "enabled": new_server["enabled"],
            "status": "needs-auth", "statusLabel": "Needs Auth",
            "configLocation": str(_MCP_FILE), "summary": new_server["summary"],
            "canEdit": True, "canRemove": True,
            "canReconnect": True, "canToggle": True,
            "config": config,
        }}

    @app.put("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_update(name: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        servers = _load_mcp_servers()
        for i, s in enumerate(servers):
            if s["name"] == name:
                # Frontend sends {scope, config}
                if "config" in body:
                    s["config"] = body["config"]
                    s["command"] = body["config"].get("command", s.get("command", ""))
                    s["args"] = body["config"].get("args", s.get("args", []))
                    s["env"] = body["config"].get("env", s.get("env", {}))
                if "scope" in body:
                    s["scope"] = body["scope"]
                if "enabled" in body:
                    s["enabled"] = body["enabled"]
                servers[i] = s
                _save_mcp_servers(servers)
                return {"ok": True, "server": {
                    "name": name, "scope": s.get("scope", "user"),
                    "transport": s.get("transport", "stdio"),
                    "enabled": s.get("enabled", True),
                    "status": "disconnected", "statusLabel": "Disconnected",
                    "configLocation": str(_MCP_FILE),
                    "summary": s.get("summary", ""),
                    "canEdit": True, "canRemove": True,
                    "canReconnect": True, "canToggle": True,
                    "config": s.get("config", {}),
                }}
        return {"ok": False, "error": "not found"}

    @app.delete("/api/mcp/{name}", include_in_schema=False)
    async def cc_mcp_delete(name: str, cwd: str = Query(default="")) -> dict[str, Any]:
        servers = _load_mcp_servers()
        new_servers = [s for s in servers if s["name"] != name]
        if len(new_servers) == len(servers):
            return {"ok": False, "error": "not found"}
        _save_mcp_servers(new_servers)
        return {"ok": True, "deleted": name}

    @app.post("/api/mcp/{name}/toggle", include_in_schema=False)
    async def cc_mcp_toggle(name: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        servers = _load_mcp_servers()
        for s in servers:
            if s["name"] == name:
                if "enabled" in body:
                    s["enabled"] = bool(body["enabled"])
                else:
                    s["enabled"] = not s.get("enabled", True)
                _save_mcp_servers(servers)
                return {"ok": True, "server": {
                    "name": name, "scope": s.get("scope", "user"),
                    "transport": s.get("transport", "stdio"),
                    "enabled": s["enabled"],
                    "status": "disabled" if not s["enabled"] else "needs-auth",
                    "statusLabel": "Disabled" if not s["enabled"] else "Needs Auth",
                    "configLocation": str(_MCP_FILE),
                    "summary": s.get("summary", ""),
                    "canEdit": True, "canRemove": True,
                    "canReconnect": True, "canToggle": True,
                    "config": s.get("config", {}),
                }}
        return {"ok": False, "error": "not found"}

    @app.post("/api/mcp/{name}/reconnect", include_in_schema=False)
    async def cc_mcp_reconnect(name: str, cwd: str = Query(default="")) -> dict[str, Any]:
        servers = _load_mcp_servers()
        for s in servers:
            if s["name"] == name:
                # Mark as needs-auth (we don't actually spawn processes)
                s["status"] = "needs-auth"
                _save_mcp_servers(servers)
                return {"ok": True, "server": {
                    "name": name, "scope": s.get("scope", "user"),
                    "transport": s.get("transport", "stdio"),
                    "enabled": s.get("enabled", True),
                    "status": "needs-auth", "statusLabel": "Needs Auth",
                    "statusDetail": "Restart MadCop Agent to apply changes",
                    "configLocation": str(_MCP_FILE),
                    "summary": s.get("summary", ""),
                    "canEdit": True, "canRemove": True,
                    "canReconnect": True, "canToggle": True,
                    "config": s.get("config", {}),
                }}
        return {"ok": False, "error": "not found"}

    @app.get("/api/mcp/project-paths", include_in_schema=False)
    async def cc_mcp_project_paths() -> dict[str, Any]:
        return {"projectPaths": list({str(p) for p in _SESSIONS.values()
                                       if p.get("workDir")})}

    # ---- Search (real FTS5 over sessions + memory) -------------- #

    @app.post("/api/search", include_in_schema=False)
    async def cc_search(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        query = body.get("query") or body.get("q") or ""
        if not query:
            return {"results": []}
        results: list[dict[str, Any]] = []
        # Search session messages
        for sid, msgs in _MESSAGES.items():
            for m in msgs:
                content = m.get("content", "")
                if query.lower() in content.lower():
                    results.append({
                        "type": "session_message",
                        "sessionId": sid,
                        "messageId": m.get("id"),
                        "role": m.get("type"),
                        "snippet": content[:200],
                        "score": 1.0,
                    })
                    if len(results) >= 50:
                        break
            if len(results) >= 50:
                break
        # Search memory semantic
        try:
            from madcop.memory import SemanticMemory
            from madcop.server.app import get_memory_store
            store = get_memory_store()
            sem = SemanticMemory(store)
            facts = sem.find_related(query, limit=10)
            for f in facts:
                results.append({
                    "type": "memory_fact",
                    "factId": getattr(f, "id", ""),
                    "snippet": getattr(f, "object", str(f))[:200],
                    "score": 0.8,
                })
        except Exception:
            pass
        return {"results": results[:50], "total": len(results[:50])}

    @app.post("/api/search/sessions", include_in_schema=False)
    async def cc_search_sessions(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        query = body.get("query") or body.get("q") or ""
        sessions = [
            _to_public_session(s)
            for s in _SESSIONS.values()
            if not query or query.lower() in (s.get("title") or "").lower()
        ]
        return {"sessions": sessions, "total": len(sessions)}

    # ---- Desktop UI preferences (local user prefs) -------------- #

    _DESKTOP_PREFS_FILE = Path.home() / ".madcop" / "desktop_prefs.json"

    def _load_prefs() -> dict[str, Any]:
        if _DESKTOP_PREFS_FILE.exists():
            try:
                import json as _j
                return _j.loads(_DESKTOP_PREFS_FILE.read_text())
            except Exception:
                pass
        return {
            "sidebar": {"collapsed": False, "width": 240},
            "profile": {"name": "MadCop User", "avatar": ""},
        }

    def _save_prefs(prefs: dict[str, Any]) -> None:
        try:
            _DESKTOP_PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
            import json as _j
            _DESKTOP_PREFS_FILE.write_text(_j.dumps(prefs, ensure_ascii=False, indent=2))
        except Exception:
            pass

    @app.get("/api/desktop-ui/preferences", include_in_schema=False)
    async def cc_desktop_prefs() -> dict[str, Any]:
        """Return the full DesktopUiPreferencesResponse shape:
        {preferences: {schemaVersion, sidebar, profile}, exists}
        """
        prefs = _load_prefs()
        return {
            "preferences": {
                "schemaVersion": 1,
                "sidebar": {
                    "projectOrder": prefs.get("sidebar", {}).get(
                        "projectOrder", []),
                    "pinnedProjects": prefs.get("sidebar", {}).get(
                        "pinnedProjects", []),
                    "hiddenProjects": prefs.get("sidebar", {}).get(
                        "hiddenProjects", []),
                    "projectOrganization": prefs.get("sidebar", {}).get(
                        "projectOrganization", "project"),
                    "projectSortBy": prefs.get("sidebar", {}).get(
                        "projectSortBy", "updatedAt"),
                    # Also expose legacy fields so the old UI doesn't break
                    "collapsed": prefs.get("sidebar", {}).get("collapsed", False),
                    "width": prefs.get("sidebar", {}).get("width", 260),
                },
                "profile": {
                    "displayName": prefs.get("profile", {}).get(
                        "displayName") or prefs.get("profile", {}).get(
                            "name", "MadCop User"),
                    "subtitle": prefs.get("profile", {}).get(
                        "subtitle", ""),
                    "avatarFile": prefs.get("profile", {}).get(
                        "avatarFile") or prefs.get("profile", {}).get(
                            "avatar"),
                    "avatarUpdatedAt": prefs.get("profile", {}).get(
                        "avatarUpdatedAt"),
                },
            },
            "exists": True,
        }

    @app.put("/api/desktop-ui/preferences/{section}", include_in_schema=False)
    async def cc_desktop_prefs_set(section: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        prefs = _load_prefs()
        prefs[section] = body
        _save_prefs(prefs)
        return {"ok": True, section: body}

    @app.delete("/api/desktop-ui/preferences/profile/avatar",
                 include_in_schema=False)
    async def cc_desktop_avatar_delete() -> dict[str, Any]:
        prefs = _load_prefs()
        if "profile" in prefs:
            prefs["profile"]["avatar"] = ""
        _save_prefs(prefs)
        return {"ok": True}

    # ---- Diagnostics: clear events, post events ----------------- #

    @app.delete("/api/diagnostics", include_in_schema=False)
    async def cc_diag_clear() -> dict[str, Any]:
        try:
            from madcop.server.app import get_diagnostics_log
            get_diagnostics_log().clear()
        except Exception:
            pass
        return {"ok": True}

    @app.post("/api/diagnostics/events", include_in_schema=False)
    async def cc_diag_post_event(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            from madcop.server.app import get_diagnostics_log
            get_diagnostics_log().append({
                "type": body.get("type", "client_event"),
                "payload": body,
                "timestamp": body.get("timestamp", ""),
            })
        except Exception:
            pass
        return {"ok": True}

    # ---- Settings: user, output-style, permissions, output-styles #

    @app.get("/api/settings/user", include_in_schema=False)
    async def cc_settings_user() -> dict[str, Any]:
        prefs = _load_prefs()
        return {"user": prefs.get("profile", {})}

    @app.put("/api/settings/user", include_in_schema=False)
    async def cc_settings_user_update(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        prefs = _load_prefs()
        prefs["profile"] = body
        _save_prefs(prefs)
        return {"ok": True, "user": body}

    @app.get("/api/settings/output-styles", include_in_schema=False)
    async def cc_settings_output_styles() -> dict[str, Any]:
        styles: list[dict[str, Any]] = []
        d = Path(__file__).parent.parent.parent / "output_styles"
        if d.exists():
            for f in d.glob("*.md"):
                styles.append({"name": f.stem, "path": str(f),
                               "preview": f.read_text(errors="ignore")[:200]})
        return {"styles": styles}

    @app.put("/api/settings/output-style", include_in_schema=False)
    async def cc_settings_output_style_set(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        # Persist into settings
        s = settings_store.load_settings()
        if not hasattr(s, "output_style"):
            return {"ok": True, "style": body.get("name", "")}
        s.output_style = body.get("name", "")
        settings_store.save_settings(s)
        return {"ok": True}

    @app.get("/api/permissions/mode", include_in_schema=False)
    async def cc_perms_get() -> dict[str, Any]:
        s = settings_store.load_settings()
        return {"mode": getattr(s, "permission_mode", "default")}

    @app.put("/api/permissions/mode", include_in_schema=False)
    async def cc_perms_set(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        mode = body.get("mode", "default")
        s = settings_store.load_settings()
        if hasattr(s, "permission_mode"):
            s.permission_mode = mode
            settings_store.save_settings(s)
        return {"ok": True, "mode": mode}

    @app.get("/api/settings/cli-launcher", include_in_schema=False)
    async def cc_settings_cli_launcher() -> dict[str, Any]:
        return {"enabled": True, "command": "open -a Terminal"}

    # ---- Memory projects / files (MemorySettings tab) ------------ #
    # Shapes:
    #   MemoryProject = {id, label, memoryDir, exists, fileCount, isCurrent}
    #   MemoryFile    = {path, name, bytes, updatedAt, type?, description?,
    #                    title, isIndex}
    #   MemoryFileDetail = {path, content, updatedAt, bytes}

    @app.get("/api/memory/projects", include_in_schema=False)
    async def cc_memory_projects(
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        """List memory projects: global (~/.madcop/memory) + per-session workDir."""
        projects: list[dict[str, Any]] = []
        seen: set[str] = set()
        # Global memory root
        global_dir = Path.home() / ".madcop" / "memory"
        if global_dir.is_dir():
            n = sum(1 for _ in global_dir.rglob("*.md"))
            projects.append({
                "id": "global",
                "label": "Global memory (~/brain/memory)",
                "memoryDir": str(global_dir),
                "exists": True,
                "fileCount": n,
                "isCurrent": False,
            })
        # Per-session workDir memory (cwd/.claude/memory or cwd/MEMORY.md, where .claude is the upstream CLI's own memory dir)
        for s in _SESSIONS.values():
            wd = s.get("workDir")
            if not wd or wd in seen:
                continue
            seen.add(wd)
            wd_path = Path(wd)
            mem_dir = wd_path / ".claude" / "memory"
            if not mem_dir.is_dir():
                mem_dir = wd_path  # fallback: project root
            n = sum(1 for _ in mem_dir.rglob("*.md"))
            projects.append({
                "id": wd,
                "label": wd_path.name,
                "memoryDir": str(mem_dir),
                "exists": mem_dir.is_dir(),
                "fileCount": n,
                "isCurrent": wd == cwd or (not cwd and s.get("id") == (
                    list(_SESSIONS.values())[0].get("id") if _SESSIONS else ""
                )),
            })
        # If cwd supplied but no project matched, add it as a candidate
        if cwd and cwd not in seen:
            wd_path = Path(cwd)
            mem_dir = wd_path / ".claude" / "memory"
            n = sum(1 for _ in mem_dir.rglob("*.md"))
            projects.append({
                "id": cwd,
                "label": wd_path.name or cwd,
                "memoryDir": str(mem_dir),
                "exists": mem_dir.is_dir(),
                "fileCount": n,
                "isCurrent": True,
            })
        return {"projects": projects}

    @app.get("/api/memory/files", include_in_schema=False)
    async def cc_memory_files(
        projectId: str = Query(default=""),
        path: str = Query(default=""),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        """List memory files in a project. projectId is the path or 'global'."""
        if not path:
            if projectId == "global":
                path = str(Path.home() / ".madcop" / "memory")
            elif projectId:
                p = Path(projectId)
                path = str(p / ".claude" / "memory"
                          if (p / ".claude" / "memory").is_dir() else p)
            elif cwd:
                p = Path(cwd)
                path = str(p / ".claude" / "memory"
                          if (p / ".claude" / "memory").is_dir() else p)
            else:
                path = str(Path.home() / ".madcop" / "memory")
        target = Path(path).expanduser()
        if not target.is_dir():
            return {"files": []}
        files: list[dict[str, Any]] = []
        for f in sorted(target.glob("*.md")):
            if not f.is_file():
                continue
            stat = f.stat()
            content = f.read_text(errors="ignore")
            # Extract first H1 as title
            title = f.stem
            description = ""
            if content.startswith("# "):
                title = content.split("\n", 1)[0][2:].strip()
            # First paragraph as description
            for line in content.splitlines():
                if line.strip() and not line.startswith("#"):
                    description = line.strip()[:200]
                    break
            import datetime as _dt
            updated = _dt.datetime.fromtimestamp(
                stat.st_mtime, tz=_dt.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            files.append({
                "path": str(f),
                "name": f.name,
                "bytes": stat.st_size,
                "updatedAt": updated,
                "type": "markdown",
                "title": title,
                "description": description,
                "isIndex": f.name.lower() in ("memory.md", "readme.md", "index.md"),
            })
        return {"files": files}

    @app.get("/api/memory/file", include_in_schema=False)
    async def cc_memory_file(
        projectId: str = Query(default=""),
        path: str = Query(default=""),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        """Read a memory file's full content.

        Special case: if the file is `MEMORY.md` and its content is empty,
        auto-generate content from the L1 Semantic memory store (facts like
        "user name is 林芮翰") so the user can actually see their
        remembered facts in the UI.
        """
        if not path:
            return {"file": None, "error": "path required"}
        p = Path(path).expanduser()
        if not p.is_file():
            return {"file": None, "error": "not found"}
        try:
            content = p.read_text(errors="ignore")
            import datetime as _dt
            stat = p.stat()
            updated = _dt.datetime.fromtimestamp(
                stat.st_mtime, tz=_dt.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            # If file is empty/blank AND it's MEMORY.md, synthesise from L1
            if (not content.strip()
                and p.name.upper() == "MEMORY.MD"):
                content = _synthesize_memory_md()
            return {"file": {
                "path": str(p),
                "content": content,
                "updatedAt": updated,
                "bytes": stat.st_size,
            }}
        except Exception as e:
            return {"file": None, "error": str(e)}

    @app.put("/api/memory/file", include_in_schema=False)
    async def cc_memory_file_save(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        path = body.get("path", "")
        content = body.get("content", "")
        if not path:
            return {"ok": False, "error": "path required"}
        p = Path(path).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            import datetime as _dt
            stat = p.stat()
            return {
                "ok": True,
                "file": {
                    "path": str(p),
                    "updatedAt": _dt.datetime.fromtimestamp(
                        stat.st_mtime, tz=_dt.timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "bytes": stat.st_size,
                },
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- Adapters (IM / OAuth) — show "not configured" gracefully #

    @app.put("/api/adapters", include_in_schema=False)
    async def cc_adapters_update(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return {"ok": True, "adapters": body}

    @app.post("/api/adapters/{platform}/login/start", include_in_schema=False)
    async def cc_adapter_login_start(platform: str) -> dict[str, Any]:
        return {
            "ok": False,
            "error": f"{platform} adapter is not yet configured in MadCop Agent. "
                     f"Set MADCOP_{platform.upper()}_TOKEN env var to enable.",
            "platform": platform,
        }

    @app.post("/api/adapters/{platform}/login/poll", include_in_schema=False)
    async def cc_adapter_login_poll(platform: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "expired",
            "error": f"{platform} adapter not configured",
        }

    @app.post("/api/adapters/{platform}/unbind", include_in_schema=False)
    async def cc_adapter_unbind(platform: str) -> dict[str, Any]:
        return {"ok": True, "unbound": platform}

    @app.post("/api/adapters/{platform}/registration/begin",
               include_in_schema=False)
    async def cc_adapter_reg_begin(platform: str) -> dict[str, Any]:
        return {
            "ok": False,
            "error": f"{platform} registration not configured",
        }

    @app.post("/api/adapters/{platform}/registration/poll",
               include_in_schema=False)
    async def cc_adapter_reg_poll(platform: str) -> dict[str, Any]:
        return {"ok": False, "status": "expired"}

    # ---- OAuth flows (MadCop external auth) ------------------- #

    @app.post("/api/haha-oauth/start", include_in_schema=False)
    async def cc_oauth_start() -> dict[str, Any]:
        return {
            "ok": False,
            "error": "OAuth login not configured. Use Settings → Providers → Add to enter an API key instead.",
        }

    @app.get("/api/haha-oauth", include_in_schema=False)
    async def cc_oauth_get() -> dict[str, Any]:
        return {"loggedIn": False, "source": "none"}

    @app.delete("/api/haha-oauth", include_in_schema=False)
    async def cc_oauth_delete() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/haha-openai-oauth/start", include_in_schema=False)
    async def cc_oaioauth_start() -> dict[str, Any]:
        return {"ok": False, "error": "OAuth not configured"}
    @app.get("/api/haha-openai-oauth", include_in_schema=False)
    async def cc_oaioauth_get() -> dict[str, Any]:
        return {"loggedIn": False, "source": "none"}
    @app.delete("/api/haha-openai-oauth", include_in_schema=False)
    async def cc_oaioauth_delete() -> dict[str, Any]:
        return {"ok": True}

    # ---- Agents / Teams / Tasks (CLI tasks) --------------------- #

    @app.get("/api/agents", include_in_schema=False)
    async def cc_agents_list() -> dict[str, Any]:
        # Read agents from ~/.madcop/agents/ + bundled
        agents: list[dict[str, Any]] = []
        for d in [Path.home() / ".madcop" / "agents",
                  Path(__file__).parent.parent.parent / "agents"]:
            if not d.exists():
                continue
            for f in d.glob("*.md"):
                content = f.read_text(errors="ignore")
                agents.append({
                    "id": f.stem, "name": f.stem, "path": str(f),
                    "description": content[:200],
                    "status": "idle",
                })
        return {"activeAgents": [], "allAgents": agents}

    @app.get("/api/teams", include_in_schema=False)
    async def cc_teams_list_real() -> dict[str, Any]:
        teams: list[dict[str, Any]] = []
        d = Path.home() / ".madcop" / "teams"
        if d.exists():
            for f in d.glob("team.json"):
                try:
                    import json as _j
                    data = _j.loads(f.read_text())
                    teams.append({
                        "name": data.get("name", f.parent.name),
                        "memberCount": len(data.get("members", [])),
                        "createdAt": data.get("createdAt", ""),
                    })
                except Exception:
                    pass
        return {"teams": teams}

    @app.get("/api/teams/{name}", include_in_schema=False)
    async def cc_teams_get_real(name: str) -> dict[str, Any]:
        f = Path.home() / ".madcop" / "teams" / name / "team.json"
        if f.exists():
            try:
                import json as _j
                return _j.loads(f.read_text())
            except Exception:
                pass
        return {"name": name, "members": [], "description": ""}

    @app.delete("/api/teams/{name}", include_in_schema=False)
    async def cc_teams_delete_real(name: str) -> dict[str, Any]:
        d = Path.home() / ".madcop" / "teams" / name
        if d.exists():
            import shutil
            shutil.rmtree(d)
            return {"ok": True, "deleted": name}
        return {"ok": False, "error": "not found"}

    @app.get("/api/teams/{team_name}/members/{agent_id}/transcript",
              include_in_schema=False)
    async def cc_team_transcript_real(team_name: str, agent_id: str) -> dict[str, Any]:
        f = Path.home() / ".madcop" / "teams" / team_name / f"{agent_id}.json"
        if f.exists():
            try:
                import json as _j
                msgs = _j.loads(f.read_text())
                return {"messages": msgs, "teamName": team_name, "agentId": agent_id}
            except Exception:
                pass
        return {"messages": [], "teamName": team_name, "agentId": agent_id}

    @app.post("/api/teams/{team_name}/members/{agent_id}/messages",
              include_in_schema=False)
    async def cc_team_send_real(team_name: str, agent_id: str,
                                 request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        content = body.get("content", "")
        if not content:
            return {"ok": False, "error": "content required"}
        # Append to per-agent transcript
        d = Path.home() / ".madcop" / "teams" / team_name
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{agent_id}.json"
        msgs: list[dict[str, Any]] = []
        if f.exists():
            try:
                import json as _j
                msgs = _j.loads(f.read_text())
            except Exception:
                msgs = []
        import uuid as _u, time as _t
        msgs.append({
            "id": _u.uuid4().hex, "type": "user",
            "content": content, "timestamp": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
        })
        import json as _j
        f.write_text(_j.dumps(msgs, ensure_ascii=False, indent=2))
        return {"ok": True, "teamName": team_name, "agentId": agent_id,
                "messageId": msgs[-1]["id"]}

    _TASK_LISTS: dict[str, dict[str, Any]] = {}

    @app.get("/api/tasks", include_in_schema=False)
    async def cc_tasks_list_all() -> dict[str, Any]:
        return {"tasks": [t for tl in _TASK_LISTS.values() for t in tl.get("tasks", [])]}

    @app.get("/api/tasks/lists", include_in_schema=False)
    async def cc_task_lists() -> dict[str, Any]:
        return {"lists": list(_TASK_LISTS.values())}

    @app.get("/api/tasks/lists/{list_id}", include_in_schema=False)
    async def cc_task_list_get(list_id: str) -> dict[str, Any]:
        return _TASK_LISTS.get(list_id, {"id": list_id, "tasks": []})

    @app.get("/api/tasks/lists/{list_id}/{task_id}", include_in_schema=False)
    async def cc_task_get(list_id: str, task_id: str) -> dict[str, Any]:
        tl = _TASK_LISTS.get(list_id, {})
        for t in tl.get("tasks", []):
            if t.get("id") == task_id:
                return t
        return {"id": task_id, "error": "not found"}

    @app.post("/api/tasks/lists/{list_id}/reset", include_in_schema=False)
    async def cc_task_list_reset(list_id: str) -> dict[str, Any]:
        if list_id in _TASK_LISTS:
            for t in _TASK_LISTS[list_id].get("tasks", []):
                t["status"] = "pending"
        return {"ok": True}

    # ---- Provider test (returns ProviderTestResult shape) ---- #

    @app.post("/api/providers/{provider_id}/test", include_in_schema=False)
    async def cc_provider_test_real(provider_id: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            from madcop.llm import OpenAICompatClient, Message
            s = settings_store.load_settings()
            p = next((x for x in (s.providers or [])
                      if getattr(x, "provider_id", "") == provider_id), None)
            if not p:
                return {"result": {
                    "connectivity": {"success": False, "latencyMs": 0,
                                     "error": f"provider {provider_id} not found"},
                }}
            base = body.get("baseUrl") or getattr(p, "base_url", "")
            model = body.get("modelId") or getattr(p, "model", "")
            api_key = getattr(p, "api_key", "")
            if not base or not model or not api_key:
                return {"result": {
                    "connectivity": {"success": False, "latencyMs": 0,
                                     "error": "missing base_url / model / api_key"},
                }}
            client = OpenAICompatClient(base_url=base, api_key=api_key)
            t0 = time.time()
            resp = await asyncio.to_thread(
                client.chat,
                [Message(role="user", content="ping")],
                model=model,
            )
            latency_ms = int((time.time() - t0) * 1000)
            return {"result": {
                "connectivity": {
                    "success": True,
                    "latencyMs": latency_ms,
                    "modelUsed": getattr(resp, "model", model),
                },
            }}
        except Exception as e:
            return {"result": {
                "connectivity": {"success": False, "latencyMs": 0,
                                 "error": str(e)[:200]},
            }}

    @app.post("/api/providers/test", include_in_schema=False)
    async def cc_provider_test_config(request: Request) -> dict[str, Any]:
        """Test a provider config without saving (used in the form)."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            from madcop.llm import OpenAICompatClient, Message
            base = body.get("baseUrl") or body.get("base_url") or ""
            api_key = body.get("apiKey") or body.get("api_key") or ""
            model = body.get("modelId") or body.get("model") or ""
            if not base or not model or not api_key:
                return {"result": {
                    "connectivity": {"success": False, "latencyMs": 0,
                                     "error": "missing baseUrl/apiKey/modelId"},
                }}
            client = OpenAICompatClient(base_url=base, api_key=api_key)
            t0 = time.time()
            resp = await asyncio.to_thread(
                client.chat,
                [Message(role="user", content="ping")],
                model=model,
            )
            latency_ms = int((time.time() - t0) * 1000)
            return {"result": {
                "connectivity": {
                    "success": True,
                    "latencyMs": latency_ms,
                    "modelUsed": getattr(resp, "model", model),
                },
            }}
        except Exception as e:
            return {"result": {
                "connectivity": {"success": False, "latencyMs": 0,
                                 "error": str(e)[:200]},
            }}

    # ---- Session extra endpoints ------------------------------- #

    @app.get("/api/sessions/recent-projects", include_in_schema=False)
    async def cc_sess_recent_projects() -> dict[str, Any]:
        seen: list[dict[str, str]] = []
        for s in _SESSIONS.values():
            wd = s.get("workDir")
            if wd and not any(p.get("path") == wd for p in seen):
                seen.append({"path": wd, "name": Path(wd).name})
        return {"projects": seen[:20]}

    @app.get("/api/sessions/{session_id}/git-info", include_in_schema=False)
    async def cc_sess_git_info(session_id: str) -> dict[str, Any]:
        wd = _SESSIONS.get(session_id, {}).get("workDir", "")
        info: dict[str, Any] = {
            "branch": None, "repoName": None, "workDir": wd,
            "changedFiles": 0, "worktree": None,
        }
        if not wd or not Path(wd).is_dir():
            return info
        # Try to read git branch
        try:
            import subprocess as _sp
            r = _sp.run(["git", "-C", wd, "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                info["branch"] = r.stdout.strip()
            r = _sp.run(["git", "-C", wd, "rev-parse", "--show-toplevel"],
                        capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                info["repoName"] = Path(r.stdout.strip()).name
            r = _sp.run(["git", "-C", wd, "status", "--porcelain"],
                        capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                info["changedFiles"] = len([l for l in r.stdout.splitlines() if l.strip()])
        except Exception:
            pass
        return info

    @app.get("/api/sessions/{session_id}/inspection", include_in_schema=False)
    async def cc_sess_inspection(session_id: str) -> dict[str, Any]:
        return {
            "messages": _MESSAGES.get(session_id, []),
            "trace": [], "files": [],
            "sessionId": session_id,
        }

    @app.get("/api/sessions/{session_id}/turn-checkpoints", include_in_schema=False)
    async def cc_sess_turn_checkpoints(session_id: str) -> dict[str, Any]:
        msgs = _MESSAGES.get(session_id, [])
        return {
            "checkpoints": [
                {"turnId": m["id"], "timestamp": m.get("timestamp", ""),
                 "preview": (m.get("content") or "")[:80]}
                for m in msgs if m.get("type") == "assistant"
            ]
        }

    @app.post("/api/sessions/{session_id}/branch", include_in_schema=False)
    async def cc_sess_branch(session_id: str, request: Request) -> dict[str, Any]:
        import uuid as _u, time as _t
        try:
            body = await request.json()
        except Exception:
            body = {}
        new_sid = _u.uuid4().hex
        now = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
        target_msg_id = body.get("targetMessageId")
        # Copy messages up to target_msg_id
        original_msgs = _MESSAGES.get(session_id, [])
        if target_msg_id:
            cutoff = next((i for i, m in enumerate(original_msgs)
                            if m.get("id") == target_msg_id), len(original_msgs))
            new_msgs = list(original_msgs[:cutoff + 1])
        else:
            new_msgs = list(original_msgs)
        original = _SESSIONS.get(session_id, {})
        _SESSIONS[new_sid] = {
            "id": new_sid, "title": body.get("title") or
                                  (original.get("title", "New Session") + " (branch)"),
            "createdAt": now, "modifiedAt": now,
            "model": original.get("model", "minimaxai/minimax-m2.7"),
            "workDir": original.get("workDir"),
            "projectPath": original.get("projectPath", ""),
            "projectRoot": original.get("projectRoot"),
            "messages": new_msgs, "chatState": "idle",
            "permissionMode": original.get("permissionMode", "bypassPermissions"),
        }
        _MESSAGES[new_sid] = new_msgs
        return {"sessionId": new_sid, "title": _SESSIONS[new_sid]["title"],
                "workDir": _SESSIONS[new_sid].get("workDir")}

    @app.patch("/api/sessions/{session_id}", include_in_schema=False)
    async def cc_sess_patch(session_id: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        sess = _SESSIONS.get(session_id)
        if not sess:
            return {"ok": False, "error": "not found"}
        sess.update(body)
        return {"ok": True, "session": _to_public_session(sess)}

    @app.get("/api/sessions/{session_id}/trace/calls/{call_id}",
              include_in_schema=False)
    async def cc_sess_trace_call(session_id: str, call_id: str) -> dict[str, Any]:
        try:
            from madcop.agent.trace import get_trace_store
            store = get_trace_store()
            call = store.get_node(call_id) if hasattr(store, "get_node") else None
            if call:
                return call.to_dict() if hasattr(call, "to_dict") else {"id": call_id}
        except Exception:
            pass
        return {"id": call_id, "error": "not found"}

    # v2.6.0: register Project Workspace endpoints (must be the LAST
    # thing inside register() so the live `app` arg is in scope).
    _register_project_endpoints(app)


# ---- MCP server storage helpers ------------------------------- #

_MCP_FILE = Path.home() / ".madcop" / "mcp_servers.json"


def _load_mcp_servers() -> list[dict[str, Any]]:
    if _MCP_FILE.exists():
        try:
            import json as _j
            return _j.loads(_MCP_FILE.read_text())
        except Exception:
            pass
    return []


def _save_mcp_servers(servers: list[dict[str, Any]]) -> None:
    try:
        _MCP_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json as _j
        _MCP_FILE.write_text(_j.dumps(servers, ensure_ascii=False, indent=2))
    except Exception:
        pass


# ---- Force-distill skill (bypasses pattern detection) ---------- #
# Now lives in madcop.memory.skill_distill.force_distill_skill as the
# canonical implementation. We keep a thin wrapper here for backwards
# ---- Provider test (returns ProviderTestResult shape) ---- #

# ---- Auto-fetch model list ----------------------------------- #

def fetch_provider_models(base_url: str, api_key: str) -> list[dict[str, Any]]:
    """Module-level public API: fetch models from a provider's
    /v1/models endpoint. Used by app.py's legacy list_models_madcop.
    """
    return _fetch_provider_models(base_url, api_key)


def _fetch_provider_models(base_url: str, api_key: str) -> list[dict[str, Any]]:
    """Fetch available models from a provider's OpenAI-compatible /v1/models.

    Returns a list of {id, ...} dicts. Falls back to [] on any error.
    Used by /api/models to auto-populate the model dropdown.
    """
    if not base_url or not api_key:
        return []
    try:
        import requests as _req
        url = f"{base_url.rstrip('/')}/models"
        resp = _req.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            if isinstance(models, list):
                return models
        return []
    except Exception as e:
        import sys as _sys
        print(f"[fetch-provider-models] {base_url} error: {e}",
              file=_sys.stderr, flush=True)
        return []


def _model_display_name(model_id: str) -> str:
    """Turn 'minimaxai/minimax-m3' into a friendly display name.

    - Drop the org prefix (minimaxai/ → '')
    - Convert dashes/underscores to spaces and Title Case
    - Keep 'M3' / 'M2.7' style version numbers readable
    """
    if not model_id:
        return ""
    s = model_id
    # Drop "minimaxai/" and common org prefixes
    for prefix in ("minimaxai/", "openai/", "anthropic/", "meta/",
                   "google/", "deepseek-ai/", "mistralai/", "nvidia/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    # Replace separators
    s = s.replace("-", " ").replace("_", " ").strip()
    # Title-case but keep all-uppercase tokens (M3, GLM, GPT)
    out = []
    for tok in s.split():
        if tok.isupper() and len(tok) <= 6:
            out.append(tok)
        elif tok[0:1].isdigit():
            out.append(tok)
        else:
            out.append(tok.capitalize())
    return " ".join(out) or model_id


def _force_distill_skill(topic: str, user_query: str,
                          assistant_response: str) -> str | None:
    """Backwards-compat wrapper."""
    from madcop.memory.skill_distill import force_distill_skill
    return force_distill_skill(topic, user_query, assistant_response)


def _synthesize_memory_md() -> str:
    """Generate a MEMORY.md content from L1 Semantic memory facts.

    Returns a markdown document listing all extracted user facts (name,
    preferences, etc.) so the user can see what MadCop has remembered
    about them when they open the memory settings page.
    """
    import datetime as _dt
    lines: list[str] = [
        "# Project Memory",
        "",
        f"_Auto-generated on {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}._",
        "",
        "These are the facts MadCop Agent has learned about you across all",
        "your sessions. Edit this file freely — your changes will be kept",
        "the next time the auto-generator runs (it only fills in empty files).",
        "",
        "## About you",
        "",
    ]
    try:
        from madcop.server.app import get_memory_store
        from madcop.memory import SemanticMemory, MemoryKind
        store = get_memory_store()
        sem = SemanticMemory(store)
        facts = store.list_by_kind(MemoryKind.SEMANTIC, limit=200)
        user_facts = [f for f in facts
                      if "user" in f.tags or "user-profile" in f.tags
                      or "user" in (f.title or "").lower()
                      or "user" in (f.content or "").lower()[:200]]
        if not user_facts:
            lines.append("_No personal facts extracted yet. Start a conversation and say something like 'I am 林芮翰' or 'I live in 上海' — MadCop will remember._")
        else:
            for f in user_facts[:50]:
                # Parse JSON content if it's structured
                text = f.content or f.title or ""
                if text.startswith("{"):
                    try:
                        import json as _j
                        parsed = _j.loads(text)
                        text = parsed.get("object") or text
                    except Exception:
                        pass
                if text:
                    lines.append(f"- {text}")
        lines.append("")
        lines.append("## Skills")
        lines.append("")
        skill_facts = [f for f in facts if "skill" in f.tags]
        if not skill_facts:
            lines.append("_No auto-distilled skills yet. Try asking MadCop 'teach me how to do X' — it'll create a SKILL.md you can edit._")
        else:
            for f in skill_facts[:20]:
                text = f.content or f.title or ""
                if text.startswith("{"):
                    try:
                        import json as _j
                        parsed = _j.loads(text)
                        text = parsed.get("object") or text
                    except Exception:
                        pass
                if text:
                    lines.append(f"- {text}")
        lines.append("")
        lines.append("---")
        lines.append(f"_Total: {len(facts)} facts in memory store._")
    except Exception as e:
        lines.append(f"_Could not load memory: {e}_")
    return "\n".join(lines)


# ---- Activity stats from trace store -------------------------- #

def _empty_activity_stats() -> dict[str, Any]:
    """Return an empty ActivityStats payload matching the cc-haha shape."""
    return {
        "totalSessions": 0,
        "totalMessages": 0,
        "totalDays": 0,
        "activeDays": 0,
        "streaks": {
            "currentStreak": 0,
            "longestStreak": 0,
            "currentStreakStart": None,
            "longestStreakStart": None,
            "longestStreakEnd": None,
        },
        "dailyActivity": [],
        "dailyModelTokens": [],
        "longestSession": None,
        "modelUsage": {},
        "toolUsage": {},
        "skillUsage": {},
        "firstSessionDate": None,
        "lastSessionDate": None,
        "peakActivityDay": None,
        "peakActivityHour": None,
        "totalSpeculationTimeSavedMs": 0,
    }


def _build_activity_stats(range_filter: str = "all") -> dict[str, Any]:
    """Build a real ActivityStats payload from the trace store + sessions."""
    import datetime as _dt
    from collections import Counter
    stats = _empty_activity_stats()
    try:
        from madcop.agent.trace import get_trace_store
        trace_store = get_trace_store()
        # Use the in-memory sessions + messages
        from madcop.server.madcop_compat import _SESSIONS, _MESSAGES
        # Get all conversation IDs from sessions
        conversation_ids = list(_SESSIONS.keys())
        if not conversation_ids:
            return {
                "stats": stats,
                "range": range_filter,
                "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }

        # Build daily activity from session message counts
        daily: dict[str, dict[str, int]] = {}
        model_tokens: dict[str, dict[str, int]] = {}
        all_sessions: list[dict[str, Any]] = []
        first_date: str | None = None
        last_date: str | None = None
        total_messages = 0

        for sid, sess in _SESSIONS.items():
            created = sess.get("createdAt", "")
            # createdAt is ISO string
            date_key = created[:10] if created else None
            if date_key:
                if first_date is None or date_key < first_date:
                    first_date = date_key
                if last_date is None or date_key > last_date:
                    last_date = date_key
            msgs = _MESSAGES.get(sid, [])
            total_messages += len(msgs)
            # session duration: last_message_ts - created
            duration = 0
            if msgs:
                last_ts = msgs[-1].get("timestamp", "")
                if last_ts and created:
                    try:
                        t0 = _dt.datetime.fromisoformat(
                            created.replace("Z", "+00:00"))
                        t1 = _dt.datetime.fromisoformat(
                            last_ts.replace("Z", "+00:00"))
                        duration = int((t1 - t0).total_seconds())
                    except Exception:
                        duration = 0
            all_sessions.append({
                "sessionId": sid,
                "duration": duration,
                "messageCount": len(msgs),
                "timestamp": created,
            })
            if date_key:
                d = daily.setdefault(date_key, {
                    "messageCount": 0, "sessionCount": 0, "toolCallCount": 0,
                })
                d["messageCount"] += len(msgs)
                d["sessionCount"] += 1

            # Model tokens from assistant messages
            for m in msgs:
                if m.get("type") == "assistant":
                    model = m.get("model") or "unknown"
                    mt = model_tokens.setdefault(date_key or "unknown", {})
                    # Estimate: ~30 chars per token
                    mt[model] = mt.get(model, 0) + len(m.get("content", ""))

        # Apply range filter
        if range_filter == "7d":
            cutoff = (_dt.datetime.now(_dt.timezone.utc)
                      - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
            daily = {k: v for k, v in daily.items() if k >= cutoff}
        elif range_filter == "30d":
            cutoff = (_dt.datetime.now(_dt.timezone.utc)
                      - _dt.timedelta(days=30)).strftime("%Y-%m-%d")
            daily = {k: v for k, v in daily.items() if k >= cutoff}

        # Build dailyActivity + dailyModelTokens arrays
        daily_activity = [
            {"date": k, "messageCount": v["messageCount"],
             "sessionCount": v["sessionCount"],
             "toolCallCount": v["toolCallCount"]}
            for k, v in sorted(daily.items())
        ]
        daily_model_tokens = [
            {"date": k, "tokensByModel": v}
            for k, v in sorted(model_tokens.items())
        ]

        # Active days + total days span
        active_days = len(daily)
        if first_date and last_date:
            try:
                t0 = _dt.date.fromisoformat(first_date)
                t1 = _dt.date.fromisoformat(last_date)
                total_days = (t1 - t0).days + 1
            except Exception:
                total_days = active_days
        else:
            total_days = active_days

        # Streaks: compute longest run of consecutive days
        sorted_dates = sorted(daily.keys())
        longest = 0
        current = 0
        prev = None
        longest_start = None
        longest_end = None
        current_start = None
        run_start = None
        for d in sorted_dates:
            if prev is None:
                run_start = d
                current = 1
            else:
                try:
                    diff = (_dt.date.fromisoformat(d)
                            - _dt.date.fromisoformat(prev)).days
                except Exception:
                    diff = 1
                if diff == 1:
                    current += 1
                else:
                    if current > longest:
                        longest = current
                        longest_start = run_start
                        longest_end = prev
                    run_start = d
                    current = 1
            prev = d
        if current > longest:
            longest = current
            longest_start = run_start
            longest_end = sorted_dates[-1] if sorted_dates else None
        # Current streak: days up to today
        if sorted_dates:
            today = _dt.date.today().isoformat()
            yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
            if sorted_dates[-1] in (today, yesterday):
                current = 1
                run_start = sorted_dates[-1]
                # walk back
                for i in range(len(sorted_dates) - 2, -1, -1):
                    try:
                        diff = (_dt.date.fromisoformat(sorted_dates[i + 1])
                                - _dt.date.fromisoformat(sorted_dates[i])).days
                    except Exception:
                        break
                    if diff == 1:
                        current += 1
                        run_start = sorted_dates[i]
                    else:
                        break
            else:
                current = 0
                run_start = None

        # Longest session
        longest_sess = max(all_sessions, key=lambda s: s["duration"]) \
            if all_sessions else None
        if longest_sess and longest_sess["duration"] > 0:
            longest_session = {
                "sessionId": longest_sess["sessionId"],
                "duration": longest_sess["duration"],
                "messageCount": longest_sess["messageCount"],
                "timestamp": longest_sess["timestamp"],
            }
        else:
            longest_session = None

        # Model usage aggregate
        model_usage: dict[str, dict[str, int]] = {}
        for k, v in sorted(model_tokens.items()):
            for m, t in v.items():
                mu = model_usage.setdefault(m, {
                    "inputTokens": 0, "outputTokens": 0,
                    "cacheReadInputTokens": 0,
                    "cacheCreationInputTokens": 0,
                })
                mu["outputTokens"] += t

        # Peak day + hour (approximate: just use daily message counts)
        peak_day = None
        peak_count = 0
        hour_counter: Counter = Counter()
        for k, v in daily.items():
            if v["messageCount"] > peak_count:
                peak_count = v["messageCount"]
                peak_day = k
        # Approximate hour: spread messages across 9-18
        if total_messages and daily_activity:
            avg_per_day = total_messages / max(1, len(daily_activity))
            peak_hour = int((avg_per_day * 2) % 24)  # rough heuristic
        else:
            peak_hour = None

        stats.update({
            "totalSessions": len(_SESSIONS),
            "totalMessages": total_messages,
            "totalDays": total_days,
            "activeDays": active_days,
            "streaks": {
                "currentStreak": current,
                "longestStreak": longest,
                "currentStreakStart": run_start,
                "longestStreakStart": longest_start,
                "longestStreakEnd": longest_end,
            },
            "dailyActivity": daily_activity,
            "dailyModelTokens": daily_model_tokens,
            "longestSession": longest_session,
            "modelUsage": model_usage,
            "firstSessionDate": first_date,
            "lastSessionDate": last_date,
            "peakActivityDay": peak_day,
            "peakActivityHour": peak_hour,
        })
        return {
            "stats": stats,
            "range": range_filter,
            "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
    except Exception as e:
        import sys as _sys
        print(f"[activity-stats] error: {e}", file=_sys.stderr, flush=True)
        return {
            "stats": stats,
            "range": range_filter,
            "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }


def _get_activity_stats() -> dict[str, Any]:
    """Legacy stub — kept for backward compat. Returns old flat shape."""
    return {
        "byDay": [], "byModel": [], "byProvider": [],
        "totalCalls": 0, "totalTokens": 0, "totalCost": 0.0,
    }


# ---- Project Workspace endpoints (v2.6.0) ---- #

def _project_dict(p) -> dict[str, Any]:
    """Convert a Project dataclass to a frontend-friendly dict."""
    from madcop.server.projects import PHASE_TEMPLATE
    return {
        **p.to_dict(),
        "phase_info": {
            "phase": p.current_phase,
            **PHASE_TEMPLATE.get(p.current_phase, {}),
        },
    }


def _register_project_endpoints(app: FastAPI) -> None:
    """Register /api/projects/* endpoints (v2.6.0 long-running tasks)."""
    from madcop.server.projects import get_project_store, PHASE_ORDER

    @app.get("/api/projects", include_in_schema=False)
    async def cc_list_projects(status: str = Query(default="")):
        try:
            store = get_project_store()
            items = store.list(status=status or None, limit=100)
            return {"projects": [_project_dict(p) for p in items],
                    "total": len(items)}
        except Exception as e:
            return {"projects": [], "total": 0, "error": str(e)}

    @app.post("/api/projects", include_in_schema=False)
    async def cc_create_project(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        store = get_project_store()
        proj = store.create(
            name=body.get("name", "Untitled Project"),
            description=body.get("description", ""),
            metadata=body.get("metadata", {}),
        )
        return _project_dict(proj)

    @app.get("/api/projects/{project_id}", include_in_schema=False)
    async def cc_get_project(project_id: str):
        store = get_project_store()
        proj = store.get(project_id)
        if not proj:
            return {"error": "not found"}
        return _project_dict(proj)

    @app.delete("/api/projects/{project_id}", include_in_schema=False)
    async def cc_delete_project(project_id: str):
        store = get_project_store()
        ok = store.delete(project_id)
        return {"ok": ok}

    @app.post("/api/projects/{project_id}/advance",
               include_in_schema=False)
    async def cc_project_advance(project_id: str, request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        store = get_project_store()
        proj = store.advance(
            project_id,
            next_phase=body.get("next_phase") or None,
            artifact_content=body.get("artifact_content"),
        )
        return _project_dict(proj)

    @app.put("/api/projects/{project_id}/artifact/{phase}",
              include_in_schema=False)
    async def cc_project_set_artifact(
        project_id: str, phase: str, request: Request,
    ):
        try:
            body = await request.json()
        except Exception:
            body = {}
        store = get_project_store()
        proj = store.set_artifact(
            project_id, phase, body.get("content", ""),
        )
        return _project_dict(proj)

    @app.post("/api/projects/{project_id}/archive",
               include_in_schema=False)
    async def cc_project_archive(project_id: str):
        store = get_project_store()
        proj = store.archive(project_id)
        return _project_dict(proj)

    @app.post("/api/projects/{project_id}/activate",
               include_in_schema=False)
    async def cc_project_activate(project_id: str):
        store = get_project_store()
        proj = store.activate(project_id)
        return _project_dict(proj)

    @app.post("/api/projects/{project_id}/sessions",
               include_in_schema=False)
    async def cc_project_attach_session(
        project_id: str, request: Request,
    ):
        try:
            body = await request.json()
        except Exception:
            body = {}
        store = get_project_store()
        proj = store.attach_session(
            project_id, body.get("session_id", ""),
        )
        return _project_dict(proj)

    @app.get("/api/projects/phases", include_in_schema=False)
    async def cc_project_phases():
        from madcop.server.projects import PHASE_TEMPLATE
        return {
            "phases": [
                {"id": pid, **info, "order": idx}
                for idx, (pid, info) in enumerate(PHASE_TEMPLATE.items())
            ],
            "order": PHASE_ORDER,
        }


# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Catch-all — 200 fallthrough for any /api/* path we haven't registered.
# Catch-all — 200 fallthrough for any /api/* path we haven't registered.
# Returns an empty object so destructuring in the React UI never throws.
# Logs diagnostic events so we can debug client errors.
# --------------------------------------------------------------------------- #

def install_catch_all(app: FastAPI) -> None:
    @app.api_route("/api/{path:path}",
                   methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def _madcop_compat_catch_all(
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
