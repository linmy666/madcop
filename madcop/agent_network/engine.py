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
                                   results, outputs, user_input)
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

        # Gather upstream outputs as context
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
            # Run blocking chat() in a thread to not block the event loop
            resp = await asyncio.to_thread(
                self.client.chat, messages,
                model=model or None,
                temperature=0.3,
                max_tokens=2048,
            )
            output = getattr(resp, "content", "") or str(resp)
        except Exception as e:
            output = f"[Agent {agent_name} 执行失败: {e}]"
            results[node_id] = NodeResult(
                node_id=node_id, agent_id=agent_id, agent_name=agent_name,
                output=output, status="error", error=str(e),
                elapsed_ms=round((time.time() - started) * 1000, 1),
                upstream=ups,
            )
            outputs[node_id] = output
            return

        outputs[node_id] = output
        results[node_id] = NodeResult(
            node_id=node_id, agent_id=agent_id, agent_name=agent_name,
            output=output, status="done",
            elapsed_ms=round((time.time() - started) * 1000, 1),
            upstream=ups,
        )


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
