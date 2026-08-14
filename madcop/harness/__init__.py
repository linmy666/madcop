"""MadCop Harness — production agent harness architecture.

Core abstractions:
- SessionLog: append-only event log (single source of truth)
- Capability protocols: swappable fs/shell/search backends
- Turn/Step state machine: formal lifecycle
- MadCopHarness: MEA loop engine (Manager→Executor→Auditor)

Three event domains, structurally separated:
- REASONING: model's internal logic (thought_*)
- TOOL: side effects (tool_start/end)
- ANSWER: user-visible output (text_delta/end)
"""
from .core import (
    SessionLog, Step, TurnState,
    HarnessEvent, EventDomain,
    FileSystemCapability, ShellCapability, SearchCapability,
    LocalFileSystem,
    reasoning_event, tool_event, answer_event, system_event,
)
from .mea_loop import MadCopHarness

__all__ = [
    "SessionLog", "Step", "TurnState",
    "HarnessEvent", "EventDomain",
    "FileSystemCapability", "ShellCapability", "SearchCapability",
    "LocalFileSystem",
    "reasoning_event", "tool_event", "answer_event", "system_event",
    "MadCopHarness",
]
