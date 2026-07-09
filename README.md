# MadCop

**A local-first AI agent desktop workstation.**

MadCop is a cross-platform desktop application that brings the power of modern LLMs into a private, agentic workflow. It runs as a single Electron binary on macOS, Windows, and Linux, talks to any OpenAI-compatible API endpoint, and keeps your conversations, files, and knowledge base entirely on your machine. No cloud lock-in, no per-seat fees, no data leaving the device.

This document explains the *why* behind the major design decisions — written for product managers and reviewers who want to understand how the system is put together, not just a list of features.

---

## What problem is MadCop solving?

The dominant LLM desktop clients (ChatGPT, Claude.ai, Gemini) are excellent chat surfaces but they assume a specific shape of interaction: one human, one model, one conversation at a time, with vendor-managed tools and memory. That works for "answer this question" but it does not work for "I need to (a) search the web, (b) read a local file, (c) summarise the result, (d) save a Markdown report to disk" — which is a normal afternoon for a product manager, analyst, or engineer.

MadCop is built around three observations:

1. **The work is multi-step.** A single useful task almost always needs several LLM calls with intermediate state. A chat that cannot sequence, branch, persist, or call external tools caps you at "Q&A on a webpage".
2. **The data is local.** A working file directory, a Notion export, a `git` history, screenshots, contracts — the substance of real work sits on the user's disk. A client that can only attach a single file per message (or pays per-token for cloud RAG) punishes the people who already have the answer.
3. **The model is a choice, not a vendor.** A senior engineer might want Claude for refactors and GLM-5.2 for Chinese-language analysis. A privacy-sensitive user wants a self-hosted endpoint. A startup wants to A/B-test cost. A single-vendor client forces that decision at sign-up and never lets you revisit it.

So the design goal is: a thin local shell that lets the user pick their own model, hand it their own files, and let the system orchestrate the rest. Everything else is in service of that.

---

## How is the system structured?

```
┌─────────────────────────────────────────────────────────┐
│                    Electron Shell                       │
│  ┌────────────────────┐   ┌────────────────────────┐  │
│  │  Vue 3 + Pinia +   │   │   Python Backend       │  │
│  │  Tailwind v4 UI    │   │   (FastAPI + Uvicorn)  │  │
│  │  (Renderer Process)│←→│                         │  │
│  └────────────────────┘   │  ┌──────────────────┐  │  │
│                            │  │  LLM Client       │  │  │
│  ┌────────────────────┐   │  │  (OpenAI Compat)  │  │  │
│  │  Workspace Picker  │   │  └──────────────────┘  │  │
│  │  Sidebar / Tabs    │   │  ┌──────────────────┐  │  │
│  │  Chat / Composer   │   │  │  Tool Registry    │  │  │
│  └────────────────────┘   │  │  + MCP Bridge      │  │  │
│                            │  └──────────────────┘  │  │
│                            │  ┌──────────────────┐  │  │
│                            │  │  Workflow Engine  │  │  │
│                            │  │  + 12 Modes       │  │  │
│                            │  └──────────────────┘  │  │
│                            │  ┌──────────────────┐  │  │
│                            │  │  Memory Pipeline  │  │  │
│                            │  │  (5-tier)         │  │  │
│                            │  └──────────────────┘  │  │
│                            └────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

The architecture is intentionally **two processes talking over HTTP** — not one big monolith — for three reasons:

1. **The Python backend can be deployed headless.** The same `madcop.server` module runs without Electron (over plain HTTP/WebSocket) for CI, scripting, or embedding in other tools.
2. **The Vue renderer is portable.** Tauri, Web, or a custom shell can reuse the frontend as-is because it never assumes anything about the backend's runtime.
3. **Process isolation protects the user.** A misbehaving tool call cannot freeze the UI; the renderer survives a hung request and can cancel it.

---

## How does model routing work?

Routing is the single most important design question in any LLM client. MadCop routes on **three axes simultaneously**:

### Axis 1: Per-request model selection

The user configures one or more model providers in the Settings panel. Each provider is a name + base URL + API key + model id (e.g. `sensenova / https://token.sensenova.cn/v1 / GLM-5.2`). The frontend exposes the active provider as a `useSettingsStore.currentModel` ref; the backend receives a `model` field on every `POST /api/chat` and forwards it to the OpenAI-compatible client.

This means **there is no "default model" hard-coded in the backend**. If you don't configure one, you get a clear error on the first request. The model lives in user data, not in the product.

### Axis 2: Per-session tool registry

