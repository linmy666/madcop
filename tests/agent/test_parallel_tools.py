"""P0-3 — parallel tool execution + sequential HITL cards.

The engine accumulates ALL native tool_calls (per index). Free calls
run in a bounded concurrent pool (failure-isolated); confirm-needed
calls run sequentially, one card at a time (Claude Code style).
"""
from __future__ import annotations

import json
import threading
import time
import unittest
from types import SimpleNamespace

from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


class _Exec:
    def __init__(self, delay_map=None):
        self.calls: list[tuple[str, dict]] = []
        self.lock = threading.Lock()
        self.delay_map = delay_map or {}

    def __call__(self, name, raw_input, work_dir=None, pre_approved=False):
        with self.lock:
            self.calls.append((name, raw_input))
        time.sleep(self.delay_map.get(name, 0))
        return json.dumps({"ok": True, "output": f"{name} done"}, ensure_ascii=False)


def _ctx(client, executor, confirm=None):
    ctx = RunContext(
        messages=[Message(role="user", content="并行查两个关键词")],
        model="fake",
        agent_mode="standard",
        client=client,
    )
    ctx.tool_executor = executor
    if confirm is not None:
        ctx.confirm_handler = confirm
    return ctx


class TestParallelTools(unittest.TestCase):

    def test_parallel_native_calls_both_execute(self):
        """Two native tool_calls in one turn → BOTH execute (index 1
        used to be silently dropped)."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 0, "id": "a", "name": "web_search",
                             "arguments": '{"query": "台风 最新"}'},
                        ),
                        text="", finish_reason=None,
                    )
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 1, "id": "b", "name": "web_search",
                             "arguments": '{"query": "台风 路径"}'},
                        ),
                        text="", finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(
                        text="两次搜索都完成了，汇总如下。",
                        finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec({"web_search": 0.2})  # slow tools prove real concurrency
        t0 = time.time()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex)))
        wall = time.time() - t0
        names = [n for n, _ in ex.calls]
        self.assertEqual(names, ["web_search", "web_search"])
        # Two 0.2s serial tools would take ≥0.4s; the pool must beat that.
        self.assertLess(wall, 0.38)
        starts = [s for s in steps if s.kind == StepKind.TOOL_START]
        ends = [s for s in steps if s.kind == StepKind.TOOL_END]
        self.assertEqual(len(starts), 2)
        self.assertEqual(len(ends), 2)
        use_ids = {s.tool_use_id for s in starts}
        self.assertEqual(len(use_ids), 2)  # distinct ids for parallel calls

    def test_failure_isolation(self):
        """One crashing call doesn't cancel its sibling."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _CrashExec:
            def __init__(self):
                self.calls = []

            def __call__(self, name, raw_input, work_dir=None, pre_approved=False):
                self.calls.append(name)
                if name == "crashy_tool":
                    raise RuntimeError("boom")
                return '{"ok": true}'

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 0, "id": "a", "name": "crashy_tool",
                             "arguments": "{}"},
                        ), text="", finish_reason=None)
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 1, "id": "b", "name": "web_search",
                             "arguments": '{"query": "x"}'},
                        ), text="", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(text="完成。", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _CrashExec()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex)))
        self.assertEqual(set(ex.calls), {"crashy_tool", "web_search"})  # both ran
        ends = {s.tool_name: s for s in steps if s.kind == StepKind.TOOL_END}
        self.assertTrue(ends["crashy_tool"].is_error)
        self.assertFalse(ends["web_search"].is_error)

    def test_confirm_tools_sequential_cards(self):
        """Two confirm-needed tools → two cards, one at a time, in order."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 0, "id": "a", "name": "write_file",
                             "arguments": '{"path": "/tmp/a.txt", "content": "A"}'},
                        ), text="", finish_reason=None)
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 1, "id": "b", "name": "bash",
                             "arguments": '{"command": "echo hi"}'},
                        ), text="", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(text="两个文件操作都完成了。", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")

        confirm_log = []

        def confirm(name, tool_input, tool_use_id):
            confirm_log.append((name, tool_use_id))
            return True  # approve all

        ex = _Exec()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex, confirm=confirm)))
        # Both confirm-needed tools executed, in call order.
        self.assertEqual([n for n, _ in ex.calls], ["write_file", "bash"])
        self.assertEqual(len(confirm_log), 2)
        # Cards emitted one per tool, each before its execution.
        cards = [s for s in steps if s.kind == StepKind.TOOL_CONFIRM_REQUEST]
        self.assertEqual(len(cards), 2)
        self.assertEqual([c.tool_name for c in cards], ["write_file", "bash"])

    def test_rejection_only_cancels_that_call(self):
        """Rejecting one confirm card cancels only that call; free
        siblings still run."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 0, "id": "a", "name": "web_search",
                             "arguments": '{"query": "x"}'},
                        ), text="", finish_reason=None)
                    yield SimpleNamespace(
                        tool_call_deltas=(
                            {"index": 1, "id": "b", "name": "bash",
                             "arguments": '{"command": "rm x"}'},
                        ), text="", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(text="搜索完成，命令已按你的选择跳过。", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec()
        steps = list(ReActEngineV4().run(_ctx(
            _C(), ex, confirm=lambda n, i, u: False)))  # reject all cards
        names = [n for n, _ in ex.calls]
        # web_search is free → executed; bash rejected → never executed.
        self.assertEqual(names, ["web_search"])
        ends = {s.tool_name: s for s in steps if s.kind == StepKind.TOOL_END}
        self.assertTrue(ends["bash"].is_error)
        self.assertFalse(ends["web_search"].is_error)


if __name__ == "__main__":
    unittest.main()
