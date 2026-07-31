# MadCop Architecture

> Local-first AI agent desktop app. FastAPI + Vue 3 + Electron.

## High-level

```
┌─────────────────────────────────────────┐
│  Electron Shell (main.cjs)              │
│  ┌───────────────────────────────────┐  │
│  │  Vue 3 Renderer (dist-vue/)       │  │
│  │  Pinia stores + TailwindCSS       │  │
│  │  SSE stream → chatStore           │  │
│  └──────────┬────────────────────────┘  │
│             │ HTTP / SSE                 │
│  ┌──────────▼────────────────────────┐  │
│  │  FastAPI Backend (localhost:8765) │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │  Agent Runtime              │  │  │
│  │  │  QuickEngine (single LLM)   │  │  │
│  │  │  ReActEngine (tool-use loop)│  │  │
│  │  │  AgentNetwork (deep mode:   │  │  │
│  │  │    planner→specialists→synth│  │  │
│  │  │    parallel asyncio waves)  │  │  │
│  │  └─────────────────────────────┘  │  │
│  │  Tools (files, web, bash, etc.)   │  │
│  │  Memory (SQLite: 5-tier hybrid)   │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Backend (`madcop/`)

| Module | Role |
|---|---|
| `server/app.py` | FastAPI app, SSE handlers, lifespan |
| `server/routes/chat_v4.py` | V4 unified SSE chat endpoint |
| `agent/react_v4.py` | ReAct engine (Thought→Action→Observation loop) |
| `agent_network/engine.py` | Deep mode: multi-agent DAG with parallel waves |
| `tools/` | Tool registry: files, web, bash, cron, RAG, MCP |
| `tools/safety.py` | Pydantic input validation + path guardrails |
| `memory/` | 5-tier memory: buffer, semantic, insight, persona, scenario |
| `llm/` | ChatClient abstraction: OpenAI-compat, Anthropic native |

## Frontend (`desktop/src/vue/`)

| Module | Role |
|---|---|
| `stores/chatStore.ts` | Session state, SSE event dispatch, message list |
| `composables/useSSEStream.ts` | SSE parsing layer (v4) |
| `composables/useAgentState.ts` | Computed derivation from SSE events |
| `components/chat/V4ChatPanel.vue` | V4 unified chat panel |
| `components/chat/SubAgentPanel.vue` | Deep-mode parallel agent grid |
| `components/layout/Sidebar.vue` | Session list, project groups, search |

## Agent Modes

| Mode | Engine | Behavior |
|---|---|---|
| `quick` | QuickEngine | Single LLM call, no tools |
| `standard` | ReActEngineV4 | Thought→Action→Observation loop with tools |
| `deep` | AgentNetwork | Planner → N specialists (parallel) → Synthesizer |

## Security Model

- Server binds to `127.0.0.1` only (no remote access)
- CORS restricted to Electron/Vite dev origins
- WebSocket validates Origin header
- API keys stored encrypted (Fernet) in `~/.madcop/settings.json`
- Tool input validation via Pydantic (`safety.py`)
- SSRF guard on web_fetch
- Path guardrails on file tools

## License

AGPL-3.0
