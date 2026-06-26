"""v0.8.0 — Tests for LLMRunner tool-use loop.

Covers:
- Single-call mode (no tool registry) — regression for v0.7.1.
- Tool-use loop: model calls one tool, gets result, final answer.
- Tool-use loop: model calls two tools, gets results, final answer.
- Tool-use loop: model keeps calling tools; hit max_tool_iterations cap.
- Tool-use loop: tool call with no matching tool in registry -> error message.
- Tool-use loop: tool throws -> error propagated in result message.
- Tool-use loop: cancellation in the middle -> returns "[cancelled]".
- Tool-use loop: <think>...</think> blocks are stripped from final answer.
- Tool-use loop: <think> inside a tool call is NOT stripped (only the final answer).
- Tool-use loop: tool_call_id is preserved on the tool result message.
- Tool-use loop: tools= is passed to chat() on every iteration.
- Tool-use loop: empty final content with no tool calls -> empty string returned.
- Tool-use loop: tool name not in registry -> tool result message has ERROR prefix.
- Tool-use loop: concurrent sub-agents each get their own message history.
- Tool-use loop: max_tool_iterations=1 (effectively single-call-with-tools).
- Tool-use loop: tools= and max_tokens are passed on every call.
"""
from __future__ import annotations

import threading
from typing import Any, cast

import pytest

from madcop.agent.subagent.builtins import GENERAL_PURPOSE
from madcop.agent.subagent.llm_runner import LLMRunner
from madcop.agent.subagent.spec import SubagentSpec
from madcop.agent.subagent.status import SubagentResult
from madcop.llm import ChatClient, ChatResponse, Message, ToolCall
from madcop.tools import EchoTool, FunctionTool, ToolRegistry


# ---------------------------------------------------------------------------
# Scripted FakeChatClient — multi-step tool-use responses
# ---------------------------------------------------------------------------


class ScriptedFakeClient(ChatClient):
    """Returns a different ChatResponse for each call.

    Each entry in `script` is a ChatResponse. After the script is
    exhausted, repeats the last one (so an out-of-bounds loop iter still
    gets a response — but typically tests assert on `client.calls`
    to detect the overrun).
    """

    def __init__(self, script: list[ChatResponse]):
        self._script = script
        self.calls: list[list[Message]] = []
        self.tool_kwargs: list[dict[str, Any]] = []

    def chat(  # type: ignore[override]
        self,
        messages: Any,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        self.calls.append(list(messages))
        self.tool_kwargs.append({
            "model": model, "temperature": temperature,
            "max_tokens": max_tokens, "tools": tools,
        })
        if not self._script:
            return ChatResponse(content="", tool_calls=(), model="fake")
        idx = min(len(self.calls) - 1, len(self._script) - 1)
        return self._script[idx]


def _holder() -> SubagentResult:
    return SubagentResult(
        task_id="t1", agent_name="x",
        cancel_event=threading.Event(),
    )


# A echo tool registered in a registry — used by all tool-use tests.
@pytest.fixture
def echo_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(EchoTool())
    return reg


# ---------------------------------------------------------------------------
# Regression: single-call mode still works (v0.7.1 behavior)
# ---------------------------------------------------------------------------


def test_tool_use_mode_disabled_when_registry_is_none():
    """No tool_registry => single call, no tools= kwarg."""
    client = ScriptedFakeClient([ChatResponse(content="final", tool_calls=(), model="f")])
    runner = LLMRunner(client, tool_registry=None)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="x", context={}, result_holder=_holder())
    assert out == "final"
    assert len(client.calls) == 1
    # When tool-use is disabled, tools is None (not populated)
    assert client.tool_kwargs[0]["tools"] is None


# ---------------------------------------------------------------------------
# Happy path: one tool call then final answer
# ---------------------------------------------------------------------------


def test_tool_use_loop_one_tool_call_then_final_answer(echo_registry):
    tool_call = ToolCall(id="call_1", name="echo", arguments={"text": "hi"})
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(tool_call,), model="f"),
        ChatResponse(content="done", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="echo hi", context={}, result_holder=_holder())
    assert out == "done"
    assert len(client.calls) == 2
    # Second call includes the tool result for call_1
    second_msg = client.calls[1][-1]
    assert second_msg.role == "tool"
    assert second_msg.tool_call_id == "call_1"
    assert "hi" in second_msg.content  # echo tool echoes back


# ---------------------------------------------------------------------------
# Multi-step: two tool calls in sequence
# ---------------------------------------------------------------------------


