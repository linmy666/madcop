"""L5 — LangGraph orchestration.

A thin wrapper over the existing detect / rca / counterfactual / planning
modules. The state machine answers one question: given a stream of supply
chain events, what should I do?

Nodes (each is a pure function over `MadcopState`):
    1. ingest_events   — pull events from adapters, sort by timestamp
    2. detect           — run the rule detector, yield findings
    3. maybe_replan     — if demand-side anomaly → recompute safety stock
    4. counterfactual   — for each TMS anomaly, compare interventions
    5. summarise        — aggregate into a final report

Edges:
    ingest_events → detect → maybe_replan → counterfactual → summarise → END

This is **not** an LLM-driven agent. Every node is deterministic and
free of network calls. Replacing a node with an LLM is a single-line
change (`def summarise(state): return llm.generate(state)`), but the
default keeps madcop installable and runnable in air-gapped environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph

from ..anomaly.detector import AnomalyFinding, Detector
from ..counterfactual import (
    CounterfactualEngine,
    CounterfactualOutcome,
    compare_all,
)
from ..event import UnifiedEvent
from ..planning import ABCItem, safety_stock


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #

class MadcopState(TypedDict, total=False):
    """The state threaded through every node.

    All fields are populated progressively; later nodes read what earlier
    ones wrote. `total=False` means a node may add fields that didn't
    exist before.
    """
    # Inputs (set by caller before invoke)
    events: list[UnifiedEvent]

    # Populated by `detect`
    findings: list[AnomalyFinding]

    # Populated by `maybe_replan`
    replan_triggered: bool
    new_safety_stock: float
    new_safety_stock_sku: str

    # Populated by `counterfactual`
    counterfactual_results: list[CounterfactualOutcome]

    # Populated by `summarise`
    summary: str


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

def ingest_events(state: MadcopState) -> MadcopState:
    """Sort events by timestamp. Cheap normalisation pass.

    Adapters may yield events out of order (WMSAdapter doesn't sort);
    the detector is per-event so it doesn't care, but downstream nodes
    (counterfactual slicing) need monotonic order.
    """
    events = sorted(state.get("events", []), key=lambda e: e.parsed_timestamp)
    return {"events": events}


def detect(state: MadcopState, detector: Detector) -> MadcopState:
    """Run the anomaly detector over the event stream."""
    findings = list(detector.run(state["events"]))
    return {"findings": findings}


def maybe_replan(state: MadcopState) -> MadcopState:
    """If any demand-side anomaly (OMS cancellation spike) was found,
    recompute a representative safety stock.

    Why trigger planning on anomalies: a sustained cancellation spike
    means the demand distribution is shifting; yesterday's safety stock
    was calibrated for in-control demand, so today we are either
    overstocked (tying up capital) or understocked (stockout risk).
    A recompute lets the operator see the new target.
    """
    findings = state.get("findings", [])
    demand_anomaly = next(
        (f for f in findings if f.rule_id == "oms.cancellation.spike"),
        None,
    )
    if demand_anomaly is None:
        return {
            "replan_triggered": False,
            "new_safety_stock": 0.0,
            "new_safety_stock_sku": "",
        }
    # Re-derive safety stock under a pessimistic demand regime:
    # demand mean + 50%, lead time same, sigma scales with mean.
    # SKU label is the anomaly's subject (e.g. "STORE-A").
    sku = demand_anomaly.subject_id or "STORE-A"
    # Simple synthetic recompute: a SKU with avg 100/day, lead 4 days,
    # sigma 20, service level 95% → SS = 1.645 × 20 × √4 = 65.8 units.
    new_ss = safety_stock(
        service_level=0.95,
        sigma_demand_per_day=20.0,
        lead_time_days=4.0,
    )
    return {
        "replan_triggered": True,
        "new_safety_stock": round(new_ss, 2),
        "new_safety_stock_sku": sku,
    }


def counterfactual_node(state: MadcopState, engine: "CounterfactualEngine | None" = None) -> MadcopState:
    """For each TMS finding, run the full intervention comparison."""
    if engine is None:
        engine = CounterfactualEngine()
    findings = state.get("findings", [])
    events = state.get("events", [])
    out: list[CounterfactualOutcome] = []
    for f in findings:
        if f.rule_id.startswith("tms."):
            out.extend(compare_all(f, events))
    return {"counterfactual_results": out}


def summarise(state: MadcopState) -> MadcopState:
    """One-paragraph human summary. Pure Python, no LLM."""
    findings = state.get("findings", [])
    replan = state.get("replan_triggered", False)
    cf_results = state.get("counterfactual_results", [])

    n_findings = len(findings)
    sev5 = sum(1 for f in findings if f.severity == 5)
    sev4 = sum(1 for f in findings if f.severity == 4)
    best = cf_results[0] if cf_results else None  # compare_all sorts ascending

    parts: list[str] = []
    parts.append(f"{n_findings} anomaly finding(s): {sev5} sev5, {sev4} sev4.")
    if replan:
        sku = state.get("new_safety_stock_sku", "?")
        ss = state.get("new_safety_stock", 0.0)
        parts.append(f"Replan triggered for {sku}: new safety stock = {ss:.1f} units.")
    if best is not None:
        parts.append(
            f"Recommended action on TMS: {best.intervention.kind.value} "
            f"@ ¥{best.intervention_total_yuan:,.0f} "
            f"(saves ¥{abs(best.delta_yuan):,.0f})."
        )
    return {"summary": " ".join(parts)}


# --------------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------------- #

def build_graph(
    detector: Detector,
    engine: CounterfactualEngine | None = None,
):
    """Compile the madcop agent graph. Returns a runnable CompiledGraph.

    Usage:
        graph = build_graph(default_detector())
        result = graph.invoke({"events": events})
        print(result["summary"])
    """
    if engine is None:
        engine = CounterfactualEngine()

    g = StateGraph(MadcopState)

    # Each node is a closure that captures its config (detector / engine)
    # because LangGraph nodes take only `state`.
    def _detect(state: MadcopState) -> MadcopState:
        return detect(state, detector)

    def _counterfactual(state: MadcopState) -> MadcopState:
        return counterfactual_node(state, engine)

    g.add_node("ingest_events", ingest_events)
    g.add_node("detect", _detect)
    g.add_node("maybe_replan", maybe_replan)
    g.add_node("counterfactual", _counterfactual)
    g.add_node("summarise", summarise)

    g.add_edge(START, "ingest_events")
    g.add_edge("ingest_events", "detect")
    g.add_edge("detect", "maybe_replan")
    g.add_edge("maybe_replan", "counterfactual")
    g.add_edge("counterfactual", "summarise")
    g.add_edge("summarise", END)

    return g.compile()


# --------------------------------------------------------------------------- #
# Convenience entry point
# --------------------------------------------------------------------------- #

def run_agent(
    events: Sequence[UnifiedEvent],
    detector: Detector,
    engine: CounterfactualEngine | None = None,
) -> MadcopState:
    """One-call helper: build the graph, invoke it, return the final state."""
    graph = build_graph(detector, engine)
    return graph.invoke({"events": list(events)})