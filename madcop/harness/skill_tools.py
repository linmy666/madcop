"""Skill hot-loader — ~/.madcop/skills/*.py become live tools.

The self-evolving half of the skill story (paper §5: skills as
first-class, runtime-grown capabilities): a distilled skill stops being
a text note and becomes an EXECUTABLE tool the moment its Python module
lands in ~/.madcop/skills/. Files are re-imported on mtime change, so
editing a skill file takes effect on the next turn — no server restart.

Authoring contract (minimal on purpose):

    # ~/.madcop/skills/my_report.py
    from madcop.harness.skill_tools import make_tool

    def _run(query: str, work_dir: str = "", **_):
        return f"report for {query}"

    TOOLS = [make_tool("my_report", "生成周报", {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }, _run, danger="safe")]

Safety model: the file itself is arbitrary code that already runs at
import, so the trust boundary is「the user put it there」— same as an
MCP server config. `danger` still routes mutating skills through HITL.
"""
from __future__ import annotations

import importlib.util
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from madcop.agent.tool_executor import ToolPlugin

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(
    __import__("os").environ.get(
        "MADCOP_SKILLS_DIR", str(Path.home() / ".madcop" / "skills"))
)

_lock = threading.Lock()
# path → mtime of last successful import
_cache_mtimes: dict[str, float] = {}
# path → loaded plugins (empty list = loaded but defines no TOOLS)
_cache_plugins: dict[str, list[ToolPlugin]] = {}


def make_tool(name: str, description: str, parameters: dict,
              fn: Callable[..., Any], danger: str = "safe",
              timeout_s: int = 60) -> ToolPlugin:
    """Build a ToolPlugin from a plain function — the one helper skill
    authors need. `fn` receives the tool's JSON args as kwargs (plus the
    injected work_dir) and returns str | list | dict."""
    return ToolPlugin(
        name=name,
        handler=fn,
        schema={
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}},
            },
        },
        danger=danger,
        timeout_s=timeout_s,
    )


def _load_one(path: Path) -> list[ToolPlugin]:
    stem = path.stem
    mod_name = f"madcop_skill_{stem}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        raw = getattr(mod, "TOOLS", None) or []
        plugins: list[ToolPlugin] = []
        for item in raw:
            if isinstance(item, ToolPlugin):
                plugins.append(item)
            elif isinstance(item, dict):
                # dict form: make_tool kwargs
                try:
                    plugins.append(make_tool(**item))
                except TypeError:
                    logger.warning("[skills] %s: dict tool missing fields", stem)
        return plugins
    except Exception as e:  # noqa: BLE001
        logger.warning("[skills] %s failed to load: %s", path.name, e)
        return []


def load_skill_plugins(force: bool = False) -> list[ToolPlugin]:
    """Every live skill tool. Cheap: stat-cached per file, re-imports
    only files whose mtime changed (or on force)."""
    out: list[ToolPlugin] = []
    try:
        paths = sorted(SKILLS_DIR.glob("*.py")) if SKILLS_DIR.exists() else []
    except Exception:  # noqa: BLE001
        return out
    with _lock:
        live_keys = {str(p) for p in paths}
        for key in list(_cache_mtimes):
            if key not in live_keys:
                _cache_mtimes.pop(key, None)
                _cache_plugins.pop(key, None)
        for p in paths:
            key = str(p)
            if p.name.startswith("_"):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            cached = _cache_plugins.get(key)
            if (not force and cached is not None
                    and _cache_mtimes.get(key) == mtime):
                out.extend(cached)
                continue
            plugins = _load_one(p)
            _cache_mtimes[key] = mtime
            _cache_plugins[key] = plugins
            out.extend(plugins)
    # Name collisions: skill tools must not shadow built-ins.
    from madcop.tools.safety import DANGER_LEVELS
    return [p for p in out if p.name not in DANGER_LEVELS]


def reload_skills() -> dict:
    """Force re-import of every skill file; returns a status payload."""
    plugins = load_skill_plugins(force=True)
    return {
        "ok": True,
        "skills_dir": str(SKILLS_DIR),
        "tools": [p.name for p in plugins],
    }


__all__ = ["make_tool", "load_skill_plugins", "reload_skills", "SKILLS_DIR"]
