# madcop

> **mad** + **cop** — the supply chain cop that goes *mad* for anomalies.
> Pluggable LangGraph framework: from "detect" to "diagnose" to "decide", with self-evolution.

[![Tests](https://img.shields.io/badge/tests-45%20passing-brightgreen)](#tests)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#requirements)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)
[![TestPyPI](https://img.shields.io/badge/TestPyPI-v0.1.0-blue)](https://test.pypi.org/project/madcop/)

## What is madcop?

**madcop** is a pluggable framework that turns raw supply chain telemetry
(orders, shipments, warehouse readings, contracts) into **decision prompts**
with full causal chains. Where most tools stop at "alert fired", madcop walks
the chain back to the **human decision** that made the anomaly possible.

The name is short for **mad cop** — a cop that goes mad for anomalies. Not
in a punitive sense, but in the sense of "won't let a single anomaly go
untraced to its source."

## Why?

A typical supply chain alert reads:

> ⚠️ Cold-chain temperature exceeded threshold at 14:30.

That tells you **what** happened, not **why** it could happen. madcop answers
the second question:

> The temperature breach on SHIP-2026-0615-CG-SH traces back to a BD
> decision (DEC-2026-03-12-N3) made three months earlier to accept the
> supplier's "fine equals exemption" concession. That decision shaped
> CLAUSE-04 — a **passive** clause that punishes the breach but does not
> prevent it. The contract was signed with 冷链速运 at Q1 cost-cutting
> pressure, and the shipment is now exposed to the same failure mode.

The PM framing: an alert without a cause is a notification. An alert with a
cause is a **decision prompt**. madcop's job is to bridge the two.

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

**L1 — Unified Data Layer** (`madcop/event.py`, `madcop/adapters/`)
A `UnifiedEvent` is the lingua franca. Every adapter implements `BaseAdapter`
and yields events with frozen, UTC-validated, severity-rated fields.

**L2 — Anomaly Engine** (`madcop/anomaly/`, `madcop/rca/`)
5 shipped rules + a `Detector` that orchestrates them. RCA walks a typed
property graph from any finding back to a decision.

**L3 — LangGraph Orchestrator** (`madcop/graph/`) — *planned, W5*
A typed state machine that sequences detect → diagnose → decide → learn.

**L4 — Strategy Router** (`madcop/strategy/`) — *planned, W7*
YAML policies + feedback-weighted registry. Self-evolution is real here:
weekly reports roll up the week's findings, and policies are ranked by
their rolling effectiveness.

## What's shipped today (W1 + W2 + W3)

| Layer | Component | Status |
|-------|-----------|--------|
| L1 | `UnifiedEvent` with UTC + severity + source/event_type validation | ✅ |
| L1 | `BaseAdapter` contract + WMS mock (cold-chain) | ✅ |
| L2 | `Detector` + 5 rules (cold-chain temp / sustained / OMS cancel / TMS lead / BMS score) | ✅ |
| L2 | `KnowledgeGraph` + `trace()` + `explain()` RCA | ✅ |
| L2 | Cold-chain seed graph (5 nodes, 4 edges) | ✅ |
| L4 | Strategy registry, weekly report, LLM backend | 🔜 W7 |

## Installation

```bash
pip install madcop
```

Or from TestPyPI (the current published version):

```bash
pip install --index-url https://test.pypi.org/simple/ madcop
```

## Quick start

```bash
# W1: see the raw event stream
python -m madcop run coldchain

# W2: detect anomalies
python -m madcop run anomalies

# W3: detect + trace each finding to a root cause (the headline feature)
python -m madcop run rca
```

### What `run rca` looks like

```
madcop RCA demo — 3 finding(s) on SHIP-2026-0615-CG-SH

━━━ finding 1/3 ━━━
  rule:    wms.coldchain.temperature_breach
  summary: Cold-chain temperature -14.2°C exceeds threshold -15.0°C by 0.8°C
  chain:   5 step(s), root cause:
╭──────────────────────────────── root cause ────────────────────────────────╮
│ decision DEC-2026-03-12-N3 (BD 接受乙方'罚款即免责'让步) (by BD-Lin) —       │
│ rationale: Q1 降本压力 → shaped clause CLAUSE-04 (温控异常通知条款) PASSIVE  │
│ ("温控异常时, 承运商应在 30 分钟内书面通知甲方, 逾期每日扣 0.5% 服务费") →   │
│ under contract CONT-2026-0312 (冷链速运 / 2026 年度框架) → carried by        │
│ 冷链速运 → on shipment SHIP-2026-0615-CG-SH (广州→上海, 冷链, 2026-06-15)    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

**45 tests, all passing.** They cover the L1 contract (UTC validation, event
type / source system consistency, adapter behavior), the L2 detector (every
rule, plus state-machine semantics for windowed rules), and the RCA graph
(forward/reverse traversal, empty chain, unknown subject).

## Roadmap

See [`ROADMAP.md`](ROADMAP.md). 8 weeks, 1 commit per week. Current: **W3
done, ready to push**.

## Requirements

- Python 3.10+
- `rich >= 13.0`

## Project status

Alpha. The architecture is real, the data layer is real, the anomaly rules
are real, and the RCA traces are real. The adapters are mock data today;
real wire integrations to OMS / TMS / WMS / BMS systems are scoped for
later (see Roadmap).

## License

MIT. See [`LICENSE`](LICENSE).

## Why "madcop"?

When the user asked for a name for "the agent that goes mad for anomalies",
the obvious answer was **mad + cop**. The product is a cop that goes mad for
anomalies — not in a punitive sense, but in the sense of "won't let a
single anomaly go untraced to its source."

## Contact

Lin Ruihan · chuiniu@me.com
