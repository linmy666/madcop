"""Tests for the replay engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from madcop.anomaly.detector import AnomalyFinding
from madcop.anomaly.rules import default_detector
from madcop.counterfactual import InterventionKind
from madcop.event import (
    EventType, SourceSystem, UnifiedEvent, make_event,
)
from madcop.replay import (
    FindingReplay,
    ReplayEngine,
    ReplayReport,
    load_events_from_json,
    write_replay_report_json,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _tms_finding(ts: str = "2026-06-15T10:00:00Z", sev: int = 4) -> AnomalyFinding:
    return AnomalyFinding(
        rule_id="tms.leadtime.overrun",
        subject_id="SHIP-X",
        timestamp=ts,
        severity=sev,
        summary="overrun",
    )


def _dispatched(ts: str, ship: str, planned_h: float) -> UnifiedEvent:
    return make_event(
        timestamp=ts, source_system=SourceSystem.TMS,
        event_type=EventType.SHIPMENT_DISPATCHED, subject_id=ship,
        attributes={"planned_lead_time_hours": planned_h},
    )


def _delivered(ts: str, ship: str) -> UnifiedEvent:
    return make_event(
        timestamp=ts, source_system=SourceSystem.TMS,
        event_type=EventType.SHIPMENT_DELIVERED, subject_id=ship,
    )


def _oms_order(ts: str) -> UnifiedEvent:
    return make_event(
        timestamp=ts, source_system=SourceSystem.OMS,
        event_type=EventType.ORDER_PLACED, subject_id="STORE-A",
        attributes={"category": "dairy"},
    )


# --------------------------------------------------------------------------- #
# ReplayEngine on TMS scenario
# --------------------------------------------------------------------------- #

def test_replay_empty_events() -> None:
    rep = ReplayEngine(default_detector()).run([])
    assert rep.n_events == 0
    assert rep.n_findings == 0
    assert rep.total_actual_loss_yuan == 0.0
    assert rep.savings_pct == 0.0


def test_replay_no_findings_no_savings() -> None:
    """Events that produce no anomalies → ¥0 / ¥0."""
    events = [_oms_order("2026-06-15T10:01:00Z")]
    rep = ReplayEngine(default_detector()).run(events)
    assert rep.n_findings == 0
    assert rep.total_savings_yuan == 0.0


def test_replay_tms_scenario_yields_savings() -> None:
    """The textbook TMS replay scenario: 1 finding, expedite_1h recommended."""
    dispatched = _dispatched("2026-06-15T10:00:00Z", "SHIP-X", 4.0)
    delivered = _delivered("2026-06-15T17:00:00Z", "SHIP-X")  # 7h actual
    orders = [
        _oms_order(f"2026-06-15T{10 + (i // 60):02d}:{i % 60:02d}:00Z")
        for i in range(20)
    ]
    rep = ReplayEngine(default_detector()).run([dispatched, delivered] + orders)
    assert rep.n_findings == 1
    assert rep.total_savings_yuan > 0
    # With 20 orders * ~25% stockout * ¥80 + sev 4 → simulate cost is small
    # relative to baseline
    assert rep.savings_pct > 0.5
    # Recommendation should be an expedite intervention, not no_action
    rec = rep.findings[0].recommendation
    assert rec != InterventionKind.NO_ACTION


def test_replay_finding_replay_fields() -> None:
    dispatched = _dispatched("2026-06-15T10:00:00Z", "SHIP-X", 4.0)
    delivered = _delivered("2026-06-15T17:00:00Z", "SHIP-X")
    orders = [
        _oms_order(f"2026-06-15T{10 + (i // 60):02d}:{i % 60:02d}:00Z")
        for i in range(10)
    ]
    rep = ReplayEngine(default_detector()).run([dispatched, delivered] + orders)
    fr = rep.findings[0]
    assert isinstance(fr, FindingReplay)
    assert fr.finding.rule_id == "tms.leadtime.overrun"
    assert fr.actual_loss_yuan > 0
    assert fr.simulated_loss_yuan >= 0
    assert fr.savings_yuan == max(fr.actual_loss_yuan - fr.simulated_loss_yuan, 0)


def test_replay_top_savings_orders_by_amount() -> None:
    """Multiple TMS findings with different severities — top_savings ranks correctly."""
    # Two TMS scenarios: one with many orders, one with few
    events = []
    for ship, n_orders in [("SHIP-A", 30), ("SHIP-B", 5)]:
        events.append(_dispatched("2026-06-15T10:00:00Z", ship, 4.0))
        events.append(_delivered("2026-06-15T17:00:00Z", ship))
        events.extend([
            _oms_order(f"2026-06-15T{10 + (i // 60):02d}:{i % 60:02d}:00Z")
            for i in range(n_orders)
        ])
    rep = ReplayEngine(default_detector()).run(events)
    top = rep.top_savings(3)
    assert len(top) >= 1
    # top_savings is sorted descending by savings
    for a, b in zip(top, top[1:]):
        assert a.savings_yuan >= b.savings_yuan


def test_replay_savings_pct_zero_when_no_actual_loss() -> None:
    """If actual loss is 0 (no actionable findings), savings_pct is 0."""
    rep = ReplayEngine(default_detector()).run([])
    assert rep.savings_pct == 0.0


def test_replay_savings_bounded_at_zero() -> None:
    """savings_yuan never negative — we don't claim we made money vs. baseline."""
    rep = ReplayEngine(default_detector()).run([_oms_order("2026-06-15T10:01:00Z")])
    for fr in rep.findings:
        assert fr.savings_yuan >= 0


