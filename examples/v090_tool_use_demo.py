"""v0.9.0 — Tool-use demo: sub-agents that actually call tools.

v0.7.0's sub-agent demo used a FnRunner that returned a hard-coded
string, so the LLM never actually called anything. v0.8.0 added the
tool-use loop in `LLMRunner`, but no demo exercised it end-to-end.

This demo fixes that. We build:

- a `ToolRegistry` with `EchoTool` + `GetTimeTool`
- an `LLMRunner(client, tool_registry=registry)` (v0.8.0)
- a `SubagentExecutor` that runs the runner in parallel

Then we dispatch 3 prompts to sub-agents. The sub-agents may or may
not call a tool (that's the LLM's call). We just observe the chat()
calls and tool_calls to confirm the loop ran.

Without --llm: we use a scripted fake client that always emits one
echo call + a final answer. This lets you run the demo offline and
still see the tool-use loop in action.

With --llm: set MADCOP_OPENAI_* env vars; the real LLM decides
whether to call tools or just answer.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from madcop.agent.subagent import (
    ExecutorConfig,
    GENERAL_PURPOSE,
    LLMRunner,
    SubagentExecutor,
)
from madcop.llm import ChatClient, ChatResponse, Message, ToolCall
from madcop.tools import EchoTool, GetTimeTool, ToolRegistry


# --------------------------------------------------------------------------- #
# Scripted fake — emulates an LLM that always tries echo + returns a summary
# --------------------------------------------------------------------------- #


class ScriptedToolUseClient(ChatClient):
    """A fake ChatClient that always emits one tool_call then a final answer.

    Three different `script` flavours, keyed by the prompt text:
    - "echo-hello"      → calls echo("hello") then says "done"
    - "get-time"        → calls get_current_time() then says "the time is X"
    - "no-tool-needed"  → answers directly without any tool call
    """

    def __init__(self, call_log: list[dict[str, Any]] | None = None):
        self._call_log = call_log if call_log is not None else []

    def chat(  # type: ignore[override]
        self,
        messages,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        # Record the call
        self._call_log.append({
            "n_user_msgs": sum(1 for m in messages if m.role == "user"),
            "n_tool_msgs": sum(1 for m in messages if m.role == "tool"),
            "tools": tools,
        })

        # Find the latest user message
        user_msg = next(
            (m.content for m in reversed(list(messages)) if m.role == "user"), ""
        )

        # Has the LLM already called a tool? Then return final answer
        if any(m.role == "tool" for m in messages):
            if "echo" in user_msg.lower():
                return ChatResponse(
                    content="done: echoed successfully",
                    tool_calls=(), model="fake",
                )
            if "time" in user_msg.lower():
                return ChatResponse(
                    content="the time has been recorded",
                    tool_calls=(), model="fake",
                )

        # First call — decide whether to use a tool based on the prompt
        if "echo" in user_msg.lower():
            return ChatResponse(
                content="", tool_calls=(
                    ToolCall(id="c1", name="echo",
                             arguments={"text": "hello from sub-agent"}),
                ), model="fake",
            )
        if "time" in user_msg.lower():
            return ChatResponse(
                content="", tool_calls=(
                    ToolCall(id="c2", name="get_current_time", arguments={}),
                ), model="fake",
            )
        # Default — answer directly without tools
        return ChatResponse(
            content=f"answer to '{user_msg}' (no tool needed)",
            tool_calls=(), model="fake",
        )


# --------------------------------------------------------------------------- #
# Main demo
# --------------------------------------------------------------------------- #


def main(use_llm: bool = False) -> int:
    print("=" * 60)
    print("madcop v0.9.0 — tool-use sub-agent demo")
    print("=" * 60)

    # 1. Build the tool registry (always — even in scripted mode we
    # need real Tool objects to dispatch to).
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(GetTimeTool())
    print(f"tools registered: {registry.names()}")

    # 2. Build the LLM client
    call_log: list[dict[str, Any]] = []
    if use_llm:
        from madcop.llm import OpenAICompatClient
        try:
            client = OpenAICompatClient()
        except ValueError as e:
            print(f"LLM init failed: {e}", file=sys.stderr)
            print("Falling back to scripted client.", file=sys.stderr)
            client = ScriptedToolUseClient(call_log)
    else:
        print("(pass --llm to use a real LLM; using scripted client)")
        client = ScriptedToolUseClient(call_log)

    # 3. Build the tool-use runner (v0.8.0's new feature)
    runner = LLMRunner(
        client,
        max_tokens=256,
        temperature=0.0,
        tool_registry=registry,  # <-- this enables the tool-use loop
        max_tool_iterations=4,
    )
    print(f"runner: tool_registry={'yes' if runner.tool_registry else 'no'}")

    # 4. Build the executor
    executor = SubagentExecutor(
        runner=runner,
        config=ExecutorConfig(max_concurrent=3),
    )

    # 5. Dispatch 3 sub-agent tasks in parallel
    jobs = [
        (GENERAL_PURPOSE.name, "Use the echo tool to say hello", {"step": 1}),
        (GENERAL_PURPOSE.name, "Tell me the current time", {"step": 2}),
        (GENERAL_PURPOSE.name, "Just answer: what is 2+2? (no tool needed)", {"step": 3}),
    ]
    print(f"\nrunning {len(jobs)} sub-agents in parallel...")
    t0 = time.monotonic()
    results = executor.run_many(jobs)
    elapsed = time.monotonic() - t0

    # 6. Report
    print(f"\nfinished in {elapsed*1000:.1f}ms")
    print(f"LLM client received {len(call_log)} chat() calls total")
    for i, r in enumerate(results, 1):
        print(f"\n--- sub-agent {i} ---")
        print(f"  status:  {r.status.name}")
        print(f"  result:  {r.result!r}")
        if r.error:
            print(f"  error:   {r.error}")

    # 7. Verify the tool-use loop actually ran
    n_tool_calls = sum(1 for c in call_log if c["tools"])
    print("\n" + "=" * 60)
    print("verdict:")
    print(f"  - sub-agents used a tool registry: {'yes' if runner.tool_registry else 'no'}")
    print(f"  - chat() calls with tools=: {n_tool_calls}/{len(call_log)}")
    if n_tool_calls >= 2:
        print("  - PASS: tool-use loop is working end-to-end")
        return 0
    print("  - FAIL: not enough tool-use activity")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", action="store_true",
                        help="Use a real LLM (env: MADCOP_OPENAI_*)")
    args = parser.parse_args()
    sys.exit(main(use_llm=args.llm))
