"""Tests for the multi-zone WMS adapter (v0.2)."""

from __future__ import annotations

import pytest

from madcop.adapters.wms import TempZone, WMSAdapter
from madcop.anomaly.rules import ColdChainTemperatureRule
from madcop.event import EventType, SourceSystem, UnifiedEvent, make_event


# --------------------------------------------------------------------------- #
# TempZone band correctness
# --------------------------------------------------------------------------- #

def test_frozen_band_is_below_zero() -> None:
    low, high = TempZone.FROZEN.band
    assert high < 0


def test_refrigerated_band_is_above_zero() -> None:
    low, high = TempZone.REFRIGERATED.band
    assert low > 0
    assert high < 10


def test_controlled_band_is_room_temperature() -> None:
    low, high = TempZone.CONTROLLED.band
    assert 10 < low < high < 30


def test_all_zones_have_non_empty_bands() -> None:
    for z in TempZone:
        low, high = z.band
        assert low < high, f"{z} has invalid band {low},{high}"


# --------------------------------------------------------------------------- #
# WMSAdapter — multi-zone streams
# --------------------------------------------------------------------------- #

def test_wms_adapter_classifies_frozen_shipment() -> None:
    a = WMSAdapter("SHIP-2026-0615-CG-SH")
    assert a.zone() == TempZone.FROZEN


def test_wms_adapter_classifies_refrigerated_shipment() -> None:
    a = WMSAdapter("SHIP-2026-0616-DR-2-SH")
    assert a.zone() == TempZone.REFRIGERATED


def test_wms_adapter_classifies_controlled_shipment() -> None:
    a = WMSAdapter("SHIP-2026-0617-CH-1-HZ")
    assert a.zone() == TempZone.CONTROLLED


def test_wms_adapter_emits_zone_attribute() -> None:
    events = list(WMSAdapter("SHIP-2026-0616-DR-2-SH").fetch())
    assert all(e.attributes.get("zone") == "refrigerated" for e in events)
    bands = {tuple(e.attributes["band_c"]) for e in events}
    assert (2.0, 8.0) in bands


def test_wms_adapter_dairy_breach_at_9_5c() -> None:
    # 9.5°C is above the refrigerated band (high=8.0)
    rule = ColdChainTemperatureRule()
    breaches = []
    for e in WMSAdapter("SHIP-2026-0616-DR-2-SH").fetch():
        f = rule.evaluate(e)
        if f is not None:
            breaches.append(f)
    assert len(breaches) == 2  # 9.5°C (sev4) and 10.2°C (sev5)
    assert all("refrigerated" in b.summary for b in breaches)
    assert all(b.details["direction"] == "above" for b in breaches)


def test_wms_adapter_chocolate_below_band_fires_with_below_direction() -> None:
    rule = ColdChainTemperatureRule()
    breaches = []
    for e in WMSAdapter("SHIP-2026-0617-CH-1-HZ").fetch():
        f = rule.evaluate(e)
        if f is not None:
            breaches.append(f)
    assert len(breaches) == 2  # 13.0°C and 12.5°C, both below band [15, 25]
    assert all(b.details["direction"] == "below" for b in breaches)
    assert all(b.details["zone"] == "controlled" for b in breaches)


# --------------------------------------------------------------------------- #
# Backwards compat — the W1 frozen demo still works
# --------------------------------------------------------------------------- #

def test_wms_default_shipment_is_frozen_and_has_breaches() -> None:
    rule = ColdChainTemperatureRule()
    findings = [rule.evaluate(e) for e in WMSAdapter().fetch()]
    findings = [f for f in findings if f is not None]
    # 2 single-reading breaches (14:30 and 15:00) + 1 sustained (14:30..15:00)
    # The instant rule alone fires 2.
    assert len(findings) >= 2
    assert any(f.details.get("reading_c", 0) > -15 for f in findings)
