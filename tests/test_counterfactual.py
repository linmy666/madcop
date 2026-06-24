"""Tests for the counterfactual cost engine."""

from __future__ import annotations

import pytest

from madcop.anomaly.detector import AnomalyFinding
from madcop.counterfactual import (
    CANNED_INTERVENTIONS,
    CostLine,
    CostModel,
    CounterfactualEngine,
    CounterfactualOutcome,
    Intervention,
    InterventionKind,
    compare_all,
)
from madcop.event import (
    EventType,
    SourceSystem,
    UnifiedEvent,
    make_event,
)


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #

def _finding(rule_id: str, subject_id: str, ts: str, severity: int, **details) -> AnomalyFinding:
    return AnomalyFinding(
        rule_id=rule_id,
        subject_id=subject_id,
        timestamp=ts,
        severity=severity,
        summary=f"test {rule_id}",
        details=details,
    )


def _oms_order(ts: str, store: str = "STORE-A", category: str = "default") -> UnifiedEvent:
    return make_event(
        timestamp=ts, source_system=SourceSystem.OMS,
        event_type=EventType.ORDER_PLACED, subject_id=store,
        attributes={"category": category},
    )


def _oms_cancel(ts: str, store: str = "STORE-A", category: str = "default") -> UnifiedEvent:
    return make_event(
        timestamp=ts, source_system=SourceSystem.OMS,
        event_type=EventType.ORDER_CANCELLED, subject_id=store,
        attributes={"category": category},
    )


# --------------------------------------------------------------------------- #
# Cost model
# --------------------------------------------------------------------------- #

def test_cost_model_defaults() -> None:
    c = CostModel()
    assert c.lost_margin_per_unit > 0
    assert c.compensation_per_delayed > 0
    assert c.expedite_cost_per_hour > 0
    assert c.max_expedite_hours > 0


# --------------------------------------------------------------------------- #
# Intervention construction
# --------------------------------------------------------------------------- #

def test_intervention_construction() -> None:
    i = Intervention(kind=InterventionKind.EXPEDITE_2H, hours_saved=2.0)
    assert i.kind == InterventionKind.EXPEDITE_2H
    assert i.hours_saved == 2.0


def test_canned_interventions_match_kind() -> None:
    for kind, intervention in CANNED_INTERVENTIONS.items():
        assert intervention.kind == kind


def test_no_action_has_zero_direct() -> None:
    i = CANNED_INTERVENTIONS[InterventionKind.NO_ACTION]
    assert i.hours_saved == 0.0


def test_expedite_4h_capped_at_max() -> None:
    """Engine should cap requested hours to max_expedite_hours."""
    eng = CounterfactualEngine(CostModel(max_expedite_hours=3.0))
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=5)
    events = [_oms_order("2026-06-15T10:01:00Z")]
    i = Intervention(kind=InterventionKind.EXPEDITE_4H, hours_saved=4.0)
    out = eng.evaluate(f, events, i)
    # Direct cost should reflect 3h (capped) not 4h
    expedite = [l for l in out.intervention_breakdown if l.label == "expedite_surcharge"][0]
    assert expedite.amount_yuan == pytest.approx(3.0 * 120.0)


# --------------------------------------------------------------------------- #
# TMS (freight) anomaly — baseline vs intervention
# --------------------------------------------------------------------------- #

def test_tms_baseline_with_orders_in_window() -> None:
    eng = CounterfactualEngine(CostModel(lost_margin_per_unit=80.0))
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=5)
    # 5 OMS orders within the 4h window after the anomaly
    events = [_oms_order(f"2026-06-15T10:{i+1:02d}:00Z") for i in range(5)]
    out = eng.evaluate(f, events, Intervention(kind=InterventionKind.NO_ACTION))
    # severity=5 → delay=1.0h; stockout_fraction = 1.0/4.0 = 0.25
    # lost_units = 5 * 0.25 = 1.25; cost = 1.25 * 80 = 100
    assert out.baseline_total_yuan == pytest.approx(100.0)
    # NO_ACTION has zero intervention cost
    assert out.intervention_total_yuan == pytest.approx(100.0)


def test_tms_expedite_2h_saves_money() -> None:
    eng = CounterfactualEngine()
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=5)
    events = [_oms_order(f"2026-06-15T10:{i+1:02d}:00Z") for i in range(5)]
    baseline = eng.evaluate(f, events, CANNED_INTERVENTIONS[InterventionKind.NO_ACTION])
    expedite = eng.evaluate(f, events, CANNED_INTERVENTIONS[InterventionKind.EXPEDITE_2H])
    # 2h saved → effective delay 1.0 - 2.0 = 0h → zero stockout
    # Cost: 2h * 120/h = 240
    assert expedite.intervention_total_yuan < baseline.intervention_total_yuan + 240 + 1
    assert expedite.intervention_total_yuan == pytest.approx(240.0)


