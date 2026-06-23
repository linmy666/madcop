"""Tests for L2 — anomaly detection (Detector + 5 rules)."""

from __future__ import annotations

import pytest

from madcop.anomaly.detector import AnomalyFinding, BaseRule, Detector
from madcop.anomaly.rules import (
    BMSSupplierScoreDropRule,
    ColdChainDurationRule,
    ColdChainTemperatureRule,
    OMSOrderCancelSpikeRule,
    TMSLeadTimeAnomalyRule,
    default_detector,
)
from madcop.event import EventType, SourceSystem, UnifiedEvent, make_event


# --------------------------------------------------------------------------- #
# Detector
# --------------------------------------------------------------------------- #

def test_detector_rejects_empty_rules() -> None:
    with pytest.raises(ValueError, match="at least one rule"):
        Detector([])


def test_detector_evaluates_event_through_all_rules() -> None:
    class AlwaysFire(BaseRule):
        rule_id = "test.always"
        description = "always fires"
        def evaluate(self, event):
            return AnomalyFinding(
                rule_id=self.rule_id, subject_id=event.subject_id,
                timestamp=event.timestamp, severity=1, summary="fire",
            )

    class NeverFire(BaseRule):
        rule_id = "test.never"
        description = "never fires"
        def evaluate(self, event):
            return None

    d = Detector([AlwaysFire(), NeverFire()])
    e = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1",
    )
    findings = d.evaluate_event(e)
    assert len(findings) == 1
    assert findings[0].rule_id == "test.always"


# --------------------------------------------------------------------------- #
# Rule 1: ColdChainTemperatureRule
# --------------------------------------------------------------------------- #

def test_coldchain_temperature_fires_above_threshold() -> None:
    rule = ColdChainTemperatureRule(threshold_c=-15.0)
    e = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-14.0,
    )
    f = rule.evaluate(e)
    assert f is not None
    assert f.severity == 3  # 1°C over


def test_coldchain_temperature_severity_scales_with_delta() -> None:
    rule = ColdChainTemperatureRule(threshold_c=-15.0)
    over_2c = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-13.0,
    )
    over_4c = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-11.0,
    )
    f2 = rule.evaluate(over_2c)
    f4 = rule.evaluate(over_4c)
    assert f2 is not None and f4 is not None
    assert f2.severity == 4
    assert f4.severity == 5


def test_coldchain_temperature_ignores_below_threshold() -> None:
    rule = ColdChainTemperatureRule()
    e = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-18.0,
    )
    assert rule.evaluate(e) is None


def test_coldchain_temperature_ignores_non_wms() -> None:
    rule = ColdChainTemperatureRule()
    e = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.TMS,
        event_type=EventType.SHIPMENT_DELAYED, subject_id="S1", value=99.0,
    )
    assert rule.evaluate(e) is None


# --------------------------------------------------------------------------- #
# Rule 2: ColdChainDurationRule
# --------------------------------------------------------------------------- #

def test_coldchain_duration_fires_only_after_window() -> None:
    rule = ColdChainDurationRule(min_duration_min=15, threshold_c=-15.0)
    base = "2026-06-15T14:30:00Z"
    # 14:30 breach — not yet sustained
    e1 = make_event(
        timestamp=base, source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-14.0,
    )
    assert rule.evaluate(e1) is None
    # 14:40 (10 min later) — still under window
    e2 = make_event(
        timestamp="2026-06-15T14:40:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-14.0,
    )
    assert rule.evaluate(e2) is None
    # 14:50 (20 min later) — sustained
    e3 = make_event(
        timestamp="2026-06-15T14:50:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-14.0,
    )
    f = rule.evaluate(e3)
    assert f is not None
    assert f.severity == 5


def test_coldchain_duration_does_not_refire_on_same_window() -> None:
    rule = ColdChainDurationRule(min_duration_min=15)
    events = [
        make_event(
            timestamp=ts, source_system=SourceSystem.WMS,
            event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-14.0,
        )
        for ts in (
            "2026-06-15T14:30:00Z",
            "2026-06-15T14:50:00Z",
            "2026-06-15T15:10:00Z",
        )
    ]
    findings = [rule.evaluate(e) for e in events]
    assert findings[0] is None
    assert findings[1] is not None
    assert findings[2] is None  # already emitted for this window


# --------------------------------------------------------------------------- #
# Rule 3: OMSOrderCancelSpikeRule
# --------------------------------------------------------------------------- #

