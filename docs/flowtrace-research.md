# Flowtrace, Agent Flow, AgentPrism & Hermes Skills — Architecture Research

> **Purpose**: Understand how three open-source trace/visualization systems work, and how the Hermes Agent skill system is structured. Extract patterns borrowable for MadCop Agent's trace/checkpoint/resume and skill system.
>
> **Date**: 2026-06-27 · **Repos analyzed**: Flowtrace (Rust+React), agent-flow (TypeScript+React), AgentPrism (React component library), Hermes Agent (Python skill system)

---

## Executive Summary

| System | What It Is | Language | Core Insight for MadCop |
|---|---|---|---|
| **Flowtrace** | File-on-disk DAG trace with git audit trail, CLI + SSE web UI | Rust + React/Next.js | "Trace as git repo" — each step writes files, state.json is the single source of truth, git commit per mutation |
| **agent-flow** | Real-time Claude Code/Codex visualizer via hooks + JSONL tailing | TypeScript + React/Next.js | Lightweight event streaming architecture — hook server → SSE → canvas rendering |
| **AgentPrism** | Reusable React components for OpenTelemetry/Langfuse trace viz | React component library | Adapter pattern for normalizing trace data → generic visualization |
| **Hermes Skills** | Markdown-based procedural memory system for AI agents | Python | YAML frontmatter + progressive disclosure + auto-save to `~/.hermes/skills/` |

---

## 1. Flowtrace (AIScientists-Dev/Flowtrace)

### What It Does

Flowtrace turns an agent's work into a **DAG of named steps** where each step writes output files to disk, the whole thing is a git repo, and a web UI renders the flow live. Instead of a stream of text that "buries you and then disappears," you get checkable, steerable, resumable work.

### Core Architecture

#### Two-layer model: Static Plan + Runtime State

```
<trace_root>/                         ← one git repository
├── .git/                              ← standard git, the audit trail
├── trace.json                         ← STATIC PLAN: steps + DAG deps + deliverable
├── steps/<step_id>/
│   ├── STEP.md                        ← per-step contract + impl hints
│   └── scripts/, resources/           ← step-local code & material
└── runs/<run_id>/
    ├── state.json                     ← RUNTIME STATE: sole source of truth
    ├── replies/NNNN.json              ← append-only structured-output stream
    └── <step_id>/                     ← run-time files (assets + scratch)
```

**Key design principle**: `trace.json` is immutable within a run. `state.json` is mutable, atomically written, and git-committed on every change. Separation of plan vs. execution state.

#### `trace.json` — The Static Plan (Rust: `schema.rs`)

```rust
pub struct Trace {
    pub id: String,
    pub title: String,
    pub description: String,
    pub version: String,                    // semver
    pub steps: BTreeMap<StepId, StepSpec>,  // DAG nodes
    pub deliverable: Deliverable,            // final output contract
    pub environment: Environment,            // optional: python/R packages
}

pub struct StepSpec {
    pub name: String,
    pub does: String,                        // one-liner for executor
    pub from_inputs: Vec<String>,            // cosmetic input labels
    pub from_steps: Vec<StepId>,             // DAG edges (dependencies)
    pub assets: Vec<String>,                 // expected output filenames
    pub asset_title: Option<String>,
    pub deprecated: bool,
}
```

The DAG is expressed purely through `from_steps` — a list of upstream step IDs. No explicit edges array.

#### `state.json` — Runtime State (Rust: `state.rs`)

```rust
pub struct RunState {
    pub name: String,
    pub started_at: DateTime<Utc>,
    pub paused: bool,                        // run-level flag
    pub aborted: bool,                       // terminal
    pub steps: BTreeMap<String, StepState>,  // per-step status
    pub deliverable: DeliverableState,
}

pub enum Status {
    Idle,
    Running { message: Option<String> },
    Blocked { message: String },             // requires message
    Done { message: Option<String> },
    Error { message: String },               // requires message
}
```

**Status is a tagged union** with kind discriminator. `Blocked` and `Error` *require* a message. Derived views (`current()`, `completed()`, `blocked()`) are computed, never stored separately.

#### Atomic Writes (Rust: `io.rs`)

```rust
pub fn atomic_write_bytes(path: &Path, tmp_prefix: &str, bytes: &[u8]) -> Result<()> {
    // write to .{prefix}.{filename}.tmp, fsync, then rename
    // notify-debouncer coalesces tmp+rename into one event
}
```