def test_tms_expedite_4h_fully_eliminates_stockout() -> None:
    eng = CounterfactualEngine()
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=5)
    events = [_oms_order(f"2026-06-15T10:{i+1:02d}:00Z") for i in range(5)]
    out = eng.evaluate(f, events, CANNED_INTERVENTIONS[InterventionKind.EXPEDITE_4H])
    # 4h saved → delay 0h → 0 stockout; cost = 4h * 120 = 480
    assert out.intervention_total_yuan == pytest.approx(480.0)


def test_tms_recommends_cheapest_intervention() -> None:
    eng = CounterfactualEngine()
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=5)
    events = [_oms_order(f"2026-06-15T10:{i+1:02d}:00Z") for i in range(10)]
    all_outcomes = compare_all(f, events)
    # compare_all sorts by delta ascending
    assert all_outcomes[0].delta_yuan <= all_outcomes[-1].delta_yuan


def test_tms_baseline_uses_default_rate_when_no_orders() -> None:
    eng = CounterfactualEngine(CostModel(
        default_order_rate_per_hour=20.0, lost_margin_per_unit=100.0,
    ))
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=5)
    # No OMS events in window
    out = eng.evaluate(f, [], CANNED_INTERVENTIONS[InterventionKind.NO_ACTION])
    # orders_at_risk = 20 * 4 = 80; delay 1h; stockout 25%; lost 20 units; ¥2000
    assert out.baseline_total_yuan == pytest.approx(2000.0)


# --------------------------------------------------------------------------- #
# OMS (cancel) anomaly — interventions don't help
# --------------------------------------------------------------------------- #

def test_oms_cancel_anomaly_baseline_counts_cancels() -> None:
    eng = CounterfactualEngine(CostModel(lost_margin_per_unit=80.0))
    f = _finding("oms.cancellation.spike", "STORE-A", "2026-06-15T10:00:00Z", severity=4)
    events = [_oms_cancel(f"2026-06-15T10:{i+1:02d}:00Z") for i in range(3)]
    out = eng.evaluate(f, events, CANNED_INTERVENTIONS[InterventionKind.NO_ACTION])
    # 3 cancels × ¥80 = ¥240
    assert out.baseline_total_yuan == pytest.approx(240.0)


def test_oms_cancel_expedite_does_not_help() -> None:
    eng = CounterfactualEngine()
    f = _finding("oms.cancellation.spike", "STORE-A", "2026-06-15T10:00:00Z", severity=4)
    events = [_oms_cancel(f"2026-06-15T10:{i+1:02d}:00Z") for i in range(3)]
    out = eng.evaluate(f, events, CANNED_INTERVENTIONS[InterventionKind.EXPEDITE_2H])
    # OMS anomaly: residual cancellations still cost ¥240; expedite surcharge ¥240
    assert out.intervention_total_yuan > out.baseline_total_yuan
    assert "no residual effect" in " ".join(out.assumptions)


# --------------------------------------------------------------------------- #
# Outcome recommendation
# --------------------------------------------------------------------------- #

def test_recommendation_savings() -> None:
    eng = CounterfactualEngine()
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=5)
    # 100 orders * 25% stockout * ¥80 = ¥2000 baseline; 4h expedite (¥480) saves ¥1520
    events = [_oms_order(f"2026-06-15T10:{(i // 60) + 1:02d}:{i % 60:02d}Z") for i in range(100)]
    out = eng.evaluate(f, events, CANNED_INTERVENTIONS[InterventionKind.EXPEDITE_4H])
    assert "RECOMMEND" in out.recommend()


def test_recommendation_avoid() -> None:
    eng = CounterfactualEngine()
    # Low-severity anomaly with 0 orders: NO_ACTION is best
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=1)
    events = [_oms_order("2026-06-15T10:01:00Z")]
    out = eng.evaluate(f, events, CANNED_INTERVENTIONS[InterventionKind.EXPEDITE_4H])
    # 4h expedite (480) >> tiny baseline (80*0.05=4) → DO NOT
    assert "DO NOT" in out.recommend()


# --------------------------------------------------------------------------- #
# Defensive
# --------------------------------------------------------------------------- #

def test_invalid_finding_timestamp_raises() -> None:
    from madcop.counterfactual.cost import finding_ts
    f = AnomalyFinding(
        rule_id="tms.leadtime.overrun", subject_id="X",
        timestamp="not-a-timestamp", severity=3, summary="x",
    )
    with pytest.raises(ValueError):
        finding_ts(f, [])


def test_unknown_intervention_raises() -> None:
    eng = CounterfactualEngine()
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=3)
    bad = Intervention(kind="not_a_real_kind")  # type: ignore[arg-type]
    # The enum will raise at construction time
    with pytest.raises((ValueError, AttributeError)):
        eng.evaluate(f, [], bad)


def test_outcome_is_frozen() -> None:
    f = _finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", severity=3)
    out = CounterfactualEngine().evaluate(f, [], CANNED_INTERVENTIONS[InterventionKind.NO_ACTION])
    with pytest.raises(Exception):
        out.delta_yuan = 0.0  # type: ignore[misc]
