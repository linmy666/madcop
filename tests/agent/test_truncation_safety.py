"""P0-1 — truncation safety: finish_reason=length voids tool calls.

A length-stopped stream may carry tool-call arguments that were cut
mid-stream. Executing them (e.g. writing half a file) is worse than
asking the model to resend. The engine must:
  1. NOT execute any tool call from a length-stopped turn,
  2. feed the error back as an observation so the model retries,
  3. execute normally when the resend arrives with finish_reason=stop.

Mirrors pi-mono's agent-loop.ts:208-214 policy.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


class _TruncatingStream:
    """Fake LLM client.

    Round 1: streams a native tool_call whose arguments get cut off,
    finishing with finish_reason='length'.
    Round 2 (after the engine feeds the truncation observation back):
    resends the complete tool call, finishing with 'stop'.
    Round 3: answers with FINAL_ANSWER so the run terminates.
    """

    def __init__(self):
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048,
               tools=None):
        self.calls += 1
        if self.calls == 1:
            # Tool-call fragment that hit the length ceiling — the
            # arguments JSON is visibly incomplete.
            yield SimpleNamespace(
                tool_call_deltas=({
                    "index": 0,
                    "id": "tc-1",
                    "name": "write_file",
                    "arguments": '{"path": "/tmp/x.html", "content": "<html>半截',
                },),
                text="",
                finish_reason=None,
            )
            yield SimpleNamespace(text="", finish_reason="length")
        elif self.calls == 2:
            yield SimpleNamespace(
                tool_call_deltas=({
                    "index": 0,
                    "id": "tc-2",
                    "name": "write_file",
                    "arguments": '{"path": "/tmp/x.html", "content": "<html>完整</html>"}',
                },),
                text="",
                finish_reason=None,
            )
            yield SimpleNamespace(text="", finish_reason="stop")
        else:
            yield SimpleNamespace(
                text="Thought: 文件已写入。\nAction: FINAL_ANSWER\nFINAL_ANSWER: 完成",
                finish_reason=None,
            )
            yield SimpleNamespace(text="", finish_reason="stop")


class _Executor:
    """Records every execution; must NOT see round 1's truncated call."""

    def __init__(self):
        self.executed: list[tuple[str, str]] = []

    def __call__(self, name, raw_input, work_dir=None, pre_approved=False):
        self.executed.append((name, str(raw_input)))
        return json.dumps({"ok": True, "output": "written"})


class TestTruncationSafety(unittest.TestCase):

    def test_length_stop_voids_tool_calls_and_retries(self):
        from madcop.agent.react_v4 import ReActEngineV4

        client = _TruncatingStream()
        executor = _Executor()
        ctx = RunContext(
            messages=[Message(role="user", content="写个 HTML 文件")],
            model="fake",
            agent_mode="standard",
            client=client,
        )
        ctx.tool_executor = executor

        steps = list(ReActEngineV4().run(ctx))
        kinds = [s.kind for s in steps]

        # The complete resend DID execute — exactly once.
        self.assertEqual(len(executor.executed), 1)
        name, raw_args = executor.executed[0]
        self.assertEqual(name, "write_file")
        self.assertIn("完整", raw_args)
        # The truncated round-1 args never reached the executor.
        self.assertNotIn("半截", raw_args)

        # Tool ran and the run finished cleanly.
        self.assertIn(StepKind.TOOL_START, kinds)
        self.assertIn(StepKind.TOOL_END, kinds)
        self.assertIn(StepKind.DONE, kinds)

        # The engine looped: round 1 rejected → round 2 resent →
        # round 3 final answer = at least 3 LLM calls.
        self.assertGreaterEqual(client.calls, 3)

    def test_truncated_pure_answer_still_streams(self):
        """Truncated prose (no tool call) is not an error — the partial
        answer streams as usual; only tool calls are voided."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _HalfAnswer:
            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                yield SimpleNamespace(
                    text="Thought: 让我想想。\nFINAL_ANSWER: 部分答案被截断",
                    finish_reason=None,
                )
                yield SimpleNamespace(text="", finish_reason="length")

        client = _HalfAnswer()
        ctx = RunContext(
            messages=[Message(role="user", content="你好")],
            model="fake",
            agent_mode="standard",
            client=client,
        )
        ctx.tool_executor = lambda *a, **k: "{}"
        steps = list(ReActEngineV4().run(ctx))
        kinds = [s.kind for s in steps]
        self.assertIn(StepKind.TEXT_DELTA, kinds)
        self.assertIn(StepKind.DONE, kinds)
        self.assertNotIn(StepKind.TOOL_START, kinds)


if __name__ == "__main__":
    unittest.main()