Different models from different vendors have wildly different tool-use quality. GLM-5.2 reliably emits `tool_call` parts but occasionally echoes the schema as text; Qwen3 is the opposite. The backend's tool dispatcher (`madcop/tools/registry.py`) registers the **same** toolset regardless of model, but the system prompt is tuned to nudge the model toward emitting function calls. Specifically, every chat request includes an explicit instruction:

> "When the user asks you to do anything that requires real-time information, you MUST call the `web_search` tool. Do not make up answers. Call the tool directly — do not output the tool's parameter description."

This works around the most common failure mode of self-hosted Chinese-tuned models (outputting the JSON schema as text instead of as a structured `tool_calls` array).

### Axis 3: Intent classification → workflow mode

A single chat turn can be either "answer this" (one LLM call) or "search the web, write a report, save to disk" (many LLM calls with tool side effects). The Mode Selector in the composer exposes **12 preset modes** from Google's "Agent design patterns" catalog:

- `single_agent` — one LLM + tools, the default
- `sequential` — Agent A → B → C, each consuming the previous output
- `parallel` — same input fanned out to N workers, results merged
- `coordinator` — a router agent classifies input, dispatches to a specialist
- `hierarchical` — top-level plan, sub-tasks, recurse
- `swarm` — many agents with shared blackboard
- `loop` — produce, critique, revise until a quality threshold is met
- `review_critique` — producer + reviewer
- `iterative_refine` — feedback loop with a separate evaluator
- `human_in_loop` — explicit user checkpoint
- `react` — Reason + Act
- `custom` — user-defined graph

When a mode is selected, the chat endpoint hands the request to the workflow engine (`madcop/workflow/executor.py`), which walks the mode's graph of nodes. Each node is a Python class with an `execute(ctx)` method that receives the inputs from upstream nodes and yields a result. The engine emits SSE events at each step so the UI can show progress live.

For users who don't want to pick a mode, the frontend performs a lightweight keyword-based intent classifier (`_classifyAndPlan` in `chatStore.ts`) that detects multi-step requests (contains words like 调研 / 搜索 / 保存 / 生成 / 写到) and injects an inline task plan into the system prompt:

> "First, search using web_search. Second, generate the report and save it to ~/Downloads/madcop/ as report.md using write_file. Third, reply to the user when done."

This gives the user the *experience* of the multi-agent system without the cognitive overhead of picking a mode from a dropdown.

---

## How are tools registered and dispatched?

The tool system is the surface where "agent" stops being marketing and becomes real. MadCop's design is **a single registry that everything reads from**, with three extension points:

1. **Built-in tools** — registered in `madcop/tools/__init__.py::default_registry()`. These include:
   - `web_search` (DuckDuckGo, no API key needed)
   - `web_fetch` (httpx + BeautifulSoup-style HTML→text)
   - `read_file` / `write_file` / `edit_file` (path-confined to allowlisted dirs)
   - `weather` (wttr.in, no key)
   - `clarify` (returns a structured question back to the user)

2. **MCP servers** — any external Model Context Protocol server can be registered at startup via `madcop/tools/mcp.py`. The bridge translates MCP `tools/call` into internal `Tool.__call__` invocations. This means a user can add a private internal API or a database client without forking MadCop.

3. **User-defined Python tools** — any function decorated with `@tool("name", description="...")` is auto-registered. The decorator captures the signature and produces an OpenAI-compatible JSON schema. This is the path for one-off internal tools.

The dispatcher is stateless: each tool call is `registry.dispatch(tool_call) -> ToolResult`. The function looks up the tool by name, validates the arguments against the schema, calls the function, and wraps the return value in a `ToolResult(is_error=..., content=...)`. The chat loop serializes the result and appends it to the message history before the second LLM call.

The frontend's `ToolCallGroup.vue` component reads these results from the SSE stream and renders them as collapsible cards under the assistant message — so the user sees which tools were called, with what inputs, and what was returned.

---

## How does the workspace integration work?

A core anti-pattern in many LLM clients is that the client doesn't know which directory the user is actually working in, so the model writes files to `os.getcwd()` of whatever process spawned it. In MadCop, this is solved with a `WorkspacePanel` component in the sidebar that:

1. Lists the current workspace directory and lets the user pick a new one via a native folder picker (Electron `dialog.showOpenDialog`).
2. Stores the selected path in `localStorage` as `madcop_workspace_dir` *and* on the backend via `POST /api/workspace/dir`.
3. On every chat request, the frontend reads `madcop_workspace_dir` and prepends a system message: *"Your current working directory is `/Users/.../madcop`. When the user asks you to save files, generate reports, or write code, save them under that directory."*

The backend's `WriteFileTool.__init__` accepts an `allowed_dirs` list and the chat handler passes `[_WORKSPACE_DIR, os.getcwd(), os.path.expanduser('~')]` to it. This means a user who picks `~/Documents/projects/foo` cannot accidentally have the model write into `~/Library/Application Support/madcop/`.