Every state mutation goes through this. No partial writes, no corruption on crash.

#### Server: Axum + SSE + File Watcher

**Routes** (`serve/mod.rs`):
```
GET    /api/traces                    — list all traces in scope
POST   /api/traces                    — create new trace
PATCH  /api/traces/{id}              — update meta
POST   /api/traces/{id}/steps        — add step
POST   /api/runs/{id}/pause          — pause run
POST   /api/runs/{id}/resume         — resume run
POST   /api/runs/{id}/steps/{step}   — set step status
GET    /api/events                    — SSE event stream
GET    /files/{*path}                — serve static assets
```

**File Watcher** (`serve/watcher.rs`): Uses `notify-debouncer-full` with 200ms debounce. Watches scope directories recursively. Classifies each filesystem event into typed SSE events:

```rust
pub enum SseEventBody {
    TraceCreated { trace_id },
    TraceUpdated { trace_id },
    RunCreated { trace_id, run_id },
    RunUpdated { trace_id, run_id },
    ReplyAppended { trace_id, run_id, seq },
    AssetChanged { trace_id, path },
    Ping,  // heartbeat every 15s
}
```

Phantom-event suppression: LRU-cached mtime check (8192 entries) to avoid WSL2 inotify phantom modify events.

**SSE → Frontend**: Frontend uses TanStack Query. SSE events invalidate specific query caches (`traceKeys.detail(...)`) so data refetches only for the affected trace/run.

### Checkpoint / Resume / Rerun

#### Pause/Resume
- `RunState.paused` is a boolean flag. Does NOT clear per-step status.
- `POST /api/runs/{id}/pause` and `/resume` endpoints.
- Pause is advisory — the trace format doesn't enforce execution semantics.

#### Rerun from Node (Steering)
The `downstream_of()` method computes the transitive set of steps that depend on a given step, in **topological order**:

```rust
pub fn downstream_of(&self, step_id: &str) -> Vec<StepId> {
    // 1. Reverse reachability: collect all steps whose from_steps includes step_id
    // 2. Kahn topological sort over the induced subgraph
    // Returns steps safe to re-run front-to-back
}
```

**How steering works**: When you change step X, you call `flowtrace show --downstream X` to get the list of steps that must re-run. You reset those steps' status to `Idle` and re-execute. Steps not downstream of X stay `Done` — their cached outputs persist.

#### Git as Audit Trail / Time Travel
Every CLI write makes exactly one git commit, scoped to declared paths:
- `state.json` + any `--asset` paths
- New reply file + cited evidence paths
- Scratch files stay untracked

The UI can time-travel: pick any step, open its version history, navigate to any past commit to see its state then.

#### Reply Stream (Append-Only)
Replies live at `runs/<run_id>/replies/NNNN.json`:

```rust
pub struct Reply {
    pub seq: u32,                           // 1-based, contiguous
    pub at: DateTime<Utc>,
    pub step_id: Option<String>,            // which step this is "about"
    pub commit: Option<String>,             // git SHA (read-time only)
    pub output: StructuredOutput,           // typed payload
}
```

Sequence allocation uses atomic `fs::hard_link` — cross-process safe with retry on collision.

### Frontend: React Flow DAG Visualization

Uses `@xyflow/react` (React Flow) for the node map. Key patterns:
- **ELK layout** (async) with sync fallback for small graphs
- **Differential updates** via refs — prevents drag state corruption when SSE pushes new data
- **Auto-zoom** to the currently-running step
- **Path highlighting** on hover — traces dependency chains

### Key Files

| File | Purpose |
|---|---|
| `crates/flowtrace-core/src/schema.rs` | Trace + StepSpec types, DAG downstream computation |
| `crates/flowtrace-core/src/state.rs` | RunState, Status enum, run lifecycle (create/pause/resume/abort) |
| `crates/flowtrace-core/src/io.rs` | Atomic write (tempfile + rename) |
| `crates/flowtrace-cli/src/main.rs` | CLI: `step`, `run`, `deliverable`, `reply`, `serve`, `show` |
| `crates/flowtrace-cli/src/serve/mod.rs` | Axum router, all API routes |
| `crates/flowtrace-cli/src/serve/watcher.rs` | File watcher → SSE event classification |
| `crates/flowtrace-cli/src/serve/events.rs` | SSE event types (TraceCreated, RunUpdated, etc.) |
| `crates/flowtrace-cli/src/reply.rs` | Append-only reply stream with atomic seq allocation |
| `frontend/src/features/trace/components/detail/node-map/` | React Flow DAG visualization |

