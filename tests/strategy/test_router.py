"""Tests for the model router — auto mode classifier + manual mode mapping."""
from __future__ import annotations

import pytest

from madcop.strategy.router import (
    ModelRouter,
    ModelTier,
    TaskSignals,
    classify,
    DEFAULT_STEP_TO_TIER,
    T1_THRESHOLD,
    T2_THRESHOLD,
)


# ---------------------------------------------------------------------------
# classify() — pure-function tests for the difficulty scorer
# ---------------------------------------------------------------------------


def test_classify_empty_signals_is_local():
    """No signals at all → score 0.0 → T3 local."""
    ds = classify(TaskSignals())
    assert ds.score == 0.0
    assert ds.tier == ModelTier.T3_LOCAL
    assert not ds.contributing_signals


def test_classify_simple_lookup_demotes_below_zero():
    """simple_lookup contributes -0.30; combined with no other signals → T3."""
    ds = classify(TaskSignals(simple_lookup=True))
    assert ds.score == -0.30
    assert ds.tier == ModelTier.T3_LOCAL
    assert "simple_lookup" in ds.contributing_signals


def test_classify_supply_chain_alone_is_strong():
    """Just `touches_supply_chain=True` is +0.30 → T2 fast (below 0.40? no, 0.30 < 0.40 → T3).

    Wait — 0.30 < 0.40 → T3 local. We need at least one more signal.
    """
    ds = classify(TaskSignals(touches_supply_chain=True))
    assert ds.score == pytest.approx(0.30)
    assert ds.tier == ModelTier.T3_LOCAL  # because 0.30 < 0.40


def test_classify_planning_plus_supply_chain_is_strong():
    """Planning (+0.30) + supply chain (+0.30) = 0.60 → T2 fast (between 0.40 and 0.70)."""
    ds = classify(TaskSignals(requires_planning=True, touches_supply_chain=True))
    assert ds.score == pytest.approx(0.60)
    assert ds.tier == ModelTier.T2_FAST


def test_classify_all_signals_is_max():
    """All positive signals + no negative → score approaches 1.0, tier T1."""
    ds = classify(TaskSignals(
        requires_planning=True,
        open_ended_goal=True,
        multi_step=True,
        touches_supply_chain=True,
        touches_finance=True,
        touches_code=True,
        context_tokens=20_000,        # triggers context_heavy
        user_emphasised_accuracy=True,
    ))
    # 0.30 + 0.20 + 0.15 + 0.30 + 0.25 + 0.15 + 0.20 + 0.10 = 1.65
    assert ds.score == pytest.approx(1.65)
    assert ds.tier == ModelTier.T1_STRONG
    assert ds.is_high()


def test_classify_threshold_boundaries():
    """The 0.70 / 0.40 thresholds are the only places the bucket changes."""
    # Just above T1 threshold
    high = classify(TaskSignals(
        requires_planning=True,        # 0.30
        touches_supply_chain=True,     # 0.30
        user_emphasised_accuracy=True, # 0.10
    ))  # 0.70 → T1
    assert high.score == pytest.approx(0.70)
    assert high.tier == ModelTier.T1_STRONG

    # Just below T1 threshold
    just_below = classify(TaskSignals(
        requires_planning=True,        # 0.30
        touches_supply_chain=True,     # 0.30
    ))  # 0.60 → T2
    assert just_below.tier == ModelTier.T2_FAST


# ---------------------------------------------------------------------------
# ModelRouter — auto mode facade
# ---------------------------------------------------------------------------


def test_router_auto_returns_correct_tier():
    router = ModelRouter.auto_default()
    decision = router.route(TaskSignals(
        requires_planning=True,
        touches_supply_chain=True,
        user_emphasised_accuracy=True,
    ))
    assert decision.tier == ModelTier.T1_STRONG
    assert "auto:" in decision.reason
    assert decision.step == "execute"  # default


def test_router_auto_requires_signals():
    """In auto mode, calling route() without signals must raise."""
    router = ModelRouter.auto_default()
    with pytest.raises(ValueError, match="auto mode requires"):
        router.route()


def test_router_manual_uses_supplied_mapping():
    """In manual mode, the per-step mapping is used directly."""
    router = ModelRouter.manual({
        "plan": "T1",
        "execute": "T2",
        "verify": "T3",
    })
    assert router.route(step="plan").tier == ModelTier.T1_STRONG
    assert router.route(step="execute").tier == ModelTier.T2_FAST
    assert router.route(step="verify").tier == ModelTier.T3_LOCAL


def test_router_manual_falls_back_to_defaults():
    """A step not in the manual map falls back to DEFAULT_STEP_TO_TIER."""
    router = ModelRouter.manual({"plan": "T1"})
    # 'reflect' is not in the manual map → falls back to default
    decision = router.route(step="reflect")
    assert decision.tier == ModelTier.T1_STRONG  # from defaults


def test_router_manual_unknown_step_defaults_to_t2():
    """Unknown step name in manual mode → T2 fast (safe default)."""
    router = ModelRouter.manual({})
    decision = router.route(step="unknown_thing")
    assert decision.tier == ModelTier.T2_FAST


def test_router_accepts_tier_string_aliases():
    """Tier aliases like 'strong' / 'fast' / 'local' are accepted."""
    router = ModelRouter.manual({
        "a": "strong",
        "b": "fast",
        "c": "local",
    })
    assert router.route(step="a").tier == ModelTier.T1_STRONG
    assert router.route(step="b").tier == ModelTier.T2_FAST
    assert router.route(step="c").tier == ModelTier.T3_LOCAL


def test_router_rejects_unknown_tier_string():
    """Bad tier strings raise immediately at construction."""
    with pytest.raises(ValueError, match="Unknown tier"):
        ModelRouter.manual({"x": "T99"})


# ---------------------------------------------------------------------------
# DEFAULT_STEP_TO_TIER — pin the table so accidental edits break tests
# ---------------------------------------------------------------------------


def test_default_step_to_tier_covers_all_agent_steps():
    """The default table should cover the main agent loop steps."""
    expected = {"plan", "execute", "verify", "reflect", "aggregate", "replan", "growth"}
    assert expected.issubset(DEFAULT_STEP_TO_TIER.keys())


def test_default_plan_is_strong():
    assert DEFAULT_STEP_TO_TIER["plan"] == ModelTier.T1_STRONG


def test_default_execute_is_fast():
    assert DEFAULT_STEP_TO_TIER["execute"] == ModelTier.T2_FAST


def test_default_verify_is_local():
    """Verify starts as T3 (rule-based). LLM is fallback."""
    assert DEFAULT_STEP_TO_TIER["verify"] == ModelTier.T3_LOCAL
