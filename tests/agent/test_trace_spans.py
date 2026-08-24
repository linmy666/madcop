"""P2-9 — engine emits a trace span tree (turn → llm_call → tool_call).

Every engine step opens an llm_call span; every tool execution opens a
tool_call span parented to its step's llm span; usage and outcomes are
recorded. The existing TraceTree UI consumes this via /api/trace.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from madcop.agent.react_v4 import ReActEngineV4
from madcop.agent.runtime import RunContext, StepKind
from madcop.agent.trace import TraceStore, reset_trace_store, get_trace_store
from madcop.llm.client import Message


class _ToolThenAnswer:
    def __init__(self):
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.calls += 1
        if self.calls == 1:
            yield SimpleNamespace(
                tool_call_deltas=({"index": 0, "id": "t", "name": "web_search",
                                    "arguments": '{"query": "x"}'},),
                text="", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")
            yield SimpleNamespace(text="", finish_reason=None,
                                  usage=SimpleNamespace(prompt_tokens=500,
                                                        completion_tokens=80,
                                                        total_tokens=580))
        else:
            yield SimpleNamespace(text="搜索完成，这是最终回答。", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")


class TestTraceSpans(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        reset_trace_store(TraceStore(Path(self._tmp.name) / "trace.db"))

    def tearDown(self):
        reset_trace_store(None)
        self._tmp.cleanup()

    def test_span_tree_hierarchy(self):
        ctx = RunContext(
            messages=[Message(role="user", content="搜索一下")],
            model="f", agent_mode="standard", client=_ToolThenAnswer(),
            session_id="trace-sess",
        )
        ctx.tool_executor = lambda *a, **k: '{"ok": true}'
        list(ReActEngineV4().run(ctx))

        store = get_trace_store()
        nodes = store.get_conversation_trace("trace-sess")
        by_type = {}
        for n in nodes:
            by_type.setdefault(n.node_type, []).append(n)

        # turn root (engine-created when the route passes no root id)
        self.assertIn("turn", by_type)
        turn = by_type["turn"][0]
        self.assertEqual(turn.parent_id, None)

        # llm_call spans, parented to the turn
        self.assertGreaterEqual(len(by_type.get("llm_call", [])), 2)
        for llm in by_type["llm_call"]:
            self.assertEqual(llm.parent_id, turn.id)
            self.assertEqual(llm.status, "done")

        # tool_call span, parented to the FIRST llm span
        tools = by_type.get("tool_call", [])
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].parent_id, by_type["llm_call"][0].id)
        self.assertEqual(tools[0].label, "web_search")
        self.assertIn("query", tools[0].input)

        # usage recorded on the llm span output
        import json
        first_llm_out = json.loads(by_type["llm_call"][0].output or "{}")
        self.assertEqual(first_llm_out.get("usage", {}).get("prompt_tokens"), 500)
        self.assertEqual(first_llm_out.get("tool_calls"), ["web_search"])

    def test_span_failure_never_breaks_engine(self):
        """A broken trace store must not kill the run."""
        class _BrokenStore:
            def create_node(self, **kw):
                raise RuntimeError("db gone")

        import madcop.agent.trace as tr
        orig = tr.get_trace_store
        tr.get_trace_store = lambda: _BrokenStore()
        try:
            ctx = RunContext(
                messages=[Message(role="user", content="你好")],
                model="f", agent_mode="standard", client=_ToolThenAnswer(),
            )
            ctx.tool_executor = lambda *a, **k: '{"ok": true}'
            steps = list(ReActEngineV4().run(ctx))
            self.assertIn(StepKind.DONE, [s.kind for s in steps])
        finally:
            tr.get_trace_store = orig


if __name__ == "__main__":
    unittest.main()