---

## 2. Agent Flow (patoles/agent-flow)

### What It Does

Real-time visualization of Claude Code and Codex agent execution. Watches agent sessions via two channels — an HTTP hook server and JSONL transcript tailing — and renders an interactive canvas showing agents, tool calls, branching, and return flows as they happen.

### Core Architecture

#### Dual Event Source Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│ Claude Code     │────▶│  Hook Server │────▶│   Relay     │
│ (hooks config)  │     │  (HTTP POST) │     │             │
└─────────────────┘     └──────────────┘     │             │
                                           │  SSE Broadcast │──▶ Browser
┌─────────────────┐     ┌──────────────┐     │             │
│ ~/.claude/      │────▶│   Session    │────▶│             │
│ projects/*.jsonl│     │   Watcher    │     └─────────────┘
│ ~/.codex/       │     │  (file tail) │
│ sessions/*.jsonl│     └──────────────┘
└─────────────────┘
```

**Two sources can be active simultaneously** — the runtime routes hook events around the watcher when the watcher is already parsing that session's transcript, avoiding duplicate events.

#### Event Protocol (`protocol.ts`)

```typescript
export type AgentEventType =
  | 'agent_spawn' | 'agent_complete' | 'agent_idle'
  | 'message' | 'context_update' | 'model_detected'
  | 'tool_call_start' | 'tool_call_end'
  | 'subagent_dispatch' | 'subagent_return'
  | 'permission_requested' | 'error'

export interface AgentEvent {
  time: number         // seconds since session start
  type: AgentEventType
  payload: Record<string, unknown>
  sessionId?: string
}
```

Events are **time-relative** (seconds from session start), not absolute timestamps. This makes replay independent of wall clock.

#### Hook Server (`hook-server.ts`)

Lightweight HTTP server (port 0 = OS-assigned) that receives Claude Code hook events:

```typescript
interface HookPayload {
  session_id: string
  hook_event_name: string  // PreToolUse, PostToolUse, SubagentStart, etc.
  tool_name?: string
  tool_input?: Record<string, unknown>
  tool_response?: string | { content: string }
  agent_id?: string
  agent_type?: string
}
```

**Key design**: Always returns HTTP 200 with empty body — it's observing, not blocking. Empty body = "success, no output" per Claude Code docs.

**Discovery mechanism**: The extension writes a discovery file (`~/.claude/agent-flow/`) containing the port. The hook script reads this at invocation time — no port hardcoded in settings.json.

#### Relay Server (`relay.ts`)

Shared module used by both the dev server and standalone `npx agent-flow-app`:

- **SSE client management**: `Set<http.ServerResponse>`, broadcast on event
- **Event buffering**: Per-session `Map<string, AgentEvent[]>`, capped at 5000 events
- **Session lifecycle**: `started`, `ended`, `updated` broadcast events
- **Inactivity detection**: Timer-based — if no activity for N seconds, emit `agent_complete`

#### Codex Support

Reads `~/.codex/sessions/**/rollout-*.jsonl` (respects `CODEX_HOME`). Surfaces tool calls, reasoning, and authoritative token counts from Codex's own event stream. Separate `CodexSessionWatcher` and `codex-rollout-parser.ts`.

### Visualization: Canvas-Based Rendering

Unlike Flowtrace (React Flow DAG) or AgentPrism (tree view), agent-flow uses a **custom canvas renderer**:

```
web/components/agent-visualizer/canvas/
├── draw-agents.ts          — agent node rendering
├── draw-tool-calls.ts      — tool call bubbles
├── draw-edges.ts           — connection lines
├── draw-bubbles.ts         — message bubbles
├── draw-cost.ts            — cost badges
├── draw-discoveries.ts     — file attention heatmap
├── draw-particles.ts       — animated effects
├── draw-effects.ts         — visual feedback
├── hit-detection.ts        — click/hover detection
├── render-cache.ts         — canvas caching
└── detect-state-changes.ts — differential rendering
```

This is a **bespoke real-time canvas** — not a graph library. Optimized for live streaming with particle effects and animations.

### Key Files

| File | Purpose |
|---|---|
| `extension/src/protocol.ts` | Event types, AgentEvent, TranscriptEntry, subagent state |
| `extension/src/hook-server.ts` | HTTP server receiving Claude Code hooks |
| `extension/src/claude-runtime.ts` | Wires hook server + session watcher together |
| `extension/src/session-watcher.ts` | Tails `~/.claude/projects/*.jsonl` |
| `extension/src/codex-session-watcher.ts` | Tails `~/.codex/sessions/**/*.jsonl` |
| `extension/src/codex-rollout-parser.ts` | Parses Codex rollout format |
| `extension/src/transcript-parser.ts` | Parses Claude Code JSONL transcripts |
| `extension/src/tool-summarizer.ts` | Summarizes tool inputs/outputs for display |
| `extension/src/token-estimator.ts` | Token count estimation |
| `scripts/relay.ts` | Shared SSE relay (dev + standalone app) |
| `app/src/server.ts` | Standalone HTTP server (SSE + static) |
| `web/components/agent-visualizer/canvas/` | Custom canvas rendering |

### Checkpoint/Resume

**Agent Flow has no checkpoint/resume concept.** It's purely observational — it visualizes what already happened. There's no way to pause, rerun, or steer from the UI. It's a debugger/viewer, not an orchestrator.

---

## 3. AgentPrism (evilmartians/agent-prism)

### What It Does

An open-source React component library for visualizing AI agent traces. Plug in OpenTelemetry or Langfuse data and get a hierarchical timeline tree showing LLM calls, tool executions, and agent workflows. Pure presentation — no event capture, no execution control.

### Core Architecture

#### Package Structure (Monorepo)

```
packages/
├── types/          — TraceRecord, TraceSpan, status enums, categories
├── data/           — SpanAdapter interface + OpenTelemetry/Langfuse adapters
├── ui/             — React components (TraceViewer, TreeView, DetailsView, SpanCard)
├── storybook/      — Interactive component playground
└── saas/           — SaaS demo app
```

#### Type System (`packages/types/src/types/index.ts`)

```typescript
export type TraceSpanStatus = "success" | "error" | "pending" | "warning";

