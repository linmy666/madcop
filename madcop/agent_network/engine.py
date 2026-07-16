"""Multi-agent execution engine.

Executes a DAG of agents connected by edges. Each agent node gets its
upstream outputs as context, calls the LLM, and passes its output
downstream. Special nodes: 'input' (passthrough), 'merge'/'output'
(combine all upstream).

No external dependencies — uses only stdlib graphlib + asyncio +
the existing madcop.llm ChatClient.
"""

from __future__ import annotations

import asyncio
import graphlib
import time
from dataclasses import dataclass, field
from typing import Any

from madcop.llm import Message
from madcop.llm.client import ChatClient, MockClient


# ── Data structures ────────────────────────────────────────────────── #

@dataclass
class NodeResult:
    """Output of a single node execution."""
    node_id: str
    agent_id: str
    agent_name: str
    output: str
    status: str = "done"           # done | error | skipped
    error: str | None = None
    elapsed_ms: float = 0.0
    upstream: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Full network execution output."""
    network_name: str
    status: str                     # completed | partial | failed
    steps: list[NodeResult]
    outputs: dict[str, str]        # node_id -> output text
    elapsed_ms: float = 0.0
    started_at: str = ""


# ── Special node types ─────────────────────────────────────────────── #

PASSTHROUGH_NODES = {"input", "start", "user"}
MERGE_NODES = {"merge", "output", "end", "result"}


# ── Engine ─────────────────────────────────────────────────────────── #

class AgentEngine:
    """Executes a multi-agent network.

    Usage:
        engine = AgentEngine(client, agents_registry)
        result = await engine.run(network_config, user_input="write a snake game")
    """

    def __init__(
        self,
        client: ChatClient,
        agents: list[dict[str, Any]] | None = None,
    ) -> None:
        self.client = client
        # Build agent lookup: id -> agent dict
        self.agents: dict[str, dict[str, Any]] = {}
        for a in (agents or []):
            aid = a.get("id", "")
            if aid:
                self.agents[aid] = a

    async def run(
        self,
        network: dict[str, Any],
        user_input: str = "",
        on_token: Any = None,
    ) -> ExecutionResult:
        """Execute a network and return all node outputs."""
        nodes: list[dict] = network.get("nodes", [])
        edges: list[dict] = network.get("edges", [])
        name = network.get("name", "Untitled")

        # Build adjacency: node_id -> list of upstream node_ids
        upstream_map: dict[str, list[str]] = {n["id"]: [] for n in nodes}
        for edge in edges:
            src = edge.get("from", "")
            dst = edge.get("to", "")
            if src in upstream_map and dst in upstream_map:
                upstream_map[dst].append(src)

        # Topological sort
        sorter: graphlib.TopologicalSorter = graphlib.TopologicalSorter()
        for nid, ups in upstream_map.items():
            sorter.add(nid, *ups)
        try:
            order = list(sorter.static_order())
        except graphlib.CycleError:
            # Fallback: just run in node list order
            order = [n["id"] for n in nodes]

        started = time.time()
        results: dict[str, NodeResult] = {}
        outputs: dict[str, str] = {}
        iso_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Group nodes into "waves" for parallel execution
        # (nodes at the same topological level run concurrently)
        waves = self._build_waves(order, upstream_map)

        for wave in waves:
            tasks = [
                self._execute_node(nid, nodes, upstream_map,
                                   results, outputs, user_input, on_token)
                for nid in wave
            ]
            await asyncio.gather(*tasks, return_exceptions=False)

        elapsed = (time.time() - started) * 1000

        # Determine overall status
        step_list = [results[nid] for nid in order if nid in results]
        has_error = any(s.status == "error" for s in step_list)
        status = "partial" if has_error else "completed"

        return ExecutionResult(
            network_name=name,
            status=status,
            steps=step_list,
            outputs=outputs,
            elapsed_ms=round(elapsed, 1),
            started_at=iso_started,
        )

    def _build_waves(
        self,
        order: list[str],
        upstream_map: dict[str, list[str]],
    ) -> list[list[str]]:
        """Split topological order into parallel waves.

        A node goes into wave N if all its upstream nodes are in waves < N.
        """
        node_wave: dict[str, int] = {}
        waves: list[list[str]] = []
        for nid in order:
            ups = upstream_map.get(nid, [])
            if ups:
                wave_num = max(node_wave.get(u, 0) for u in ups) + 1
            else:
                wave_num = 0
            node_wave[nid] = wave_num
            while len(waves) <= wave_num:
                waves.append([])
            waves[wave_num].append(nid)
        return waves

    async def _execute_node(
        self,
        node_id: str,
        nodes: list[dict],
        upstream_map: dict[str, list[str]],
        results: dict[str, NodeResult],
        outputs: dict[str, str],
        user_input: str,
        on_token: Any = None,
    ) -> None:
        """Execute a single node and store its result."""
        node = next((n for n in nodes if n["id"] == node_id), {"id": node_id})
        agent_id = node.get("agentId") or node_id
        agent = self.agents.get(agent_id, {})
        agent_name = agent.get("name", node.get("name", agent_id))
        ups = upstream_map.get(node_id, [])

        started = time.time()

        # Handle passthrough nodes (input/start)
        if agent_id in PASSTHROUGH_NODES or node_id in PASSTHROUGH_NODES:
            output = user_input
            outputs[node_id] = output
            results[node_id] = NodeResult(
                node_id=node_id, agent_id=agent_id, agent_name=agent_name,
                output=output, status="done",
                elapsed_ms=round((time.time() - started) * 1000, 1),
                upstream=ups,
            )
            return

        # Gather upstream outputs as context. SKIP nodes that errored —
        # their output is "" (error isolation), so they naturally drop out
        # of the concatenation and don't pollute downstream synthesis.
        upstream_context = ""
        if ups:
            parts = []
            for u in ups:
                u_out = outputs.get(u, "")
                u_name = results.get(u, NodeResult("", "", "", "")).agent_name or u
                if u_out:
                    parts.append(f"[{u_name}]\n{u_out}")
            upstream_context = "\n\n---\n\n".join(parts)

        # Handle merge nodes (combine upstream, no LLM call)
        if agent_id in MERGE_NODES or node_id in MERGE_NODES:
            output = upstream_context if upstream_context else user_input
            outputs[node_id] = output
            results[node_id] = NodeResult(
                node_id=node_id, agent_id=agent_id, agent_name=agent_name,
                output=output, status="done",
                elapsed_ms=round((time.time() - started) * 1000, 1),
                upstream=ups,
            )
            return

        # Build system prompt from agent definition
        caps = agent.get("capabilities", [])
        caps_str = ", ".join(caps) if caps else "general assistance"
        desc = agent.get("description", "You are a helpful AI assistant.")
        model = agent.get("model", "")

        # The synthesizer node gets a bespoke prompt that tells it to merge
        # all upstream outputs into one coherent report. Other agents use
        # their role definition + the generic "do your part" instruction.
        if node_id == SYNTHESIZER_NODE_ID:
            system_prompt = _SYNTH_PROMPT
        else:
            system_prompt = (
                f"你是「{agent_name}」。{desc}\n"
                f"你的核心能力: {caps_str}。\n"
                f"请根据上游 agent 的输出和用户请求，完成你负责的部分。\n"
                f"只输出你的工作结果，不要重复上游的内容。"
            )

        # Build user message
        if upstream_context:
            user_msg = (
                f"用户原始请求:\n{user_input}\n\n"
                f"上游 agent 的输出:\n{upstream_context}"
            )
        else:
            user_msg = user_input

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_msg),
        ]

        try:
            # Stream the agent's output token-by-token. stream() is a sync
            # generator; run it in a thread and accumulate, invoking on_token
            # for each text chunk so the caller (e.g. the SSE handler) can
            # forward it live. Multiple nodes in the same wave run their own
            # threads concurrently, so their tokens interleave on the wire.
            #
            # Retry transient failures (connection drops, timeouts, 5xx).
            # Auth/param errors (4xx) are not retried — they'll fail every
            # time. A failed agent stores an EMPTY output (not an error
            # string) so it doesn't pollute downstream synthesis.
            def _drain_once() -> str:
                parts: list[str] = []
                for chunk in self.client.stream(
                    messages,
                    model=model or None,
                    temperature=0.3,
                    max_tokens=2048,
                ):
                    if chunk.text:
                        parts.append(chunk.text)
                        if on_token:
                            try:
                                on_token(node_id, agent_name, agent_id, chunk.text)
                            except Exception:
                                pass
                return "".join(parts)

            def _is_retryable(exc: Exception) -> bool:
                """Connection/timeout/server errors are worth retrying."""
                msg = str(exc).lower()
                if any(k in msg for k in (
                    "timeout", "timed out", "connection",
                    "reset", "broken pipe", "eof", "unreachable",
                    "502", "503", "504", "overloaded", "rate limit",
                    "rate_limit", "temporar",
                )):
                    return True
                # openai.APIStatusError with 5xx — check attribute
                status = getattr(exc, "status_code", None)
                if isinstance(status, int) and status >= 500:
                    return True
                return False

            last_err: Exception | None = None
            output = ""
            for _attempt in range(3):
                try:
                    output = await asyncio.to_thread(_drain_once)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    if _attempt < 2 and _is_retryable(e):
                        # Exponential backoff: 1s, 2s before 2nd/3rd try.
                        await asyncio.sleep(2 ** _attempt)
                        continue
                    break

            if last_err is not None:
                # Error isolation: store EMPTY output, not an error string,
                # so downstream agents (esp. synthesizer) don't ingest
                # "[Agent X failed...]" as if it were real content.
                outputs[node_id] = ""
                results[node_id] = NodeResult(
                    node_id=node_id, agent_id=agent_id, agent_name=agent_name,
                    output="", status="error", error=str(last_err),
                    elapsed_ms=round((time.time() - started) * 1000, 1),
                    upstream=ups,
                )
                return
        except Exception as e:
            # Defensive: any unexpected error outside the retry loop.
            outputs[node_id] = ""
            results[node_id] = NodeResult(
                node_id=node_id, agent_id=agent_id, agent_name=agent_name,
                output="", status="error", error=str(e),
                elapsed_ms=round((time.time() - started) * 1000, 1),
                upstream=ups,
            )
            return

        outputs[node_id] = output
        results[node_id] = NodeResult(
            node_id=node_id, agent_id=agent_id, agent_name=agent_name,
            output=output, status="done",
            elapsed_ms=round((time.time() - started) * 1000, 1),
            upstream=ups,
        )


# ── Task-typed deep networks ──────────────────────────────────────── #
# Instead of a single fixed planner→coder→reviewer pipeline for every
# deep task, classify the task and pick an agent roster that fits.
# A research report doesn't need a coder; a bug fix doesn't need a
# designer. Each template lists the agent node ids from the builtin set:
#   planner / coder / researcher / designer / reviewer
#
# DAG shape (always):
#   input → planner → (specialist₁ ‖ specialist₂ ‖ …) → synthesizer → output
# The specialists run in a PARALLEL wave (the multi-sprite effect). The
# synthesizer is a real LLM agent that merges all specialist outputs into
# ONE coherent final report — so the answer the user sees is never a raw
# "[规划]…---[审查]…" concatenation. `output` is still a merge node, but
# with only synthesizer upstream, it just passes the synthesis through.

import re as _re

# The synthesizer node uses the builtin `assistant` agent role but with a
# bespoke system prompt injected at execution time (see _SYNTH_PROMPT).
SYNTHESIZER_NODE_ID = "synthesizer"
SYNTHESIZER_AGENT_ID = "assistant"

_SYNTH_PROMPT = (
    "你是「综合编辑」。你的职责是把上游各领域专家的产出整合成一份"
    "连贯、完整、结构清晰的最终回复。\n"
    "要求：\n"
    "- 直接面向用户输出最终结果，不要提及\"上游\"\"专家\"等内部过程。\n"
    "- 保留所有关键信息和数据，去除冗余、重复和过程性内容（如审查意见、"
    "内部讨论、规划草稿）。\n"
    "- 用清晰的标题、列表、段落组织内容，使用 Markdown 格式。\n"
    "- 如果上游专家之间存在矛盾，给出你的综合判断并说明理由。\n"
    "- 不要添加上游没有的事实信息；可以重新组织表达，但不可杜撰。"
)

# Signal patterns → task category. Checked in priority order.
# Each roster lists the PARALLEL specialists (planner + synthesizer are
# added automatically by build_network_for_task).
_TASK_CATEGORIES: list[tuple[str, list, list[str]]] = [
    # (category, [compiled patterns], [specialist agent ids])
    ("coding", [
        _re.compile(r"代码|code|bug|修复|fix|函数|function|实现|implement|程序|脚本|script|重构|refactor|算法|algorithm|API|接口|类|class|游戏|game|应用|app|网站|web|开发|develop|搭建.*服务|后端|前端|backend|frontend", _re.IGNORECASE),
    ], ["coder", "reviewer"]),
    ("design", [
        _re.compile(r"设计|design|UI|界面|原型|prototype|样式|CSS|布局|layout|配色|主题|theme|页面", _re.IGNORECASE),
    ], ["designer", "reviewer"]),
    ("research", [
        _re.compile(r"调研|研究|报告|report|分析|analysis|资料|搜索|查阅|文献|市场|行业|论文|综述|survey|investigat", _re.IGNORECASE),
    ], ["researcher"]),
]


def classify_task(user_input: str) -> tuple[str, list[str]]:
    """Return (category, [specialist agent ids]) for a deep-mode task.

    The returned list EXCLUDES planner and synthesizer (those are added
    automatically by build_network_for_task). Falls back to a
    general-purpose roster when no category matches.
    """
    for category, patterns, agents in _TASK_CATEGORIES:
        for pat in patterns:
            if pat.search(user_input):
                return category, list(agents)
    # General / writing / unknown — researcher covers information needs.
    return "general", ["researcher"]


def build_network_for_task(user_input: str) -> dict:
    """Build a DAG network tailored to the task category.

    Shape: input → planner → (specialists in parallel) → synthesizer → output.
    Specialists run in the same wave (parallel). The synthesizer then
    runs alone, receiving all specialist outputs, and produces the final
    coherent answer.
    """
    _category, specialist_ids = classify_task(user_input)

    _ZH_NAME = {
        "coder": "编码", "designer": "设计",
        "researcher": "调研", "reviewer": "审查",
        "assistant": "综合",
    }

    nodes: list[dict] = [
        {"id": "input", "agentId": "", "name": "输入"},
        {"id": "planner", "agentId": "planner", "name": "规划"},
    ]
    # Parallel specialists.
    for aid in specialist_ids:
        nodes.append({"id": aid, "agentId": aid, "name": _ZH_NAME.get(aid, aid)})
    # Synthesizer — real LLM agent (assistant role) that merges everything.
    nodes.append({"id": SYNTHESIZER_NODE_ID, "agentId": SYNTHESIZER_AGENT_ID, "name": "综合"})
    nodes.append({"id": "output", "agentId": "", "name": "输出"})

    edges: list[dict] = [
        {"from": "input", "to": "planner"},
    ]
    # planner fans out to each specialist (parallel wave).
    for aid in specialist_ids:
        edges.append({"from": "planner", "to": aid})
        edges.append({"from": aid, "to": SYNTHESIZER_NODE_ID})
    # synthesizer → output (final answer).
    edges.append({"from": SYNTHESIZER_NODE_ID, "to": "output"})

    return {"name": "deep", "nodes": nodes, "edges": edges}


# ── Convenience: build engine from settings ────────────────────────── #

def build_engine() -> AgentEngine:
    """Build an AgentEngine using the active LLM client and built-in agents."""
    from madcop.config import settings as settings_store
    from madcop.llm.client import OpenAICompatClient

    s = settings_store.load_settings()
    cfg = settings_store.get_active_client_config(s)

    if cfg and cfg.get("api_key"):
        client = OpenAICompatClient(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"],
            timeout=120.0,
        )
    else:
        client = MockClient(
            default_response="[No API key configured — agent execution skipped]"
        )

    # Collect all known agents (builtin + installed)
    from madcop.agent_network.api import BUILTIN_AGENTS, _load, _AGENTS_FILE
    installed = _load(_AGENTS_FILE)
    all_agents = BUILTIN_AGENTS + installed

    return AgentEngine(client, all_agents)