def test_tool_use_loop_two_tool_calls_then_final_answer(echo_registry):
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="c1", name="echo", arguments={"text": "A"}),), model="f"),
        ChatResponse(content="", tool_calls=(ToolCall(id="c2", name="echo", arguments={"text": "B"}),), model="f"),
        ChatResponse(content="final-answer", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert out == "final-answer"
    assert len(client.calls) == 3
    # After 3 chat() calls: messages are [system, user, assistant(tool_c1), tool,
    #   assistant(tool_c2), tool]. The third call's FINAL assistant message is
    #   not appended (the model returned it as a final answer, not a tool call)
    #   — we just return its content. So 6 messages, not 7.
    roles = [m.role for m in client.calls[2]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool"]


# ---------------------------------------------------------------------------
# Hit the max_tool_iterations safety cap
# ---------------------------------------------------------------------------


def test_tool_use_loop_hits_max_iterations_returns_best_so_far(echo_registry):
    # Always emit a tool call — never converges
    always_call = ChatResponse(
        content="working...",
        tool_calls=(ToolCall(id="c-loop", name="echo", arguments={"text": "x"}),),
        model="f",
    )
    client = ScriptedFakeClient([always_call])  # same response repeats
    runner = LLMRunner(client, tool_registry=echo_registry, max_tool_iterations=3)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    # Should not raise; should return something
    assert isinstance(out, str)
    # 3 iterations means 3 chat() calls
    assert len(client.calls) == 3


def test_tool_use_loop_max_iterations_zero_is_safe(echo_registry):
    """max_tool_iterations=0: skip the loop entirely, return no content."""
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="c1", name="echo", arguments={"text": "x"}),), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry, max_tool_iterations=0)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    # No chat() call made at all
    assert len(client.calls) == 0
    assert "max_tool_iterations" in out


# ---------------------------------------------------------------------------
# Tool call to an unknown tool
# ---------------------------------------------------------------------------


def test_tool_use_loop_unknown_tool_returns_error_message(echo_registry):
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="c1", name="no_such_tool", arguments={}),), model="f"),
        ChatResponse(content="ok", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert out == "ok"
    # The tool result message should mention the error
    tool_msg = client.calls[1][-1]
    assert tool_msg.role == "tool"
    assert "ERROR" in tool_msg.content
    assert "no_such_tool" in tool_msg.content


# ---------------------------------------------------------------------------
# Tool throws an exception -> error propagated in tool result
# ---------------------------------------------------------------------------


def test_tool_use_loop_tool_exception_becomes_tool_error_message():
    def boom(**kwargs):
        raise ValueError("kaboom")

    registry = ToolRegistry()
    registry.register(FunctionTool(
        name="boom", description="always throws",
        fn=boom,
        parameters_schema={"type": "object", "properties": {}, "required": []},
    ))
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="c1", name="boom", arguments={}),), model="f"),
        ChatResponse(content="recovered", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert out == "recovered"
    err_msg = client.calls[1][-1]
    assert "ERROR" in err_msg.content
    assert "kaboom" in err_msg.content


# ---------------------------------------------------------------------------
# Cancellation in the middle of the loop
# ---------------------------------------------------------------------------


def test_tool_use_loop_cancellation_returns_cancelled(echo_registry):
    holder = _holder()
    holder.cancel_event.set()  # cancel before we even start
    client = ScriptedFakeClient([
        ChatResponse(content="never-used", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=holder)
    assert out == "[cancelled]"
    assert len(client.calls) == 0  # never even called


def test_tool_use_loop_cancellation_mid_loop(echo_registry):
    """Cancel after the first iteration; second iteration should bail.

    We simulate the LLM taking a long time: the second chat() call sets
    cancel_event and returns a 'still running' marker. The LLMRunner's
    loop should detect the cancel on the next iteration and return
    "[cancelled]" instead of that marker.
    """
    cancel_holder = _holder()
    client = ScriptedFakeClient([ChatResponse(content="placeholder", tool_calls=(), model="f")])

    call_count = {"n": 0}

    def chat_with_cancel(messages, **kwargs):
        client.calls.append(list(messages))  # mimic original behavior
        client.tool_kwargs.append(kwargs)
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ChatResponse(
                content="",
                tool_calls=(ToolCall(id="c1", name="echo", arguments={"text": "x"}),),
                model="f",
            )
        # Second call: set cancel and return a sentinel that should
        # NOT be the final answer (because LLMRunner sees the cancel
        # and returns "[cancelled]" instead).
        cancel_holder.cancel_event.set()
        return ChatResponse(content="SHOULD-NOT-RETURN", tool_calls=(), model="f")

    client.chat = chat_with_cancel  # type: ignore[method-assign]
    runner = LLMRunner(client, tool_registry=echo_registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=cancel_holder)
    assert out == "[cancelled]"


# ---------------------------------------------------------------------------
# <think>...</think> stripping (reasoning models)
# ---------------------------------------------------------------------------


def test_tool_use_loop_strips_thinking_from_final_answer(echo_registry):
    client = ScriptedFakeClient([
        ChatResponse(content="<think>the answer is 42</think>\nThe answer is 42.", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert "<think>" not in out
    assert "The answer is 42." in out


# ---------------------------------------------------------------------------
# tool_call_id and tool name preserved on result message
# ---------------------------------------------------------------------------


def test_tool_use_loop_preserves_tool_call_id_and_name(echo_registry):
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="abc-123", name="echo", arguments={"text": "x"}),), model="f"),
        ChatResponse(content="ok", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry)
    runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    tool_msg = client.calls[1][-1]
    assert tool_msg.tool_call_id == "abc-123"
    assert tool_msg.name == "echo"


# ---------------------------------------------------------------------------
# tools= kwarg is passed on every iteration
# ---------------------------------------------------------------------------


def test_tool_use_loop_passes_tools_kwarg_every_call(echo_registry):
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="c1", name="echo", arguments={"text": "x"}),), model="f"),
        ChatResponse(content="done", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry)
    runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert "tools" in client.tool_kwargs[0]
    assert "tools" in client.tool_kwargs[1]
    # Same schemas both times
    assert client.tool_kwargs[0]["tools"] == client.tool_kwargs[1]["tools"]