# --------------------------------------------------------------------------- #
# load_events_from_json
# --------------------------------------------------------------------------- #

def test_load_events_from_bare_list(tmp_path: Path) -> None:
    payload = [
        {
            "timestamp": "2026-06-15T10:00:00Z",
            "source_system": "OMS",
            "event_type": "ORDER_PLACED",
            "subject_id": "STORE-A",
            "attributes": {"category": "dairy"},
        },
    ]
    p = tmp_path / "events.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    events = load_events_from_json(p)
    assert len(events) == 1
    assert events[0].subject_id == "STORE-A"


def test_load_events_from_wrapped_dict(tmp_path: Path) -> None:
    payload = {"events": [
        {
            "timestamp": "2026-06-15T10:00:00Z",
            "source_system": "WMS",
            "event_type": "TEMPERATURE_READING",
            "subject_id": "S1",
            "value": -12.0,
            "attributes": {"zone": "frozen"},
        },
    ]}
    p = tmp_path / "events.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    events = load_events_from_json(p)
    assert events[0].value == -12.0


def test_load_events_rejects_missing_events_key(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"findings": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_events_from_json(p)


def test_load_events_validates_iso8601(tmp_path: Path) -> None:
    p = tmp_path / "bad_ts.json"
    p.write_text(json.dumps([
        {"timestamp": "not-iso", "source_system": "OMS",
         "event_type": "ORDER_PLACED", "subject_id": "X"},
    ]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_events_from_json(p)


# --------------------------------------------------------------------------- #
# write_replay_report_json
# --------------------------------------------------------------------------- #

def test_write_replay_report_roundtrip(tmp_path: Path) -> None:
    rep = ReplayReport(
        n_events=100, n_findings=2,
        findings=(),
        total_actual_loss_yuan=500.0,
        total_simulated_loss_yuan=100.0,
        total_savings_yuan=400.0,
    )
    p = tmp_path / "report.json"
    write_replay_report_json(rep, p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["n_events"] == 100
    assert data["savings_pct"] == pytest.approx(0.8, abs=1e-4)
    assert data["total_savings_yuan"] == 400.0


def test_write_replay_report_includes_top_savings(tmp_path: Path) -> None:
    """A real FindingReplay should appear in top_savings."""
    f = AnomalyFinding(
        rule_id="tms.leadtime.overrun", subject_id="S",
        timestamp="2026-06-15T10:00:00Z", severity=4, summary="x",
    )
    rep = ReplayReport(
        n_events=10, n_findings=1,
        findings=(FindingReplay(
            finding=f,
            recommendation=InterventionKind.EXPEDITE_1H,
            actual_loss_yuan=100.0,
            simulated_loss_yuan=20.0,
            savings_yuan=80.0,
        ),),
        total_actual_loss_yuan=100.0,
        total_simulated_loss_yuan=20.0,
        total_savings_yuan=80.0,
    )
    p = tmp_path / "report.json"
    write_replay_report_json(rep, p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data["top_savings"]) == 1
    assert data["top_savings"][0]["recommendation"] == "expedite_1h"
    assert data["top_savings"][0]["savings_yuan"] == 80.0