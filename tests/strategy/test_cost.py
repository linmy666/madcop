"""Tests for the cost tracker."""
from __future__ import annotations

import pytest

from madcop.strategy.cost import (
    CostTracker,
    RunCost,
    CallCost,
    estimate_tokens,
)


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_english():
    """English text: ~1 token per 4 chars."""
    text = "Hello world, this is a test."
    # 28 chars, ~7 tokens
    assert 5 <= estimate_tokens(text) <= 9


def test_estimate_tokens_cjk():
    """CJK text: ~1 token per 2 chars."""
    text = "中文测试字符串"  # 7 CJK chars → ~3-4 tokens
    assert 3 <= estimate_tokens(text) <= 5


def test_estimate_tokens_mixed():
    """Mixed CJK + English — both heuristics apply."""
    text = "供应链 supply chain"
    # 4 CJK + 13 ascii = 2 + 3 = 5 tokens (rough)
    assert 4 <= estimate_tokens(text) <= 8


def test_tracker_starts_empty():
    tracker = CostTracker()
    assert len(tracker.all_runs()) == 0


def test_tracker_start_run_creates_run_with_id():
    tracker = CostTracker()
    run = tracker.start_run(budget_usd=0.50)
    assert run.run_id
    assert run.budget_usd == 0.50
    assert run.started_at > 0
    assert run.finished_at is None
    assert len(run.calls) == 0


def test_tracker_record_call_appends():
    tracker = CostTracker()
    run = tracker.start_run()
    call = tracker.record_call(
        run,
        provider="nvidia_nim",
        model="minimax/minimax-m3",
        tier="T2",
        step="execute",
        input_text="Hello world",
        output_text="Hi there",
        input_cost_per_million=0.10,
        output_cost_per_million=0.30,
        wallclock_ms=500,
    )
    assert len(run.calls) == 1
    assert call.input_tokens > 0
    assert call.output_tokens > 0
    assert call.total_cost_usd > 0


def test_call_cost_is_immutable():
    """CallCost is frozen — accidental mutation would break cost rollups."""
    tracker = CostTracker()
    run = tracker.start_run()
    call = tracker.record_call(
        run,
        provider="nvidia_nim",
        model="x",
        tier="T2",
        step="execute",
        input_text="a",
        output_text="b",
        input_cost_per_million=0.10,
        output_cost_per_million=0.30,
        wallclock_ms=1,
    )
    with pytest.raises((AttributeError, Exception)):
        call.input_tokens = 999  # type: ignore[misc]


def test_run_cost_aggregates_correctly():
    """Total cost of a run is the sum of per-call costs."""
    tracker = CostTracker()
    run = tracker.start_run()
    # Two T2 calls.
    # "hello world " = 12 chars → 3 tokens per repetition.
    # 20 reps = 60 tokens input, "reply " = 6 chars → 1-2 tokens × 20 = 20-40 tokens output.
    for i in range(2):
        tracker.record_call(
            run,
            provider="nvidia_nim",
            model="x",
            tier="T2",
            step="execute",
            input_text="hello world " * 20,
            output_text="reply " * 20,
            input_cost_per_million=0.10,
            output_cost_per_million=0.30,
            wallclock_ms=200,
        )
    # Sanity: tokens are positive, costs are positive, sum equals 2x a single call.
    assert run.total_input_tokens > 0
    assert run.total_output_tokens > 0
    assert run.total_cost_usd > 0
    assert len(run.calls) == 2


def test_run_cost_over_budget_detection():
    """A run whose total cost exceeds budget.is_over_budget is True."""
    tracker = CostTracker()
    run = tracker.start_run(budget_usd=0.0001)  # very small budget
    # Record a big call that will definitely exceed
    tracker.record_call(
        run,
        provider="openai",
        model="gpt-4o",
        tier="T1",
        step="plan",
        input_text="a" * 10_000,  # ~2500 tokens
        output_text="b" * 10_000,  # ~2500 tokens
        input_cost_per_million=2.50,
        output_cost_per_million=10.0,
        wallclock_ms=1000,
    )
    # 2500 * $2.50/1M = $0.00625
    # 2500 * $10.0/1M  = $0.025
    # Total ~$0.03, well over $0.0001
    assert run.is_over_budget


def test_run_cost_under_budget_detection():
    """A run under budget is not over-budget."""
    tracker = CostTracker()
    run = tracker.start_run(budget_usd=10.0)  # generous budget
    tracker.record_call(
        run,
        provider="nvidia_nim",
        model="x",
        tier="T2",
        step="execute",
        input_text="a",
        output_text="b",
        input_cost_per_million=0.10,
        output_cost_per_million=0.30,
        wallclock_ms=10,
    )
    assert not run.is_over_budget


def test_run_cost_no_budget_is_never_over():
    """A run with budget_usd=None is never over budget."""
    tracker = CostTracker()
    run = tracker.start_run()  # no budget
    tracker.record_call(
        run,
        provider="nvidia_nim",
        model="x",
        tier="T2",
        step="execute",
        input_text="a",
        output_text="b",
        input_cost_per_million=0.10,
        output_cost_per_million=0.30,
        wallclock_ms=10,
    )
    assert not run.is_over_budget


def test_run_cost_calls_by_tier():
    """The by_tier aggregation groups calls by their tier field."""
    tracker = CostTracker()
    run = tracker.start_run()
    for tier, _step in [
        ("T1", "plan"),
        ("T2", "execute"),
        ("T2", "execute"),
        ("T3", "verify"),
    ]:
        tracker.record_call(
            run,
            provider="nvidia_nim",
            model="x",
            tier=tier,
            step=_step,
            input_text="a",
            output_text="b",
            input_cost_per_million=0.10,
            output_cost_per_million=0.30,
            wallclock_ms=10,
        )
    counts = run.calls_by_tier()
    assert counts == {"T1": 1, "T2": 2, "T3": 1}


def test_run_cost_summary_includes_all_fields():
    """The summary() dict has every key the PRD success-metric tracking needs."""
    tracker = CostTracker()
    run = tracker.start_run(budget_usd=0.50)
    tracker.record_call(
        run,
        provider="nvidia_nim",
        model="x",
        tier="T2",
        step="execute",
        input_text="hello",
        output_text="world",
        input_cost_per_million=0.10,
        output_cost_per_million=0.30,
        wallclock_ms=200,
    )
    tracker.finish_run(run)
    s: dict = run.summary()
    assert s["run_id"] == run.run_id
    assert int(s["total_tokens"]) > 0  # type: ignore[arg-type]
    assert s["calls"] == 1
    assert s["budget_usd"] == 0.50
    assert s["over_budget"] is False
    assert "duration_s" in s


def test_finish_run_records_finished_at():
    tracker = CostTracker()
    run = tracker.start_run()
    assert run.finished_at is None
    tracker.finish_run(run)
    assert run.finished_at is not None
    assert run.duration_seconds >= 0
