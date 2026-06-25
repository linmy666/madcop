"""v0.7.0 — Sub-agent layer.

Public surface:

  spec:        SubagentSpec (configuration dataclass)
  status:      SubagentStatus, SubagentResult (race-safe state machine)
  builtins:    GENERAL_PURPOSE, BASH, BUILTIN_SUBAGENTS, get_builtin
  executor:    SubagentExecutor, ExecutorConfig, Runner, FnRunner

The sub-agent layer is a small, parallel-running extension to the
v0.6.0 plan-execute loop. The lead agent's plan_execute loop
recognises `PlanStep.subagent` and dispatches the step to the named
sub-agent instead of running it inline.

Design notes (kept internal — see
~/.hermes/skills/research/madcop-v070-subagent-design.md):

  - Sub-agents CANNOT spawn more sub-agents. The `task` tool is
    always blocked, even if the user overrides disallowed_tools.
  - Concurrency is capped at 3 (clamped to [1, 4]) via a
    ThreadPoolExecutor.
  - Context is deep-copied at dispatch. Sub-agent writes don't
    leak back to the parent.
  - Cancellation: setting `holder.cancel_event` requests a stop;
    the runner is responsible for checking it between LLM calls.
"""
from __future__ import annotations

from .spec import SubagentSpec
from .status import SubagentResult, SubagentStatus
from .builtins import BASH, BUILTIN_SUBAGENTS, GENERAL_PURPOSE, get_builtin
from .executor import (
    DEFAULT_CONCURRENT,
    ExecutorConfig,
    FnRunner,
    MAX_CONCURRENT,
    MIN_CONCURRENT,
    Runner,
    SubagentExecutor,
)

__all__ = [
    # spec
    "SubagentSpec",
    # status
    "SubagentResult",
    "SubagentStatus",
    # builtins
    "GENERAL_PURPOSE",
    "BASH",
    "BUILTIN_SUBAGENTS",
    "get_builtin",
    # executor
    "ExecutorConfig",
    "SubagentExecutor",
    "Runner",
    "FnRunner",
    "MIN_CONCURRENT",
    "MAX_CONCURRENT",
    "DEFAULT_CONCURRENT",
]
