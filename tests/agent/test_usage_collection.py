"""P1-5 — token usage collection end-to-end.

Providers report usage on the stream's final chunk. The client must
forward it on a trailing StreamChunk, the engine must drain the stream
(not break on finish_reason) and sum it across steps, and the DONE
step must carry it in metadata for the UI's context budget.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


class _UsageStream:
    """Round 1: tool call + usage chunk. Round 2: answer + usage chunk."""

    def __init__(self):
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.calls += 1
        if self.calls == 1:
            yield SimpleNamespace(
                tool_call_deltas=({"index": 0, "id": "t", "name": "web_search",
                                    "arguments": '{"query": "x"}'},),
                text="", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="tool_calls")
            yield SimpleNamespace(
                text="", finish_reason=None,
                usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=50, total_tokens=1050))
        else:
            yield SimpleNamespace(text="搜索完成，这是答案内容。", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")
            yield SimpleNamespace(
                text="", finish_reason=None,
                usage=SimpleNamespace(prompt_tokens=1800, completion_tokens=120, total_tokens=1920))


class TestUsageCollection(unittest.TestCase):

    def test_done_carries_accumulated_usage(self):
        from madcop.agent.react_v4 import ReActEngineV4

        ctx = RunContext(
            messages=[Message(role="user", content="搜索一下")],
            model="fake", agent_mode="standard", client=_UsageStream(),
        )
        ctx.tool_executor = lambda *a, **k: '{"ok":true}'

        steps = list(ReActEngineV4().run(ctx))
        done = [s for s in steps if s.kind == StepKind.DONE]
        self.assertEqual(len(done), 1)
        usage = done[0].metadata.get("usage", {})
        # prompt: max across calls (context grows) = 1800
        self.assertEqual(usage.get("prompt_tokens"), 1800)
        # completion: sum across calls = 50 + 120
        self.assertEqual(usage.get("completion_tokens"), 170)
        self.assertEqual(usage.get("total_tokens"), 1970)
        # The tool round executed despite finish_reason=tool_chunks
        # arriving BEFORE the usage chunk (engine drains the stream).
        self.assertIn(StepKind.TOOL_END, [s.kind for s in steps])


if __name__ == "__main__":
    unittest.main()
