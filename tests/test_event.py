"""Tests for L1 — unified event + adapter contract.

Why this file is the most important one in W1:
`UnifiedEvent` is the contract. Every later module (rules, RCA, counterfactual,
LangGraph state) trusts its invariants. A bug here cascades.
"""

from __future__ import annotations

import pytest

from madcop.event import (
    EventType,
    SourceSystem,
    UnifiedEvent,
    make_event,
)
from madcop.adapters.base import Action, BaseAdapter, UnsupportedActionError
from madcop.adapters.wms import WMSAdapter


# --------------------------------------------------------------------------- #
# UnifiedEvent — invariants
# --------------------------------------------------------------------------- #

def test_unified_event_accepts_utc_z_suffix() -> None:
    e = make_event(
        timestamp="2026-06-15T08:00:00Z",
        source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING,
        subject_id="SHIP-1",
        value=-18.0,
    )
    assert e.timestamp == "2026-06-15T08:00:00Z"


def test_unified_event_accepts_utc_offset() -> None:
    e = make_event(
        timestamp="2026-06-15T08:00:00+00:00",
        source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING,
        subject_id="SHIP-1",
        value=-18.0,
    )
    assert e.parsed_timestamp.tzinfo is not None


def test_unified_event_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="must be UTC"):
        make_event(
            timestamp="2026-06-15T08:00:00",
            source_system=SourceSystem.WMS,
            event_type=EventType.TEMPERATURE_READING,
            subject_id="SHIP-1",
        )


def test_unified_event_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="must be UTC"):
        make_event(
            timestamp="2026-06-15T08:00:00+08:00",  # Shanghai, not UTC
            source_system=SourceSystem.WMS,
            event_type=EventType.TEMPERATURE_READING,
            subject_id="SHIP-1",
        )


def test_unified_event_rejects_mismatched_event_type() -> None:
    # ORDER_PLACED is an OMS event, not WMS.
    with pytest.raises(ValueError, match="not valid for source_system"):
        make_event(
            timestamp="2026-06-15T08:00:00Z",
            source_system=SourceSystem.WMS,
            event_type=EventType.ORDER_PLACED,
            subject_id="ORD-1",
        )


def test_unified_event_rejects_out_of_range_severity() -> None:
    with pytest.raises(ValueError, match="severity"):
        make_event(
            timestamp="2026-06-15T08:00:00Z",
            source_system=SourceSystem.WMS,
            event_type=EventType.TEMPERATURE_READING,
            subject_id="SHIP-1",
            severity=6,
        )


def test_unified_event_is_frozen() -> None:
    e = make_event(
        timestamp="2026-06-15T08:00:00Z",
        source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING,
        subject_id="SHIP-1",
    )
    with pytest.raises(Exception):  # FrozenInstanceError is a subclass of AttributeError
        e.subject_id = "TAMPERED"  # type: ignore[misc]


def test_source_system_parse_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown source system"):
        SourceSystem.parse("elasticsearch")


# --------------------------------------------------------------------------- #
# WMSAdapter — the W1 deliverable
# --------------------------------------------------------------------------- #

def test_wms_adapter_source_system() -> None:
    assert WMSAdapter().source_system == SourceSystem.WMS


def test_wms_adapter_yields_cold_chain_stream() -> None:
    events = list(WMSAdapter().fetch())
    assert len(events) == 6
    for e in events:
        assert e.source_system == SourceSystem.WMS
        assert e.event_type == EventType.TEMPERATURE_READING
        assert e.subject_id == "SHIP-2026-0615-CG-SH"


def test_wms_adapter_marks_breach_with_severity_4_or_5() -> None:
    events = list(WMSAdapter().fetch())
    breaches = [e for e in events if e.value is not None and e.value > WMSAdapter.COLD_CHAIN_THRESHOLD_C]
    assert len(breaches) == 2
    assert {b.severity for b in breaches} == {4, 5}


def test_wms_adapter_filter_by_subject_id() -> None:
    events = list(WMSAdapter().fetch(subject_id="OTHER-SHIPMENT"))
    assert events == []


def test_wms_adapter_filter_by_subject_id_match() -> None:
    events = list(WMSAdapter().fetch(subject_id="SHIP-2026-0615-CG-SH"))
    assert len(events) == 6


def test_wms_adapter_execute_supported_action() -> None:
    out = WMSAdapter().execute(Action(
        target_system=SourceSystem.WMS,
        action_type="mark_exception",
        subject_id="SHIP-1",
        parameters={"reason": "temperature breach"},
    ))
    assert out["ok"] is True
    assert out["action"] == "mark_exception"


def test_wms_adapter_rejects_unsupported_action() -> None:
    with pytest.raises(UnsupportedActionError):
        WMSAdapter().execute(Action(
            target_system=SourceSystem.WMS,
            action_type="sign_contract",  # this is a BMS action, not WMS
            subject_id="CONTRACT-1",
            parameters={},
        ))


def test_wms_adapter_is_a_base_adapter() -> None:
    # Structural check — adapters must satisfy the contract.
    assert isinstance(WMSAdapter(), BaseAdapter)