export type TraceSpanCategory =
  | "llm_call" | "tool_execution" | "agent_invocation"
  | "chain_operation" | "retrieval" | "embedding"
  | "create_agent" | "span" | "event" | "guardrail" | "unknown";

export type TraceSpan<TMetadata = Record<string, unknown>> = {
  id: string;
  title: string;
  startTime: Date;
  endTime: Date;
  duration: number;
  type: TraceSpanCategory;
  raw: string;                           // original JSON
  input?: string;
  output?: string;
  attributes?: TraceSpanAttribute[];
  children?: TraceSpan<TMetadata>[];     // nested spans = tree
  status: TraceSpanStatus;
  cost?: number;
  tokensCount?: number;
  metadata?: TMetadata;
};

export type TraceRecord = {
  id: string;
  name: string;
  spansCount: number;
  durationMs: number;
  agentDescription: string;
  totalCost?: number;
  totalTokens?: number;
  startTime?: number;
};
```

**Key**: `children?: TraceSpan[]` — traces are **nested trees**, not flat DAGs. This matches OpenTelemetry's span model.

#### Adapter Pattern (`packages/data/src/types.ts`)

```typescript
export interface SpanAdapter<TRawDocument, TRawSpan> {
  convertRawDocumentsToSpans(documents: TRawDocument[]): TraceSpan[];
  convertRawSpansToSpanTree(spans: TRawSpan[]): TraceSpan[];
  convertRawSpanToTraceSpan(span: TRawSpan): TraceSpan;
  getSpanDuration(span: TRawSpan): number;
  getSpanCost(span: TRawSpan): number;
  getSpanTokensCount(span: TRawSpan): number;
  getSpanInputOutput(span: TRawSpan): InputOutputData;
  getSpanStatus(span: TRawSpan): TraceSpanStatus;
  getSpanCategory(span: TRawSpan): TraceSpanCategory;
}
```

**Two built-in adapters**:
1. `openTelemetrySpanAdapter` — converts OTel resourceSpans to TraceSpan trees
2. `langfuseSpanAdapter` — converts Langfuse observations

The adapter normalizes any trace format into the generic `TraceSpan` tree. **This is the key extensibility point** — you can write an adapter for any trace format.

#### TraceViewer Component

The main entry point provides a complete UI:
- **TraceList** — browse multiple traces
- **TreeView** — hierarchical span visualization with search and expand/collapse
- **DetailsView** — inspect individual span attributes, input/output, raw data
- **Responsive** — separate desktop/mobile layouts

```tsx
<TraceViewer
  data={[{
    traceRecord: yourTraceRecord,
    spans: openTelemetrySpanAdapter.convertRawDocumentsToSpans(yourData),
  }]}
