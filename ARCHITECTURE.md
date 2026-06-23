# madcop

> **mad** + **cop** — the supply chain cop that goes *mad* for anomalies.
> Pluggable LangGraph framework: from "detect" to "diagnose" to "decide",
> with self-evolution.

## What this is (today)

A framework that unifies data from **OMS / TMS / WMS / BMS** behind a single
`UnifiedEvent` schema, runs rule + LLM hybrid anomaly detection, traces root
causes through the event graph, and routes to a pluggable policy for action.
**Self-evolution is real**: every detected anomaly + human feedback writes back
into a weekly report and a feedback-weighted policy registry.

## What this is NOT (yet)

- A production-grade data integration platform — adapters ship as **pluggable
  stubs** that talk to mock data. The interface is real; the wire is not.
- A replacement for o9 / Kinaxis / Blue Yonder — those run on real customer
  telemetry. This runs on **structured synthetic events** you can replay.
- A self-training reinforcement learner. "Self-evolution" here means
  **rule/policy feedback** and a **weekly report**, not gradient updates.

## Architecture (4 layers, 1 graph)

```
┌──────────────────────────────────────────────────────┐
│  L4  Strategy Router    — zero-code YAML policies     │
├──────────────────────────────────────────────────────┤
│  L3  LangGraph          — detect → diagnose → decide  │
│                         → learn (state machine)        │
├──────────────────────────────────────────────────────┤
│  L2  Anomaly Engine     — rules · RCA · counterfactual│
├──────────────────────────────────────────────────────┤
│  L1  Unified Data Layer — OMS/TMS/WMS/BMS adapters    │
└──────────────────────────────────────────────────────┘
```

### L1 — Unified Data Layer

`UnifiedEvent` is the lingua franca. Every adapter (`oms`, `tms`, `wms`, `bms`)
implements `BaseAdapter` and yields `UnifiedEvent`s with these fields:

- `id`, `timestamp`, `source_system`, `event_type`
- `subject_id` (SKU / order / shipment / contract)
- `value` (numeric measurement, e.g. temperature, lead_time_hours)
- `attributes` (free-form dict)
- `severity` (1-5, set by the adapter)

### L2 — Anomaly Engine

Three composable modules:

- **rules** — declarative thresholds (`temp > -15°C for >15min`).
- **rca** — causal trace: "this delay traces to contract X, clause Y".
- **counterfactual** — "what if we'd picked supplier B?" simulator.

### L3 — LangGraph Orchestrator

A typed state machine. The state holds the current event, the running
hypothesis, the chosen policy, and the feedback score. Each node is a pure
function that takes the state and returns a partial update. The graph
sequences: `detect → diagnose → decide → learn`.

### L4 — Strategy Router

Strategies are **YAML** in `madcop/strategy/policies/`. A policy is
`(trigger, action)`. The router picks one per anomaly, and humans rate the
result on a 1-5 scale. Ratings feed the `PolicyRegistry`, which ranks
strategies by their rolling effectiveness.

## Roadmap (8 weeks, 1 commit/week)

See [`ROADMAP.md`](ROADMAP.md). The current `main` branch is **W1**.

## License

MIT.
