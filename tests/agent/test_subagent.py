"""Tests for v0.7.0 sub-agent layer.

Covers:
  - spec.py:       SubagentSpec, effective_tools, defaults
  - status.py:     SubagentStatus, SubagentResult, try_set_terminal race-safety
  - builtins.py:   GENERAL_PURPOSE, BASH, registry
  - executor.py:   SubagentExecutor.run_one / run_many, concurrency, cancellation
"""
from __future__ import annotations

import threading
import time

import pytest

from madcop.agent.subagent.spec import SubagentSpec
from madcop.agent.subagent.status import SubagentResult, SubagentStatus
from madcop.agent.subagent.builtins import (
    BASH,
    BUILTIN_SUBAGENTS,
    GENERAL_PURPOSE,
    get_builtin,
)
from madcop.agent.subagent.executor import (
    DEFAULT_CONCURRENT,
    ExecutorConfig,
    FnRunner,
    MAX_CONCURRENT,
    MIN_CONCURRENT,
    SubagentExecutor,
    _clamp_concurrent,
)


# ---------------------------------------------------------------------------
# spec.py
# ---------------------------------------------------------------------------


def test_spec_defaults_disallow_task_tool():
    spec = SubagentSpec(name="x", description="x")
    assert "task" in spec.disallowed_tools


def test_spec_effective_tools_inherits_when_none():
    spec = SubagentSpec(name="x", description="x")
    tools = spec.effective_tools(parent_tools=("read", "write", "bash", "task"))
    assert "read" in tools
    assert "write" in tools
    assert "bash" in tools
    # task is ALWAYS blocked, even if user has weird overrides
    assert "task" not in tools


def test_spec_effective_tools_uses_explicit_allow_list():
    spec = SubagentSpec(name="x", description="x", tools=("read", "write"))
    tools = spec.effective_tools(parent_tools=("read", "write", "bash"))
    assert set(tools) == {"read", "write"}


def test_spec_effective_tools_removes_disallowed():
    spec = SubagentSpec(
        name="x", description="x",
        tools=("read", "write", "bash"),
        disallowed_tools=("bash",),
    )
    tools = spec.effective_tools(parent_tools=("read", "write", "bash"))
    assert "bash" not in tools


def test_spec_to_dict_truncates_long_descriptions():
    spec = SubagentSpec(name="x", description="a" * 200)
    d = spec.to_dict()
    assert d["name"] == "x"
    assert d["description"].endswith("...")
    assert len(d["description"]) < 200


def test_spec_default_timeout_is_5_minutes():
    spec = SubagentSpec(name="x", description="x")
    assert spec.timeout_seconds == 300


# ---------------------------------------------------------------------------
# status.py
# ---------------------------------------------------------------------------


def test_status_starts_as_pending():
    r = SubagentResult(task_id="t1", agent_name="x")
    assert r.status == SubagentStatus.PENDING
    assert r.started_at is None
    assert not r.status.is_terminal


def test_mark_running_transitions_pending_to_running():
    r = SubagentResult(task_id="t1", agent_name="x")
    r.mark_running()
    assert r.status == SubagentStatus.RUNNING
    assert r.started_at is not None


def test_try_set_terminal_first_writer_wins():
    r = SubagentResult(task_id="t1", agent_name="x")
    r.mark_running()
    accepted = r.try_set_terminal(SubagentStatus.COMPLETED, result="hello")
    assert accepted is True
    assert r.status == SubagentStatus.COMPLETED
    assert r.result == "hello"


def test_try_set_terminal_late_writers_lose():
    r = SubagentResult(task_id="t1", agent_name="x")
    r.mark_running()
    r.try_set_terminal(SubagentStatus.COMPLETED, result="first")

    # Second writer tries to overwrite — must fail
    accepted = r.try_set_terminal(SubagentStatus.FAILED, error="too late")
    assert accepted is False
    # State is unchanged
    assert r.status == SubagentStatus.COMPLETED
    assert r.result == "first"
    assert r.error is None


def test_try_set_terminal_rejects_non_terminal_status():
    r = SubagentResult(task_id="t1", agent_name="x")
    with pytest.raises(ValueError):
        r.try_set_terminal(SubagentStatus.RUNNING)  # not terminal


def test_terminal_states_are_terminal():
    for s in [SubagentStatus.COMPLETED, SubagentStatus.FAILED,
              SubagentStatus.CANCELLED, SubagentStatus.TIMED_OUT]:
        assert s.is_terminal
    assert not SubagentStatus.PENDING.is_terminal
    assert not SubagentStatus.RUNNING.is_terminal