/>
```

#### Data Utilities (`packages/data/src/index.ts`)

```typescript
export { flattenSpans } from "./common/flatten-spans.js";
export { filterSpansRecursively } from "./common/filter-spans-recursively.js";
export { getTimelineData } from "./common/get-timeline-data.js";
export { findTimeRange } from "./common/find-time-range.js";
export { getDurationMs, formatDuration } from "./common/...";
```

### Key Files

| File | Purpose |
|---|---|
| `packages/types/src/types/index.ts` | Core types: TraceSpan, TraceRecord, categories |
| `packages/data/src/types.ts` | SpanAdapter interface |
| `packages/data/src/open-telemetry/adapter.ts` | OTel → TraceSpan conversion |
| `packages/data/src/langfuse/adapter.ts` | Langfuse → TraceSpan conversion |
| `packages/ui/src/components/TraceViewer/TraceViewer.tsx` | Main viewer component |
| `packages/ui/src/components/TreeView.tsx` | Hierarchical span tree |
| `packages/ui/src/components/DetailsView/` | Span detail inspector |
| `packages/ui/src/components/SpanCard/` | Individual span card |

### Checkpoint/Resume

**None.** AgentPrism is purely a visualization library. It reads trace data (from OTel, Langfuse, or any adapter) and renders it. No execution control, no pause/resume, no rerun.

---

## 4. Hermes Agent Skill System

### What It Is

A markdown-based procedural memory system. Skills are directories containing a `SKILL.md` file with YAML frontmatter (metadata) + markdown body (instructions). The agent loads skill metadata on startup, injects full content when relevant, and can create/edit skills to capture proven approaches.

### Skill Structure

```
~/.hermes/skills/                       ← single source of truth
├── .bundled_manifest                   ← hash manifest of bundled skills
├── .hub/                               ← hub-installed skills
├── .archive/                           ← curator-archived skills
├── .usage.json                         ← skill usage tracking
├── .webui-managed-skills.json          ← web UI managed skills
├── creative/                           ← category folders
│   └── <skill-name>/
│       └── SKILL.md
├── software-development/
│   └── <skill-name>/
│       ├── SKILL.md
│       ├── references/                 ← supporting docs
│       ├── templates/                  ← output templates
│       └── assets/                     ← supplementary files
└── madcop-development/
    └── SKILL.md
```

### SKILL.md Format

```yaml
---
name: skill-name                          # Required, max 64 chars
description: Brief description            # Required, max 1024 chars
version: 1.0.0                            # Optional
license: MIT                              # Optional
platforms: [macos]                        # Optional — restrict to OS
prerequisites:                            # Optional — runtime requirements
  env_vars: [API_KEY]
  commands: [curl, jq]
metadata:                                 # Optional, arbitrary
  hermes:
    tags: [fine-tuning, llm]
    related_skills: [peft, lora]
    config:                               # Skill-declared config vars
      - key: wiki.path
        description: Path to wiki
        default: "~/wiki"
when_to_use:                              # Optional — activation hints
  - When user asks about X
  - When working on Y
---

# Skill Title

Full instructions here...
```

### How Skills Are Loaded (`skills_tool.py` + `skill_utils.py`)

#### 1. Discovery (Startup)
```python
# Walks all skill directories (local + external_dirs from config)
for skills_dir in get_all_skills_dirs():
    for skill_file in iter_skill_index_files(skills_dir, "SKILL.md"):
        frontmatter, _ = parse_frontmatter(skill_file.read_text())
        # Check: disabled? platform match? prerequisites met?