The `DirectoryPicker` component in the composer echoes the same path so the user always sees where files would go.

---

## How does persistence work?

The frontend is responsible for **local-first persistence of the conversation log** via `chatStore._persistSession()`:

- Every `sendMessage` writes the current messages + title of that session to `localStorage["madcop_chat_messages"]`.
- On reload, `getSession()` is called the first time a session id is referenced; if the in-memory state has no messages but `localStorage` does, the messages are hydrated.
- The tab list (`madcop_tabs`) and session metadata (`madcop_sessions`) are persisted the same way.

The reason this matters: the backend's session store uses UUIDs but the frontend's session ids are `session-${Date.now()}` (e.g. `session-1783…`). These are two different id schemes that would break hydration if you tried to map them through the backend. Instead, the frontend owns the conversation history and the backend is treated as stateless from the LLM's perspective. This is a deliberate trade: the backend can be restarted, the database can be wiped, the model can be swapped, and the user never loses their thread.

---

## How does the multi-agent routing actually work in practice?

The current v0.9 implementation has two layers:

**Layer 1: Local keyword intent classification.** Before every chat, the frontend's `chatStore._classifyAndPlan` runs a regex over the user's input:

- contains `调研 / 搜索 / 查 / 报告 / 行业` → `needsResearch = true`
- contains `保存 / 生成 / 写到 / md / 存到` → `needsFileWrite = true`
- contains `代码 / 实现 / 写个 / 做个` → `needsCode = true`

If any of these match, a plan prompt is injected into the system message:

> "## Task plan
> Step 1: Search the web. Call `web_search` to find relevant information.
> Step 2: Generate a file. Use `write_file` to save the report to `/Users/.../madcop/report.md`.
> Final: Reply to the user."

