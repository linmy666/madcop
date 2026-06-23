"""L1 — Unified data layer.

Every event from every system (OMS / TMS / WMS / BMS) is normalized to
`UnifiedEvent` before reaching the rest of the framework. This file is the
contract — adapters translate, anomaly rules read, LangGraph state holds.

Design choices, briefly justified:

- `timestamp` is **UTC ISO 8601**. Mixed timezones are a top-3 supply chain
  integration bug. We refuse to be flexible here.
- `source_system` is a free string but we expose the enum `SourceSystem` for
  the four systems we ship adapters for. New systems just add an enum value.
- `subject_id` is the join key — SKU / order id / shipment id / contract id.
  It carries the **same** identity across systems when a single business
  object spans multiple systems (e.g. an order in OMS that creates a shipment
  in TMS that flows into a warehouse in WMS).
- `value` is numeric because every rule we ship is numeric (temperature,
  lead_time_hours, fill_rate, etc). Free-form text lives in `attributes`.
- `severity` is set by the **adapter**, not by the rule. The adapter knows
  the source system's own severity model. Rules add their own
  `AnomalyFinding.severity` on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class SourceSystem(str, Enum):
    OMS = "oms"  # Order Management System — 订单
    TMS = "tms"  # Transport Management System — 运输
    WMS = "wms"  # Warehouse Management System — 仓
    BMS = "bms"  # Business Management System — 合同/供应商/财务

    @classmethod
    def parse(cls, raw: str) -> "SourceSystem":
        try:
            return cls(raw.lower())
        except ValueError as e:
            raise ValueError(
                f"unknown source system: {raw!r}; expected one of {[s.value for s in cls]}"
            ) from e


# A loose taxonomy of event kinds. Adapters pick one that fits.
# Rules are written against these names.
class EventType(str, Enum):
    # OMS
    ORDER_PLACED = "order.placed"
    ORDER_CANCELLED = "order.cancelled"
    # TMS
    SHIPMENT_DISPATCHED = "shipment.dispatched"
    SHIPMENT_DELIVERED = "shipment.delivered"
    SHIPMENT_DELAYED = "shipment.delayed"
    # WMS
    TEMPERATURE_READING = "wms.temperature"
    INBOUND_RECEIVED = "wms.inbound"
    OUTBOUND_DISPATCHED = "wms.outbound"
    # BMS
    CONTRACT_SIGNED = "bms.contract.signed"
    SUPPLIER_SCORED = "bms.supplier.scored"


_VALID_EVENT_TYPES: dict[SourceSystem, set[EventType]] = {
    SourceSystem.OMS: {EventType.ORDER_PLACED, EventType.ORDER_CANCELLED},
    SourceSystem.TMS: {
        EventType.SHIPMENT_DISPATCHED,
        EventType.SHIPMENT_DELIVERED,
        EventType.SHIPMENT_DELAYED,
    },
    SourceSystem.WMS: {
        EventType.TEMPERATURE_READING,
        EventType.INBOUND_RECEIVED,
        EventType.OUTBOUND_DISPATCHED,
    },
    SourceSystem.BMS: {EventType.CONTRACT_SIGNED, EventType.SUPPLIER_SCORED},
}


@dataclass(frozen=True)
class UnifiedEvent:
    """The lingua franca. Adapters produce these; the rest of the framework consumes them.

    Frozen so that adapters cannot accidentally mutate events after creation —
    the LangGraph state depends on event immutability for reproducible traces.
    """

    timestamp: str                            # UTC ISO 8601
    source_system: SourceSystem
    event_type: EventType
    subject_id: str                           # join key (SKU / order / shipment / contract)
    value: float | None                       # numeric measurement
    attributes: Mapping[str, Any] = field(default_factory=dict)
    severity: int = 1                         # 1=info, 5=critical, set by adapter
    id: str | None = None                     # optional upstream id, for tracing

    def __post_init__(self) -> None:
        # Validate timestamp is ISO 8601 UTC.
        # We accept both "Z" suffix and explicit "+00:00".
        ts = self.timestamp
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(ts)
        except ValueError as e:
            raise ValueError(f"timestamp must be ISO 8601, got {self.timestamp!r}") from e
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError(
                f"timestamp must be UTC, got {self.timestamp!r}. "
                "Convert with .astimezone(timezone.utc) before constructing."
            )
        # Validate event_type belongs to source_system
        allowed = _VALID_EVENT_TYPES[self.source_system]
        if self.event_type not in allowed:
            raise ValueError(
                f"event_type {self.event_type.value!r} is not valid for "
                f"source_system {self.source_system.value!r}. "
                f"Allowed: {sorted(e.value for e in allowed)}"
            )
        if not 1 <= self.severity <= 5:
            raise ValueError(f"severity must be 1..5, got {self.severity}")

    @property
    def parsed_timestamp(self) -> datetime:
        """Return the timestamp as a tz-aware UTC datetime."""
        ts = self.timestamp[:-1] + "+00:00" if self.timestamp.endswith("Z") else self.timestamp
        return datetime.fromisoformat(ts)


def make_event(
    *,
    timestamp: str,
    source_system: SourceSystem | str,
    event_type: EventType | str,
    subject_id: str,
    value: float | None = None,
    attributes: Mapping[str, Any] | None = None,
    severity: int = 1,
    id: str | None = None,
) -> UnifiedEvent:
    """Convenience constructor that accepts strings for the enums.

    Use this from adapters that parse external data; use the dataclass directly
    in tests for clarity.
    """
    ss = source_system if isinstance(source_system, SourceSystem) else SourceSystem.parse(source_system)
    et = event_type if isinstance(event_type, EventType) else EventType(event_type)
    return UnifiedEvent(
        timestamp=timestamp,
        source_system=ss,
        event_type=et,
        subject_id=subject_id,
        value=value,
        attributes=attributes or {},
        severity=severity,
        id=id,
    )
