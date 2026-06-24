"""L6 — Anomaly replay engine.

Take a historical event log, re-run the entire madcop stack (detect →
counterfactual → recommend), and quantify: **"if every recommendation
had been adopted, what would we have saved?"**

This is the answer every supply-chain manager wants but most systems
don't produce: a single number that connects anomaly detection to
operational ROI. madcop already has the pieces — replay is the glue.

Inputs:
    events: any iterable of UnifiedEvent (sorted by timestamp)

Outputs:
    ReplayReport: per-finding recommendation + per-window loss totals +
                  overall ROI
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from ..anomaly.detector import AnomalyFinding, Detector
from ..counterfactual import (
    CANNED_INTERVENTIONS,
    CostModel,
    CounterfactualEngine,
    CounterfactualOutcome,
    InterventionKind,
    compare_all,
)
from ..event import UnifiedEvent


# --------------------------------------------------------------------------- #
# Per-finding recommendation row
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FindingReplay:
    """One finding's recommendation and the ¥ we'd save by adopting it."""
    finding: AnomalyFinding
    recommendation: InterventionKind    # the cheapest-cost intervention
    actual_loss_yuan: float            # cost if we did nothing
    simulated_loss_yuan: float         # cost if we adopt the recommendation
    savings_yuan: float                # actual - simulated (>=0)

    @property
    def savings_pct(self) -> float:
        if self.actual_loss_yuan <= 0:
            return 0.0
        return self.savings_yuan / self.actual_loss_yuan


# --------------------------------------------------------------------------- #
# Whole-window report
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ReplayReport:
    """The aggregate result of replaying an event log."""
    n_events: int
    n_findings: int
    findings: tuple[FindingReplay, ...]
    total_actual_loss_yuan: float
    total_simulated_loss_yuan: float
    total_savings_yuan: float
    cost_model: CostModel = field(default_factory=CostModel)

    @property
    def savings_pct(self) -> float:
        if self.total_actual_loss_yuan <= 0:
            return 0.0
        return self.total_savings_yuan / self.total_actual_loss_yuan

    def top_savings(self, n: int = 3) -> list[FindingReplay]:
        """Return the top-N findings ranked by ¥ savings (descending)."""
        return sorted(self.findings, key=lambda r: -r.savings_yuan)[:n]


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

class ReplayEngine:
    """Re-run madcop over a historical event stream and quantify ROI."""

    def __init__(
        self,
        detector: Detector,
        cost_model: CostModel | None = None,
    ):
        self.detector = detector
        self.cf_engine = CounterfactualEngine(cost_model)
        self.cost_model = cost_model or CostModel()

    def run(self, events: Iterable[UnifiedEvent]) -> ReplayReport:
        ev_list = sorted(events, key=lambda e: e.parsed_timestamp)
        findings = list(self.detector.run(ev_list))

        per_finding: list[FindingReplay] = []
        total_actual = 0.0
        total_simulated = 0.0

        for f in findings:
            outcomes = compare_all(f, ev_list)
            if not outcomes:
                # Finding with no intervention options (e.g. OMS cancel that
                # we can only cost). Treat recommendation as NO_ACTION.
                actual = self._standalone_baseline(f, ev_list)
                per_finding.append(FindingReplay(
                    finding=f,
                    recommendation=InterventionKind.NO_ACTION,
                    actual_loss_yuan=round(actual, 2),
                    simulated_loss_yuan=round(actual, 2),
                    savings_yuan=0.0,
                ))
                total_actual += actual
                total_simulated += actual
                continue

            # outcomes are sorted ascending by delta_yuan; [0] is the best
            best = outcomes[0]
            # The baseline scenario is NO_ACTION (always included)
            no_action = next(
                (o for o in outcomes if o.intervention.kind == InterventionKind.NO_ACTION),
                outcomes[0],
            )
            actual = no_action.intervention_total_yuan
            simulated = best.intervention_total_yuan
            # savings is bounded at >= 0 (we never claim we make money vs baseline)
            savings = max(actual - simulated, 0.0)
            per_finding.append(FindingReplay(
                finding=f,
                recommendation=best.intervention.kind,
                actual_loss_yuan=round(actual, 2),
                simulated_loss_yuan=round(simulated, 2),
                savings_yuan=round(savings, 2),
            ))
            total_actual += actual
            total_simulated += simulated

        return ReplayReport(
            n_events=len(ev_list),
            n_findings=len(per_finding),
            findings=tuple(per_finding),
            total_actual_loss_yuan=round(total_actual, 2),
            total_simulated_loss_yuan=round(total_simulated, 2),
            total_savings_yuan=round(max(total_actual - total_simulated, 0.0), 2),
            cost_model=self.cost_model,
        )

    def _standalone_baseline(
        self, finding: AnomalyFinding, events: Sequence[UnifiedEvent],
    ) -> float:
        """Fallback cost when the finding has no compare_all options."""
        # Run NO_ACTION against an empty event window; the engine returns 0
        # baseline for non-freight, non-OMS findings. We assume the cost
        # equals the finding's severity * a fixed multiplier (¥100/sev unit).
        return float(finding.severity) * 100.0


# --------------------------------------------------------------------------- #
# Event-file I/O
# --------------------------------------------------------------------------- #

def load_events_from_json(path: str | Path) -> list[UnifiedEvent]:
    """Load a JSON file of events.

    Accepted shapes:
        [event, event, ...]                   bare list
        {"events": [event, ...]}              wrapped
        {"findings": [...], "events": [...]}  full report (we extract events)

    Each event must contain at minimum: timestamp, source_system, event_type,
    subject_id. Optional: value, attributes, severity.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        raw_list = data
    elif isinstance(data, dict):
        if "events" not in data:
            raise ValueError(
                f"JSON event file {p} has no 'events' key; "
                f"keys found: {list(data.keys())}"
            )
        raw_list = data["events"]
    else:
        raise ValueError(f"JSON event file {p} must be a list or dict, got {type(data)}")

    out: list[UnifiedEvent] = []
    for raw in raw_list:
        # Reuse make_event so all validation (ISO 8601, etc.) re-applies.
        # JSON convention is UPPER_SNAKE_CASE for the enum-like fields; our
        # Python enums use lower.dot.case. Normalise by name lookup so users
        # don't have to read our internals to write a JSON event file.
        from ..event import EventType, SourceSystem, make_event
        ss_raw = raw["source_system"]
        et_raw = raw["event_type"]
        # If the value already matches an enum value, leave it; otherwise
        # try to resolve by enum NAME (upper snake case).
        ss = (
            ss_raw if ss_raw in {s.value for s in SourceSystem}
            else SourceSystem[ss_raw.upper()].value
        )
        et = (
            et_raw if et_raw in {e.value for e in EventType}
            else EventType[et_raw.upper()].value
        )
        out.append(make_event(
            timestamp=raw["timestamp"],
            source_system=ss,
            event_type=et,
            subject_id=raw["subject_id"],
            value=raw.get("value"),
            attributes=raw.get("attributes") or {},
            severity=raw.get("severity", 1),
            id=raw.get("id"),
        ))
    return out


def write_replay_report_json(report: ReplayReport, path: str | Path) -> None:
    """Serialize a ReplayReport to JSON for later inspection."""
    p = Path(path)
    payload = {
        "n_events": report.n_events,
        "n_findings": report.n_findings,
        "total_actual_loss_yuan": report.total_actual_loss_yuan,
        "total_simulated_loss_yuan": report.total_simulated_loss_yuan,
        "total_savings_yuan": report.total_savings_yuan,
        "savings_pct": round(report.savings_pct, 4),
        "top_savings": [
            {
                "rule_id": r.finding.rule_id,
                "subject_id": r.finding.subject_id,
                "timestamp": r.finding.timestamp,
                "severity": r.finding.severity,
                "recommendation": r.recommendation.value,
                "actual_loss_yuan": r.actual_loss_yuan,
                "simulated_loss_yuan": r.simulated_loss_yuan,
                "savings_yuan": r.savings_yuan,
                "savings_pct": round(r.savings_pct, 4),
            }
            for r in report.top_savings()
        ],
    }
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)