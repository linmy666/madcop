"""L3 — Per-call + per-run cost tracking.

Why this matters:
  The PRD's success metric is "single run < ¥0.10". Without explicit cost
  tracking we cannot verify that. This module is the budget guard.

Currency: USD internally (everyone reports tokens in the same unit, so we
  just multiply by the per-million rate from ProviderSpec). The user can
  convert to CNY at the CLI boundary.

The tracker is append-only — CallCost records are immutable. The aggregate
  RunCost is rebuilt from CallCost records on demand.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Iterable, Sequence


def _estimate_tokens(text: str) -> int:
    """Cheap token estimate (~1 token per 4 chars for English; ~1 per 1.5 chars for CJK).

    We use a simple heuristic that is good enough for budget tracking.
    v0.7.0 can swap in a real tokenizer (tiktoken).
    """
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return cjk // 2 + other // 4


@dataclass(frozen=True)
class CallCost:
    """One LLM call's cost. Immutable."""

    call_id: str
    provider: str
    model: str
    tier: str                       # "T1" / "T2" / "T3"
    step: str                       # "plan" / "execute" / "verify" / ...
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    wallclock_ms: int
    timestamp: float                # unix seconds

    @property
    def total_cost_usd(self) -> float:
        return self.input_cost_usd + self.output_cost_usd

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class RunCost:
    """All calls in a single agent run."""

    run_id: str
    started_at: float
    finished_at: float | None = None
    calls: list[CallCost] = field(default_factory=list)
    budget_usd: float | None = None

    @property
    def total_cost_usd(self) -> float:
        return sum(c.total_cost_usd for c in self.calls)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def duration_seconds(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.time()
        return end - self.started_at

    @property
    def is_over_budget(self) -> bool:
        if self.budget_usd is None:
            return False
        return self.total_cost_usd > self.budget_usd

    def calls_by_tier(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.calls:
            out[c.tier] = out.get(c.tier, 0) + 1
        return out

    def summary(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "duration_s": round(self.duration_seconds, 2),
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "budget_usd": self.budget_usd,
            "over_budget": self.is_over_budget,
            "calls": len(self.calls),
            "calls_by_tier": self.calls_by_tier(),
        }


class CostTracker:
    """Records CallCost entries and computes RunCost aggregates.

    Thread-safe: not actually thread-safe. Add a lock if you go multi-thread.
    v0.6.0 is single-threaded async, so this is fine.
    """

    def __init__(self, budget_usd: float | None = None) -> None:
        self._runs: dict[str, RunCost] = {}

    def start_run(self, budget_usd: float | None = None) -> RunCost:
        run = RunCost(
            run_id=uuid.uuid4().hex[:12],
            started_at=time.time(),
            budget_usd=budget_usd,
        )
        self._runs[run.run_id] = run
        return run

    def record_call(
        self,
        run: RunCost,
        *,
        provider: str,
        model: str,
        tier: str,
        step: str,
        input_text: str,
        output_text: str,
        input_cost_per_million: float,
        output_cost_per_million: float,
        wallclock_ms: int,
    ) -> CallCost:
        """Append one call to the run. Returns the recorded CallCost."""
        in_tok = _estimate_tokens(input_text)
        out_tok = _estimate_tokens(output_text)
        in_cost = (in_tok / 1_000_000) * input_cost_per_million
        out_cost = (out_tok / 1_000_000) * output_cost_per_million
        call = CallCost(
            call_id=uuid.uuid4().hex[:12],
            provider=provider,
            model=model,
            tier=tier,
            step=step,
            input_tokens=in_tok,
            output_tokens=out_tok,
            input_cost_usd=in_cost,
            output_cost_usd=out_cost,
            wallclock_ms=wallclock_ms,
            timestamp=time.time(),
        )
        run.calls.append(call)
        return call

    def finish_run(self, run: RunCost) -> RunCost:
        run.finished_at = time.time()
        return run

    def get(self, run_id: str) -> RunCost:
        if run_id not in self._runs:
            raise KeyError(f"Unknown run: {run_id}")
        return self._runs[run_id]

    def all_runs(self) -> Sequence[RunCost]:
        return list(self._runs.values())


__all__ = [
    "CallCost",
    "RunCost",
    "CostTracker",
    "estimate_tokens",  # exposed for tests
]


# Re-export the token estimator under a public name for tests
estimate_tokens = _estimate_tokens