```

**Progressive disclosure** (3 tiers):
- **Tier 1**: `skills_list()` — returns metadata only (name + description). Token-efficient.
- **Tier 2**: `skill_view("name")` — loads full SKILL.md body.
- **Tier 3**: `skill_view("name", "references/api.md")` — loads linked files on demand.

#### 2. Preprocessing (`skill_preprocessing.py`)
Before injection into the prompt, skill content is preprocessed:

```python
def preprocess_skill_content(content, skill_dir, session_id, skills_cfg):
    # 1. Template variable substitution: ${HERMES_SKILL_DIR} → absolute path
    if cfg.get("template_vars", True):
        content = substitute_template_vars(content, skill_dir, session_id)
    # 2. Inline shell expansion: !`date +%Y-%m-%d` → "2026-06-27"
    if cfg.get("inline_shell", False):
        content = expand_inline_shell(content, skill_dir, timeout)
    return content
```

#### 3. Platform Matching (`skill_utils.py`)
```python
PLATFORM_MAP = {"macos": "darwin", "linux": "linux", "windows": "win32"}

def skill_matches_platform(frontmatter):
    platforms = frontmatter.get("platforms")
    if not platforms:
        return True  # compatible with all (default)
    for platform in platforms:
        mapped = PLATFORM_MAP.get(platform, platform)
        if sys.platform.startswith(mapped):
            return True
    return False
```

#### 4. Conditional Activation (`skill_utils.py`)
Skills can declare activation conditions in frontmatter:
```yaml
metadata:
  hermes:
    fallback_for_toolsets: [...]   # activate if these toolsets are missing
    requires_toolsets: [...]       # activate only if these exist
    fallback_for_tools: [...]
    requires_tools: [...]
```

### How Skills Are Managed (`skill_manager_tool.py`)

The agent can create, edit, patch, and delete skills:

```python
# Actions:
#   create     — Create new skill (SKILL.md + directory)
#   edit       — Replace SKILL.md content (full rewrite)
#   patch      — Targeted find-and-replace
#   delete     — Remove skill entirely
#   write_file — Add/overwrite supporting file
#   remove_file — Remove supporting file
```

**Security**: External hub installs always get security-scanned. Agent-created skills only scanned when `skills.guard_agent_created` is on (default off — the agent can already execute the same code via terminal).

**Pin protection**: Skills can be pinned to prevent deletion (both curator auto-archive and agent delete). Pin doesn't block editing — only irrecoverable loss.

### Auto-Save Mechanism

Skills are the agent's **procedural memory**. When the agent discovers a successful approach, it captures it:

1. Agent calls `skill_manage(action="create", name="...", description="...", content="...")`
2. System creates `~/.hermes/skills/<name>/SKILL.md`
3. Skill is immediately available via `skills_list()` and `skill_view()`
4. On next session, skill metadata appears in the startup banner

**No separate "save" step** — the create/edit/patch actions write directly to disk using `atomic_replace()`.

### Usage Tracking

`~/.hermes/skills/.usage.json` tracks skill usage (when viewed, how often). Used by:
- The curator (auto-archive unused skills)
- The pin system (prevent deletion of important skills)
- Telemetry (opt-in)

### Key Files

| File | Purpose |
|---|---|
| `~/.hermes/hermes-agent/tools/skills_tool.py` | `skills_list()`, `skill_view()` — reading skills |
| `~/.hermes/hermes-agent/tools/skill_manager_tool.py` | `skill_manage()` — create/edit/delete skills |
| `~/.hermes/hermes-agent/agent/skill_utils.py` | Frontmatter parsing, platform matching, discovery |
| `~/.hermes/hermes-agent/agent/skill_preprocessing.py` | Template vars, inline shell expansion |
| `~/.hermes/hermes-agent/agent/skill_commands.py` | Slash command (`/skill-name`) invocation |
| `~/.hermes/hermes-agent/tools/skills_guard.py` | Security scanning for hub installs |
| `~/.hermes/hermes-agent/tools/skill_usage.py` | Usage tracking |

---

## 5. What We Can Borrow for MadCop Agent

### From Flowtrace

#### ✅ BORROW: File-as-state + Git audit trail
```
madcop/traces/<trace_id>/
├── trace.json                    ← plan (steps, deps, deliverable)
├── runs/<run_id>/state.json      ← runtime state (atomic write)
└── runs/<run_id>/replies/        ← append-only output stream
```

**Why**: SQLite is great for queries, but git gives you free time-travel, diffing, and human-readable audit. Use files for trace state, SQLite for memory/search.

#### ✅ BORROW: Status as tagged enum
```python
class StepStatus:
    IDLE = "idle"
    RUNNING = "running"      # + optional message
    BLOCKED = "blocked"      # + required message (what's needed)
    DONE = "done"            # + optional takeaway
    ERROR = "error"          # + required message
