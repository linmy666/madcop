# DeerFlow 2.0 vs madcop — Architecture Analysis & Gap Report

> Source: GitHub API analysis of `bytedance/deer-flow` (v2.0, main branch)
> Date: 2026-06-24

## 1. DeerFlow Architecture Overview

DeerFlow 2.0 is a **ground-up rewrite** — LangGraph-based AI super-agent with:
- **Backend**: FastAPI Gateway + embedded LangGraph agent runtime
- **Frontend**: Next.js 16 + React 19 + Tailwind CSS 4
- **IM Channels**: Feishu, Slack, Telegram, Discord, DingTalk, WeChat, WeCom
- **Reverse Proxy**: Nginx unified entry (port 2026)

### Service Topology
| Service | Port | Role |
|---------|------|------|
| Nginx | 2026 | Unified reverse proxy entry |
| Gateway API | 8001 | FastAPI REST + LangGraph agent runtime |
| Frontend | 3000 | Next.js web interface |
| Provisioner | 8002 | Optional K8s sandbox provisioner |

### Backend Package Structure
```
backend/packages/harness/deerflow/
├── agents/
│   ├── lead_agent/     # Main agent (factory + system prompt)
│   ├── middlewares/    # Middleware chain components
│   ├── memory/         # Memory extraction, queue, prompts
│   └── thread_state.py # ThreadState schema
├── sandbox/            # Code execution sandbox
│   ├── local/          # Local filesystem provider
│   ├── tools.py        # bash, ls, read/write/str_replace
│   └── middleware.py   # Sandbox lifecycle management
├── subagents/          # Subagent delegation
│   ├── builtins/       # general-purpose, bash agents
│   ├── executor.py     # Background execution engine
│   └── registry.py     # Agent registry
├── tools/builtins/     # present_files, ask_clarification, view_image
├── mcp/                # MCP integration
├── models/             # Model factory with thinking/vision support
├── skills/             # Skills discovery, loading, parsing
├── community/          # Community tools (search, scrape, image search)
├── config/             # Configuration system
└── client.py           # Embedded Python client
```

### Frontend Source Layout
```
frontend/src/
├── app/               # Next.js App Router (chat, agents, auth, docs, blog)
├── components/        # React components
│   ├── ui/            # Shadcn UI primitives
│   ├── ai-elements/   # Vercel AI SDK elements
│   ├── workspace/     # Chat page (messages, artifacts, settings)
│   └── landing/       # Landing page
├── core/              # Business logic
│   ├── threads/       # Thread creation, streaming, state
│   ├── api/           # LangGraph client singleton
│   ├── agents/        # Custom agents
│   ├── auth/          # Authentication
│   ├── artifacts/     # File/code artifacts
│   ├── channels/      # IM connections
│   ├── settings/      # User settings
│   ├── memory/        # Memory management
│   ├── skills/        # Skills UI
│   ├── messages/      # Message rendering
│   └── tools/         # Tool management
├── hooks/             # React hooks
└── lib/               # Utilities
```

### Key Tech Stack
- **Backend**: Python 3.12+, FastAPI, LangGraph
- **Frontend**: Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4, pnpm 10.26
- **UI Components**: Shadcn UI, MagicUI, React Bits, Vercel AI SDK
- **State**: TanStack Query
- **Streaming**: LangGraph SDK streaming
- **Tests**: Backend (pytest), Frontend (Rstest + Playwright E2E)

---

## 2. Core Patterns Worth Learning

### 2.1 Middleware Chain (both have this!)
DeerFlow and madcop both implement a middleware chain for agent execution hooks.
- DeerFlow: `agents/middlewares/` — memory, sandbox lifecycle, tool filtering
- madcop: `agent/middleware.py` — QianControlMiddleware, LoggingMiddleware

### 2.2 Subagent Delegation
DeerFlow has a full subagent system:
- `subagents/builtins/` — general-purpose agent + bash-only agent
- `subagents/executor.py` — background execution
- `subagents/registry.py` — register and dispatch

**madcop has**: `agent/routing_executor.py` but no formal subagent registry.

### 2.3 Sandbox Execution
DeerFlow: `sandbox/` with local filesystem provider + K8s provisioner option
madcop: `tools/docker_sandbox.py` (v1.9) + `tools/sandbox.py` (subprocess)

