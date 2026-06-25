"""v0.7.0 — Built-in sub-agent configurations.

Two ships with v0.7.0:
  - general-purpose: multi-step reasoning, all tools (minus `task`)
  - bash:           shell command execution, only `bash` tool

Both are deliberately simple. Custom sub-agents from user config
land in v0.7.1.
"""
from __future__ import annotations

from .spec import SubagentSpec


GENERAL_PURPOSE = SubagentSpec(
    name="general-purpose",
    description=(
        "A capable agent for multi-step tasks that need both exploration "
        "and action. Use this when a sub-task would otherwise crowd the "
        "main agent's context with intermediate results."
    ),
    system_prompt=(
        "You are a general-purpose sub-agent. Complete the delegated task "
        "autonomously and return a clear, concise result.\n\n"
        "Guidelines:\n"
        "  - Focus on the delegated task; don't go off-script\n"
        "  - Use available tools as needed\n"
        "  - Return a structured summary: what was done, key findings, "
        "any issues\n"
        "  - Do NOT ask for clarification — work with the information given\n"
    ),
    # tools=None means "inherit from parent"
    # disallowed_tools defaults to ("task",) so we can't recurse
    max_turns=50,
    timeout_seconds=300,  # 5 min
)


BASH = SubagentSpec(
    name="bash",
    description=(
        "Specialist for running a series of related shell commands in an "
        "isolated context. Use this when the main agent needs to chain "
        "multiple bash calls whose intermediate output would clutter its "
        "own context."
    ),
    system_prompt=(
        "You are a bash command execution specialist. Execute the requested "
        "commands carefully and report results clearly.\n\n"
        "Guidelines:\n"
        "  - Run commands in order when they depend on each other\n"
        "  - Run independent commands in parallel\n"
        "  - Report both stdout and stderr when relevant\n"
        "  - Be cautious with destructive operations\n"
        "  - Return a concise summary of what was executed and the result\n"
    ),
    # tools is the explicit bash-only allow-list
    tools=("bash",),
    max_turns=20,
    timeout_seconds=120,  # 2 min — bash tasks should be quick
)


# Registry: name -> SubagentSpec. Used by SubagentExecutor.
BUILTIN_SUBAGENTS: dict[str, SubagentSpec] = {
    GENERAL_PURPOSE.name: GENERAL_PURPOSE,
    BASH.name: BASH,
}


def get_builtin(name: str) -> SubagentSpec | None:
    """Look up a built-in sub-agent by name. Returns None if not found."""
    return BUILTIN_SUBAGENTS.get(name)


__all__ = ["GENERAL_PURPOSE", "BASH", "BUILTIN_SUBAGENTS", "get_builtin"]
