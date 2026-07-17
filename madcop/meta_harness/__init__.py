"""Meta-Harness landing for MadCop — optimize *task* harnesses (not vendor API profiles).

Paper: Meta-Harness (Lee et al., arXiv:2603.28052). In MadCop terms:

- ``madcop.llm.harness``  → provider/API shape (max_tokens field, etc.) — fixed adapters
- ``madcop.meta_harness`` → what to store/retrieve/show to the model during chat/agent work

Phase 0 (this package):
  - First-class ``ChatTaskHarness`` knobs
  - Filesystem archive of candidates + scores + traces
  - Eval loop using ``madcop.eval.EvalRunner``
  - Active harness loaded at chat time

Later phases (not fully automated here): coding-agent proposer, full agent traces, Pareto front.
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
