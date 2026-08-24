"""P2-12 — pluggable hook chain (PreToolUse veto, PostToolUse observe).

Two shipped hooks demonstrate the API:
  - SafetyHook: PreToolUse on `bash` denies destructive patterns
  - FormatterHook: PostToolUse on write_file/edit_file appends an
    extra_observation

Hooks never break the engine: a raise inside a hook is logged and
skipped. priority orders execution; continue_=False vetoes; modified
input is rewritten; extra observations fold into the model's next turn.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from madcop.agent.hooks import (
    Hook, HookChain, HookContext, HookEvent, HookResult,
    SafetyHook, FormatterHook,
)
from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


class _Exec:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
    def __call__(self, name, raw_input, work_dir=None, pre_approved=False):
        import json
        try:
            self.calls.append((name, json.loads(raw_input)))
        except Exception:
            self.calls.append((name, {"raw": raw_input}))
        return json.dumps({"ok": True})


class _TwoTurnClient:
    """Round 1: bash tool call. Round 2: cleanup."""

    def __init__(self):
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.calls += 1
        if self.calls == 1:
            yield SimpleNamespace(
                tool_call_deltas=({"index": 0, "id": "t", "name": "bash",
                                    "arguments": '{"command": "rm -rf /"}'},),
                text="", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")
        else:
            yield SimpleNamespace(text="好的。", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")


class _WriteFileClient:
    def __init__(self):
        self.calls = 0
    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.calls += 1
        if self.calls == 1:
            yield SimpleNamespace(
                tool_call_deltas=({"index": 0, "id": "t", "name": "write_file",
                                    "arguments": '{"path": "/tmp/x.txt", "content": "hi"}'},),
                text="", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")
        else:
            yield SimpleNamespace(text="完成。", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")


class TestHooks(unittest.TestCase):

    def test_safety_vetoes_dangerous_bash(self):
        from madcop.agent.react_v4 import ReActEngineV4
        ctx = RunContext(
            messages=[Message(role="user", content="清空系统")],
            model="f", agent_mode="standard", client=_TwoTurnClient(),
        )
        ctx.tool_executor = _Exec()
        ctx.hooks = HookChain(hooks=[
            Hook("safety", HookEvent.PRE_TOOL_USE,
                 SafetyHook(), tool_filter="bash", priority=0),
        ])
        steps = list(ReActEngineV4().run(ctx))
        end = [s for s in steps if s.kind == StepKind.TOOL_END]
        self.assertTrue(end and end[0].is_error)
        self.assertIn("拒绝", end[0].tool_result)
        self.assertEqual(end[0].metadata.get("is_hook_rejected"), True)
        # The tool executor was NEVER called
        self.assertEqual(ctx.tool_executor.calls, [])

    def test_safety_allows_safe_bash(self):
        from madcop.agent.react_v4 import ReActEngineV4
        class _Safe:
            def __init__(self): self.calls = 0
            def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        tool_call_deltas=({"index": 0, "id": "t", "name": "bash",
                                            "arguments": '{"command": "ls /tmp"}'},),
                        text="", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(text="ok.", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")
        ex = _Exec()
        ctx = RunContext(
            messages=[Message(role="user", content="查文件")],
            model="f", agent_mode="standard", client=_Safe(),
        )
        ctx.tool_executor = ex
        ctx.hooks = HookChain(hooks=[
            Hook("safety", HookEvent.PRE_TOOL_USE,
                 SafetyHook(), tool_filter="bash", priority=0),
        ])
        steps = list(ReActEngineV4().run(ctx))
        self.assertEqual([n for n, _ in ex.calls], ["bash"])
        self.assertFalse(any(
            s.metadata.get("is_hook_rejected") for s in steps
            if s.kind == StepKind.TOOL_END
        ))

    def test_formatter_appends_observation(self):
        from madcop.agent.react_v4 import ReActEngineV4
        ex = _Exec()
        ctx = RunContext(
            messages=[Message(role="user", content="写文件")],
            model="f", agent_mode="standard", client=_WriteFileClient(),
        )
        ctx.tool_executor = ex
        ctx.hooks = HookChain(hooks=[
            Hook("fmt", HookEvent.POST_TOOL_USE,
                 FormatterHook(), tool_filter="write_file", priority=0),
        ])
        steps = list(ReActEngineV4().run(ctx))
        end = [s for s in steps if s.kind == StepKind.TOOL_END]
        self.assertEqual(len(end), 1)
        self.assertIn("[fmt]", end[0].tool_result)

    def test_buggy_hook_does_not_break_engine(self):
        def _crash(ctx):
            raise RuntimeError("boom")

        from madcop.agent.react_v4 import ReActEngineV4
        ex = _Exec()
        ctx = RunContext(
            messages=[Message(role="user", content="写")],
            model="f", agent_mode="standard", client=_WriteFileClient(),
        )
        ctx.tool_executor = ex
        ctx.hooks = HookChain(hooks=[
            Hook("crashy", HookEvent.PRE_TOOL_USE, _crash, tool_filter="write_file"),
            Hook("ok", HookEvent.PRE_TOOL_USE, lambda c: None, tool_filter="write_file"),
        ])
        # Engine still completes despite the crashing hook
        steps = list(ReActEngineV4().run(ctx))
        self.assertIn(StepKind.DONE, [s.kind for s in steps])

    def test_hook_can_rewrite_input(self):
        from madcop.agent.react_v4 import ReActEngineV4
        def _upper(ctx):
            if ctx.tool_input.get("command"):
                return HookResult(modified_input={"command": "echo SAFE"})
            return HookResult()

        class _C:
            def __init__(self): self.calls = 0
            def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
                self.calls += 1
                if self.calls == 1:
                    yield SimpleNamespace(
                        tool_call_deltas=({"index": 0, "id": "t", "name": "bash",
                                            "arguments": '{"command": "rm something"}'},),
                        text="", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")
                else:
                    yield SimpleNamespace(text="ok", finish_reason=None)
                    yield SimpleNamespace(text="", finish_reason="stop")

        ex = _Exec()
        ctx = RunContext(
            messages=[Message(role="user", content="go")],
            model="f", agent_mode="standard", client=_C(),
        )
        ctx.tool_executor = ex
        ctx.hooks = HookChain(hooks=[
            Hook("rewrite", HookEvent.PRE_TOOL_USE, _upper, tool_filter="bash"),
        ])
        list(ReActEngineV4().run(ctx))
        # The executor received the REWRITTEN input, not the original
        self.assertEqual(ex.calls[0][1]["command"], "echo SAFE")


if __name__ == "__main__":
    unittest.main()