```

**Why**: The `Blocked` status with a required message is brilliant for human-in-the-loop. The agent can pause and say "I need X to continue."

#### ✅ BORROW: `downstream_of()` for steering
```python
def downstream_of(steps: dict, step_id: str) -> list[str]:
    """Topological sort of all steps depending on step_id.
    When you change step X, these are the steps that must re-run."""
```

**Why**: This is the core of "fix one step, only re-run what depends on it." Simple graph algorithm, huge UX impact.

#### ✅ BORROW: SSE event classification
Instead of polling, push typed events:
```python
SSE_EVENTS = {
    "step_updated": {"trace_id", "run_id", "step_id", "status"},
    "reply_appended": {"trace_id", "run_id", "seq"},
    "asset_changed": {"trace_id", "path"},
}
```

**Why**: MadCop already has SSE for chat streaming. Extending it to trace events is natural.

#### ⚠️ ADAPT: Atomic write pattern
Flowtrace uses tempfile + rename in Rust. In Python:
```python
def atomic_write_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(path)  # atomic on POSIX
```

### From Agent Flow

#### ✅ BORROW: Hook-based event capture
Agent Flow's hook server receives structured events from Claude Code. MadCop can emit similar events from its agent loop:

```python
# In madcop/agent/loop.py, after each step:
emit_event({
    "type": "tool_call_start",
    "tool": tool_name,
    "args": args,
    "timestamp": time.time(),
    "step_id": current_step_id,
})
```

**Why**: This gives real-time visualization without file-watcher overhead.

#### ✅ BORROW: Time-relative events
Events use `time: seconds_since_session_start` not absolute timestamps. Makes replay portable.

#### ⚠️ ADAPT: Canvas rendering is overkill
Agent Flow's custom canvas with particles is cool but heavy. MadCop should use React Flow (like Flowtrace) for the DAG, and reserve canvas for specific visualizations (token usage over time, etc.).

### From AgentPrism

#### ✅ BORROW: Adapter pattern for trace normalization
```python
class TraceAdapter(ABC):
    @abstractmethod
    def to_span_tree(self, raw_data: Any) -> list[TraceSpan]:
        """Convert any trace format to our generic span tree."""

class MadCopTraceAdapter(TraceAdapter):
    def to_span_tree(self, raw_data: dict) -> list[TraceSpan]:
        # Convert madcop's internal trace format to display format
```

**Why**: Decouples trace storage from visualization. Change storage format without breaking the UI.

#### ✅ BORROW: Span categories
```python
SPAN_CATEGORIES = [
    "llm_call",         # model invocation
    "tool_execution",   # tool call
    "agent_invocation", # sub-agent dispatch
    "retrieval",        # memory search
    "planning",         # plan creation/modification
    "reflection",       # self-evaluation
]
```

**Why**: Color-coding by category makes traces scannable.

#### ⚠️ ADAPT: Tree vs DAG
AgentPrism uses nested trees (parent-child spans). Flowtrace uses DAGs. **MadCop should use DAG** — our steps have explicit dependencies, not just nesting. But we can render a tree view *within* a step (showing the agent's internal tool call sequence as a nested tree).

### From Hermes Skills

#### ✅ BORROW: YAML frontmatter format
```yaml
---
name: madcop-trace-builder
description: Build and manage traces for complex multi-step tasks
when_to_use:
  - When the user asks for a complex task with verifiable steps
  - When checkpoint/resume is needed
metadata:
  tags: [trace, workflow, checkpoint]
---
```

**Why**: Proven format. Compatible with the broader skill ecosystem.

#### ✅ BORROW: Progressive disclosure
- Tier 1: Skill list shows name + description (metadata only)
- Tier 2: Full SKILL.md loaded when skill is activated
- Tier 3: Supporting files loaded on demand

**Why**: With 50+ skills, loading all content at once would blow the context window.

#### ✅ BORROW: Template variables + inline shell
```markdown
Working directory: ${MADCOP_TRACE_DIR}
Current date: !`date +%Y-%m-%d`
```

**Why**: Skills become dynamic without code.

#### ⚠️ ADAPT: Auto-save with guard rails
Hermes lets the agent create skills freely (guard off by default). MadCop should require human approval for skill creation — our traces are higher-stakes.

### Code Patterns Worth Adapting (Not Copying)

#### Pattern 1: Plan/State Separation
```python
# trace.json (immutable within a run)
@dataclass
class TracePlan:
    id: str
    steps: dict[str, StepSpec]  # step_id → spec
    deliverable: DeliverableSpec