This is intentionally **not a real LLM call** — it adds no latency to the chat flow. The trade-off is that regex matching misses nuance (e.g. "查一下明天的天气" wouldn't match), but the most common multi-step requests (research + write) are caught reliably.

**Layer 2: Per-mode workflow execution.** The 12 preset modes are not "tricks" — they are real graph executors. When the user explicitly picks `coordinator` from the Mode Selector, the chat endpoint hands the request to the workflow engine, which:

1. Spins up a "RequirementAnalysis" node that uses the LLM to extract structured intent from the user input.
2. Picks a specialist agent based on the extracted intent (a `coordinator` LLM call).
3. Dispatches the actual work to that specialist, with a tailored prompt.
4. A `synthesis` node merges results and streams the final response.

Each node is a Python class implementing `execute(ctx) -> NodeResult`. The engine persists each step to a `workflow_node_runs` table so the trace can be replayed. The UI shows a live graph of which node is currently running with timing.

For users who don't want to pick a mode, the keyword layer (Layer 1) gives them most of the benefit.

---

## How does the design tool work?

The `DesignPage.vue` is a separate page reachable from the sidebar. It contains:

- A text prompt on the left.
- A live canvas on the right showing the generated UI tree as nested Vue components.
- 11 component types (Button, Input, Card, etc.) plus nested Container.
- Per-page state, undo/redo (10 levels), and a `.madcop` file format for save/load.
- Multi-page projects with a directory tree.
- Export to HTML.

The interesting design decision here is that the canvas is **not** an iframe of a separate renderer. It's a Vue tree generated by an LLM call to `DesignTool` (in `madcop/design/`), which produces a structured `DesignData` JSON that the page then renders as live Vue components. The user can click on any element to select it, drag to move, and tweak properties in an inspector. Because the canvas is "real" Vue and not a screenshot, the elements are interactive — you can type into a generated `Input` and see the value update.

---

## How is quality controlled?

A test suite of **1,321 tests** (all passing) covers:

- The memory store, the consolidation / pruning pipeline, the prescreen for sensitive content.
- The statistics engine (CUSUM, z-score anomaly detection, counterfactual cost).
- The design tool's component tree compiler.
- The workflow engine's executor and all 12 modes.
- The backend's HTTP routes and SSE streaming.

The key test discipline is that **the backend is exercised as a black box** — the tests build a FastAPI app, make real HTTP requests, and assert on the response shape. This means the same tests catch the kind of regression that a unit test of `madcop.brain.store` would miss (e.g. a routing change that breaks the URL pattern).

The frontend has lightweight Vitest coverage; most UI behavior is verified manually because the Vue/Pinia state is straightforward to inspect in the browser devtools and the failure modes are visual.

---

## What is the intended audience?

MadCop is built for **power users who have a clear sense of "I have a task" and want to do it in one window**:

- Product managers writing briefs that pull from internal docs and external research, then save as Markdown to a project folder.
- Engineers who want a chat interface that can also `read_file` a source file, `edit_file` a function, and explain what changed.
- Analysts who need a tool that can pull data from the web, structure it, and save the result to disk in a format a colleague can read.
- Researchers who want a local RAG-style workflow over their own document folder, with the model picked from a dropdown rather than dictated by the vendor.

It is **not** built for:

- Users who want a "polished" SaaS experience. The UI is functional, not pretty.
- Users who want a cloud sync model. There is no cloud sync. (If you want one, file an issue.)
- Users who are not comfortable with a config screen full of model API keys. The trade-off for "any model you want" is "you have to bring your own API key".

---

## What is the deployment story?

The intended install is:

```bash
git clone https://github.com/linmy666/madcop.git
cd madcop
pip install -e .
python -m madcop.server  # terminal 1: backend on :8765
cd desktop
bun install
bun run build:electron  # terminal 2: build the Electron app
./node_modules/electron/dist/Electron.app/Contents/MacOS/Electron \
  ./electron-dist/main.cjs --no-sandbox
```

For a packaged distribution (DMG / EXE / AppImage), see `desktop/electron-builder` config. The expected distribution is a single ~150MB binary that bundles Python via a tree-shaken `pymalloc` style or via the user's system Python, depending on platform.

The model API key is supplied by the user at first launch via the Settings panel. There is no built-in default, no anonymous telemetry, and no required account. The product is the desktop app, not a service.

---

## What is the future direction?

The roadmap in priority order:

1. **Local inference** — integrate MLX (macOS) and llama.cpp (cross-platform) so a user with a 64GB Mac can run a 70B model entirely offline. This unlocks the "no API key needed" path for privacy-sensitive users.
2. **Visual understanding** — current GLM-5.2 endpoint is text-only; once a multimodal model is wired in, the design tool and the workflow editor both benefit from "show me a screenshot, generate the component that matches it".
3. **Skill marketplace** — a "skill" is a named workflow + tool bundle (e.g. "competitor research", "weekly status report"). The current `/api/skills` endpoint is the local-only seed; the next step is opt-in cloud discovery with a rating system.
4. **Mobile companion** — a thin iOS/Android app that talks to the desktop backend over LAN. The local-first model is a good fit for this; the alternative is "no mobile at all".

Each item is independently shippable. None of them require rewriting what already works.

---

## Project structure

```
madcop/
├── desktop/                  Electron desktop (Vue 3 + Pinia + Tailwind v4)
│   ├── src/vue/              ~155 .vue files (renderer)
│   ├── public/               Static assets (mascot, icons)
│   ├── electron/             Main process scripts
│   └── theme/                CSS theme system
│
├── madcop/                   Python backend
│   ├── server/               FastAPI app, route handlers, SSE streaming
│   ├── llm/                  OpenAI-compatible client + model config
│   ├── tools/                Tool registry, built-in tools, MCP bridge
│   ├── workflow/             Workflow engine + 12 mode presets + node types
│   ├── agent_network/        Agent network API
│   ├── memory/               5-tier memory system (episodic / semantic / reflective / scenario / persona / insight)
│   ├── training/             Continuous learning (local feedback, opt-in)
│   ├── arena/                Multi-LLM comparison endpoint
│   ├── design/               AI design tool backend
│   ├── analysis/             Supply-chain analysis (CUSUM, counterfactual)
│   └── planning/             Heuristic planners (safety stock, EOQ, ABC)
│
├── docs/                     Documentation
│   ├── screenshots/          README product screenshots
│   ├── img/                  Historical assets
│   ├── design-tool/          Design tool docs
│   └── workflow-editor/      Workflow editor docs
│
├── tests/                    1,300+ pytest tests (backend-focused)
├── README.md
├── LICENSE
└── pyproject.toml
```

---

## License

MadCop is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. The full license text is in [LICENSE](LICENSE).

In short:

- You may use, modify, and distribute MadCop for personal or internal use freely.
- If you run a modified MadCop as a **network service** (e.g. a hosted AI agent workstation for your customers), you **must release the full source code** of your modified version to those users, under the same AGPL-3.0.
- Closed-source SaaS forks are explicitly prohibited by the AGPL. If you want to use MadCop in a commercial product you do not wish to open-source, contact the author for a separate commercial license.

See the additional notice in [LICENSE](LICENSE) for the full text and rationale.


## Author

Lin Ruihan (林芮翰) — Product Manager / engineer.
- GitHub: [@linmy666](https://github.com/linmy666)
- Email: chuiniu@me.com
