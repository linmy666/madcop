"""P0-2 — native tool calls are the PRIMARY protocol.

Every mature agent SDK uses native function calling; text protocols
(``Thought:/Action:``) are a fallback for providers without tools
support. This pins the engine's routing after the state-machine
removal:

  1. Native tool_calls → executed (args accumulated across deltas).
  2. Preamble text + tool_calls in one turn → text streams as
     TEXT_DELTA *and* the tool executes (interleaved timeline).
  3. <think> tags + tool_calls → thinking on THOUGHT channel, never
     leaked into the answer.
  4. Text protocol (no tool_calls) → still parsed as fallback.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


class _Exec:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, raw_input, work_dir=None, pre_approved=False):
        args = json.loads(raw_input) if isinstance(raw_input, str) and raw_input.strip().startswith("{") else {"raw": raw_input}
        self.calls.append((name, args))
        return json.dumps({"ok": True, "output": f"{name} done"}, ensure_ascii=False)


def _ctx(client, executor):
    ctx = RunContext(
        messages=[Message(role="user", content="查一下天气")],
        model="fake",
        agent_mode="standard",
        client=client,
    )
    ctx.tool_executor = executor
    return ctx


class TestNativeToolCallsPrimary(unittest.TestCase):

    def test_fragmented_args_accumulate_and_execute(self):
        """Args streamed in many deltas reassemble into one call."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    for frag in ('{"que', 'ry": "', "台风", ' 最新"}'):
                        yield SimpleNamespace(
                            tool_call_deltas=({"index": 0, "id": "t1",
                                                "name": "web_search" if frag == '{"que' else None,
                                                "arguments": frag},),
                            text="", finish_reason=None,
                        )
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(
                        text="已按要求完成搜索。",
                        finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex)))
        self.assertEqual(ex.calls, [("web_search", {"query": "台风 最新"})])
        self.assertIn(StepKind.TOOL_START, [s.kind for s in steps])

    def test_preamble_text_plus_tool_call_interleave(self):
        """Prose before a tool call streams to TEXT_DELTA, and the tool
        still executes — the answer channel must not swallow the call."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        text="我先搜索一下最新的台风信息，然后汇总给你。",
                        finish_reason=None,
                    )
                    yield SimpleNamespace(
                        tool_call_deltas=({"index": 0, "id": "t1",
                                            "name": "web_search",
                                            "arguments": '{"query": "台风 最新"}'},),
                        text="", finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(
                        text="根据搜索结果，近期无台风。",
                        finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex)))
        kinds = [s.kind for s in steps]
        self.assertEqual(len(ex.calls), 1)  # tool executed once
        self.assertIn(StepKind.TEXT_DELTA, kinds)  # preamble streamed
        self.assertIn(StepKind.TOOL_START, kinds)
        # No think-tag or protocol leakage in the streamed text.
        text_all = "".join((s.content or "") for s in steps if s.kind == StepKind.TEXT_DELTA)
        self.assertNotIn("<think>", text_all)
        self.assertNotIn("Action:", text_all)
        self.assertIn(StepKind.DONE, kinds)

    def test_think_tags_route_to_thought_channel(self):
        """<think> content lands on THOUGHT, never on TEXT."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    for piece in ("<think>用户问天气，我需要搜索。", "具体查台风路径。</think>", "我来搜索。"):
                        yield SimpleNamespace(text=piece, finish_reason=None)
                    yield SimpleNamespace(
                        tool_call_deltas=({"index": 0, "id": "t1",
                                            "name": "web_search",
                                            "arguments": '{"query": "台风 最新"}'},),
                        text="", finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(
                        text="近期无台风。",
                        finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex)))
        thoughts = "".join((s.content or "") for s in steps if s.kind == StepKind.THOUGHT_DELTA)
        texts = "".join((s.content or "") for s in steps if s.kind == StepKind.TEXT_DELTA)
        self.assertIn("用户问天气", thoughts)
        self.assertNotIn("<think>", thoughts)
        self.assertNotIn("用户问天气", texts)
        self.assertEqual(len(ex.calls), 1)

    def test_text_protocol_fallback_still_works(self):
        """A provider without function calling (no tool_calls emitted)
        still gets its Action:/Action Input: text parsed and executed."""
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        text='Thought: 需要搜索\nAction: web_search\nAction Input: {"query": "台风 最新"}',
                        finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(
                        text="Thought: 完成\nAction: FINAL_ANSWER\nFINAL_ANSWER: 近期无台风。",
                        finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex)))
        kinds = [s.kind for s in steps]
        self.assertEqual(ex.calls[0][0], "web_search")
        self.assertIn(StepKind.DONE, kinds)
        # Fallback Thought surfaces on the thought channel.
        self.assertIn(StepKind.THOUGHT_DELTA, kinds)
        thoughts = "".join((s.content or "") for s in steps if s.kind == StepKind.THOUGHT_DELTA)
        self.assertIn("需要搜索", thoughts)


