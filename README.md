# madcop

> A personal AI agent that lives in your terminal, talks to any LLM,
> remembers what you taught it, and gets smarter the more you use it.
> Runs in one process. Stores everything locally. No cloud, no team,
> no platform.

[![Tests](https://img.shields.io/badge/tests-467%20passing-brightgreen)](#tests)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#requirements)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)
[![PyPI](https://img.shields.io/badge/pypi/v/madcop)](https://pypi.org/project/madcop/)


<p align="center">
  <img src="docs/img/characters/madcop-mascot.png" alt="madcop mascot" width="320">
</p>

## What is madcop?

**madcop** is a personal AI agent for your terminal. You point it at
a goal, it walks that goal through a plan-execute-replan loop,
dispatches to specialised sub-agents when it helps, and writes what
it learned to a local memory store. Next time you ask a similar
question, it already knows.

It works with any OpenAI-compatible LLM endpoint (OpenAI, NVIDIA
NIM, GLM, DeepSeek, Qwen, local Ollama). It does not need a
gateway, a database server, or a cloud account. One `pip install`,
one process, one SQLite file.

The name is short for **mad cop** — a cop that goes mad for
anomalies. Not in a punitive sense, but in the sense of "won't let
a single anomaly go untraced to its source". The framework was
originally a supply-chain anomaly detector; v0.6.0 generalised it
into a personal agent. The supply-chain skills are still there,
but they're no longer the only thing it does.

## What's new in v0.6.0 + v0.7.0

| v0.5.0 | v0.6.0 + v0.7.0 |
|--------|----------------|
| Fixed linear graph (ingest → detect → counterfactual → decision → summarise) | Plan-execute-replan loop with 4 modes (flash / standard / pro / ultra) + sub-agent fan-out |
| Single LLM call per session | Multi-model orchestration: auto router picks T1/T2/T3 per step, manual override via `~/.madcop/config.yaml` |
| Single LLM provider (OpenAI-compat) | 5 default providers, YAML config, env-var resolution, no vendor lock-in |
| 2-layer memory (working + episodic) | 4-layer memory: L1 working / L2 episodic / L3 semantic / L4 reflective, cross-layer retriever with time-decay, 3-mechanism self-growth engine |
| No self-growth | M1 distillation + M2 feedback reflection + M3 meta-pattern mining — the agent gets smarter with use |
| No CLI for free-text goals | `madcop plan "..." --llm` runs the new loop end-to-end with a real LLM |
| No sub-agents | Lead agent dispatches plan steps to `general-purpose` or `bash` sub-agents in parallel (capped 3), with context isolation and race-safe state machine. **v0.7.2**: `RoutingStepExecutor` lets you write `PlanStep(subagent="general-purpose")` and the main loop dispatches for you — no more 20-line router_fn hack. |
| No config file | `madcop config init` writes a default `~/.madcop/config.yaml`; `madcop config show` resolves it |
| Ad-hoc eval | EvalRunner v2: cross-run trend tracking, robustness probing, adversarial safety checks |
| 214 tests | **674 tests** |

### Quick taste

Plan a goal through the new loop. With a real LLM:

```bash
export MADCOP_OPENAI_BASE_URL=https://your-endpoint/v1
export MADCOP_OPENAI_API_KEY=sk-...
export MADCOP_OPENAI_MODEL=your-model
pip install madcop
madcop config init
madcop plan "Why did OMS cancellations spike in the last 24 hours?" --llm --mode pro
```

<p align="center">
  <img src="docs/img/banner.png" alt="madcop CLI welcome" width="720">
</p>

Sub-agent fan-out (v0.7.0) — dispatch a plan to a sub-agent:

```python
from madcop.agent import PlanStep, Plan, ExecutionMode, PlanExecuteLoop, TrivialPlanner, FnStepExecutor
from madcop.agent.subagent import SubagentExecutor, ExecutorConfig, LLMRunner
from madcop.llm import OpenAICompatClient

client = OpenAICompatClient()
subagent_executor = SubagentExecutor(
    runner=LLMRunner(client, max_tokens=512, temperature=0.0),
    config=ExecutorConfig(max_concurrent=3),
    parent_tools=("read", "write", "bash"),
)

plan = Plan(steps=[
    PlanStep(name="ingest", action="gather the last 24h of OMS events"),
    PlanStep(name="analyse", action="classify findings by severity", subagent="general-purpose"),
    PlanStep(name="report", action="build a CSV summary", subagent="bash"),
])

loop = PlanExecuteLoop(my_planner, my_inline_executor)
result = loop.run("diagnose OMS cancel spike")
```

### Design philosophy (v0.6.0+)

Five principles shaped v0.6.0 and v0.7.0. They're not features; they're
decisions about what kind of software madcop wants to be.

**1. Personal-first, not team-first.** madcop runs on a laptop. One
process, one SQLite file, one operator. No gateway, no Redis, no
Kubernetes. If you need a multi-tenant agent platform, you're
looking for the wrong tool — and that's fine, those exist.

**2. Local-first, no cloud lock-in.** Memory is a SQLite file at
`~/.madcop/memory.db`. Trends are a JSONL file. Eval results are
JSON. You can `cat` everything, `grep` everything, and back up
everything with `rsync`. There is no Langfuse or LangSmith to log
into.

**3. Self-growth over time.** madcop is the only mainstream AI agent
framework (that we know of) where the memory layer is the
*primary* deliverable, not an afterthought. The 3-mechanism 成长
engine means that the longer you use madcop, the more it knows
about your domain, your preferences, and your meta-strategies.

**4. Cost-aware routing as a first-class concern.** Every step of
every run can pick a different model. The auto router scores each
step on 4 signals (structural / domain / context / user) and
picks T1 (reasoning) / T2 (balanced) / T3 (fast). Manual override
per provider in `~/.madcop/config.yaml`. Built because shipping
"always-call-gpt-4" demos is a lie.

**5. The harness is small enough to read in one sitting.** The whole
plan-execute-replan loop is ~90 lines. The router is ~300 lines.
The memory layer is 6 modules averaging 200 lines each. The
sub-agent executor is ~270 lines. We picked this deliberately —
every line of indirection is a line you can't debug.

## What's new in v0.7.0

v0.7.0 adds a **sub-agent layer** to the v0.6.0 plan-execute loop.
The lead agent can now dispatch steps to specialised sub-agents
that run in parallel, in isolated contexts, and cannot recursively
spawn more sub-agents.

The pieces:

- `SubagentSpec` — a frozen dataclass describing a sub-agent (name,
  description, system_prompt, tools, disallowed_tools, max_turns,
  timeout). Two ships with v0.7.0: `general-purpose` (multi-step
  reasoning, inherits parent tools) and `bash` (shell command
  execution, tools = `("bash",)`).
- `SubagentResult` + `SubagentStatus` — race-safe state machine with
  `try_set_terminal()`. The first writer of a terminal status
  wins; late writes are no-ops. The four terminal states are
  `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`.
- `SubagentExecutor` — runs sub-agents on a `ThreadPoolExecutor`
  capped at 3 (clamped to `[1, 4]`). Each sub-agent gets a deep
  copy of the parent's context (no leakage back). Cancellation is
  cooperative: set `holder.cancel_event`, the runner checks it
  between LLM calls.
- `PlanStep.subagent` — set this on any plan step to dispatch the
  step to a sub-agent instead of running it inline. The lead
  agent's plan-execute loop routes sub-agent steps through the
  executor; inline steps go through the v0.6.0 path.
- `LLMRunner` — a real-LLM-backed Runner that wraps any
  `ChatClient` and adapts it to the sub-agent Runner protocol.

Three things we deliberately did not do:

- Sub-agents cannot spawn sub-agents. The `task` tool is hard-coded
  as disallowed; this prevents recursive explosions.
- We did not implement custom sub-agents from user config. That's
  v0.7.1.
- We did not build an async executor. The thread pool is enough
  for personal use; if you need asyncio, open an issue.

## What's new in v1.0.0-rc.1 (Middleware chain)

madcop v1.0.0 introduces a **middleware chain** — an extension point
in the plan-execute loop where you can observe, mutate, and halt runs
at five well-defined hook points:

  - `plan_start`  — before the planner runs
  - `step_start`  — before each step's executor runs
  - `step_end`    — after each step's executor returns
  - `replan`      — before a new plan is installed
  - `plan_end`    — after the final outcome is collected

This is inspired by the middleware pattern in production agent
frameworks, but kept small and local-first. The whole chain
infrastructure is ~150 lines; the four included middlewares
are ~600 lines total.

### v1.0.0 design philosophy: Qian control theory

Each middleware must respect three invariants from Qian Xuesen's
engineering cybernetics:

  1. **Closed-loop feedback** — every step outcome is observed
     before the next one starts
  2. **Early correction** — if a step is clearly broken (3 identical
     retries, rate-limit error repeated 3x), the middleware halts
     before the next iteration burns more compute
  3. **Controllability** — progress is logged every N steps, so
     the user can see what the loop is doing without tracing

The included `QianControlMiddleware` enforces these. Every other
middleware should follow the same pattern.

### v1.0.0 included middlewares

| Middleware | Purpose | LOC | Tests |
|-----------|---------|-----|-------|
| `MiddlewareChain` | The chain itself — composition + ordering + halt semantics | ~80 | — |
| `LoggingMiddleware` | Logs every hook at DEBUG | ~15 | — |
| `QianControlMiddleware` | The invariants: closed-loop, early correction, progress | ~80 | 11 |
| `TodoMiddleware` | Lets the LLM write its own plan via a `todo_update` tool call | ~180 | 17 |
| `LoopDetectionMiddleware` | Halts after N identical consecutive steps (or K-of-M duplicate outputs) | ~110 | 11 |
| `ClarificationMiddleware` | Asks the user when the goal is too short / too vague | ~150 | 20 |

Total v1.0.0-rc.1: 5 new modules, 70 new tests, 634 total.

### Writing your own middleware

A middleware is just a callable with a name:

```python
from madcop.agent.middleware import HookContext, HOOK_STEP_END, MiddlewareChain

class MyMiddleware:
    name = "my_mw"

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook == HOOK_STEP_END and ctx.outcome and not ctx.outcome.success:
            print(f"step {ctx.step.name} failed: {ctx.outcome.error}")

chain = MiddlewareChain([MyMiddleware()])
```

For a full example (with `ctx.directives.append(Directive(kind='HALT', ...))`
to stop the run), see `tests/agent/test_middleware.py`.

## What's new in v1.1.0-rc.1 (Sandbox + Deferred loading)

v1.1.0 adds two infrastructure pieces that are easy to bolt on after
the middleware chain is in place:

### SubprocessSandbox + BashTool

A safe-ish way to run shell commands without a full Docker container.
Defenses (cheap, no container needed):

- **Timeout** — every command has a hard wall-clock cap
- **Working-directory allowlist** — `cwd` must be inside `allowed_dirs`
- **Environment filter** — only vars in `allowed_env_vars` pass through
- **No shell=True by default** — argv is split via shlex
- **Output size cap** — stdout/stderr truncated to `max_output_chars`

```python
from pathlib import Path
from madcop.tools import SubprocessSandbox, BashTool

sandbox = SubprocessSandbox(
    allowed_dirs=[Path.home() / "projects"],
    default_timeout_s=30,
    max_output_chars=50_000,
)
tool = BashTool(sandbox)
# The LLM can now call bash(command="ls -la", cwd="~/projects")
```

22 tests in `tests/tools/test_sandbox.py` cover happy path, timeout,
truncation, env filter, cwd restriction, and the BashTool wrapper.

For real production isolation, use a Docker container. The sandbox
is enough for personal/local use.

### DeferredToolCatalog

When you have 100+ tools, putting them all in the LLM prompt at once
bloats tokens and confuses the model. The `DeferredToolCatalog`
solves this with a "load on demand" pattern:

```python
from madcop.tools import DeferredToolCatalog, EchoTool

catalog = DeferredToolCatalog()
catalog.register(EchoTool(), category="demo", description="echoes text")
catalog.register(ReadFileTool(), category="filesystem", description="read a file")
catalog.register(HttpGetTool(), category="network", description="fetch URL")

# The LLM starts with an EMPTY registry. It asks the catalog
# to search for what it needs:
matches = catalog.search("read a file")
# → [("filesystem", ["read_file"])]

# Then load the category:
catalog.load_category("filesystem")
# Now catalog.registry contains ReadFileTool.
```

Search is cheap (string match on names + descriptions, no LLM call).
Loaded categories are tracked so you can see what the agent
actually used in a run.

18 tests in `tests/tools/test_deferred.py` cover registration, search
scoring, load semantics, and integration with the LLM tool-call flow.

## What madcop actually does

Five end-to-end demos ship with the repo. Run them with `python -m madcop ...`
or directly with `python examples/...py`. The first four use madcop's
own supply-chain rule pack; the last one is the new plan-execute loop
that you point at any goal.

| # | Demo | How to run |
|---|------|------------|
| 1 | v0.5.0 LangGraph agent on cold-chain stream | `python -m madcop run agent` |
| 2 | v0.6.0 plan-execute loop on a free-text goal (mock) | `python -m madcop plan "your goal"` |
| 3 | v0.6.0 plan-execute loop on a free-text goal (real LLM) | `MADCOP_OPENAI_API_KEY=*** python -m madcop plan "your goal" --llm` |
| 4 | v0.7.0 sub-agent fan-out (mock) | `python examples/v070_subagent_demo.py` |
| 5 | v0.7.1 real-LLM golden-set (3 scenarios) | `python examples/v071_golden_benchmark.py` |

Demos 2-5 are the new world. They exercise the plan-execute loop,
the 4-layer memory, the self-growth engine, and the sub-agent
fan-out. They cost real money when you point them at a real LLM
(about a cent per demo with the default tier); they cost nothing
in mock mode.

## Architecture

The codebase is laid out in 6 layers, each independently testable
and replaceable. Lower layers are pure-Python; upper layers call
out to an LLM.

```
madcop/
  event.py            # L1: UnifiedEvent contract
  adapters/           # L1: OMS / TMS / WMS / BMS adapters
  anomaly/            # L2: CUSUM detector + 5 anomaly rules
  rca/                # L2: root-cause analysis graph
  counterfactual/     # L2: cost simulation
  decision/           # L2: operator-fatigue diff
  replay/             # L2: historical ROI replay
  llm/                # L3: ChatClient + OpenAICompatClient + MockClient
  strategy/           # L3: ModelRouter + ProviderRegistry + CostTracker + Scratchpad + ContextCompactor (v0.6.0)
  memory/             # L4: 4-layer SQLite+FTS5 memory + 3-mechanism growth (v0.6.0)
  agent/              # L5: LangGraph orchestrator (v0.5.0) + plan_execute (v0.6.0) + sub-agent (v0.7.0)
  config/             # v0.7.1: ~/.madcop/config.yaml loader
  eval/               # EvalRunner v2 with trend / robustness / adversarial (v0.6.0)
```

Each layer ships with its own tests. The full suite is 453 tests
as of v0.7.1.

## Installation

```bash
pip install madcop
```

Requires Python 3.10+. `langgraph`, `rich`, and `openai` are bundled
as hard dependencies.

## Quick start

```bash
# 1. Initialise your config (writes ~/.madcop/config.yaml with defaults)
python -m madcop config init
python -m madcop config show    # verify env-var resolution

# 2. Run the v0.5.0 deterministic agent on the cold-chain stream
python -m madcop run coldchain
python -m madcop run anomalies

# 3. Run the v0.6.0 plan-execute loop on a free-text goal
#    (mock client, no LLM, free)
python -m madcop plan "Why did OMS cancellations spike in the last 24h?"

# 4. Same as 3, but with a real LLM
export MADCOP_OPENAI_API_KEY=sk-...
export MADCOP_OPENAI_BASE_URL=https://api.openai.com/v1
export MADCOP_OPENAI_MODEL=gpt-4o-mini
python -m madcop plan "Why did OMS cancellations spike in the last 24h?" --llm

# 5. Sub-agent fan-out (v0.7.0)
python examples/v070_subagent_demo.py

# 6. Real-LLM golden-set benchmark (v0.7.1)
python examples/v071_golden_benchmark.py
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

**674 tests, all passing** (Python 3.10–3.12, macOS / Linux). CI runs
on every push via GitHub Actions. Coverage:

- L1 event contract (UTC validation, event type / source consistency)
- L2 detector (every rule, windowed-rule state machine, multi-zone bands)
- L2 RCA graph (forward/reverse traversal, empty chain, unknown subject)
- L3 CUSUM (Siegmund ARL₀→h, category baselines, persistent-shift detection)
- L3 LLM client (mock + real-OpenAI-compat, retry, usage tracking)
- L3 strategy (model router scoring, provider registry, cost tracking, scratchpad, compactor)
- L4 memory (4 layers, FTS5 search, time-decay retriever, growth engine)
- L5 plan-execute (4 modes, replan, step outcomes, aggregation)
- L5 sub-agent (spec, race-safe state, builtins, executor, LLMRunner)
- L5 routing executor (mixed inline + sub-agent plan dispatch)
- L6 eval (cases, trend, robustness, adversarial, integration)
- L6 config (loader, env-var resolution, defaults, malformed handling)

## Why "madcop"?

The original name came from "the agent that goes mad for anomalies".
The product is a cop that goes mad for anomalies — not in a punitive
sense, but in the sense of "won't let a single anomaly go
untraced to its source". The framework has since grown past anomaly
detection into a general personal AI agent, but the name stuck.

## License

MIT. See [`LICENSE`](LICENSE).

## Contact

Lin Ruihan · chuiniu@me.com