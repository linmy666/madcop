"""L3 — Counterfactual cost modeling.

Given a `CostModel` (pure cost parameters) and an `Intervention` (what
action we imagine having taken), the engine simulates the financial
impact of that action against the *baseline* (what actually happened).

Pure functions, no I/O. All randomness in tests must be mocked by the
caller — the engine is deterministic.

Why a separate module from W2 rules: rules *detect* anomalies, this
module *costs* them. Mixing the two confuses "what went wrong" with
"what would have happened if…". The OR expert (week 4 audit) flagged
exactly this confusion in v0.1 — the cost of a finding should not be
inside the finding itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence

from ..anomaly.detector import AnomalyFinding
from ..event import EventType, SourceSystem, UnifiedEvent


# --------------------------------------------------------------------------- #
# Cost model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CostModel:
    """Pure cost parameters. Defaults reflect a typical e-commerce / cold-chain
    operator: stockout is expensive (lost margin + customer churn), delay is
    cheap (coupon compensation), expedite shipping is the dominant lever.

    All currency values in ¥. All time values in hours.

    These defaults are *illustrative*. A real implementation would read them
    from a config or accept overrides at the CLI.
    """

    # Lost margin per stockout (¥/unit). When a TMS shipment slips past
    # OMS demand, the demand evaporates. This is the cost of losing that
    # sale, not the cost of the unit itself.
    lost_margin_per_unit: float = 80.0

    # Customer compensation per delayed shipment (¥/shipment). A voucher,
    # discount, or refund that we typically hand out for late deliveries.
    compensation_per_delayed: float = 15.0

    # Expedite shipping surcharge (¥/hour-saved). Pulling forward a TMS
    # shipment by 1h typically costs this much on the freight invoice.
    expedite_cost_per_hour: float = 120.0

    # Maximum expedite cap. We won't simulate expediting by more than this
    # number of hours even if asked, because real freight has physical
    # limits (driver rest, vehicle availability).
    max_expedite_hours: float = 6.0

    # Order rate assumption (orders/hour) when the stream doesn't tell us.
    # The OMS stream itself is the source of truth; this is the fallback
    # for hypothetical events beyond the stream.
    default_order_rate_per_hour: float = 50.0


# --------------------------------------------------------------------------- #
# Interventions
# --------------------------------------------------------------------------- #

class InterventionKind(str, Enum):
    """Closed set of actions we know how to cost. Anything else raises."""
    NO_ACTION = "no_action"
    EXPEDITE_1H = "expedite_1h"
    EXPEDITE_2H = "expedite_2h"
    EXPEDITE_4H = "expedite_4h"
    REROUTE = "reroute"


@dataclass(frozen=True)
class Intervention:
    """A hypothetical action taken at the moment of the anomaly."""
    kind: InterventionKind
    hours_saved: float = 0.0    # effective time saved on the at-risk shipment
    extra_cost: float = 0.0     # direct cost of the action itself (¥)


# --------------------------------------------------------------------------- #
# Outcome
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CostLine:
    """One row in the breakdown table."""
    label: str
    amount_yuan: float
    note: str = ""


@dataclass(frozen=True)
class CounterfactualOutcome:
    """The full cost comparison between baseline and intervention."""
    intervention: Intervention
    baseline_total_yuan: float
    intervention_total_yuan: float
    delta_yuan: float                # intervention - baseline (negative = savings)
    baseline_breakdown: tuple[CostLine, ...]
    intervention_breakdown: tuple[CostLine, ...]
    assumptions: tuple[str, ...] = ()

    def recommend(self) -> str:
        if self.delta_yuan < -1e-6:
            return f"RECOMMEND: {self.intervention.kind.value} (saves ¥{abs(self.delta_yuan):.0f})"
        if self.delta_yuan > 1e-6:
            return f"DO NOT: {self.intervention.kind.value} (costs ¥{self.delta_yuan:.0f} more)"
        return f"NEUTRAL: {self.intervention.kind.value} (~¥0)"


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

# Anomalies that block OMS demand (TMS-related). These are the ones where
# expediting makes sense; OMS cancellation spikes don't benefit from
# freight expediting.
_FREIGHT_ANOMALY_PREFIXES = ("tms.",)


class CounterfactualEngine:
    """Cost-simulate interventions for a single anomaly on a single event stream.

    Scope: the engine looks at events that *follow* the anomaly timestamp
    on the same `subject_id`, and at the OMS orders that fall in the
    `affected_window_hours` after the anomaly.

    The engine is **stateless** — it does not remember past calls. Pass
    the full stream each time. This keeps the math inspectable.
    """

    def __init__(
        self,
        cost_model: CostModel | None = None,
        affected_window_hours: float = 4.0,
    ):
        self.cost = cost_model or CostModel()
        self.affected_window_hours = affected_window_hours

    # ----- public API ----- #

    def evaluate(
        self,
        finding: AnomalyFinding,
        events: Iterable[UnifiedEvent],
        intervention: Intervention,
    ) -> CounterfactualOutcome:
        ev_list = sorted(events, key=lambda e: e.parsed_timestamp)
        after, affected_oms = self._slice(finding, ev_list)

        baseline_lines, base_assumptions = self._baseline_cost(finding, after, affected_oms)
        int_lines, int_assumptions = self._intervention_cost(
            finding, after, affected_oms, intervention,
        )

        baseline_total = sum(line.amount_yuan for line in baseline_lines)
        int_total = sum(line.amount_yuan for line in int_lines)

        return CounterfactualOutcome(
            intervention=intervention,
            baseline_total_yuan=round(baseline_total, 2),
            intervention_total_yuan=round(int_total, 2),
            delta_yuan=round(int_total - baseline_total, 2),
            baseline_breakdown=tuple(baseline_lines),
            intervention_breakdown=tuple(int_lines),
            assumptions=tuple(base_assumptions + int_assumptions),
        )

    # ----- helpers ----- #

    def _slice(
        self, finding: AnomalyFinding, ev_list: Sequence[UnifiedEvent],
    ) -> tuple[list[UnifiedEvent], list[UnifiedEvent]]:
        """Return (events_after_anomaly, OMS events in affected window)."""
        try:
            anom_ts = finding_ts(finding, ev_list)
        except ValueError:
            return [], []
        affected_window_end = anom_ts.timestamp() + self.affected_window_hours * 3600
        after = [e for e in ev_list if e.parsed_timestamp.timestamp() >= anom_ts.timestamp()]
        affected_oms = [
            e for e in after
            if e.source_system == SourceSystem.OMS
            and e.parsed_timestamp.timestamp() <= affected_window_end
        ]
        return after, affected_oms

    def _baseline_cost(
        self,
        finding: AnomalyFinding,
        after: list[UnifiedEvent],
        affected_oms: list[UnifiedEvent],
    ) -> tuple[list[CostLine], list[str]]:
        """Cost what actually happened.

        For TMS (freight) anomalies: every OMS order in the window is
        considered at risk of being lost.
        For OMS (cancel) anomalies: every cancelled order is the cost.
        """
        assumptions: list[str] = []
        lines: list[CostLine] = []

        if not _is_freight_anomaly(finding):
            # OMS-side anomaly (e.g. cancellation spike): each cancel in
            # the window costs us lost margin.
            cancels = [e for e in affected_oms if e.event_type == EventType.ORDER_CANCELLED]
            if cancels:
                lines.append(CostLine(
                    label="lost_orders",
                    amount_yuan=len(cancels) * self.cost.lost_margin_per_unit,
                    note=f"{len(cancels)} cancels × ¥{self.cost.lost_margin_per_unit:.0f}/unit",
                ))
            else:
                lines.append(CostLine(label="lost_orders", amount_yuan=0.0))
            assumptions.append(
                f"OMS anomaly: {len(cancels)} cancels in {self.affected_window_hours:.0f}h window"
            )
            return lines, assumptions

        # TMS anomaly: every order in the window is at risk of being
        # lost because the shipment was supposed to fulfill them.
        if not affected_oms:
            assumptions.append(
                "TMS anomaly: 0 OMS orders in window — using default rate"
            )
            orders_at_risk = int(
                self.cost.default_order_rate_per_hour * self.affected_window_hours
            )
        else:
            orders_at_risk = len(affected_oms)
            assumptions.append(
                f"TMS anomaly: {orders_at_risk} OMS orders in {self.affected_window_hours:.0f}h window"
            )

        # Stockout rate model: every hour of delay → X% of demand lost.
        # We assume the anomaly causes `anomaly_severity * 0.2` hours
        # of effective delay (1→0.2h, 5→1.0h).
        delay_h = 0.2 * finding.severity
        stockout_fraction = min(delay_h / max(self.affected_window_hours, 1e-6), 1.0)
        lost_units = orders_at_risk * stockout_fraction
        lines.append(CostLine(
            label="stockout_loss",
            amount_yuan=lost_units * self.cost.lost_margin_per_unit,
            note=f"{lost_units:.1f} units × ¥{self.cost.lost_margin_per_unit:.0f} (sev={finding.severity}→{delay_h:.1f}h delay)",
        ))
        lines.append(CostLine(label="shipping_normal", amount_yuan=0.0))
        assumptions.append(
            f"Delay model: severity {finding.severity} → {delay_h:.1f}h effective delay, "
            f"stockout fraction {stockout_fraction:.0%}"
        )
        return lines, assumptions

    def _intervention_cost(
        self,
        finding: AnomalyFinding,
        after: list[UnifiedEvent],
        affected_oms: list[UnifiedEvent],
        intervention: Intervention,
    ) -> tuple[list[CostLine], list[str]]:
        """Cost what would have happened under the intervention."""
        assumptions: list[str] = []
        lines: list[CostLine] = []
        c = self.cost

        # Direct cost of the intervention itself
        if intervention.kind == InterventionKind.NO_ACTION:
            lines.append(CostLine(label="intervention_cost", amount_yuan=0.0))
            assumptions.append("No action: zero direct cost")
        elif intervention.kind in (
            InterventionKind.EXPEDITE_1H,
            InterventionKind.EXPEDITE_2H,
            InterventionKind.EXPEDITE_4H,
        ):
            hours = intervention.hours_saved
            if hours > c.max_expedite_hours:
                hours = c.max_expedite_hours
                assumptions.append(
                    f"Expedite capped to max {c.max_expedite_hours:.1f}h"
                )
            direct = hours * c.expedite_cost_per_hour
            lines.append(CostLine(
                label="expedite_surcharge",
                amount_yuan=direct,
                note=f"{hours:.1f}h × ¥{c.expedite_cost_per_hour:.0f}/h",
            ))
        elif intervention.kind == InterventionKind.REROUTE:
            # Reroute: flat extra cost (configured) + same time saved as 2h expedite
            direct = intervention.extra_cost or (2.0 * c.expedite_cost_per_hour)
            lines.append(CostLine(
                label="reroute_cost",
                amount_yuan=direct,
                note=f"reroute flat cost",
            ))
        else:
            raise ValueError(f"unknown intervention: {intervention.kind!r}")

        # Indirect cost: remaining stockout after the intervention
        if not _is_freight_anomaly(finding):
            # OMS-side: expediting doesn't help; cancels still happen
            cancels = [e for e in affected_oms if e.event_type == EventType.ORDER_CANCELLED]
            lines.append(CostLine(
                label="residual_cancellations",
                amount_yuan=len(cancels) * c.lost_margin_per_unit,
                note=f"{len(cancels)} cancels (intervention doesn't help OMS-side)",
            ))
            assumptions.append("OMS-side anomaly: intervention has no residual effect")
            return lines, assumptions

        # TMS-side: each hour saved reduces stockout fraction
        orders_at_risk = len(affected_oms) if affected_oms else int(
            c.default_order_rate_per_hour * self.affected_window_hours
        )
        delay_h = 0.2 * finding.severity
        if intervention.kind in (
            InterventionKind.EXPEDITE_1H,
            InterventionKind.EXPEDITE_2H,
            InterventionKind.EXPEDITE_4H,
        ):
            delay_h = max(delay_h - intervention.hours_saved, 0.0)
        elif intervention.kind == InterventionKind.REROUTE:
            delay_h = max(delay_h - 2.0, 0.0)
        # NO_ACTION leaves delay_h unchanged
        stockout_fraction = min(delay_h / max(self.affected_window_hours, 1e-6), 1.0)
        lost_units = orders_at_risk * stockout_fraction
        lines.append(CostLine(
            label="residual_stockout",
            amount_yuan=lost_units * c.lost_margin_per_unit,
            note=f"{lost_units:.1f} units after intervention (delay {delay_h:.1f}h)",
        ))
        return lines, assumptions


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #

def finding_ts(finding: AnomalyFinding, ev_list: Sequence[UnifiedEvent]):
    """Get the anomaly's timestamp as a `datetime`."""
    from datetime import datetime
    try:
        ts = datetime.fromisoformat(finding.timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise ValueError(f"invalid finding timestamp: {finding.timestamp!r}") from e
    return ts


def _is_freight_anomaly(finding: AnomalyFinding) -> bool:
    return any(finding.rule_id.startswith(p) for p in _FREIGHT_ANOMALY_PREFIXES)


# --------------------------------------------------------------------------- #
# Convenience: a small library of canned interventions
# --------------------------------------------------------------------------- #

CANNED_INTERVENTIONS: dict[InterventionKind, Intervention] = {
    InterventionKind.NO_ACTION:   Intervention(kind=InterventionKind.NO_ACTION),
    InterventionKind.EXPEDITE_1H: Intervention(kind=InterventionKind.EXPEDITE_1H, hours_saved=1.0),
    InterventionKind.EXPEDITE_2H: Intervention(kind=InterventionKind.EXPEDITE_2H, hours_saved=2.0),
    InterventionKind.EXPEDITE_4H: Intervention(kind=InterventionKind.EXPEDITE_4H, hours_saved=4.0),
    InterventionKind.REROUTE:     Intervention(kind=InterventionKind.REROUTE, extra_cost=300.0),
}


def compare_all(
    finding: AnomalyFinding,
    events: Iterable[UnifiedEvent],
    cost_model: CostModel | None = None,
) -> list[CounterfactualOutcome]:
    """Run every canned intervention and return outcomes sorted by delta (lowest first)."""
    engine = CounterfactualEngine(cost_model)
    out = [
        engine.evaluate(finding, events, intervention)
        for intervention in CANNED_INTERVENTIONS.values()
    ]
    out.sort(key=lambda o: o.delta_yuan)
    return out
