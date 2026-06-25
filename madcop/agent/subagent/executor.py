"""v0.7.0 — Sub-agent executor.

Spawns sub-agent runs on a thread pool. Cap at 3 concurrent (matches
the v0.6.0 ExecutionMode.ULTRA's MAX_REPLANS clamp [2,4]).

The executor is intentionally thin:
  - One thread per active sub-agent
  - Context is deep-copied at dispatch (so sub-agents can't pollute parent)
  - Sub-agent sees only the prompt + its tools + a snapshot of parent ctx
  - Sub-agent returns a string result (no shared state with parent)
  - Cancellation via `cancel_event` — set it, the worker checks at safe points

Real LLM work is delegated to a `Runner` protocol — you provide one
(real impl wraps madcop.llm.ChatClient, test impl is a mock). The
executor doesn't know about LLMs.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .builtins import BUILTIN_SUBAGENTS, get_builtin
from .spec import SubagentSpec
from .status import SubagentResult, SubagentStatus

logger = logging.getLogger(__name__)


# Hard cap on concurrent sub-agent runs. Mirrors MAX_REPLANS clamp.
MIN_CONCURRENT = 1
MAX_CONCURRENT = 4
DEFAULT_CONCURRENT = 3


def _clamp_concurrent(n: int) -> int:
    return max(MIN_CONCURRENT, min(MAX_CONCURRENT, n))


# ---------------------------------------------------------------------------
# Runner protocol — the "real work" abstraction
# ---------------------------------------------------------------------------


class Runner(Protocol):
    """Anyone who can run a sub-agent's prompt and return a string.

    Real impl: a thin wrapper that builds the messages, calls the LLM,
    and returns the response.
    Test impl: a mock that returns scripted text.
    """

    def run(
        self,
        *,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
        result_holder: SubagentResult,
    ) -> str: ...


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


@dataclass
class ExecutorConfig:
    """Tuning knobs for the executor."""
    max_concurrent: int = DEFAULT_CONCURRENT
    default_timeout_s: int = 300


class SubagentExecutor:
    """Run sub-agents in parallel, with isolation + cancellation.

    Usage:
        executor = SubagentExecutor(my_runner)
        results = executor.run_many([
            ("general-purpose", "research X", parent_ctx),
            ("bash", "run Y", parent_ctx),
        ])
    """

    def __init__(
        self,
        runner: Runner,
        config: ExecutorConfig | None = None,
        parent_tools: tuple[str, ...] = (),
    ):
        self._runner = runner
        self._config = config or ExecutorConfig()
        self._max = _clamp_concurrent(self._config.max_concurrent)
        self._parent_tools = parent_tools
        # ThreadPoolExecutor with max_workers == concurrent cap.
        # Threads are daemonised so they don't block process exit.
        self._pool = ThreadPoolExecutor(
            max_workers=self._max,
            thread_name_prefix="madcop-subagent-",
        )
        # Active results, keyed by task_id. Used for cancellation.
        self._active: dict[str, SubagentResult] = {}
        self._active_lock = threading.Lock()

    # ----- public API -----------------------------------------------------

    def run_many(
        self,
        jobs: list[tuple[str, str, dict]],   # [(agent_name, prompt, parent_ctx)]
    ) -> list[SubagentResult]:
        """Run a batch of sub-agents in parallel (capped at max_concurrent).

        Returns one SubagentResult per job, in the same order.
        """
        results: list[SubagentResult] = [None] * len(jobs)  # type: ignore[list-item]
        futures: list[tuple[int, Future]] = []

        for idx, (agent_name, prompt, parent_ctx) in enumerate(jobs):
            spec = get_builtin(agent_name)
            if spec is None:
                r = SubagentResult(
                    task_id=f"task-{uuid.uuid4().hex[:8]}",
                    agent_name=agent_name,
                    status=SubagentStatus.FAILED,
                    error=f"unknown sub-agent: {agent_name!r}",
                )
                results[idx] = r
                continue
            holder = SubagentResult(
                task_id=f"task-{uuid.uuid4().hex[:8]}",
                agent_name=agent_name,
            )
            results[idx] = holder
            with self._active_lock:
                self._active[holder.task_id] = holder
            fut = self._pool.submit(
                self._run_one,
                spec=spec,
                prompt=prompt,
                parent_ctx=parent_ctx,
                holder=holder,
            )
            futures.append((idx, fut))

        # Wait for all (in submission order)
        for idx, fut in futures:
            try:
                fut.result()  # the holder is already populated; this just re-raises
            except Exception as e:  # noqa: BLE001
                logger.exception("sub-agent %s crashed", results[idx].agent_name)
                results[idx].try_set_terminal(SubagentStatus.FAILED, error=f"crash: {e}")

        return results

    def run_one(
        self,
        agent_name: str,
        prompt: str,
        parent_ctx: dict,
    ) -> SubagentResult:
        """Run a single sub-agent. Convenience wrapper around run_many."""
        return self.run_many([(agent_name, prompt, parent_ctx)])[0]

    def cancel(self, task_id: str) -> bool:
        """Request cancellation of a running sub-agent by task_id."""
        with self._active_lock:
            holder = self._active.get(task_id)
        if holder is None:
            return False
        holder.request_cancel()
        return True

    def cancel_all(self) -> int:
        """Cancel all active sub-agents. Returns count of cancellation signals sent."""
        with self._active_lock:
            holders = list(self._active.values())
        for h in holders:
            h.request_cancel()
        return len(holders)

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting new sub-agents. Optionally wait for in-flight ones."""
        self._pool.shutdown(wait=wait)

    # ----- internals ------------------------------------------------------

    def _run_one(
        self,
        *,
        spec: SubagentSpec,
        prompt: str,
        parent_ctx: dict,
        holder: SubagentResult,
    ) -> None:
        """Body of one sub-agent run. Populates `holder` in place."""
        holder.mark_running()

        # Context isolation: deep-copy so sub-agent writes don't leak.
        sub_ctx = deepcopy(parent_ctx)

        # Effective tools (None = inherit, minus disallowed + 'task')
        effective_tools = spec.effective_tools(self._parent_tools)

        # Wrap the cancel event so the runner can check it (real impls
        # should poll this between LLM calls; for v0.7.0 we expose it
        # via the context).
        sub_ctx["__subagent_cancel_event__"] = holder.cancel_event
        sub_ctx["__subagent_effective_tools__"] = list(effective_tools)
        sub_ctx["__subagent_max_turns__"] = spec.max_turns

        try:
            output = self._runner.run(
                agent=spec,
                prompt=prompt,
                context=sub_ctx,
                result_holder=holder,
            )
            # If the runner didn't already set a terminal status, default to COMPLETED
            if not holder.status.is_terminal:
                holder.try_set_terminal(SubagentStatus.COMPLETED, result=output)
        except Exception as e:  # noqa: BLE001
            logger.exception("sub-agent %s raised", spec.name)
            holder.try_set_terminal(SubagentStatus.FAILED, error=f"{type(e).__name__}: {e}")
        finally:
            with self._active_lock:
                self._active.pop(holder.task_id, None)


# ---------------------------------------------------------------------------
# Built-in runner: a synchronous mock for tests + simple integrations
# ---------------------------------------------------------------------------


class FnRunner:
    """A Runner that delegates to a Python callable.

    Useful for:
      - tests (return scripted strings)
      - production: a thin wrapper that takes the prompt + context and
        calls a known LLM client (e.g. madcop.llm.OpenAICompatClient).
    """

    def __init__(self, fn: Callable[..., str]):
        self._fn = fn

    def run(
        self,
        *,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
        result_holder: SubagentResult,
    ) -> str:
        return self._fn(agent=agent, prompt=prompt, context=context, result_holder=result_holder)


__all__ = [
    "ExecutorConfig",
    "SubagentExecutor",
    "Runner",
    "FnRunner",
    "MIN_CONCURRENT",
    "MAX_CONCURRENT",
    "DEFAULT_CONCURRENT",
]
