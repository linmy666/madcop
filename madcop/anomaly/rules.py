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
from .cusum import CUSUMTracker, baseline_for
from .detector import AnomalyFinding, BaseRule, Detector


# --------------------------------------------------------------------------- #
# 1. Cold-chain temperature — instant rule (multi-zone)
# --------------------------------------------------------------------------- #

class ColdChainTemperatureRule(BaseRule):
    """Fires when a WMS temperature reading leaves the configured band.

    v0.2 update: the rule is **band-aware**, not single-threshold. A reading
    is in-spec when it sits inside `[band_low, band_high]`. Out-of-spec
    means either too cold or too warm — both are anomalies, and a frozen
    reading in a refrigerated zone is a *worse* anomaly than a warm one.

    Severity scales with how far the reading is from the band edge, **not**
    from a single threshold. A reading 5°C outside the band is worse than
    one 0.5°C outside, regardless of which direction.

    Backwards compatibility: if the event has no `band_c` attribute (v0.1
    shipments), the rule falls back to the configured single threshold
    `threshold_c`. This is so the W1 frozen demo and the W3 RCA demo still
    work unchanged.
    """

    rule_id = "wms.coldchain.temperature_breach"
    description = "WMS temperature reading leaves configured band"

    def __init__(self, threshold_c: float = -15.0):
        # Legacy single-threshold fallback (used when event has no band).
        self.threshold_c = threshold_c

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        if event.source_system != SourceSystem.WMS:
            return None
        if event.event_type != EventType.TEMPERATURE_READING:
            return None
        if event.value is None:
            return None

        # Prefer band-aware check; fall back to legacy threshold.
        band = event.attributes.get("band_c") if isinstance(event.attributes, dict) else None
        if band is not None:
            low, high = float(band[0]), float(band[1])
            value = event.value
            if low <= value <= high:
                return None
            # how far outside?
            if value < low:
                delta = low - value
                direction = "below"
            else:
                delta = value - high
                direction = "above"
            zone = event.attributes.get("zone", "unknown")
            # severity by |delta|
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
                    f"WMS [{zone}] temperature {value:.1f}°C is {delta:.1f}°C "
                    f"{direction} band [{low}, {high}]°C"
                ),
                details={
                    "reading_c": value,
                    "band_low_c": low,
                    "band_high_c": high,
                    "delta_c": round(delta, 2),
                    "direction": direction,
                    "zone": zone,
                },
            )

        # Legacy fallback
        if event.value <= self.threshold_c:
            return None
        delta = event.value - self.threshold_c
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
# 3. OMS order-cancel spike — CUSUM change-point detector
# --------------------------------------------------------------------------- #

class OMSOrderCancelSpikeRule(BaseRule):
    """Fires when the CUSUM-detected cancellation rate exceeds the in-control
    baseline for a category.

    v0.2 update: this rule no longer uses a fixed 30% threshold. It runs
    a one-sided CUSUM (Page 1954) per (subject_id, category) and fires
    when the cumulative positive deviation of the observed cancel rate
    from the category-specific baseline crosses a threshold `h`. The
    threshold is set so that under the null (rate = baseline), the
    average run length until a false alarm is ~1000 events — a standard
    industrial SPC target (ARL0 = 1000, Montgomery §9.4).

    Why this beats the v0.1 fixed-threshold approach:
    - A 30% rate from 10 orders is noise; from 1,000 orders is a signal.
      CUSUM accumulates, so it correctly differentiates.
    - Different categories have different baselines (apparel = 30% is
      normal, dairy = 30% is a crisis). CUSUM uses each category's
      baseline so a fashion spike doesn't fire as if it were a food
      emergency.
    - A small but persistent shift (e.g. baseline +2pp for 50 orders in
      a row) is detectable. The fixed-threshold rule would miss it.
    """

    rule_id = "oms.cancellation.spike"
    description = "Order cancellation rate spikes vs. category baseline (CUSUM)"

    def __init__(
        self,
        arl0: float = 1000.0,
        k: float = 0.02,
        category_attribute: str = "category",
    ):
        self.arl0 = arl0
        self.k = k
        self.category_attribute = category_attribute
        # subject_id (a store/channel) → category → tracker
        self._trackers: dict[tuple[str, str], "CUSUMTracker"] = {}

    def _tracker_for(self, subject_id: str, category: str) -> "CUSUMTracker":
        from .cusum import CUSUMTracker, baseline_for
        key = (subject_id, category)
        t = self._trackers.get(key)
        if t is None:
            t = CUSUMTracker(
                category=category,
                p0=baseline_for(category),
                k=self.k,
                arl0=self.arl0,
            )
            self._trackers[key] = t
        return t

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        from .cusum import CUSUMTracker  # local import for clarity
        if event.source_system != SourceSystem.OMS:
            return None
        if event.event_type not in (EventType.ORDER_PLACED, EventType.ORDER_CANCELLED):
            return None
        # value is the event's numeric payload; for OMS we use 1=cancel, 0=placed
        # if the upstream adapter doesn't set it, fall back to the event type
        if event.event_type == EventType.ORDER_CANCELLED:
            observed = 1.0
        else:
            observed = 0.0
        category = (
            event.attributes.get(self.category_attribute)
            if isinstance(event.attributes, dict) else None
        ) or "default"
        subject_id = event.subject_id or "OMS_GLOBAL"
        tracker = self._tracker_for(subject_id, category)
        new_cusum = tracker.update(observed)
        if new_cusum < tracker.h:
            return None
        # Fire and reset (standard "CUSUM with reset after signal")
        tracker.reset()
        # Severity: scale with how far past h the CUSUM was at the moment
        # of signal. Past-h is at most one observation's worth (s ≤ 1),
        # so we grade by category baseline shift: higher-p0 categories
        # get lower severity by default.
        severity = 4 if tracker.p0 < 0.10 else 3
        return AnomalyFinding(
            rule_id=self.rule_id,
            subject_id=subject_id,
            timestamp=event.timestamp,
            severity=severity,
            summary=(
                f"Cancellation spike (CUSUM) on {subject_id}/{category}: "
                f"cusum crossed h={tracker.h:.2f} at observation #{tracker.n_updates} "
                f"(baseline rate {tracker.p0:.0%})"
            ),
            details={
                "category": category,
                "baseline_p0": tracker.p0,
                "cusum_threshold_h": round(tracker.h, 2),
                "cusum_at_signal": round(new_cusum, 3),
                "observation_index": tracker.n_updates,
                "arl0_target": self.arl0,
                "k_allowance": self.k,
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
