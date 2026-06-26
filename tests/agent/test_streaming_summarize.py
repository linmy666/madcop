"""v1.7.0 — Tests for streaming and summarization middleware."""
from __future__ import annotations

import json
import pytest
from types import SimpleNamespace
from typing import Any

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_STEP_END,
    HOOK_STEP_START,
    HookContext,
    MiddlewareChain,
)
from madcop.agent.streaming import StreamStepMiddleware
from madcop.agent.summarize import (
    SummarizationMiddleware,
    DEFAULT_MAX_TOKENS,
    _estimate_tokens,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_ctx(
    goal: str = "test goal",
    hook: str = HOOK_STEP_END,
    *,
    step_name: str = "step1",
    step_action: str = "do something",
    output: str = "result text",
    success: bool = True,
    plan_steps: list | None = None,
) -> HookContext:
    step = SimpleNamespace(name=step_name, action=step_action)
    plan = SimpleNamespace(steps=plan_steps or [step])
    outcome = SimpleNamespace(
        step_name=step_name,
        output=output,
        success=success,
        cost_usd=0.001,
        duration_s=0.5,
        error=None,
    )
    ctx = HookContext(hook=hook, goal=goal, plan=plan, step=step, outcome=outcome)
    ctx.shared["step_outcomes"] = {step_name: outcome}
    ctx.shared["_step_index"] = 0
    ctx.shared["_step_total"] = 1
    return ctx


class FakeClient:
    """LLM client that returns canned responses."""
    def __init__(self, response: str = "Summary of the step."):
        self._response = response
        self.call_count = 0

    def chat(self, **kwargs):
        self.call_count += 1
        return {"choices": [{"message": {"content": self._response}}]}


# --------------------------------------------------------------------------- #
# StreamStepMiddleware
# --------------------------------------------------------------------------- #


class TestStreamStepMiddleware:
    def test_raw_step_end_event(self):
        events = []
        mw = StreamStepMiddleware(on_stream=lambda evt, data: events.append((evt, data)))
        ctx = _make_ctx(hook=HOOK_STEP_END, output="hello world")
        mw(ctx)
        assert len(events) == 1
        assert events[0][0] == "step_end"
        assert events[0][1]["step_name"] == "step1"
        assert events[0][1]["output"] == "hello world"
        assert events[0][1]["success"] is True

    def test_raw_plan_start_event(self):
        events = []
        mw = StreamStepMiddleware(on_stream=lambda evt, data: events.append((evt, data)))
        ctx = _make_ctx(hook=HOOK_PLAN_START, plan_steps=[
            SimpleNamespace(name="a", action="x"),
            SimpleNamespace(name="b", action="y"),
        ])
        mw(ctx)
        assert events[0][0] == "plan_start"
        assert events[0][1]["step_count"] == 2
        assert events[0][1]["goal"] == "test goal"

    def test_raw_plan_end_event(self):
        events = []
        mw = StreamStepMiddleware(on_stream=lambda evt, data: events.append((evt, data)))
        ctx = _make_ctx(hook=HOOK_PLAN_END)
        ctx.shared["plan_summary"] = {
            "plan_success": True,
            "total_cost": 0.003,
            "total_duration": 1.5,
            "plan_lines": ["a", "b", "c"],
            "failure_modes": [],
        }
        mw(ctx)
        assert events[0][0] == "plan_end"
        assert events[0][1]["success"] is True
        assert events[0][1]["total_cost"] == 0.003

    def test_text_format_step_end(self):
        lines = []
        mw = StreamStepMiddleware(
            on_stream=lambda evt, data: lines.append(data["line"]),
            fmt="text",
        )
        ctx = _make_ctx(hook=HOOK_STEP_END, output="hello")
        mw(ctx)
        assert len(lines) == 1
        assert "✓" in lines[0]
        assert "step1" in lines[0]
        assert "hello" in lines[0]

    def test_text_format_step_start(self):
        lines = []
        mw = StreamStepMiddleware(
            on_stream=lambda evt, data: lines.append(data["line"]),
            fmt="text",
        )
        ctx = _make_ctx(hook=HOOK_STEP_START)
        mw(ctx)
        assert len(lines) == 1
        assert "[1/1]" in lines[0]

    def test_text_format_long_output_truncated(self):
        lines = []
        mw = StreamStepMiddleware(
            on_stream=lambda evt, data: lines.append(data["line"]),
            fmt="text",
        )
        ctx = _make_ctx(hook=HOOK_STEP_END, output="x" * 300)
        mw(ctx)
        assert "..." in lines[0]

    def test_text_format_failed_step(self):
        lines = []
        mw = StreamStepMiddleware(
            on_stream=lambda evt, data: lines.append(data["line"]),
            fmt="text",
        )
        ctx = _make_ctx(hook=HOOK_STEP_END, success=False, output="error!")
        mw(ctx)
        assert "✗" in lines[0]

    def test_ignores_irrelevant_hooks(self):
        events = []
        mw = StreamStepMiddleware(on_stream=lambda evt, data: events.append(evt))
        # HOOK_REPLAN should be ignored
        ctx = _make_ctx(hook="replan")
        mw(ctx)
        assert len(events) == 0


# --------------------------------------------------------------------------- #
# SummarizationMiddleware
# --------------------------------------------------------------------------- #


class TestSummarizationMiddleware:
    def test_no_action_under_budget(self):
        """If total tokens < max, do nothing."""
        client = FakeClient()
        mw = SummarizationMiddleware(client, max_tokens=100_000)
        ctx = _make_ctx(output="small output")
        mw(ctx)
        assert client.call_count == 0

    def test_summarizes_when_over_budget(self):
        """When total exceeds max_tokens, old steps should be summarized."""
        client = FakeClient(response="Short summary.")
        mw = SummarizationMiddleware(
            client, max_tokens=50, keep_recent=1,
        )
        # Build a context with many steps that exceed token budget
        outcomes = {}
        for i in range(5):
            name = f"step_{i}"
            outcome = SimpleNamespace(
                step_name=name,
                output=f"This is a long output for step {i}. " * 20,
                success=True,
                cost_usd=0.001,
                duration_s=0.5,
                error=None,
            )
            outcomes[name] = outcome

        ctx = HookContext(hook=HOOK_STEP_END, goal="test", plan=SimpleNamespace(steps=[]))
        ctx.shared["step_outcomes"] = outcomes

        mw(ctx)

        assert client.call_count > 0
        log = mw.compaction_log
        assert len(log) == 1
        assert log[0]["steps_summarized"] >= 1
        assert log[0]["tokens_saved"] > 0

    def test_keeps_recent_steps_verbatim(self):
        """The most recent N steps should not be summarized."""
        client = FakeClient(response="Summary.")
        mw = SummarizationMiddleware(
            client, max_tokens=10, keep_recent=2,
        )
        outcomes = {}
        for i in range(5):
            name = f"step_{i}"
            outcomes[name] = SimpleNamespace(
                step_name=name,
                output=f"Long output {i}. " * 30,
                success=True,
                cost_usd=0.0,
                duration_s=0.0,
                error=None,
            )
        ctx = HookContext(hook=HOOK_STEP_END, goal="test", plan=SimpleNamespace(steps=[]))
        ctx.shared["step_outcomes"] = outcomes

        mw(ctx)

        # Last 2 steps (step_3, step_4) should not be modified
        assert not outcomes["step_4"].output.startswith("[summarized]")
        assert not outcomes["step_3"].output.startswith("[summarized]")
        # Earlier steps should be summarized
        assert outcomes["step_0"].output.startswith("[summarized]")

    def test_skips_when_few_steps(self):
        """Don't summarize if there are fewer than keep_recent + min_summarize steps."""
        client = FakeClient()
        mw = SummarizationMiddleware(client, max_tokens=1, keep_recent=3)
        outcomes = {
            "a": SimpleNamespace(step_name="a", output="x" * 100, success=True,
                                 cost_usd=0, duration_s=0, error=None),
            "b": SimpleNamespace(step_name="b", output="y" * 100, success=True,
                                 cost_usd=0, duration_s=0, error=None),
        }
        ctx = HookContext(hook=HOOK_STEP_END, goal="t", plan=SimpleNamespace(steps=[]))
        ctx.shared["step_outcomes"] = outcomes
        mw(ctx)
        assert client.call_count == 0

    def test_llm_failure_graceful(self):
        """If LLM call fails, step output stays unchanged."""
        class BadClient:
            def chat(self, **kwargs):
                raise RuntimeError("LLM down")
        mw = SummarizationMiddleware(BadClient(), max_tokens=10, keep_recent=1)
        outcomes = {}
        for i in range(4):
            outcomes[f"s{i}"] = SimpleNamespace(
                step_name=f"s{i}", output="x" * 200, success=True,
                cost_usd=0, duration_s=0, error=None,
            )
        ctx = HookContext(hook=HOOK_STEP_END, goal="t", plan=SimpleNamespace(steps=[]))
        ctx.shared["step_outcomes"] = outcomes
        mw(ctx)
        # Outputs should be unchanged (no [summarized] prefix)
        for outcome in outcomes.values():
            assert not outcome.output.startswith("[summarized]")

    def test_compaction_log_records_events(self):
        client = FakeClient(response="Summarized.")
        mw = SummarizationMiddleware(client, max_tokens=10, keep_recent=1)
        outcomes = {}
        for i in range(5):
            outcomes[f"s{i}"] = SimpleNamespace(
                step_name=f"s{i}", output="x" * 200, success=True,
                cost_usd=0, duration_s=0, error=None,
            )
        ctx = HookContext(hook=HOOK_STEP_END, goal="t", plan=SimpleNamespace(steps=[]))
        ctx.shared["step_outcomes"] = outcomes
        mw(ctx)
        log = mw.compaction_log
        assert len(log) == 1
        assert "tokens_before" in log[0]
        assert "tokens_after" in log[0]
        assert log[0]["tokens_before"] > log[0]["tokens_after"]


# --------------------------------------------------------------------------- #
# Token estimation
# --------------------------------------------------------------------------- #


class TestEstimateTokens:
    def test_english_text(self):
        text = "The quick brown fox jumps over the lazy dog."
        tokens = _estimate_tokens(text)
        assert 10 < tokens < 15  # ~44 chars / 4

    def test_chinese_text(self):
        text = "供应链异常检测系统设计"
        tokens = _estimate_tokens(text)
        assert tokens == 5  # 11 CJK chars / 2

    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_mixed(self):
        text = "OMS cancel rate 取消率 spike"
        tokens = _estimate_tokens(text)
        assert tokens > 0


# --------------------------------------------------------------------------- #
# Composes with MiddlewareChain
# --------------------------------------------------------------------------- #


class TestComposition:
    def test_stream_and_summarize_compose(self):
        """Both middlewares can run in the same chain."""
        events = []
        client = FakeClient()
        chain = MiddlewareChain([
            StreamStepMiddleware(on_stream=lambda evt, data: events.append(evt)),
            SummarizationMiddleware(client, max_tokens=100_000),  # won't trigger
        ])
        ctx = _make_ctx(hook=HOOK_STEP_END, output="test")
        chain(ctx)
        # Stream should have fired
        assert "step_end" in events
        # Summarize should NOT have called the LLM
        assert client.call_count == 0
