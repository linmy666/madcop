"""v0.8.0 — Tests for the async sub-agent executor."""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from madcop.agent.subagent.async_executor import (
    AsyncFnRunner,
    AsyncSubagentExecutor,
)
from madcop.agent.subagent.executor import ExecutorConfig
from madcop.agent.subagent.status import SubagentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scripted_async(script: dict[str, str]):
    """Return an async fn that returns script[prompt] or 'default'."""
    async def fn(*, agent, prompt, context, result_holder):
        # Simulate a bit of work so other coroutines have a chance
        # to interleave (otherwise tests run "too fast" to detect races).
        await asyncio.sleep(0.001)
        return script.get(prompt, f"echo: {prompt}")
    return fn


def _slow_async(seconds: float, return_value: str = "done"):
    async def fn(*, agent, prompt, context, result_holder):
        await asyncio.sleep(seconds)
        return return_value
    return fn


# ---------------------------------------------------------------------------
# Basic run
# ---------------------------------------------------------------------------


def test_async_run_one_returns_completed():
    async def main():
        runner = AsyncFnRunner(_scripted_async({"x": "result-x"}))
        executor = AsyncSubagentExecutor(runner)
        result = await executor.run_one("general-purpose", "x", {})
        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "result-x"
    asyncio.run(main())


def test_async_run_one_unknown_agent_fails():
    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(_scripted_async({})))
        result = await executor.run_one("no-such-agent", "x", {})
        assert result.status == SubagentStatus.FAILED
        assert result.error is not None
        assert "unknown" in result.error.lower()
    asyncio.run(main())


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


def test_async_run_many_executes_jobs_in_parallel():
    """3 jobs each sleeping 0.1s should finish in ~0.1s, not 0.3s."""
    async def main():
        runner = AsyncFnRunner(_slow_async(0.1, return_value="ok"))
        executor = AsyncSubagentExecutor(runner, ExecutorConfig(max_concurrent=3))
        t0 = time.monotonic()
        results = await executor.run_many([
            ("general-purpose", "a", {}),
            ("general-purpose", "b", {}),
            ("general-purpose", "c", {}),
        ])
        elapsed = time.monotonic() - t0
        assert elapsed < 0.25, f"expected parallel, got {elapsed:.3f}s"
        assert all(r.status == SubagentStatus.COMPLETED for r in results)
    asyncio.run(main())


def test_async_run_many_preserves_input_order():
    async def main():
        async def slow_with_value(*, agent, prompt, context, result_holder):
            # Return different values with different delays
            await asyncio.sleep(0.01 if "first" in prompt else 0.05)
            return f"got:{prompt}"
        executor = AsyncSubagentExecutor(AsyncFnRunner(slow_with_value))
        results = await executor.run_many([
            ("general-purpose", "first", {}),
            ("general-purpose", "second", {}),
        ])
        assert [r.result for r in results] == ["got:first", "got:second"]
    asyncio.run(main())


# ---------------------------------------------------------------------------
# Concurrency cap
# ---------------------------------------------------------------------------


def test_async_concurrency_cap_is_enforced():
    """With max_concurrent=2 and 4 jobs each sleeping 0.1s, total should
    be ~0.2s (two waves), not 0.1s (all four at once) or 0.4s (serial)."""
    concurrent_now = 0
    concurrent_max = 0
    elapsed_holder: dict = {}
    lock = threading.Lock()

    async def fn(*, agent, prompt, context, result_holder):
        nonlocal concurrent_now, concurrent_max
        with lock:
            concurrent_now += 1
            concurrent_max = max(concurrent_max, concurrent_now)
        try:
            await asyncio.sleep(0.1)
            return "ok"
        finally:
            with lock:
                concurrent_now -= 1

    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(fn), ExecutorConfig(max_concurrent=2))
        t0 = time.monotonic()
        await executor.run_many([
            ("general-purpose", f"job-{i}", {}) for i in range(4)
        ])
        elapsed_holder["t"] = time.monotonic() - t0

    asyncio.run(main())
    elapsed = elapsed_holder["t"]
    # Two waves of 2 = 0.2s
    assert 0.18 < elapsed < 0.30, f"unexpected elapsed: {elapsed:.3f}s"
    # Never saw more than 2 in flight
    assert concurrent_max == 2, f"concurrency cap violated: saw {concurrent_max}"


def test_async_concurrency_clamped_to_max_4():
    executor = AsyncSubagentExecutor(AsyncFnRunner(_scripted_async({})), ExecutorConfig(max_concurrent=99))
    assert executor.max_concurrent == 4


