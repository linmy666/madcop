"""Searchable chat/agent task harness knobs.

These parameters currently live as magic numbers in ``app._build_memory_system_prompt``.
Making them a dataclass is the first step toward Meta-Harness-style search.
"""
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
    """Task harness for MadCop chat memory + skill injection.

    Optimizable axes (Meta-Harness search space for chat domain):
      - memory section token budgets
      - whether / how many skills to inject
      - identity / language policy flags (conservative defaults)
    """

    # Memory injection budgets (approx token caps in _truncate_to_budget)
    profile_budget: int = 800
    relevant_budget: int = 800
    preferences_budget: int = 400
    skills_budget: int = 300

    # Skill list injection
    inject_skills: bool = True
    max_skills: int = 10

    # Optional short system addendum (free-form; proposer can write this)
    system_addendum: str = ""

    # Metadata
    name: str = "baseline"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChatTaskHarness:
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)

    def mutate(self, **overrides: Any) -> ChatTaskHarness:
        d = self.to_dict()
        d.update(overrides)
        return ChatTaskHarness.from_dict(d)


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
        {"name": "system_addendum", "type": "str"},
    ]