def test_oms_cancel_spike_fires_when_rate_high() -> None:
    rule = OMSOrderCancelSpikeRule()
    # 10 orders placed over an hour, then 5 cancels
    base_ts = "2026-06-15T10:"
    for i in range(10):
        e = make_event(
            timestamp=f"{base_ts}{i:02d}:00Z", source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_PLACED, subject_id=f"O{i}",
        )
        rule.evaluate(e)
    for i in range(5):
        e = make_event(
            timestamp=f"{base_ts}{i:02d}:30Z", source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_CANCELLED, subject_id=f"O{i}",
        )
        result = rule.evaluate(e)
        if result is not None:
            assert result.severity == 4
            return
    # If we never got a result, fail
    raise AssertionError("expected cancel spike to fire")


def test_oms_cancel_spike_silent_on_low_volume() -> None:
    rule = OMSOrderCancelSpikeRule()
    for i in range(3):
        e = make_event(
            timestamp=f"2026-06-15T10:0{i}:00Z", source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_PLACED, subject_id=f"O{i}",
        )
        rule.evaluate(e)
    e = make_event(
        timestamp="2026-06-15T10:01:00Z", source_system=SourceSystem.OMS,
        event_type=EventType.ORDER_CANCELLED, subject_id="O0",
    )
    assert rule.evaluate(e) is None  # < 5 orders, no rate


# --------------------------------------------------------------------------- #
# Rule 4: TMSLeadTimeAnomalyRule
# --------------------------------------------------------------------------- #

def test_tms_leadtime_fires_on_50pct_overrun() -> None:
    rule = TMSLeadTimeAnomalyRule(overrun_ratio=0.5)
    dispatched = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.TMS,
        event_type=EventType.SHIPMENT_DISPATCHED, subject_id="SH-1",
        value=0.0, attributes={"planned_lead_time_hours": 10.0},
    )
    rule.evaluate(dispatched)
    # delivered 16h later (60% overrun)
    delivered = make_event(
        timestamp="2026-06-16T00:00:00Z", source_system=SourceSystem.TMS,
        event_type=EventType.SHIPMENT_DELIVERED, subject_id="SH-1", value=0.0,
    )
    f = rule.evaluate(delivered)
    assert f is not None
    assert f.severity in (4, 5)


def test_tms_leadtime_silent_on_time_delivery() -> None:
    rule = TMSLeadTimeAnomalyRule(overrun_ratio=0.5)
    dispatched = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.TMS,
        event_type=EventType.SHIPMENT_DISPATCHED, subject_id="SH-1",
        value=0.0, attributes={"planned_lead_time_hours": 10.0},
    )
    rule.evaluate(dispatched)
    delivered = make_event(
        timestamp="2026-06-15T16:00:00Z", source_system=SourceSystem.TMS,
        event_type=EventType.SHIPMENT_DELIVERED, subject_id="SH-1", value=0.0,
    )
    assert rule.evaluate(delivered) is None


# --------------------------------------------------------------------------- #
# Rule 5: BMSSupplierScoreDropRule
# --------------------------------------------------------------------------- #

def test_bms_supplier_score_drop_fires_on_significant_drop() -> None:
    rule = BMSSupplierScoreDropRule(min_drop=0.5)
    e1 = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.BMS,
        event_type=EventType.SUPPLIER_SCORED, subject_id="SUP-1", value=4.5,
    )
    rule.evaluate(e1)
    e2 = make_event(
        timestamp="2026-06-22T08:00:00Z", source_system=SourceSystem.BMS,
        event_type=EventType.SUPPLIER_SCORED, subject_id="SUP-1", value=3.8,
    )
    f = rule.evaluate(e2)
    assert f is not None
    assert f.severity in (4, 5)


def test_bms_supplier_score_drop_silent_on_small_change() -> None:
    rule = BMSSupplierScoreDropRule(min_drop=0.5)
    e1 = make_event(
        timestamp="2026-06-15T08:00:00Z", source_system=SourceSystem.BMS,
        event_type=EventType.SUPPLIER_SCORED, subject_id="SUP-1", value=4.5,
    )
    rule.evaluate(e1)
    e2 = make_event(
        timestamp="2026-06-22T08:00:00Z", source_system=SourceSystem.BMS,
        event_type=EventType.SUPPLIER_SCORED, subject_id="SUP-1", value=4.3,
    )
    assert rule.evaluate(e2) is None


# --------------------------------------------------------------------------- #
# default_detector() — the integration smoke test
# --------------------------------------------------------------------------- #

def test_default_detector_ships_with_five_rules() -> None:
    d = default_detector()
    assert len(d.rules) == 5


def test_default_detector_catches_wms_breach() -> None:
    d = default_detector()
    e = make_event(
        timestamp="2026-06-15T14:30:00Z", source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING, subject_id="S1", value=-14.0,
    )
    findings = d.evaluate_event(e)
    # Both temperature rule (instant) and duration rule (window) may fire;
    # at minimum, the instant rule must fire.
    rule_ids = {f.rule_id for f in findings}
    assert "wms.coldchain.temperature_breach" in rule_ids
