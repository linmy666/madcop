"""P1-7 — prompt-cache-friendly prefix stabilization.

Claude SDK's exclude_dynamic_sections insight: the SYSTEM prompt must
stay byte-stable within a session or provider prefix caches never hit.
MadCop's system prompt used to change every request (date + memory +
per-turn directives). Now:
  - system prompt = memory persona + style + mode directives (stable)
  - volatile context (time, build-request directive) rides on the
    last USER message as a [Context] block
  - the block is stripped before the log/persist layer records the
    user's turn (the log stores the user's actual words)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tempfile

from madcop.agent.react_v4 import ReActEngineV4
from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message
from madcop.harness.core import (
    SessionLog, EventDomain, HarnessEvent,
    system_event, answer_event,
)


class _RecordingClient:
    """Records the message list of each call; answers immediately."""

    def __init__(self):
        self.calls: list[list[Message]] = []

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None, effort=None):
        self.calls.append(list(messages))
        yield SimpleNamespace(text="这是回答内容，足够长了。", finish_reason=None)
        yield SimpleNamespace(text="", finish_reason="stop")


class TestSystemPromptStability(unittest.TestCase):

    def test_react_system_prompt_has_no_time(self):
        """The engine's system prompt is byte-identical across two runs
        minutes apart (no current_time fill)."""
        client = _RecordingClient()

        def run():
            ctx = RunContext(
                messages=[Message(role="user", content="你好")],
                model="f", agent_mode="standard", client=client,
            )
            list(ReActEngineV4().run(ctx))

        run()
        sys1 = client.calls[0][0].content
        run()
        sys2 = client.calls[1][0].content
        self.assertEqual(sys1, sys2)
        self.assertNotIn("当前时间", sys1)
        self.assertNotIn("Today is", sys1)

    def test_react_time_block_not_duplicated_into_system(self):
        """Even when the route injects a [Context] time block on the
        user message, the system prompt stays clean."""
        client = _RecordingClient()
        ctx = RunContext(
            messages=[
                Message(role="user",
                        content="[Context] Today is Monday.\n\n你好"),
            ],
            model="f", agent_mode="standard", client=client,
        )
        list(ReActEngineV4().run(ctx))
        sys_msg = client.calls[0][0]
        self.assertEqual(sys_msg.role, "system")
        self.assertNotIn("[Context]", sys_msg.content)


class TestContextBlockStrip(unittest.TestCase):

    def test_derive_stores_user_words_not_context_block(self):
        """A log written via turn_start (with the block stripped by the
        route) replays as the user's actual words."""
        with tempfile.TemporaryDirectory() as d:
            log = SessionLog(Path(d) / "s.jsonl")
            # What the route would log after stripping:
            log.append(system_event("turn_start", "做个游戏"))
            log.append(answer_event("text_delta", "做好了"))
            msgs = log.derive_messages()
            self.assertIn("做个游戏", msgs[0]["content"])
            self.assertNotIn("[Context]", msgs[0]["content"])


if __name__ == "__main__":
    unittest.main()
