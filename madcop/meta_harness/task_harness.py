"""Searchable chat/agent task harness knobs (Meta-Harness search space)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path.home() / ".madcop" / "meta_harness"
_ACTIVE_PATH = _ROOT / "active.json"


@dataclass
class ChatTaskHarness:
    """Task harness for MadCop chat + agent construction.

    Phase 0–3 axes: memory budgets, skills, tools, deep/plan/compact flags.
    """

    # Memory injection budgets (approx token caps)
    profile_budget: int = 800
    relevant_budget: int = 800
    preferences_budget: int = 400
    skills_budget: int = 300

    # Skill list injection
    inject_skills: bool = True
    max_skills: int = 10

    # Tool policy (applied when building openai_schemas for chat)
    max_tools: int = 64
    tool_allowlist: tuple[str, ...] = ()  # empty = all tools
    enable_tools: bool = True

    # Agent / deep-mode style flags
    enable_deep_mode: bool = True
    enable_plan_mode: bool = True
    enable_context_compact: bool = True
    compact_threshold_messages: int = 40

    # Optional short system addendum (proposer can write this)
    system_addendum: str = ""

    # Metadata
    name: str = "baseline"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # JSON-friendly
        d["tool_allowlist"] = list(self.tool_allowlist)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChatTaskHarness:
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "tool_allowlist" in kwargs and kwargs["tool_allowlist"] is not None:
            kwargs["tool_allowlist"] = tuple(kwargs["tool_allowlist"])
        return cls(**kwargs)

    def mutate(self, **overrides: Any) -> ChatTaskHarness:
        d = self.to_dict()
        d.update(overrides)
        return ChatTaskHarness.from_dict(d)

    def filter_tool_schemas(self, schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply enable_tools / allowlist / max_tools to OpenAI-style tool schemas."""
        if not self.enable_tools:
            return []
        out = list(schemas or [])
        if self.tool_allowlist:
            allow = set(self.tool_allowlist)
            filtered = []
            for s in out:
                fn = s.get("function") or s
                name = fn.get("name") or s.get("name") or ""
                if name in allow:
                    filtered.append(s)
            out = filtered
        if self.max_tools >= 0:
            out = out[: int(self.max_tools)]
        return out


def ensure_root() -> Path:
    _ROOT.mkdir(parents=True, exist_ok=True)
    return _ROOT


def load_active_harness() -> ChatTaskHarness:
    """Load the harness used by live chat (falls back to baseline defaults)."""
    try:
        if _ACTIVE_PATH.exists():
            data = json.loads(_ACTIVE_PATH.read_text(encoding="utf-8"))
            return ChatTaskHarness.from_dict(data)
    except Exception as e:
        logger.debug("load active harness: %s", e)
    return ChatTaskHarness()


def save_active_harness(h: ChatTaskHarness) -> Path:
    ensure_root()
    _ACTIVE_PATH.write_text(
        json.dumps(h.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return _ACTIVE_PATH


def list_knob_axes() -> list[dict[str, Any]]:
    """Describe searchable axes for proposers / UIs."""
    return [
        {"name": "profile_budget", "type": "int", "min": 0, "max": 4000, "step": 100},
        {"name": "relevant_budget", "type": "int", "min": 0, "max": 4000, "step": 100},
        {"name": "preferences_budget", "type": "int", "min": 0, "max": 2000, "step": 50},
        {"name": "skills_budget", "type": "int", "min": 0, "max": 1500, "step": 50},
        {"name": "inject_skills", "type": "bool"},
        {"name": "max_skills", "type": "int", "min": 0, "max": 30, "step": 1},
        {"name": "max_tools", "type": "int", "min": 0, "max": 128, "step": 1},
        {"name": "enable_tools", "type": "bool"},
        {"name": "tool_allowlist", "type": "list[str]"},
        {"name": "enable_deep_mode", "type": "bool"},
        {"name": "enable_plan_mode", "type": "bool"},
        {"name": "enable_context_compact", "type": "bool"},
        {"name": "compact_threshold_messages", "type": "int", "min": 8, "max": 200, "step": 4},
        {"name": "system_addendum", "type": "str"},
    ]