### 2.4 Skills System
DeerFlow: `skills/` directory with discovery, loading, parsing + `.agent/skills/` SKILL.md format
madcop: `skill/` module — similar concept, less developed

### 2.5 Thread-based Persistence
DeerFlow: `ThreadState` schema with per-thread isolation
madcop: Currently uses localStorage (frontend) + no backend persistence

### 2.6 Streaming
DeerFlow: LangGraph SDK native streaming + StreamBridge
madcop: SSE via FastAPI StreamingResponse (works, but simpler)

---

## 3. Gap Analysis: madcop vs DeerFlow

| Feature | DeerFlow 2.0 | madcop v2.1 | Gap |
|---------|-------------|-------------|-----|
| **Backend runtime** | LangGraph agent + middleware chain | Manual plan-execute loop + middleware chain | Small — both have agent loop |
| **Web UI framework** | Next.js 16 + React 19 + Tailwind | Single-file HTML + vanilla JS | **Large** — need React or at least structured JS |
| **Streaming** | LangGraph SDK native SSE | Custom SSE with tool/reasoning/text events | Small — our SSE works |
| **Tool use** | MCP + built-in + community tools | WebSearch + Weather + WebFetch + File tools | Medium — need MCP integration |
| **Subagent delegation** | Full registry + executor + builtins | routing_executor only | **Large** |
| **Memory/persistence** | Per-thread ThreadState + memory extraction | 4-layer memory (working/episodic/semantic/reflective) | Small — madcop has memory |
| **Sandbox** | Local FS + K8s provisioner | Docker sandbox + subprocess fallback | Small |
| **IM Channels** | Feishu, Slack, Telegram, Discord, DingTalk, WeChat, WeCom | Telegram + Discord (v1.8) | Medium — have channels but fewer |
| **Config hot-reload** | Full config system | hotreload.py (v1.8) | Small |
| **Event bus** | Not explicitly documented | EventBus + WebhookSub (v1.9) | madcop leads |
| **Skills** | Full discovery/loading/parsing + SKILL.md | skill/ module (basic) | Medium |
| **Auth** | JWT + OIDC + password + credential file | None | **Large** for multi-user |
| **Artifacts** | File/code artifact system | None | Medium |
| **i18n** | en-US, zh-CN | zh-CN only | Small (personal tool) |
| **Frontend features** | Chat + artifacts + todos + settings + agents UI | Chat + settings + tools display | Medium |

---

## 4. What madcop Should Borrow (Priority Order)

### P0 (Immediate — user-visible impact)
1. **React/Next.js frontend** — our single-file HTML is hitting limits. marked.js + vanilla JS can't match a component framework for complex UI (artifacts, todos, custom agents)
2. **Thread persistence on backend** — currently conversations are in browser localStorage. Need server-side thread state.

### P1 (Near-term — feature parity)
3. **Subagent registry** — formal system for registering and dispatching subagents
4. **MCP integration** — connect to external MCP servers for tool extensibility
5. **Artifact system** — display generated files/code/images inline in chat

### P2 (Medium-term — differentiation)
6. **Custom agent UI** — let users define their own agents with custom prompts
7. **Todos in UI** — show agent task lists inline
8. **E2E tests** — Playwright tests for the web UI

### P3 (Nice-to-have)
9. **Auth system** — JWT for multi-user
10. **More IM channels** — Feishu, Slack, DingTalk

---

## 5. Conclusion

DeerFlow 2.0 is significantly more mature than madcop in:
- **Frontend architecture** (Next.js vs single-file HTML)
- **Subagent system** (formal registry vs ad-hoc)
- **MCP integration** (full MCP client vs none)
- **Thread persistence** (server-side vs localStorage)

But madcop has unique strengths:
- **Engineering control theory** (QianControlMiddleware — unique middleware design philosophy)
- **4-layer memory system** (more structured than DeerFlow's memory extraction)
- **EventBus + WebhookSub** (DeerFlow doesn't have explicit event bus)
- **Docker sandbox** (comparable to DeerFlow's sandbox)
- **Channels** (Telegram + Discord already built)

**Next step**: The biggest ROI is migrating the frontend from single-file HTML to a proper React/Next.js app. This is the single largest gap that affects user experience.
