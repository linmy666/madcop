"""Tests for the context compactor."""
from __future__ import annotations

import pytest

from madcop.strategy.context_compactor import (
    ContextCompactor,
    CompactionResult,
)
from madcop.strategy.scratchpad import StepRecord


def _step(i: int, input_len: int = 100, output_len: int = 100) -> StepRecord:
    return StepRecord(
        step_index=i,
        step_name="execute",
        tier="T2",
        provider="nvidia_nim",
        model="m",
        input_summary="a" * input_len,
        output_summary="b" * output_len,
        input_tokens=input_len // 4,
        output_tokens=output_len // 4,
        cost_usd=0.0,
        wallclock_ms=100,
    )


def test_compactor_empty_steps():
    c = ContextCompactor(context_budget=1000)
    res = c.plan([])
    assert not res.needs_compaction
    assert res.keep_recent == 0
    assert res.estimated_input_tokens_after == 0


def test_compactor_under_budget_no_compaction():
    """3 small steps easily fit in a 10K budget — no compaction needed."""
    c = ContextCompactor(context_budget=10_000, keep_recent=2)
    steps = [_step(0, 100, 100), _step(1, 100, 100), _step(2, 100, 100)]
    res = c.plan(steps)
    assert not res.needs_compaction
    assert res.keep_recent == 3
    assert "fits in budget" in res.reason


def test_compactor_over_budget_summarises_older():
    """When total > budget, older steps are summarised; recent kept verbatim.

    With context_budget=1000, keep_recent=2, and 30 steps of ~50 tokens each:
    - keep 2 verbatim = 100 tokens
    - summarise 28 = 28 × 50 = 1400 tokens  → total 1500, still > 1000
    - fallback: keep_recent=1, summarise 29 = 29 × 50 = 1450 + 50 = 1500, still > 1000
    - even with keep=1 + summarise all, it remains over because summary is 50 tok.
    → compactor keeps the latest 1 verbatim + summarises the rest.
    """
    c = ContextCompactor(context_budget=1000, keep_recent=2)
    steps = [_step(i, 200, 200) for i in range(30)]
    res = c.plan(steps)
    assert res.needs_compaction
    # 29 older steps should be summarised (only the latest kept verbatim)
    assert len(res.summarise_indices) == 29
    assert res.summarise_indices[0] == 0
    assert res.summarise_indices[-1] == 28
    assert res.keep_recent == 1  # fell back to 1 because summarisation wasn't enough


def test_compactor_reduces_token_count():
    """After compaction, the projected prompt is smaller."""
    c = ContextCompactor(context_budget=1500, keep_recent=2)
    steps = [_step(i, 400, 400) for i in range(10)]  # ~200 tokens each
    res = c.plan(steps)
    assert res.saves_tokens > 0


def test_compactor_extreme_overflow_keeps_only_one():
    """When summarising isn't enough, keep only the latest step verbatim."""
    c = ContextCompactor(context_budget=2000, keep_recent=3)
    # Each step ~1000 tokens. 10 steps = 10,000 tokens. Way over.
    steps = [_step(i, 4000, 4000) for i in range(10)]
    res = c.plan(steps)
    assert res.needs_compaction
    # With summarisation alone (50 tokens per older step):
    #   keep 3 verbatim = 3*1000 = 3000
    #   summarise 7 = 7*50 = 350
    #   total = 3350, still > 2000.
    # → compactor falls back to keep_recent=1
    assert res.keep_recent == 1
    assert len(res.summarise_indices) == 9


def test_compactor_rejects_tiny_budget():
    with pytest.raises(ValueError, match="context_budget too small"):
        ContextCompactor(context_budget=10)


def test_compactor_rejects_zero_keep_recent():
    with pytest.raises(ValueError, match="keep_recent must be >= 1"):
        ContextCompactor(keep_recent=0)


def test_summarise_template_returns_string():
    c = ContextCompactor()
    s = _step(0, 50, 50)
    tpl = c.summarise_template(s)
    assert isinstance(tpl, str)
    assert "step 0" in tpl
    assert "execute" in tpl
    assert "T2" in tpl