# state.json (mutable, atomic writes)
@dataclass
class RunState:
    run_id: str
    started_at: datetime
    paused: bool
    steps: dict[str, StepStatus]  # step_id → current status
```

#### Pattern 2: Append-Only Reply Stream
```python
def append_reply(trace_root: Path, run_id: str, output: StructuredOutput) -> int:
    """Append a structured output to the reply stream.
    Returns the assigned sequence number."""
    seq = next_seq(trace_root, run_id)
    reply = Reply(seq=seq, at=datetime.utcnow(), output=output)
    path = trace_root / "runs" / run_id / "replies" / f"{seq:04d}.json"
    atomic_write_json(path, reply.dict())
    return seq
```

#### Pattern 3: Event-Driven UI Updates
```python
# Backend: classify filesystem events → typed SSE
def classify_event(path: Path) -> SSEEvent:
    if path.name == "state.json":
        return StepUpdated(trace_id=..., run_id=..., ...)
    elif path.parent.name == "replies":
        return ReplyAppended(trace_id=..., run_id=..., seq=...)
    elif path.name == "trace.json":
        return TraceUpdated(trace_id=...)

# Frontend: invalidate specific query caches
useSSEEvent((event) => {
    if (event.type === 'step_updated') {
        queryClient.invalidateQueries(['run', event.run_id])
    }
})
```

#### Pattern 4: Skill as Markdown + Frontmatter
```python
def load_skill(skill_dir: Path) -> Skill:
    content = (skill_dir / "SKILL.md").read_text()
    frontmatter, body = parse_frontmatter(content)
    return Skill(
        name=frontmatter["name"],
        description=frontmatter["description"],
        when_to_use=frontmatter.get("when_to_use", []),
        body=body,
        dir=skill_dir,
    )
```

#### Pattern 5: Adapter for Visualization
```python
class TraceToVisualizationAdapter:
    """Converts MadCop's trace format to a visualization-ready structure."""

    def to_dag_nodes(self, trace: TracePlan, state: RunState) -> list[Node]:
        return [
            Node(
                id=step_id,
                label=spec.name,
                status=state.steps.get(step_id, StepStatus.IDLE),
                dependencies=spec.from_steps,
            )
            for step_id, spec in trace.steps.items()
        ]

    def to_span_tree(self, replies: list[Reply]) -> list[Span]:
        """Convert reply stream to nested span tree for detail view."""
```

---

## 6. Recommended Architecture for MadCop Agent

Based on this research, here's the recommended approach:

### Trace System
1. **Storage**: Files on disk (like Flowtrace) — `trace.json` (plan) + `state.json` (runtime) + `replies/` (output stream)
2. **Audit**: Git commits per mutation (time-travel, diffing, human-readable)
3. **Visualization**: React Flow DAG (like Flowtrace) for the step graph; AgentPrism-style tree for within-step detail
4. **Events**: SSE streaming (extend existing MadCop SSE) with typed events
5. **Steering**: `downstream_of()` for selective rerun; `Blocked` status for human-in-the-loop

### Skill System
1. **Format**: Markdown + YAML frontmatter (compatible with Hermes format)
2. **Storage**: `~/.madcop/skills/` or project-local `.madcop/skills/`
3. **Loading**: Progressive disclosure (metadata → full content → linked files)
4. **Auto-save**: Agent can create skills, but require human confirmation
5. **Preprocessing**: Template variables (`${TRACE_DIR}`) + optional inline shell

### Integration
- Traces reference skills: each step's `STEP.md` can invoke a skill
- Skills can create traces: a "trace-builder" skill that converts a task into a DAG
- Memory layer: completed traces feed back into episodic memory (L2)

---

*End of research document. Generated 2026-06-27 from analysis of Flowtrace (commit HEAD), agent-flow (commit HEAD), AgentPrism (commit HEAD), and Hermes Agent skill system (installed at `~/.hermes/hermes-agent/`).*