if __name__ == "__main__":
    unittest.main()


class TestToolArgParsing(unittest.TestCase):
    """P0-2 hardening: nested-brace payloads, malformed JSON, concat JSON."""

    def _run(self, client, executor):
        from madcop.agent.react_v4 import ReActEngineV4
        return list(ReActEngineV4().run(_ctx(client, executor)))

    @staticmethod
    def _one_shot_tc(name, args_str, then="搜索完成，无异常。"):
        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        tool_call_deltas=({"index": 0, "id": "t1",
                                            "name": name,
                                            "arguments": args_str},),
                        text="", finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(text=then, finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")
        return _C()

    def test_nested_brace_payload_parses(self):
        """write_file HTML content with braces inside the JSON value."""
        html = "<html><body><script>if (a > b) { alert('hi'); }</script></body></html>"
        args = json.dumps({"path": "/tmp/x.html", "content": html}, ensure_ascii=False)
        ex = _Exec()
        steps = self._run(self._one_shot_tc("write_file", args), ex)
        self.assertEqual(ex.calls[0][0], "write_file")
        self.assertEqual(ex.calls[0][1]["content"], html)

    def test_malformed_json_fails_clean_no_execution(self):
        """Unescaped quotes → validation error fed back, tool NOT executed
        with stuffed defaults."""
        bad = '{"path": "/tmp/x.html", "content": "he said "hi" loudly"}'
        ex = _Exec()
        steps = self._run(self._one_shot_tc("write_file", bad), ex)
        self.assertEqual(ex.calls, [])  # never executed
        ends = [s for s in steps if s.kind == StepKind.TOOL_END]
        self.assertTrue(ends and ends[0].is_error)
        self.assertIn("JSON", (ends[0].tool_result or ""))

    def test_concat_json_first_block_wins(self):
        """Two concatenated JSON objects (dual-search style) → first parses."""
        concat = '{"query": "台风 最新"}{"query": "台风 路径"}'
        ex = _Exec()
        steps = self._run(self._one_shot_tc("web_search", concat), ex)
        self.assertEqual(ex.calls[0][1], {"query": "台风 最新"})


class TestThinkPollutedProtocol(unittest.TestCase):
    """E2E regression: a model that writes format explanations INSIDE
    <think> ("Action: write_file\\n- Action Input: JSON with path...")
    made the text-protocol parser glue everything from the in-think
    'Action:' to end-of-string into one giant bogus tool name."""

    def test_think_explanations_do_not_pollute_tool_name(self):
        from madcop.agent.react_v4 import ReActEngineV4

        class _C:
            def __init__(self):
                self.calls = 0

            def stream(self, messages, model=None, temperature=0.1,
                       max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        text=(
                            "<think>用户要写一首短诗到指定路径，我直接调用 write_file。\n"
                            "Action: write_file\n"
                            "- Action Input: JSON with path and content</think>\n\n"
                            "Thought: 直接写文件。\n"
                            "Action: write_file\n"
                            'Action Input: {"path": "/tmp/poem.txt", "content": "夜深"}'
                        ),
                        finish_reason=None,
                    )
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(text="已写入。", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec()
        steps = list(ReActEngineV4().run(_ctx(_C(), ex)))
        # The tool name must be clean 'write_file', not the glued blob.
        self.assertEqual(ex.calls[0][0], "write_file")
        self.assertEqual(ex.calls[0][1], {"path": "/tmp/poem.txt", "content": "夜深"})
        # And it executed (not a '工具 不存在' error round-trip).
        ends = [s for s in steps if s.kind == StepKind.TOOL_END]
        self.assertTrue(ends and not ends[0].is_error)