def test_concurrent_try_set_terminal_race_safe():
    """The classic case: timeout watcher and worker race to finalise.

    Exactly one must win; the other is a no-op.
    """
    r = SubagentResult(task_id="t1", agent_name="x")
    r.mark_running()

    winners: list[SubagentStatus] = []
    lock = threading.Lock()

    def writer(status: SubagentStatus) -> None:
        accepted = r.try_set_terminal(status, result=f"from {status.value}")
        if accepted:
            with lock:
                winners.append(status)

    threads = [
        threading.Thread(target=writer, args=(SubagentStatus.COMPLETED,)),
        threading.Thread(target=writer, args=(SubagentStatus.TIMED_OUT,)),
        threading.Thread(target=writer, args=(SubagentStatus.FAILED,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1  # exactly one winner
    # The result is whichever winner set
    assert r.status == winners[0]


def test_request_cancel_sets_event_but_does_not_change_status():
    r = SubagentResult(task_id="t1", agent_name="x")
    r.mark_running()
    r.request_cancel()
    assert r.cancel_event.is_set()
    # Status is still RUNNING — only the worker can finalise it
    assert r.status == SubagentStatus.RUNNING


def test_duration_s_computed_when_started():
    r = SubagentResult(task_id="t1", agent_name="x")
    assert r.duration_s is None
    r.mark_running()
    time.sleep(0.001)
    d = r.duration_s
    assert d is not None
    assert d > 0


# ---------------------------------------------------------------------------
# builtins.py
# ---------------------------------------------------------------------------


def test_builtin_registry_has_expected_agents():
    assert set(BUILTIN_SUBAGENTS.keys()) == {"general-purpose", "bash"}


def test_get_builtin_returns_spec():
    spec = get_builtin("general-purpose")
    assert spec is not None
    assert spec.name == "general-purpose"
    assert spec is GENERAL_PURPOSE


def test_get_builtin_returns_none_for_unknown():
    assert get_builtin("does-not-exist") is None


def test_general_purpose_inherits_tools():
    """general-purpose's `tools` is None → inherits from parent."""
    assert GENERAL_PURPOSE.tools is None


def test_bash_explicit_tools_allow_list():
    assert BASH.tools == ("bash",)


def test_bash_disallowed_tools_includes_task():
    assert "task" in BASH.disallowed_tools


def test_builtins_have_distinct_max_turns():
    """No copy-paste mistake — each has its own value."""
    assert GENERAL_PURPOSE.max_turns != BASH.max_turns


# ---------------------------------------------------------------------------
# executor.py — concurrent run
# ---------------------------------------------------------------------------


def test_clamp_concurrent_respects_bounds():
    assert _clamp_concurrent(0) == MIN_CONCURRENT
    assert _clamp_concurrent(1) == 1
    assert _clamp_concurrent(3) == 3
    assert _clamp_concurrent(99) == MAX_CONCURRENT


def test_default_concurrent_is_3():
    assert DEFAULT_CONCURRENT == 3


def _make_executor(fn) -> SubagentExecutor:
    return SubagentExecutor(
        runner=FnRunner(fn),
        parent_tools=("read", "write", "bash", "task"),
    )


def test_executor_run_one_with_known_agent():
    def fn(agent, prompt, context, result_holder):
        return f"[{agent.name}] {prompt}"

    ex = _make_executor(fn)
    r = ex.run_one("general-purpose", "research X", {"ctx_key": "v"})
    assert r.status == SubagentStatus.COMPLETED
    assert r.result == "[general-purpose] research X"
    assert r.agent_name == "general-purpose"


def test_executor_run_one_unknown_agent_fails_fast():
    ex = _make_executor(lambda **kw: "should not be called")
    r = ex.run_one("does-not-exist", "x", {})
    assert r.status == SubagentStatus.FAILED
    assert "unknown sub-agent" in (r.error or "")


def test_executor_run_many_runs_in_parallel():
    """Three sub-agents should run roughly concurrently, not serially."""
    barrier = threading.Barrier(3, timeout=2.0)

    def fn(agent, prompt, context, result_holder):
        barrier.wait()  # all 3 must reach here before any can finish
        return f"done:{prompt}"

    ex = _make_executor(fn)
    t0 = time.time()
    results = ex.run_many([
        ("general-purpose", "a", {}),
        ("general-purpose", "b", {}),
        ("general-purpose", "c", {}),
    ])
    elapsed = time.time() - t0
    # If serial this would take ~3x the time of a single sub-agent.
    # Parallel: roughly 1x. We give some slack for thread startup.
    assert all(r.status == SubagentStatus.COMPLETED for r in results)
    assert elapsed < 1.0  # generous


def test_executor_preserves_job_order_in_results():
    ex = _make_executor(
        lambda agent, prompt, context, result_holder: f"{prompt}:{agent.name}"
    )
    results = ex.run_many([
        ("bash", "first", {}),
        ("general-purpose", "second", {}),
        ("bash", "third", {}),
    ])
    assert len(results) == 3
    assert results[0].result == "first:bash"
    assert results[1].result == "second:general-purpose"
    assert results[2].result == "third:bash"


def test_executor_runner_exception_becomes_failed_result():
    def fn(agent, prompt, context, result_holder):
        raise ValueError("boom")

    ex = _make_executor(fn)
    r = ex.run_one("general-purpose", "x", {})
    assert r.status == SubagentStatus.FAILED
    assert "ValueError" in (r.error or "")
    assert "boom" in (r.error or "")


def test_executor_subagent_sees_isolated_context():
    """Sub-agent writes to its context must NOT affect parent."""
    seen: dict = {}

    def fn(agent, prompt, context, result_holder):
        # Mutate the context — should NOT leak back to parent
        context["new_key"] = "from_subagent"
        seen["context_id"] = id(context)
        return "ok"

    ex = _make_executor(fn)
    parent_ctx = {"original": "parent_value"}
    parent_id = id(parent_ctx)
    ex.run_one("general-purpose", "x", parent_ctx)
    assert seen["context_id"] != parent_id  # deep-copied
    assert "new_key" not in parent_ctx      # isolation works


def test_executor_subagent_cannot_access_task_tool():
    """Even if parent has 'task' tool, sub-agent must not see it."""
    seen_tools: list = []

    def fn(agent, prompt, context, result_holder):
        seen_tools.append(context.get("__subagent_effective_tools__"))
        return "ok"

    ex = _make_executor(fn)
    ex.run_one("general-purpose", "x", {})
    tools = seen_tools[0]
    assert "task" not in tools


def test_executor_inherits_parent_tools_for_general_purpose():
    """general-purpose should see all parent tools (minus task)."""
    seen: list = []

    def fn(agent, prompt, context, result_holder):
        seen.append(context.get("__subagent_effective_tools__"))
        return "ok"

    ex = _make_executor(fn)
    ex.run_one("general-purpose", "x", {})
    tools = seen[0]
    assert set(tools) == {"read", "write", "bash"}  # task stripped


def test_executor_bash_only_gets_bash_tool():
    seen: list = []

    def fn(agent, prompt, context, result_holder):
        seen.append(context.get("__subagent_effective_tools__"))
        return "ok"

    ex = _make_executor(fn)
    ex.run_one("bash", "x", {})
    tools = seen[0]
    assert tools == ["bash"]


def test_executor_cancel_unknown_task_returns_false():
    ex = _make_executor(lambda **kw: "ok")
    assert ex.cancel("does-not-exist") is False


def test_executor_max_concurrent_clamped_to_max():
    cfg = ExecutorConfig(max_concurrent=99)
    ex = SubagentExecutor(runner=FnRunner(lambda **kw: "ok"), config=cfg)
    # Internal pool max_workers should be clamped
    assert ex._max == MAX_CONCURRENT


def test_executor_min_concurrent_clamped_to_min():
    cfg = ExecutorConfig(max_concurrent=0)
    ex = SubagentExecutor(runner=FnRunner(lambda **kw: "ok"), config=cfg)
    assert ex._max == MIN_CONCURRENT


# ---------------------------------------------------------------------------
# PlanStep.subagent integration
# ---------------------------------------------------------------------------


def test_plan_step_default_subagent_is_none():
    from madcop.agent.plan_execute import PlanStep
    s = PlanStep(name="x", action="y")
    assert s.subagent is None


def test_plan_step_can_carry_subagent_name():
    from madcop.agent.plan_execute import PlanStep
    s = PlanStep(name="x", action="y", subagent="general-purpose")
    assert s.subagent == "general-purpose"


def test_plan_execute_loop_still_works_with_subagent_field():
    """Adding the subagent field must not break the v0.6.0 loop."""
    from madcop.agent.plan_execute import (
        ExecutionMode, FnStepExecutor, PlanExecuteConfig,
        PlanExecuteLoop, TrivialPlanner, StepOutcome,
    )

    def fn(step, ctx):
        return StepOutcome(step_name=step.name, output="ok", success=True)

    loop = PlanExecuteLoop(
        TrivialPlanner(),
        FnStepExecutor(fn),
        PlanExecuteConfig(mode=ExecutionMode.FLASH),
    )
    # TrivialPlanner doesn't set subagent, so we can still pass it via ctx
    # (this is a backward-compat smoke test)
    result = loop.run("a")
    assert result.success
