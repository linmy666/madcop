# MadCop Agent (周巡)

> **周思万虑，巡行无疆** — Infinite Minds, Boundless Strides
>
> A local-first AI agent with a 4-layer growing memory, tool-use, streaming
> web UI, and a plan-execute-replan loop. Runs in one process. Stores
> everything locally. No cloud, no platform.

[![Tests](https://img.shields.io/badge/tests-1272%20passing-brightgreen)](#tests)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#requirements)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)
[![Version](https://img.shields.io/badge/version-2.3.0-purple)](#changelog)

<p align="center">
  <img src="web/mascot.png" alt="madcop" width="200">
</p>

---

## What is madcop?

**madcop** is a personal AI agent that remembers what you told it across
sessions. It can search the web, check the weather, read and write files,
execute code in a sandbox, and stream responses in real time — all from a
local web UI or your terminal.

It works with any OpenAI-compatible LLM endpoint. One `pip install`, one
process, one SQLite file.

### Key features

- **Streaming web UI** — dark/light theme, markdown rendering, code
  highlighting, reasoning fold-out, thinking animation, voice input,
  file attachments, context meter ("rage bar")
- **4-layer growing memory** — working / episodic / semantic / reflective,
  with auto-extraction, cross-session recall, temporal validity, and
  token-budgeted injection
- **Agent-managed memory** — the LLM can `store_memory`, `recall_memory`,
  and `forget_memory` via tool calls
- **Tool use** — web search (DuckDuckGo), web fetch, weather (wttr.in),
  file read/write/edit, cron scheduler, Docker sandbox, event bus
- **Encrypted API key storage** — Fernet (AES-128-CBC + HMAC) at rest,
  masked in API responses
- **Multi-provider** — OpenAI, Anthropic, MiniMax, DeepSeek, GLM, NVIDIA
  NIM, or any custom endpoint
- **Conversation compaction** — old turns are auto-summarised when the
  context window fills up
- **Hybrid retrieval** — FTS5 keyword + lightweight TF-IDF semantic
  scoring for memory search
- **IM channels** — Telegram and Discord integrations (v1.8)
- **Config hot-reload** — change settings without restarting (v1.8)

---

## Quick start

```bash
# Install
pip install -e ".[dev]"

# Run the web UI
python3 -m madcop.server
# → open http://127.0.0.1:8765/

# Or use the CLI
python3 -m madcop run --goal "analyse the cancel spike in OMS data"
python3 -m madcop doctor  # self-check
```

### Configure your LLM

Open **Settings** (gear icon in the sidebar), choose a provider, paste your
API key, and save. Keys are encrypted with Fernet before writing to disk.

Or set environment variables:

```bash
export MADCOP_OPENAI_API_KEY="sk-..."
export MADCOP_OPENAI_BASE_URL="https://api.openai.com/v1"
export MADCOP_OPENAI_MODEL="gpt-4o-mini"
```

---

## Architecture

```
                        ┌──────────────────────────┐
                        │     Web UI (port 8765)    │
                        │  Single-file HTML + JS    │
                        └───────────┬──────────────┘
                                    │
                        ┌───────────▼──────────────┐
                        │   FastAPI Server (v2.1+)  │
                        │  /api/chat (SSE streaming) │
                        │  /api/settings (encrypted) │
                        │  /api/memory (CRUD + FTS5) │
                        └───────────┬──────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           ▼                        ▼                        ▼
  ┌─────────────────┐    ┌───────────────────┐    ┌─────────────────┐
  │  Tool Registry   │    │  4-Layer Memory   │    │  LLM Client     │
  │  • web_search    │    │  L1: Buffer       │    │  OpenAI-compat  │
  │  • get_weather   │    │  L2: Episodic     │    │  + streaming    │
  │  • web_fetch     │    │  L3: Semantic     │    │  + reasoning    │
  │  • file R/W/E    │    │  L4: Reflective   │    │                 │
  │  • store_memory  │    │  + GrowthEngine   │    │                 │
  │  • recall_memory │    │  + Compactor      │    │                 │
  │  • forget_memory │    │  + Hybrid Search  │    │                 │
  │  • docker        │    │                   │    │                 │
  │  • cron          │    │                   │    │                 │
  │  • eventbus      │    │                   │    │                 │
  └─────────────────┘    └───────────────────┘    └─────────────────┘
           │                        │
           ▼                        ▼
  ┌─────────────────┐    ┌───────────────────┐
  │  External APIs   │    │  SQLite (~/.madcop/)│
  │  DuckDuckGo      │    │  memory.db         │
  │  wttr.in         │    │  brain.db          │
  └─────────────────┘    │  settings.json     │
                         └───────────────────┘
```

---

## Memory system

madcop's memory is a 4-layer architecture backed by SQLite + FTS5:

| Layer | Name | What it stores | Persisted? |
|-------|------|---------------|------------|
| L1 | Working | Current conversation turns | In-memory |
| L2 | Episodic | Task history (goal → outcome) | `memory.db` |
| L3 | Semantic | Distilled facts (name, prefs, skills) | `memory.db` |
| L4 | Reflective | Meta-strategies, feedback, prefs | `memory.db` |

### How it works

1. **Injection** — before each LLM call, madcop searches memory for facts
   relevant to your message and injects them into the system prompt
   (token-budgeted at 800/800/400 tokens per section).
2. **Extraction** — after each response, a background thread scans your
   message for facts ("我叫X", "I like X") and stores them in L3.
   Debounced at 30s to avoid duplicate writes.
3. **Agent tools** — the LLM can call `store_memory`, `recall_memory`,
   and `forget_memory` to actively manage what it remembers.
4. **Temporal validity** — memories can have an expiry
   (`valid_for_days`); expired entries are excluded from injection.
5. **Compaction** — when a conversation exceeds 8K tokens, old turns are
   summarised into a single system message.
6. **Hybrid retrieval** — memory search combines FTS5 keyword matching
   with TF-IDF cosine similarity for semantic recall.

### Memory API

```python
from madcop.memory import MemoryStore, SemanticMemory, MemoryKind

store = MemoryStore()
sem = SemanticMemory(store)

# Store a fact
store.insert(
    kind=MemoryKind.SEMANTIC,
    title="User location",
    content="User lives in Hangzhou",
    tags=("user-profile",),
)

# Search
results = sem.search("Hangzhou")

# Update an existing fact
store.update(record_id, content="User moved to Shanghai",
             metadata_patch={"superseded_by": record_id})
```

---

## Tool use

```python
from madcop.tools import default_registry

registry = default_registry(store=MemoryStore())
print([t.name for t in registry.list_tools()])
# ['echo', 'get_time', 'web_search', 'web_fetch', 'get_weather',
#  'store_memory', 'recall_memory', 'forget_memory']
```

The LLM receives tool schemas as OpenAI function-calling definitions. When
it decides to call a tool, madcop executes it and feeds the result back
for a second LLM call.

---

## Web UI features

| Feature | Description |
|---------|-------------|
| Streaming | Token-level SSE with reasoning + content separation |
| Markdown | Full GFM (tables, code blocks, lists, links) via marked.js |
| Code highlight | highlight.js with GitHub Dark theme |
| Dark / Light | Toggle via sidebar, persisted in localStorage |
| Reasoning | MiniMax M2.7 / DeepSeek R1 reasoning_content in fold-out |
| Rage bar | Context window usage indicator |
| Strength | Low / Medium / High → temperature mapping |
| Model switch | Change model mid-conversation |
| History | Conversation list with search, persisted in localStorage |
| Memory page | View / add / delete memories |
| Settings | Provider dropdown, API key (encrypted), model |
| Voice | Web Speech API for voice input (Chinese) |
| Attachments | File upload (display only, multi-modal pending) |
| Mascot | Custom 3D character in sidebar + welcome |

---

## Project structure

```
madcop/
├── madcop/
│   ├── llm/            # ChatClient ABC + Mock + OpenAICompat + streaming
│   ├── memory/         # 4-layer memory + compactor + hybrid search
│   ├── brain/          # PageDB knowledge brain + unified façade
│   ├── tools/          # Tool registry + 12 built-in tools
│   ├── agent/          # Plan-execute loop + middleware chain
│   ├── config/         # YAML config + encrypted settings + hot-reload
│   ├── channels/       # Telegram + Discord integrations
│   ├── anomaly/        # Supply-chain anomaly detection (CUSUM, etc.)
│   ├── server/         # FastAPI app + SSE + memory pipeline
│   └── ...
├── web/                # Single-file web UI (index.html + mascot.png)
├── tests/              # 1272 tests
├── docs/               # Architecture analyses
└── pyproject.toml
```

---

## Requirements

- Python 3.10+
- Dependencies: `fastapi`, `uvicorn`, `openai`, `cryptography`, `sse-starlette`, `httpx`, `langgraph`, `rich`

```bash
pip install -e ".[dev]"
```

---

## Tests

```bash
pytest
# ====================== 1272 passed in 25s ======================
```

Coverage spans:
- Memory store (CRUD, FTS5, update, temporal validity)
- Memory tools (store/recall/forget, dedup, supersedes)
- Hybrid retrieval (TF-IDF + cosine + FTS5)
- Context compaction (budget, summarise, fallback)
- Server (settings CRUD, chat SSE, tool-use flow, memory API)
- Tools (web search, weather, file ops, cron, docker, eventbus)
- Agent (middleware chain, streaming, summarise)
- Channels (Telegram, Discord, hot-reload)

---

## Changelog

### v2.2.0 — Memory system overhaul
- 10 memory gaps closed (agent-managed memory, UPDATE/NOOP,
  token-budgeted injection, temporal validity, context compaction,
  async debounce, hybrid retrieval, unified brain+memory)
- 1272 tests (was 1182)
- Literature survey of 7 memory systems in `docs/memory-research.md`

### v2.1.0 — Web UI + tool-use + encrypted settings
- Codex-style single-file web UI
- Fernet-encrypted API key storage
- Token-level SSE streaming with reasoning_content support
- Tool-use loop (web search, weather, file ops)
- 4-layer memory integrated into chat (inject + extract)
- DuckDuckGo lite endpoint for web search
- v1.6–v1.9 features cherry-picked (streaming, channels, docker, eventbus)

### v1.5.0 — Computer use + permissions
- ComputerUseTool (mouse, keyboard, screenshot)
- PermissionManager with action levels
- MCP client (Model Context Protocol)

### v1.3.0 — Middleware chain
- QianControlMiddleware (engineering control theory)
- LoggingMiddleware, TodoMiddleware
- Brain middleware (prescreen + consolidate)

### v1.0.0 — Initial release
- Plan-execute-replan loop
- 4-layer growing memory
- Sub-agent routing
- CUSUM anomaly detection
- Root-cause analysis

---

## License

MIT © Lin Ruihan
