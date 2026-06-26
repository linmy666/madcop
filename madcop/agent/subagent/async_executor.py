"""v0.8.0 — Async sub-agent executor.

The v0.7.0 `SubagentExecutor` runs runners on a `ThreadPoolExecutor`.
That's fine for blocking I/O (HTTP calls release the GIL while
awaiting the socket), but if a runner is *truly* async (e.g. uses
`asyncio` + `aiohttp`, or a chat SDK that already exposes
`async def chat(...)`), then waiting on a thread blocks an event loop
thread for no reason.

This module provides the same surface area as the sync executor, but
backed by `asyncio` instead of threads.

Key design choices:
- `AsyncRunner` is a separate Protocol (an `async def run(...)`).
  Users pick which they implement; the executor they pick is matched
  to the runner's nature.
- `AsyncSubagentExecutor.run_many()` is itself `async def`. Callers
  must be in an event loop (use `asyncio.run(...)` for one-off).
- Concurrency cap is enforced via a semaphore, NOT a thread pool.
  Coroutines are cheap; we don't need a worker pool.
- The active-task registry (for `cancel(task_id)`) is the same as
  the sync executor, minus the lock: coroutines run on a single
  thread, so dict mutations are safe by construction.
- Cancellation: setting `cancel_event` is a Python `threading.Event`
  — coroutines poll it the same way threads do. The event loop will
  run other coroutines while a cancelled one bails out.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol

from .builtins import get_builtin
from .executor import (
    DEFAULT_CONCURRENT,
    MAX_CONCURRENT,
    MIN_CONCURRENT,
    ExecutorConfig,
    _clamp_concurrent,
)
from .spec import SubagentSpec
from .status import SubagentResult, SubagentStatus

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# AsyncRunner protocol
# --------------------------------------------------------------------------- #


class AsyncRunner(Protocol):
    """An async version of the Runner protocol.

    Real impl: a wrapper around an `async def chat(...)` SDK.
    Test impl: an `async def` that returns scripted text.
    """

    async def run(
        self,
        *,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
        result_holder: SubagentResult,
    ) -> str: ...


# --------------------------------------------------------------------------- #
# Executor
# --------------------------------------------------------------------------- #


class AsyncSubagentExecutor:
    """Run async sub-agents concurrently (capped at max_concurrent).

    Usage:
        async def my_runner(*, agent, prompt, context, result_holder):
            return await some_async_llm(prompt)

        executor = AsyncSubagentExecutor(my_runner)
        results = await executor.run_many([
            ("general-purpose", "research X", parent_ctx),
            ("bash", "run Y", parent_ctx),
        ])
    """

    def __init__(
        self,
        runner: AsyncRunner,
        config: ExecutorConfig | None = None,
        parent_tools: tuple[str, ...] = (),
    ):
        self._runner = runner
        self._config = config or ExecutorConfig()
        self._max = _clamp_concurrent(self._config.max_concurrent)
        self._parent_tools = parent_tools
        # Active results, keyed by task_id. No lock needed: asyncio is
        # single-threaded; mutations happen between `await` points.
        self._active: dict[str, SubagentResult] = {}
        # Semaphore to cap concurrency.
        self._sem = asyncio.Semaphore(self._max)

    @property
    def max_concurrent(self) -> int:
        return self._max

    @property
    def active_count(self) -> int:
        return len(self._active)

    # ----- public API -----------------------------------------------------

    async def run_many(
        self,
        jobs: list[tuple[str, str, dict]],
    ) -> list[SubagentResult]:
        """Run a batch of sub-agents concurrently (capped at max_concurrent).

        Returns one `SubagentResult` per job, in input order.
        """
        # First, build holders for unknown-agent jobs synchronously.
        results: list[SubagentResult | None] = [None] * len(jobs)
        tasks: list[asyncio.Task] = []
        task_indices: list[int] = []

        for idx, (agent_name, prompt, parent_ctx) in enumerate(jobs):
            spec = get_builtin(agent_name)
            if spec is None:
                results[idx] = SubagentResult(
                    task_id=f"task-{uuid.uuid4().hex[:8]}",
                    agent_name=agent_name,
                    status=SubagentStatus.FAILED,
                    error=f"unknown sub-agent: {agent_name!r}",
                )
                continue
            holder = SubagentResult(
                task_id=f"task-{uuid.uuid4().hex[:8]}",
                agent_name=agent_name,
            )
            results[idx] = holder
            self._active[holder.task_id] = holder
            task = asyncio.create_task(
                self._run_one(spec=spec, prompt=prompt, parent_ctx=parent_ctx, holder=holder),
                name=f"subagent-{spec.name}-{holder.task_id[:6]}",
            )
            tasks.append(task)
            task_indices.append(idx)

        # Wait for all to finish. asyncio.gather preserves order via
        # the tasks list, but we want results in *jobs* order, so we
        # also track which task maps to which result slot.
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=False)
            # After gather, every holder should be in a terminal state.
            # If something still isn't (shouldn't happen), force a fail.
            for idx in task_indices:
                h = results[idx]
                assert h is not None
                if not h.status.is_terminal:
                    h.try_set_terminal(
                        SubagentStatus.FAILED, error="exited without terminal status"
                    )

        # Pop all active entries
        for h in list(self._active.values()):
            self._active.pop(h.task_id, None)

        # All slots filled now
        out: list[SubagentResult] = []
        for r in results:
            assert r is not None
            out.append(r)
        return out

    async def run_one(
        self,
        agent_name: str,
        prompt: str,
        parent_ctx: dict,
    ) -> SubagentResult:
        """Run a single sub-agent. Convenience wrapper around run_many."""
        return (await self.run_many([(agent_name, prompt, parent_ctx)]))[0]

    def cancel(self, task_id: str) -> bool:
        """Request cancellation of a running sub-agent by task_id."""
        holder = self._active.get(task_id)
        if holder is None:
            return False
        holder.request_cancel()
        return True

    def cancel_all(self) -> int:
        """Cancel all active sub-agents. Returns count of signals sent."""
        holders = list(self._active.values())
        for h in holders:
            h.request_cancel()
        return len(holders)

    # ----- internals ------------------------------------------------------

    async def _run_one(
        self,
        *,
        spec: SubagentSpec,
        prompt: str,
        parent_ctx: dict,
        holder: SubagentResult,
    ) -> None:
        """Body of one async sub-agent run. Populates `holder` in place."""
        async with self._sem:  # cap concurrency
            holder.mark_running()
            # Context isolation: deep-copy so sub-agent writes don't leak.
            sub_ctx = deepcopy(parent_ctx)
            effective_tools = spec.effective_tools(self._parent_tools)
            sub_ctx["__subagent_cancel_event__"] = holder.cancel_event
            sub_ctx["__subagent_effective_tools__"] = list(effective_tools)
            sub_ctx["__subagent_max_turns__"] = spec.max_turns

            try:
                output = await self._runner.run(
                    agent=spec,
                    prompt=prompt,
                    context=sub_ctx,
                    result_holder=holder,
                )
                if not holder.status.is_terminal:
                    holder.try_set_terminal(SubagentStatus.COMPLETED, result=output)
            except asyncio.CancelledError:
                holder.try_set_terminal(SubagentStatus.CANCELLED, error="asyncio cancelled")
                raise
            except Exception as e:  # noqa: BLE001
                logger.exception("sub-agent %s raised", spec.name)
                holder.try_set_terminal(
                    SubagentStatus.FAILED, error=f"{type(e).__name__}: {e}"
                )
            finally:
                self._active.pop(holder.task_id, None)


# --------------------------------------------------------------------------- #
# Built-in async runner
# --------------------------------------------------------------------------- #


class AsyncFnRunner:
    """An `AsyncRunner` that delegates to a coroutine.

    Useful for tests and for thin wrappers around async LLM SDKs.
    """

    def __init__(self, fn: Callable[..., Awaitable[str]]):
        self._fn = fn

    async def run(
        self,
        *,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
        result_holder: SubagentResult,
    ) -> str:
        return await self._fn(agent=agent, prompt=prompt, context=context, result_holder=result_holder)


__all__ = [
    "AsyncRunner",
    "AsyncSubagentExecutor",
    "AsyncFnRunner",
]
