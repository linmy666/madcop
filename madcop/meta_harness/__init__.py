"""Meta-Harness for MadCop — optimize task harnesses (not vendor API profiles).

Phases:
  0 — knobs + archive + local search
  1 — full eval suites (lang, distill, tools, coding)
  2 — pluggable archive-aware / mock coding proposers
  3 — expanded axes applied on live chat (tools/deep/plan/compact)
  4 — HTTP API + settings UI
"""

from .task_harness import ChatTaskHarness, load_active_harness, save_active_harness
from .archive import HarnessArchive
from .loop import MetaHarnessLoop, LoopResult

__all__ = [
    "ChatTaskHarness",
    "load_active_harness",
    "save_active_harness",
    "HarnessArchive",
    "MetaHarnessLoop",
    "LoopResult",
]
