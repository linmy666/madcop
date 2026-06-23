"""WMS mock adapter — cold-chain temperature monitoring.

W1 deliverable: 1 of 4 mock adapters. This one is real-enough to drive a
cold-chain anomaly demo. Future weeks add OMS, TMS, BMS as separate files
following the same shape.

The "data" is hardcoded. That's intentional — a real wire adapter would swap
`fetch()` for an HTTP call, but the **shape** is what the framework depends
on, and the shape lives in `BaseAdapter`.

Scenario: a 冷链 (cold-chain) shipment from 广州仓 → 上海仓 on 2026-06-15.
- 08:00 dispatch, setpoint -18°C
- 12:00 routine reading, -17.8°C
- 14:30 reading: -14.2°C (!!! threshold breach, severity 4)
- 15:00 reading: -13.8°C
- 15:30 reading: -17.5°C (recovered — driver opened the door, not equipment)
- 18:42 delivered, last reading -17.6°C
"""

from __future__ import annotations

from typing import Iterator

from ..event import EventType, SourceSystem, UnifiedEvent, make_event
from .base import Action, BaseAdapter, UnsupportedActionError


class WMSAdapter(BaseAdapter):
    """WMS adapter (mock). Cold-chain temperature stream for one shipment."""

    source_system = SourceSystem.WMS

    # Cold-chain threshold, in °C. Anything above this for any reading is
    # an anomaly. We hardcode it here; in a real adapter it would come from
    # the WMS product master.
    COLD_CHAIN_THRESHOLD_C = -15.0

    def __init__(self, shipment_id: str = "SHIP-2026-0615-CG-SH"):
        self.shipment_id = shipment_id

    def fetch(
        self,
        *,
        since: str | None = None,
        subject_id: str | None = None,
    ) -> Iterator[UnifiedEvent]:
        # The data: a single shipment's temperature stream.
        # In a real adapter this would come from `requests.get(...)` or a DB
        # query. Here it's a static list so the demo is reproducible.
        raw = [
            # (timestamp,           value,  severity,  attributes)
            ("2026-06-15T08:00:00Z", -18.0, 1, {"setpoint_c": -18.0, "phase": "dispatch"}),
            ("2026-06-15T12:00:00Z", -17.8, 1, {"setpoint_c": -18.0, "phase": "in_transit"}),
            ("2026-06-15T14:30:00Z", -14.2, 4, {"setpoint_c": -18.0, "phase": "in_transit",
                                                "note": "threshold breach"}),
            ("2026-06-15T15:00:00Z", -13.8, 5, {"setpoint_c": -18.0, "phase": "in_transit",
                                                "note": "still rising"}),
            ("2026-06-15T15:30:00Z", -17.5, 1, {"setpoint_c": -18.0, "phase": "in_transit",
                                                "note": "recovered — door opened at 15:25"}),
            ("2026-06-15T18:42:00Z", -17.6, 1, {"setpoint_c": -18.0, "phase": "delivered"}),
        ]
        for ts, value, sev, attrs in raw:
            if subject_id and subject_id != self.shipment_id:
                continue
            yield make_event(
                timestamp=ts,
                source_system=SourceSystem.WMS,
                event_type=EventType.TEMPERATURE_READING,
                subject_id=self.shipment_id,
                value=value,
                attributes=attrs,
                severity=sev,
            )

    def execute(self, action: Action) -> dict:
        # WMS can mark exceptions, request re-icing, dispatch a recovery team.
        # Anything else is out of scope.
        supported = {"mark_exception", "request_re_ice", "dispatch_recovery"}
        if action.action_type not in supported:
            raise UnsupportedActionError(
                f"WMSAdapter does not support action {action.action_type!r}; "
                f"supported: {sorted(supported)}"
            )
        # Mock: just echo.
        return {
            "ok": True,
            "system": "wms",
            "action": action.action_type,
            "subject_id": action.subject_id,
            "parameters": dict(action.parameters),
        }

    def health_check(self) -> bool:
        return True
