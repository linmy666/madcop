# madcop Roadmap — v1.6 → v2.0

> Principle: each version is independently shippable. 1 day per version.
> If a version slips, we cut scope, not borrow time.

## v1.6 — Tool Layer Expansion (agent becomes useful)

| # | Feature | Module | LoC est. |
|---|---------|--------|----------|
| 1 | Web search/fetch tool | `tools/web.py` | ~200 |
| 2 | File read/write/edit tools | `tools/files.py` | ~200 |
| 3 | Cron scheduler | `tools/cron.py` + CLI `madcop cron` | ~150 |

**Done =** agent can search the web, read/write files, and schedule tasks.

## v1.7 — Agent Core Improvements

| # | Feature | Module | LoC est. |
|---|---------|--------|----------|
| 4 | Streaming output (SSE/CLI) | `agent/streaming.py` | ~250 |
| 5 | Context summarization middleware | `agent/summarize.py` | ~200 |

**Done =** agent streams tokens to terminal, context stays under budget on long runs.

## v1.8 — Productization (agent becomes a product)

| # | Feature | Module | LoC est. |
|---|---------|--------|----------|
| 6 | Telegram channel | `channels/telegram.py` | ~300 |
| 7 | Discord channel | `channels/discord.py` | ~250 |
| 8 | Config hot-reload | `config/hotreload.py` | ~150 |

**Done =** madcop runs as a daemon, talks to users on Telegram/Discord.

## v1.9 — Infrastructure Hardening

| # | Feature | Module | LoC est. |
|---|---------|--------|----------|
| 9 | Docker sandbox provider | `tools/docker_sandbox.py` | ~300 |
| 10 | Event bus + webhooks | `tools/eventbus.py` | ~200 |

**Done =** agent runs code in isolated containers, external services can subscribe to events.

## v2.0 — Web UI

| # | Feature | Module | LoC est. |
|---|---------|--------|----------|
| 11 | FastAPI server + WebSocket | `server/` | ~400 |
| 12 | React/Next.js frontend | `web/` | ~600 |

**Done =** madcop has a full Web UI dashboard. v2.0 release.
