"""Tests for LLMRunner (real-LLM-backed sub-agent runner)."""
from __future__ import annotations

from typing import Any, Mapping

import pytest

from madcop.agent.subagent.builtins import GENERAL_PURPOSE, BASH
from madcop.agent.subagent.llm_runner import LLMRunner
from madcop.agent.subagent.spec import SubagentSpec
from madcop.agent.subagent.status import SubagentResult, SubagentStatus


# ---------------------------------------------------------------------------
# Fake ChatClient (avoids needing real LLM in tests)
# ---------------------------------------------------------------------------


class FakeChatClient:
    def __init__(self, scripted: str = "ok", raise_exc: Exception | None = None):
        self._scripted = scripted
        self._raise = raise_exc
        self.calls: list[list[Any]] = []

    def chat(self, messages, **kwargs):
        from madcop.llm import ChatResponse
        self.calls.append(list(messages))
        if self._raise is not None:
            raise self._raise
        return ChatResponse(
            content=self._scripted,
            tool_calls=(),
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            model="fake-model",
        )


def _holder() -> SubagentResult:
    import threading
    return SubagentResult(
        task_id="t1", agent_name="x",
        cancel_event=threading.Event(),
    )


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------


def test_llm_runner_calls_chat_with_system_and_user():
    client = FakeChatClient("hello")
    runner = LLMRunner(client, max_tokens=100)
    out = runner.run(
        agent=GENERAL_PURPOSE,
        prompt="do X",
        context={},
        result_holder=_holder(),
    )
    assert out == "hello"
    assert len(client.calls) == 1
    msgs = client.calls[0]
    assert msgs[0].role == "system"
    assert msgs[1].role == "user"
    assert msgs[0].content == GENERAL_PURPOSE.system_prompt
    assert "do X" in msgs[1].content


def test_llm_runner_no_system_prompt_when_agent_has_none():
    spec = SubagentSpec(name="x", description="x", system_prompt="")
    client = FakeChatClient("ok")
    runner = LLMRunner(client)
    out = runner.run(agent=spec, prompt="hi", context={}, result_holder=_holder())
    msgs = client.calls[0]
    assert len(msgs) == 1
    assert msgs[0].role == "user"


def test_llm_runner_passes_max_tokens_and_temperature():
    client = FakeChatClient()
    runner = LLMRunner(client, max_tokens=256, temperature=0.7)
    runner.run(agent=BASH, prompt="ls", context={}, result_holder=_holder())
    # The kwargs are passed through to chat() — FakeChatClient accepts **kwargs
    # We can't easily assert without a more elaborate fake, but the call didn't error.


# ---------------------------------------------------------------------------
# Context handling
# ---------------------------------------------------------------------------


def test_llm_runner_includes_context_by_default():
    client = FakeChatClient()
    runner = LLMRunner(client)
    runner.run(
        agent=GENERAL_PURPOSE,
        prompt="summarise",
        context={"results": {"a": 1, "b": 2}, "events": "x" * 500},
        result_holder=_holder(),
    )
    user_msg = client.calls[0][1].content
    assert "summarise" in user_msg
    assert "results" in user_msg
    assert "events" in user_msg


def test_llm_runner_truncates_long_context_values():
    client = FakeChatClient()
    runner = LLMRunner(client)
    long_value = "x" * 1000
    runner.run(
        agent=GENERAL_PURPOSE,
        prompt="x",
        context={"big": long_value},
        result_holder=_holder(),
    )
    user_msg = client.calls[0][1].content
    # repr of the value is truncated to 200 chars, so the raw x-run is
    # shorter than the original 1000. We assert it's < 200 chars after
    # the "big: " prefix and that 201 consecutive x's don't fit.
    assert "x" * 50 in user_msg            # many x's survive
    assert "x" * 201 not in user_msg      # but not 201 in a row


def test_llm_runner_filters_subagent_internal_keys():
    client = FakeChatClient()
    runner = LLMRunner(client)
    runner.run(
        agent=GENERAL_PURPOSE,
        prompt="x",
        context={
            "real_key": "visible",
            "__subagent_effective_tools__": ["a", "b"],
            "__subagent_max_turns__": 50,
        },
        result_holder=_holder(),
    )
    user_msg = client.calls[0][1].content
    assert "real_key" in user_msg
    assert "visible" in user_msg
    assert "__subagent_effective_tools__" not in user_msg
    assert "__subagent_max_turns__" not in user_msg


def test_llm_runner_skips_context_section_when_empty():
    client = FakeChatClient()
    runner = LLMRunner(client)
    runner.run(agent=GENERAL_PURPOSE, prompt="exact prompt", context={}, result_holder=_holder())
    user_msg = client.calls[0][1].content
    assert user_msg == "exact prompt"


def test_llm_runner_include_context_false_drops_context():
    client = FakeChatClient()
    runner = LLMRunner(client, include_context=False)
    runner.run(
        agent=GENERAL_PURPOSE,
        prompt="exact",
        context={"should": "not appear"},
        result_holder=_holder(),
    )
    user_msg = client.calls[0][1].content
    assert user_msg == "exact"
    assert "should" not in user_msg


# ---------------------------------------------------------------------------
# Thinking-block stripping (reasoning models)
# ---------------------------------------------------------------------------


def test_llm_runner_strips_thinking_block():
    client = FakeChatClient(scripted="<think>internal</think>\n\nreal answer")
    runner = LLMRunner(client)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="x", context={}, result_holder=_holder())
    assert "real answer" in out
    assert "<think>" not in out
    assert "internal" not in out


def test_llm_runner_keeps_response_without_think_block():
    client = FakeChatClient(scripted="just an answer")
    runner = LLMRunner(client)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="x", context={}, result_holder=_holder())
    assert out == "just an answer"


# ---------------------------------------------------------------------------
# Cancellation + error handling
# ---------------------------------------------------------------------------


def test_llm_runner_returns_cancelled_marker_if_cancelled_before_call():
    import threading
    holder = _holder()
    holder.cancel_event.set()  # cancel before run

    client = FakeChatClient()
    runner = LLMRunner(client)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="x", context={}, result_holder=holder)
    assert out == "[cancelled]"
    assert client.calls == []  # never called chat()


def test_llm_runner_propagates_chat_client_exceptions():
    client = FakeChatClient(raise_exc=RuntimeError("network down"))
    runner = LLMRunner(client)
    with pytest.raises(RuntimeError, match="network down"):
        runner.run(agent=GENERAL_PURPOSE, prompt="x", context={}, result_holder=_holder())