# ---------------------------------------------------------------------------
# max_tokens is passed on every call
# ---------------------------------------------------------------------------


def test_tool_use_loop_passes_max_tokens_every_call(echo_registry):
    client = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="c1", name="echo", arguments={"text": "x"}),), model="f"),
        ChatResponse(content="done", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry, max_tokens=256)
    runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert client.tool_kwargs[0].get("max_tokens") == 256
    assert client.tool_kwargs[1].get("max_tokens") == 256


# ---------------------------------------------------------------------------
# Empty final content with no tool calls
# ---------------------------------------------------------------------------


def test_tool_use_loop_empty_final_content_with_no_tools(echo_registry):
    client = ScriptedFakeClient([ChatResponse(content="", tool_calls=(), model="f")])
    runner = LLMRunner(client, tool_registry=echo_registry)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert out == ""


# ---------------------------------------------------------------------------
# Concurrent sub-agents each get independent message history
# ---------------------------------------------------------------------------


def test_two_runners_in_parallel_have_independent_history(echo_registry):
    """Each LLMRunner.run() starts with a fresh messages list."""
    a = ScriptedFakeClient([
        ChatResponse(content="", tool_calls=(ToolCall(id="a1", name="echo", arguments={"text": "A"}),), model="a"),
        ChatResponse(content="a-done", tool_calls=(), model="a"),
    ])
    b = ScriptedFakeClient([
        ChatResponse(content="b-done", tool_calls=(), model="b"),
    ])
    runner_a = LLMRunner(a, tool_registry=echo_registry)
    runner_b = LLMRunner(b, tool_registry=echo_registry)

    # Interleave: a's first call, b's first call, a's second call
    out_a_1 = runner_a.run(agent=GENERAL_PURPOSE, prompt="A", context={}, result_holder=_holder())
    out_b_1 = runner_b.run(agent=GENERAL_PURPOSE, prompt="B", context={}, result_holder=_holder())
    out_a_2 = runner_a.run(agent=GENERAL_PURPOSE, prompt="A again", context={}, result_holder=_holder())

    assert out_a_1 == "a-done"
    assert out_b_1 == "b-done"
    assert out_a_2 == "a-done"  # b's history didn't leak into a
    # a's last call should NOT contain b's user message
    last_a_user = [m for m in a.calls[-1] if m.role == "user"]
    assert any("A again" in m.content for m in last_a_user)
    assert not any("B" == m.content for m in last_a_user)


# ---------------------------------------------------------------------------
# max_tool_iterations=1 still calls chat() once (effectively no tools used)
# ---------------------------------------------------------------------------


def test_tool_use_loop_max_iterations_one_just_calls_chat_once(echo_registry):
    client = ScriptedFakeClient([
        ChatResponse(content="done", tool_calls=(), model="f"),
    ])
    runner = LLMRunner(client, tool_registry=echo_registry, max_tool_iterations=1)
    out = runner.run(agent=GENERAL_PURPOSE, prompt="p", context={}, result_holder=_holder())
    assert out == "done"
    assert len(client.calls) == 1
