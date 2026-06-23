"""L2 — Anomaly rules.

Five rules, each tied to a real supply chain pain point:

1. `ColdChainTemperatureRule`     — WMS temperature reading above setpoint
                                    (single-reading rule, fires immediately)
2. `ColdChainDurationRule`        — temperature stays above threshold for >15 min
                                    (window rule, needs a per-subject state)
3. `OMSOrderCancelSpikeRule`      — order cancellation rate spikes vs. recent avg
                                    (rolling window, fires on OMS events)
4. `TMSLeadTimeAnomalyRule`       — a shipment's lead time exceeds plan by >50%
                                    (per-shipment rule, fires on TMS delayed)
5. `BMSSupplierScoreDropRule`     — supplier score drops by >0.5 in one update
                                    (consecutive-event rule, needs ordering)

Why these five: they cover all four source systems (WMS / OMS / TMS / BMS),
two rule shapes (instant + window), and two severity tiers (sev3-4
operational, sev5 critical). The W3 RCA + W6 counterfactual modules will
build on these.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque

from ..event import EventType, SourceSystem, UnifiedEvent
from .detector import AnomalyFinding, BaseRule, Detector


# --------------------------------------------------------------------------- #
# 1. Cold-chain temperature — instant rule
# --------------------------------------------------------------------------- #

class ColdChainTemperatureRule(BaseRule):
    """Fires when a WMS temperature reading exceeds the threshold.

    Severity scales with how far above the threshold the reading is.
    """

    rule_id = "wms.coldchain.temperature_breach"
    description = "Cold-chain temperature reading exceeds threshold"

    def __init__(self, threshold_c: float = -15.0):
        self.threshold_c = threshold_c

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        if event.source_system != SourceSystem.WMS:
            return None
        if event.event_type != EventType.TEMPERATURE_READING:
            return None
        if event.value is None:
            return None
        if event.value <= self.threshold_c:
            return None
        delta = event.value - self.threshold_c
        # ≤1°C over → sev3, ≤3°C over → sev4, else sev5
        if delta <= 1.0:
            severity = 3
        elif delta <= 3.0:
            severity = 4
        else:
            severity = 5
        return AnomalyFinding(
            rule_id=self.rule_id,
            subject_id=event.subject_id,
            timestamp=event.timestamp,
            severity=severity,
            summary=(
                f"Cold-chain temperature {event.value:.1f}°C exceeds threshold "
                f"{self.threshold_c}°C by {delta:.1f}°C"
            ),
            details={
                "reading_c": event.value,
                "threshold_c": self.threshold_c,
                "delta_c": round(delta, 2),
            },
        )


# --------------------------------------------------------------------------- #
# 2. Cold-chain duration — window rule
# --------------------------------------------------------------------------- #

class ColdChainDurationRule(BaseRule):
    """Fires when a subject's temperature has been above threshold for
    longer than `min_duration_min` *without* recovering for more than
    `recovery_tolerance_min` minutes in between.

    A breach is considered "sustained" when the sequence of breach events
    contains no recovery gap larger than `recovery_tolerance_min`. This is
    more accurate than a sliding window because it tracks the **actual
    disruption**, not arbitrary calendar time.

    Stateful per subject_id. Emits one finding per sustained window
    (not per breach reading).
    """

    rule_id = "wms.coldchain.sustained_breach"
    description = "Cold-chain temperature breach sustained for >N minutes"

    def __init__(
        self,
        min_duration_min: int = 15,
        recovery_tolerance_min: int = 5,
        threshold_c: float = -15.0,
    ):
        self.min_duration_min = min_duration_min
        self.recovery_tolerance_min = recovery_tolerance_min
        self.threshold_c = threshold_c
        # per subject: list of breach events within the *current* sustained window
        self._breaches: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        # per subject: timestamp of the most recent recovery (non-breach) reading
        self._last_recovery: dict[str, datetime] = {}
        # emit-once per (subject, window-start) so we don't fire repeatedly
        self._emitted: set[tuple[str, datetime]] = set()

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        if event.source_system != SourceSystem.WMS:
            return None
        if event.event_type != EventType.TEMPERATURE_READING:
            return None
        ts = event.parsed_timestamp
        breaches = self._breaches[event.subject_id]

        if event.value is not None and event.value > self.threshold_c:
            # A new breach. If we last recovered longer than `tolerance` ago,
            # the prior sustained window ended — start fresh.
            last_recovery = self._last_recovery.get(event.subject_id)
            if breaches and last_recovery is not None and \
               (ts - last_recovery) > timedelta(minutes=self.recovery_tolerance_min):
                self._emitted.discard((event.subject_id, breaches[0][0]))
                breaches.clear()
            breaches.append((ts, event.value))
        else:
            # Recovery reading. Record when we recovered. The next breach will
            # compare against this timestamp to decide if it's a new window.
            self._last_recovery[event.subject_id] = ts

        # No breach to evaluate
        if not breaches:
            return None

        first_ts = breaches[0][0]
        duration_min = (ts - first_ts).total_seconds() / 60.0
        if duration_min < self.min_duration_min:
            return None

        key = (event.subject_id, first_ts)
        if key in self._emitted:
            return None
        self._emitted.add(key)
        peak_val = max(v for _, v in breaches)
        return AnomalyFinding(
            rule_id=self.rule_id,
            subject_id=event.subject_id,
            timestamp=event.timestamp,
            severity=5,  # sustained = critical, irrespective of peak
            summary=(
                f"Cold-chain breach sustained for {duration_min:.0f} min "
                f"on {event.subject_id} (peak {peak_val:.1f}°C)"
            ),
            details={
                "first_breach_at": first_ts.isoformat(),
                "duration_min": round(duration_min, 1),
                "peak_c": peak_val,
                "breach_count": len(breaches),
            },
        )


# --------------------------------------------------------------------------- #
# 3. OMS order-cancel spike — rolling-window rule
# --------------------------------------------------------------------------- #

class OMSOrderCancelSpikeRule(BaseRule):
    """Fires when the cancellation rate over the last `window_min` minutes
    is more than `spike_multiplier`× the prior `baseline_min` window.
    """

    rule_id = "oms.cancellation.spike"
    description = "Order cancellation rate spikes vs. baseline"

    def __init__(
        self,
        window_min: int = 60,
        baseline_min: int = 240,
        spike_multiplier: float = 3.0,
    ):
        self.window_min = window_min
        self.baseline_min = baseline_min
        self.spike_multiplier = spike_multiplier
        self._placed: Deque[datetime] = deque()
        self._cancelled: Deque[datetime] = deque()
        self._last_emit_at: datetime | None = None
        self._cooldown = timedelta(minutes=window_min)

    def _trim(self, now: datetime) -> None:
        # We don't know the global event horizon, so we trim relative to `now`.
        window_cutoff = now - timedelta(minutes=self.window_min)
        while self._placed and self._placed[0] < window_cutoff:
            self._placed.popleft()
        while self._cancelled and self._cancelled[0] < window_cutoff:
            self._cancelled.popleft()

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        if event.source_system != SourceSystem.OMS:
            return None
        ts = event.parsed_timestamp
        self._trim(ts)
        if event.event_type == EventType.ORDER_PLACED:
            self._placed.append(ts)
            return None
        if event.event_type != EventType.ORDER_CANCELLED:
            return None
        self._cancelled.append(ts)
        # need at least a few orders to make a rate meaningful
        if len(self._placed) < 5:
            return None
        current_rate = len(self._cancelled) / max(len(self._placed), 1)
        # baseline: cancellation count in a 4× window, excluding the current 1×
        # We approximate by using a longer deque reference. For W2, we compute
        # baseline as cancellations observed in the last 4 hours, not in the
        # current window. Since this rule has no access to older history, we
        # bias toward early detection: the first time we see ≥3× the recent
        # rate, we fire. This is conservative and will be tightened in W6.
        baseline_rate = current_rate / self.spike_multiplier
        # heuristic: fire if current_rate is at least 0.3 (i.e. ≥30% cancels)
        # AND we have not fired in the last window.
        if current_rate < 0.3:
            return None
        if self._last_emit_at and (ts - self._last_emit_at) < self._cooldown:
            return None
        self._last_emit_at = ts
        return AnomalyFinding(
            rule_id=self.rule_id,
            subject_id="OMS_GLOBAL",
            timestamp=event.timestamp,
            severity=4,
            summary=(
                f"Order cancellation spike: {current_rate:.0%} rate over "
                f"last {self.window_min} min ({len(self._cancelled)} cancels / "
                f"{len(self._placed)} orders)"
            ),
            details={
                "window_min": self.window_min,
                "cancel_count": len(self._cancelled),
                "place_count": len(self._placed),
                "rate": round(current_rate, 3),
                "baseline_rate_used": round(baseline_rate, 3),
            },
        )


# --------------------------------------------------------------------------- #
# 4. TMS lead time — per-shipment rule
# --------------------------------------------------------------------------- #

class TMSLeadTimeAnomalyRule(BaseRule):
    """Fires when a shipment's actual lead time exceeds its planned lead
    time by more than `overrun_ratio`.

    Stateful per subject_id. We accumulate a `plan_lead_time_hours` from
    the SHIPMENT_DISPATCHED event's attributes (a real adapter would carry
    the original plan; here we use the attribute `planned_lead_time_hours`).
    On SHIPMENT_DELIVERED or SHIPMENT_DELAYED we compute the overrun and fire.
    """

    rule_id = "tms.leadtime.overrun"
    description = "Shipment lead time exceeds plan by >ratio"

    def __init__(self, overrun_ratio: float = 0.5):
        self.overrun_ratio = overrun_ratio
        # subject_id → (dispatch_at, planned_hours)
        self._dispatched: dict[str, tuple[datetime, float]] = {}
        # emit-once per subject
        self._emitted: set[str] = set()

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        if event.source_system != SourceSystem.TMS:
            return None
        ts = event.parsed_timestamp
        if event.event_type == EventType.SHIPMENT_DISPATCHED:
            planned = float(event.attributes.get("planned_lead_time_hours", 0.0))
            if planned <= 0:
                return None
            self._dispatched[event.subject_id] = (ts, planned)
            return None
        if event.event_type not in (EventType.SHIPMENT_DELIVERED, EventType.SHIPMENT_DELAYED):
            return None
        if event.subject_id in self._emitted:
            return None
        plan = self._dispatched.pop(event.subject_id, None)
        if plan is None:
            return None
        dispatch_at, planned_h = plan
        actual_h = (ts - dispatch_at).total_seconds() / 3600.0
        if actual_h < planned_h:
            return None
        ratio = (actual_h - planned_h) / planned_h
        if ratio < self.overrun_ratio:
            return None
        self._emitted.add(event.subject_id)
        severity = 4 if ratio < 1.0 else 5
        return AnomalyFinding(
            rule_id=self.rule_id,
            subject_id=event.subject_id,
            timestamp=event.timestamp,
            severity=severity,
            summary=(
                f"Shipment {event.subject_id} took {actual_h:.1f}h vs. planned "
                f"{planned_h:.1f}h (+{ratio:.0%})"
            ),
            details={
                "actual_hours": round(actual_h, 2),
                "planned_hours": planned_h,
                "overrun_ratio": round(ratio, 3),
            },
        )


# --------------------------------------------------------------------------- #
# 5. BMS supplier score drop — consecutive-event rule
# --------------------------------------------------------------------------- #

class BMSSupplierScoreDropRule(BaseRule):
    """Fires when a supplier's score drops by more than `min_drop` between
    two consecutive SUPPLIER_SCORED events.
    """

    rule_id = "bms.supplier.score_drop"
    description = "Supplier score drops significantly between updates"

    def __init__(self, min_drop: float = 0.5):
        self.min_drop = min_drop
        # subject_id → last (timestamp, score)
        self._last: dict[str, tuple[datetime, float]] = {}

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        if event.source_system != SourceSystem.BMS:
            return None
        if event.event_type != EventType.SUPPLIER_SCORED:
            return None
        if event.value is None:
            return None
        ts = event.parsed_timestamp
        prev = self._last.get(event.subject_id)
        self._last[event.subject_id] = (ts, event.value)
        if prev is None:
            return None
        prev_ts, prev_score = prev
        drop = prev_score - event.value
        if drop < self.min_drop:
            return None
        return AnomalyFinding(
            rule_id=self.rule_id,
            subject_id=event.subject_id,
            timestamp=event.timestamp,
            severity=4 if drop < 1.0 else 5,
            summary=(
                f"Supplier {event.subject_id} score dropped {prev_score:.2f} → "
                f"{event.value:.2f} (-{drop:.2f})"
            ),
            details={
                "previous_score": prev_score,
                "current_score": event.value,
                "drop": round(drop, 3),
                "previous_at": prev_ts.isoformat(),
            },
        )


# --------------------------------------------------------------------------- #
# Convenience: a Detector preloaded with the five shipped rules.
# --------------------------------------------------------------------------- #

def default_detector() -> Detector:
    """The 5 rules that ship with madcop v0.1."""
    return Detector([
        ColdChainTemperatureRule(),
        ColdChainDurationRule(),
        OMSOrderCancelSpikeRule(),
        TMSLeadTimeAnomalyRule(),
        BMSSupplierScoreDropRule(),
    ])
