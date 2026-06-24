"""Tests for the LangGraph orchestration."""

from __future__ import annotations

import pytest

from madcop.adapters.wms import WMSAdapter
from madcop.agent import MadcopState, build_graph, run_agent
from madcop.anomaly.detector import AnomalyFinding
from madcop.anomaly.rules import default_detector
from madcop.event import (
    EventType, SourceSystem, UnifiedEvent, make_event,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _finding(rule_id: str, subject_id: str, ts: str, severity: int) -> AnomalyFinding:
    return AnomalyFinding(
        rule_id=rule_id, subject_id=subject_id, timestamp=ts,
        severity=severity, summary=f"test {rule_id}",
    )


def _oms_order(ts: str) -> UnifiedEvent:
    return make_event(
        timestamp=ts, source_system=SourceSystem.OMS,
        event_type=EventType.ORDER_PLACED, subject_id="STORE-A",
        attributes={"category": "default"},
    )


# --------------------------------------------------------------------------- #
# Node tests
# --------------------------------------------------------------------------- #

def test_ingest_sorts_events_by_timestamp() -> None:
    from madcop.agent.graph import ingest_events
    e1 = _oms_order("2026-06-15T10:00:00Z")
    e2 = _oms_order("2026-06-15T09:00:00Z")
    e3 = _oms_order("2026-06-15T11:00:00Z")
    out = ingest_events({"events": [e1, e2, e3]})
    assert [e.parsed_timestamp for e in out["events"]] == sorted(
        e.parsed_timestamp for e in [e1, e2, e3]
    )


def test_maybe_replan_no_anomaly() -> None:
    from madcop.agent.graph import maybe_replan
    out = maybe_replan({"findings": [_finding("wms.coldchain.temperature_breach", "S1", "2026-06-15T10:00:00Z", 4)]})
    assert out["replan_triggered"] is False
    assert out["new_safety_stock"] == 0.0


def test_maybe_replan_with_oms_spike() -> None:
    from madcop.agent.graph import maybe_replan
    out = maybe_replan({
        "findings": [_finding("oms.cancellation.spike", "STORE-X", "2026-06-15T10:00:00Z", 4)],
    })
    assert out["replan_triggered"] is True
    assert out["new_safety_stock"] > 0
    assert out["new_safety_stock_sku"] == "STORE-X"


def test_summarise_aggregates_counts() -> None:
    from madcop.agent.graph import summarise
    out = summarise({
        "findings": [
            _finding("a", "X", "2026-06-15T10:00:00Z", 5),
            _finding("b", "Y", "2026-06-15T10:00:00Z", 5),
            _finding("c", "Z", "2026-06-15T10:00:00Z", 4),
            _finding("d", "W", "2026-06-15T10:00:00Z", 3),
        ],
        "replan_triggered": False,
        "counterfactual_results": [],
    })
    assert "4 anomaly" in out["summary"]
    assert "2 sev5" in out["summary"]
    assert "1 sev4" in out["summary"]


# --------------------------------------------------------------------------- #
# Graph tests
# --------------------------------------------------------------------------- #

def test_build_graph_returns_compiled() -> None:
    graph = build_graph(default_detector())
    # CompiledStateGraph exposes .invoke; check it's callable
    assert callable(graph.invoke)


def test_graph_runs_on_empty_events() -> None:
    graph = build_graph(default_detector())
    out = graph.invoke({"events": []})
    assert out["findings"] == []
    assert out["replan_triggered"] is False
    assert "0 anomaly" in out["summary"]


def test_graph_runs_on_wms_stream() -> None:
    """End-to-end with the default WMSAdapter seed."""
    events = sorted(WMSAdapter().fetch(), key=lambda e: e.parsed_timestamp)
    out = run_agent(events, default_detector())
    # Default seed has temperature breaches → some WMS findings
    assert len(out["findings"]) > 0
    assert isinstance(out["summary"], str)


def test_graph_handles_oms_anomaly() -> None:
    """Synthetic OMS cancellation spike → replan should fire."""
    # 30 cancels in a row (above pharma baseline 0.02)
    events = [
        make_event(
            timestamp=f"2026-06-15T10:{(i // 60) + 1:02d}:{i % 60:02d}Z",
            source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_CANCELLED,
            subject_id="STORE-A",
            attributes={"category": "pharma"},
        )
        for i in range(30)
    ]
    out = run_agent(events, default_detector())
    assert out["replan_triggered"] is True
    assert out["new_safety_stock"] > 0


def test_graph_handles_tms_anomaly_for_counterfactual() -> None:
    """Synthetic TMS finding + orders → counterfactual node returns results."""
    finding = _finding("tms.leadtime.overrun", "SHIP-X", "2026-06-15T10:00:00Z", 4)
    # The graph only runs findings detected from the stream, so we need to
    # feed events that the detector will recognise. We call counterfactual_node
    # directly to verify it runs all 5 canned interventions when given a TMS finding.
    from madcop.agent.graph import counterfactual_node
    cf_state = counterfactual_node(
        {"events": [], "findings": [finding]},
        engine=None,
    )
    # Empty events → default rate kicks in → all 5 interventions evaluated
    assert len(cf_state["counterfactual_results"]) == 5  # 5 canned interventions


def test_graph_summary_recommends_action_on_tms() -> None:
    """If counterfactual node yields results, summary should name an action."""
    from madcop.counterfactual import (
        CANNED_INTERVENTIONS, CounterfactualOutcome, InterventionKind,
    )
    from madcop.agent.graph import summarise
    outcome = CounterfactualOutcome(
        intervention=CANNED_INTERVENTIONS[InterventionKind.EXPEDITE_1H],
        baseline_total_yuan=200.0,
        intervention_total_yuan=120.0,
        delta_yuan=-80.0,
        baseline_breakdown=(),
        intervention_breakdown=(),
        assumptions=(),
    )
    out = summarise({
        "findings": [_finding("tms.leadtime.overrun", "SHIP-1", "2026-06-15T10:00:00Z", 4)],
        "replan_triggered": False,
        "counterfactual_results": [outcome],
    })
    assert "expedite_1h" in out["summary"]