# Roadmap — 8 Weeks, 1 Commit / Week

> "Real rhythm" = the **smallest** thing that lets the next layer stand on top.
> If a week slips, we shrink the next week. We never grow scope past time.

| Wk | Deliverable | Done = ... | Time |
|----|-------------|------------|------|
| **W1** | L1 — `UnifiedEvent` + 4 mock adapters + cold-chain scenario | `python -m madcop run coldchain` prints a real timeline | 6-8h |
| **W2** | L2 — Anomaly rules engine + 5 real rules | 5 unit tests pass; demo detects 3 anomaly types | 6-8h |
| **W3** | L2 — `rca.py` causal trace | Demo traces 1 cold-chain delay back to a contract clause | 6-8h |
| **W4** | **Push to GitHub (MVP)** | README + 1 demo output | 3h |
| **W5** | L3 — LangGraph state machine (detect→diagnose→decide) | State graph rendered, demo runs end-to-end | 6-8h |
| **W6** | L2 — `counterfactual.py` simulator | Demo: "supplier A vs B" with cost model | 6-8h |
| **W7** | L4 — Strategy registry + feedback log + weekly report | `madcop report` outputs first weekly summary | 6-8h |
| **W8** | **Push to GitHub (v1.0)** | Roadmap done, v1.0 tag | 3h |

## What's NOT on this roadmap (deferred)

- Real OMS/TMS/WMS wire integrations (interface is real, wire is mock).
- Reinforcement learning / model fine-tuning. "Self-evolution" = feedback log + report.
- Strategy marketplace UI. We expose a `StrategyRegistry` interface, no UI.
- Auth, multi-tenant, cloud deploy. Local-first SQLite.

## What is on the roadmap (after W8, "v1.x")

- Real adapter to a public sandbox (e.g. 快递100 / 菜鸟开放平台测试账号).
- Pluggable LLM backend (openai / anthropic / local ollama).
- Web UI for the strategy router (v2).
- Cross-company strategy sharing (v3, requires network effects — out of scope for solo).

## Commit cadence

- 1 commit per week, **at minimum**.
- If a week produces 0 commits, we **shrink the next week's scope** in our next sync.
- We do not borrow time from later weeks. We cut features.