def test_async_concurrency_clamped_to_min_1():
    executor = AsyncSubagentExecutor(AsyncFnRunner(_scripted_async({})), ExecutorConfig(max_concurrent=0))
    assert executor.max_concurrent == 1


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_async_cancel_via_task_id():
    """Set cancel_event mid-run; the runner should see it and bail."""
    holder_ref: dict = {}
    started = asyncio.Event()

    async def slow_with_cancel(*, agent, prompt, context, result_holder):
        holder_ref["h"] = result_holder
        started.set()
        # Poll cancel for 2s
        for _ in range(20):
            if result_holder.cancel_event.is_set():
                return "[cancelled]"
            await asyncio.sleep(0.1)
        return "ran to completion"

    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(slow_with_cancel))
        # Schedule the run, then cancel after a tiny delay.
        task = asyncio.create_task(executor.run_one("general-purpose", "x", {}))
        await started.wait()
        h = holder_ref["h"]
        executor.cancel(h.task_id)
        result = await task
        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "[cancelled]"

    asyncio.run(main())


def test_async_cancel_all_returns_count():
    started = [asyncio.Event()]

    async def slow(*, agent, prompt, context, result_holder):
        started[0].set()
        await asyncio.sleep(0.5)
        return "should not reach"

    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(slow), ExecutorConfig(max_concurrent=2))
        task = asyncio.create_task(executor.run_many([
            ("general-purpose", "a", {}),
            ("general-purpose", "b", {}),
        ]))
        # Wait for both to be in flight
        await started[0].wait()
        await asyncio.sleep(0.05)
        n = executor.cancel_all()
        assert n == 2
        await task
    asyncio.run(main())


def test_async_cancel_unknown_task_id_returns_false():
    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(_scripted_async({})))
        assert executor.cancel("nope") is False
    asyncio.run(main())


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


def test_async_runner_exception_marks_failed():
    async def boom(*, agent, prompt, context, result_holder):
        raise ValueError("kaboom")

    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(boom))
        result = await executor.run_one("general-purpose", "x", {})
        assert result.status == SubagentStatus.FAILED
        assert result.error is not None
        assert "kaboom" in result.error
    asyncio.run(main())


def test_async_many_with_one_exception_marks_only_that_one_failed():
    async def maybe_boom(*, agent, prompt, context, result_holder):
        if "bad" in prompt:
            raise ValueError("bad job")
        return f"ok:{prompt}"

    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(maybe_boom))
        results = await executor.run_many([
            ("general-purpose", "good-1", {}),
            ("general-purpose", "bad", {}),
            ("general-purpose", "good-2", {}),
        ])
        assert results[0].status == SubagentStatus.COMPLETED
        assert results[1].status == SubagentStatus.FAILED
        assert results[2].status == SubagentStatus.COMPLETED
    asyncio.run(main())


# ---------------------------------------------------------------------------
# Context isolation (deepcopy, like the sync executor)
# ---------------------------------------------------------------------------


def test_async_subagent_cannot_pollute_parent_context():
    seen_in_runner: list = []

    async def mutating(*, agent, prompt, context, result_holder):
        seen_in_runner.append(dict(context))  # snapshot
        # Try to mutate
        if "shared" in context:
            context["shared"].append("from-subagent")
        return "ok"

    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(mutating))
        parent_ctx = {"shared": ["original"]}
        await executor.run_one("general-purpose", "x", parent_ctx)
        # Parent context was deep-copied, so the original list is intact
        assert parent_ctx["shared"] == ["original"]
        # But the sub-agent saw the mutation in its own copy
        assert "from-subagent" in seen_in_runner[0]["shared"]
    asyncio.run(main())


# ---------------------------------------------------------------------------
# Active count tracking
# ---------------------------------------------------------------------------


def test_async_active_count_during_run():
    in_flight = []

    async def track(*, agent, prompt, context, result_holder):
        in_flight.append(len(context.get("__subagent_effective_tools__", [])))
        await asyncio.sleep(0.05)
        return "ok"

    async def main():
        executor = AsyncSubagentExecutor(AsyncFnRunner(track), ExecutorConfig(max_concurrent=2))
        task = asyncio.create_task(executor.run_many([
            ("general-purpose", "a", {}),
            ("general-purpose", "b", {}),
        ]))
        # Give them a moment to start
        await asyncio.sleep(0.01)
        # Both should be in flight (concurrent cap = 2)
        assert executor.active_count == 2
        await task
        # After completion, all popped
        assert executor.active_count == 0
    asyncio.run(main())
