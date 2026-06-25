"""L3 — Context compactor.

The PRD's success metric is "context peak per run < 30K tokens". This
module enforces that limit by summarising older step outputs when the
total prompt would exceed the budget.

Two strategies, used together:
1. Sliding window: keep the most recent K step outputs verbatim.
2. Summary: replace earlier outputs with a single-sentence summary each,
   produced by an LLM call (T2 by default — the summariser is tool-flavored).

The compactor does NOT call the LLM itself — it returns a CompactionResult
describing what to summarise; the agent loop (plan_execute.py) actually
issues the summarise call. This separation lets us test the compactor
without a real LLM.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

from .scratchpad import StepRecord


def _estimate_tokens(text: str) -> int:
    """Same heuristic as cost.py — duplicate intentionally to avoid
    circular import between strategy/ modules."""
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return cjk // 2 + other // 4


@dataclass
class CompactionResult:
    """What the compactor decided to do."""

    needs_compaction: bool
    keep_recent: int                          # how many of the latest steps stay verbatim
    summarise_indices: list[int] = field(default_factory=list)
    estimated_input_tokens_before: int = 0
    estimated_input_tokens_after: int = 0
    reason: str = ""

    @property
    def saves_tokens(self) -> int:
        return self.estimated_input_tokens_before - self.estimated_input_tokens_after


class ContextCompactor:
    """Decides which steps to keep verbatim and which to summarise.

    Inputs:
        - context_budget: total tokens allowed in the next prompt
        - keep_recent: always keep the most recent N step outputs verbatim
        - summarise_template: how to phrase a single-step summary

    Output: CompactionResult.
    """

    def __init__(
        self,
        context_budget: int = 30_000,
        keep_recent: int = 3,
    ) -> None:
        if context_budget < 1000:
            raise ValueError("context_budget too small (< 1000 tokens)")
        if keep_recent < 1:
            raise ValueError("keep_recent must be >= 1")
        self.context_budget = context_budget
        self.keep_recent = keep_recent

    def plan(self, steps: Sequence[StepRecord]) -> CompactionResult:
        """Decide which steps to keep verbatim, which to summarise.

        Strategy:
        - Total token budget = context_budget.
        - Always keep the last `keep_recent` steps verbatim.
        - For each older step, decide if it fits or needs to be summarised.
        - Summary costs ~50 tokens per step (a single sentence).
        """
        if not steps:
            return CompactionResult(
                needs_compaction=False,
                keep_recent=0,
                estimated_input_tokens_before=0,
                estimated_input_tokens_after=0,
                reason="no steps",
            )

        # Compute per-step cost
        per_step = [_estimate_tokens(s.input_summary) + _estimate_tokens(s.output_summary) for s in steps]
        total_before = sum(per_step)

        if total_before <= self.context_budget:
            return CompactionResult(
                needs_compaction=False,
                keep_recent=len(steps),
                estimated_input_tokens_before=total_before,
                estimated_input_tokens_after=total_before,
                reason=f"fits in budget ({total_before}/{self.context_budget})",
            )

        # Need compaction. Keep the most recent N verbatim, summarise the rest.
        n = len(steps)
        keep = min(self.keep_recent, n)
        to_summarise_indices = list(range(0, n - keep))

        # Each summary costs ~50 tokens (a single sentence).
        summary_cost_per = 50
        total_after = sum(per_step[-keep:]) + summary_cost_per * len(to_summarise_indices)

        # If still over budget, summarise more aggressively
        if total_after > self.context_budget:
            # Reduce keep to 1; keep only the latest step verbatim
            keep = 1
            to_summarise_indices = list(range(0, n - keep))
            total_after = sum(per_step[-keep:]) + summary_cost_per * len(to_summarise_indices)

        return CompactionResult(
            needs_compaction=True,
            keep_recent=keep,
            summarise_indices=to_summarise_indices,
            estimated_input_tokens_before=total_before,
            estimated_input_tokens_after=total_after,
            reason=(
                f"over budget ({total_before}/{self.context_budget}); "
                f"summarise {len(to_summarise_indices)} older steps"
            ),
        )

    def summarise_template(self, step: StepRecord) -> str:
        """Default single-sentence summary template.

        In production the agent loop will call an LLM with this template
        and the step's full content. For tests we return a placeholder.
        """
        return (
            f"[step {step.step_index} {step.step_name}/{step.tier}] "
            f"{step.input_summary[:80]} -> {step.output_summary[:80]}"
        )


__all__ = [
    "ContextCompactor",
    "CompactionResult",
]
