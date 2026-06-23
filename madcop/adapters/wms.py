"""WMS mock adapter — multi-zone temperature monitoring.

This is the v0.2 of the WMS adapter. The v0.1 (W1) only supported frozen
(-18°C) shipments, which the supply-chain domain expert flagged as
"covering ~30% of real cold-chain scenarios." v0.2 adds **explicit
temperature zones** with zone-specific thresholds, matching what a real
WMS product master would carry.

Zones (drawn from the GxP / WHO TRS 961 / 食品冷链通则 vocabulary):

    FROZEN       <-25°C..-15°C  (ice cream, frozen meat, vaccines)
    REFRIGERATED  +2°C.. +8°C   (dairy, fresh meat, fruit, vegetables)
    CONTROLLED   +15°C..+25°C  (chocolate, candy, ambient pharma)
    AMBIENT       -5°C..+30°C  (no active control; monitor only)

Note: zone **range** is a target band; an alarm fires when the reading
leaves the band, not when it crosses a single threshold. This is the
correct model — a single-threshold rule treats "too cold" and "too warm"
as the same alarm, which is wrong (a -20°C reading in a +4°C dairy
shipment is a *worse* problem than -16°C; both would alarm under
"any value > -15" but the first one is a frozen-product crisis).
"""

from __future__ import annotations

from enum import Enum
from typing import Iterator

from ..event import EventType, SourceSystem, UnifiedEvent, make_event
from .base import Action, BaseAdapter, UnsupportedActionError


class TempZone(str, Enum):
    """A controlled-temperature band defined by a real WMS product master."""
    FROZEN = "frozen"             # e.g. -18°C
    REFRIGERATED = "refrigerated" # e.g. +4°C
    CONTROLLED = "controlled"     # e.g. +20°C
    AMBIENT = "ambient"            # no active control

    @property
    def band(self) -> tuple[float, float]:
        """(low_c, high_c). A reading inside the band is in-spec; outside is not."""
        return _BANDS[self]


_BANDS: dict[TempZone, tuple[float, float]] = {
    TempZone.FROZEN:       (-25.0, -15.0),
    TempZone.REFRIGERATED: (  2.0,   8.0),
    TempZone.CONTROLLED:   ( 15.0,  25.0),
    TempZone.AMBIENT:      ( -5.0,  30.0),
}


# A demo shipment per zone, with realistic event streams showing in-spec,
# breach, and recovery. The frozen one is the same as v0.1 for backwards
# compat with the existing RCA demo.
_DEMO_STREAMS: dict[str, list[tuple[str, float, int, dict]]] = {
    "SHIP-2026-0615-CG-SH": [
        # frozen: setpoint -18°C, two breaches at 14:30 and 15:00
        ("2026-06-15T08:00:00Z", -18.0, 1, {"phase": "dispatch"}),
        ("2026-06-15T12:00:00Z", -17.8, 1, {"phase": "in_transit"}),
        ("2026-06-15T14:30:00Z", -14.2, 4, {"phase": "in_transit", "note": "above band"}),
        ("2026-06-15T15:00:00Z", -13.8, 5, {"phase": "in_transit", "note": "above band, rising"}),
        ("2026-06-15T15:30:00Z", -17.5, 1, {"phase": "in_transit", "note": "recovered"}),
        ("2026-06-15T18:42:00Z", -17.6, 1, {"phase": "delivered"}),
    ],
    "SHIP-2026-0616-DR-2-SH": [
        # dairy/refrigerated: setpoint +4°C, breach up to 9.5°C at 11:00
        ("2026-06-16T06:00:00Z",   4.0, 1, {"phase": "dispatch"}),
        ("2026-06-16T09:30:00Z",   4.3, 1, {"phase": "in_transit"}),
        ("2026-06-16T11:00:00Z",   9.5, 4, {"phase": "in_transit", "note": "refrigeration cycle off"}),
        ("2026-06-16T11:30:00Z",  10.2, 5, {"phase": "in_transit", "note": "still rising"}),
        ("2026-06-16T12:15:00Z",   6.8, 3, {"phase": "in_transit", "note": "recovering"}),
        ("2026-06-16T15:40:00Z",   4.1, 1, {"phase": "delivered"}),
    ],
    "SHIP-2026-0617-CH-1-HZ": [
        # chocolate/controlled: setpoint +20°C, breach to +13°C
        ("2026-06-17T07:00:00Z",  20.5, 1, {"phase": "dispatch"}),
        ("2026-06-17T10:00:00Z",  20.1, 1, {"phase": "in_transit"}),
        ("2026-06-17T13:30:00Z",  13.0, 4, {"phase": "in_transit", "note": "AC failure"}),
        ("2026-06-17T14:00:00Z",  12.5, 5, {"phase": "in_transit", "note": "still falling"}),
        ("2026-06-17T15:00:00Z",  17.2, 2, {"phase": "in_transit", "note": "recovering"}),
        ("2026-06-17T18:00:00Z",  20.0, 1, {"phase": "delivered"}),
    ],
}


class WMSAdapter(BaseAdapter):
    """WMS adapter (mock). Multi-zone temperature stream across shipments.

    The default constructor returns the W1 frozen shipment so the existing
    RCA demo still works unchanged. Pass a different `shipment_id` to read
    a different zone's stream.
    """

    source_system = SourceSystem.WMS

    # Backwards-compat alias for v0.1 callers. New code should use TempZone.
    COLD_CHAIN_THRESHOLD_C = -15.0

    def __init__(self, shipment_id: str = "SHIP-2026-0615-CG-SH"):
        self.shipment_id = shipment_id

    def zone(self) -> TempZone | None:
        """Infer the zone from the shipment id (v0.2 seed only)."""
        sid = self.shipment_id
        if "CG" in sid or "FZ" in sid:
            return TempZone.FROZEN
        if "DR" in sid:
            return TempZone.REFRIGERATED
        if "CH" in sid:
            return TempZone.CONTROLLED
        if "AM" in sid:
            return TempZone.AMBIENT
        return None

    def fetch(
        self,
        *,
        since: str | None = None,
        subject_id: str | None = None,
    ) -> Iterator[UnifiedEvent]:
        # Use the requested subject_id, or fall back to our default
        sid = subject_id or self.shipment_id
        raw = _DEMO_STREAMS.get(sid, [])
        zone = self.zone() if sid == self.shipment_id else None
        for ts, value, sev, attrs in raw:
            enriched = dict(attrs)
            if zone is not None:
                enriched["zone"] = zone.value
                enriched["band_c"] = list(zone.band)
            yield make_event(
                timestamp=ts,
                source_system=SourceSystem.WMS,
                event_type=EventType.TEMPERATURE_READING,
                subject_id=sid,
                value=value,
                attributes=enriched,
                severity=sev,
            )

    def execute(self, action: Action) -> dict:
        supported = {"mark_exception", "request_re_ice", "dispatch_recovery",
                    "mark_refrigeration_failure", "dispatch_reefer_tech"}
        if action.action_type not in supported:
            raise UnsupportedActionError(
                f"WMSAdapter does not support action {action.action_type!r}; "
                f"supported: {sorted(supported)}"
            )
        return {
            "ok": True,
            "system": "wms",
            "action": action.action_type,
            "subject_id": action.subject_id,
            "parameters": dict(action.parameters),
        }

    def health_check(self) -> bool:
        return True
