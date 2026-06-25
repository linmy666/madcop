"""v0.7.0 — Sub-agent specification.

The contract for "what kind of sub-agent is this?". Inspired by
common agent frameworks' separation of config from execution.

Key design decision (kept from internal design notes):
  - `disallowed_tools` defaults to `["task"]` so sub-agents CANNOT
    spawn more sub-agents (prevents recursive explosion).
  - `model: "inherit"` means "use whatever model the parent used".
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Tools that a sub-agent is never allowed to use, regardless of config.
# "task" is the dispatch tool — banning it stops sub-agents from
# recursively spawning more sub-agents.
_DEFAULT_DISALLOWED_TOOLS: tuple[str, ...] = ("task",)


@dataclass(frozen=True)
class SubagentSpec:
    """Configuration for a sub-agent.

    Attributes:
        name: Unique identifier. Built-ins: "general-purpose", "bash".
        description: When the lead agent should delegate to this sub-agent.
                    (Free-form text shown to the LLM.)
        system_prompt: The sub-agent's operating instructions.
        tools: Explicit allow-list of tool names. None = inherit from parent.
        disallowed_tools: Always-on deny-list. Default: ("task",).
        skills: List of skill names to load. None = inherit; [] = none.
        model: Model name OR "inherit" to use parent's model.
        max_turns: Maximum agent turns before stopping.
        timeout_seconds: Hard execution-time cap. 0 = no cap.
    """

    name: str
    description: str
    system_prompt: str = ""
    tools: tuple[str, ...] | None = None
    disallowed_tools: tuple[str, ...] = field(default_factory=lambda: _DEFAULT_DISALLOWED_TOOLS)
    skills: tuple[str, ...] | None = None
    model: str = "inherit"
    max_turns: int = 50
    timeout_seconds: int = 300  # 5 min default (vs. deerflow's 30 min — personal use)

    def effective_tools(self, parent_tools: tuple[str, ...]) -> tuple[str, ...]:
        """Resolve the actual tool list this sub-agent gets.

        Rules:
        - Start with parent's tools (if `tools` is None) or explicit allow-list
        - Remove `disallowed_tools`
        - Always remove "task" (defense in depth, even if user overrides)
        """
        if self.tools is None:
            available = list(parent_tools)
        else:
            available = list(self.tools)
        blocked = set(self.disallowed_tools) | {"task"}  # task ALWAYS blocked
        return tuple(t for t in available if t not in blocked)

    def to_dict(self) -> dict:
        """Serialise for logging / debugging. Not for persistence."""
        return {
            "name": self.name,
            "description": self.description[:80] + ("..." if len(self.description) > 80 else ""),
            "tools": "inherit" if self.tools is None else list(self.tools),
            "disallowed_tools": list(self.disallowed_tools),
            "skills": "inherit" if self.skills is None else list(self.skills),
            "model": self.model,
            "max_turns": self.max_turns,
            "timeout_seconds": self.timeout_seconds,
        }


__all__ = ["SubagentSpec"]
