"""P2-4 — ReActEngineV4 yields CLARIFY AgentStep when ask_user runs.

The legacy ReAct path emits `clarification_request` SSE (app.py:2599).
v4 (react_v4.py) used to swallow ask_user as an ordinary tool result
with `__clarify_pending__` marker, so users could never actually
answer the LLM's clarifying questions. This test pins the new
behaviour: when ask_user fires with __clarify_pending__, the engine
yields one extra CLARIFY AgentStep (question+options) and pauses.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


class _Stream:
    """Fake LLM client. Pretends the LLM decided to call ask_user."""
    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048,
               tools=None):
        # Phase 1: emit a thought + the ask_user call wrapped in the
        # standard ReAct protocol text (parsed by react_v4 the same
        # way as for any tool).
        yield SimpleNamespace(
            text=(
                "Thought: I need to ask.\n"
                "Action: ask_user\n"
                "Action Input: {\"question\": \"Which DB?\", \"options\": [\"Postgres\", \"MySQL\"]}\n"
            ),
            finish_reason=None,
        )
        yield SimpleNamespace(text="", finish_reason="stop")


def _tool_executor(name: str, raw_input: str, work_dir=None, pre_approved=False):
    """Mimic react_v4's expected tool-executor contract.

    react_v4 inspects the return with `hasattr(raw_result, 'to_observation')
    and hasattr(raw_result, 'is_error')`. To keep things simple here we
    return a dict that has the same string key (`output`) the v4 code
    falls back to when neither attribute is present, so the engine sees
    our clarify JSON.
    """
    if name.lower() in ("ask_user", "clarify"):
        return json.dumps({
            "__clarify_pending__": True,
            "question": "Which DB?",
            "options": ["Postgres", "MySQL"],
        }, ensure_ascii=False)
    return json.dumps({})


def _build_ctx() -> RunContext:
    ctx = RunContext(
        messages=[Message(role="user", content="Set up a DB")],
        model="fake-model",
        agent_mode="standard",
        client=_Stream(),
    )
    ctx.tool_executor = _tool_executor
    return ctx


class TestClarifyEmission(unittest.TestCase):
    def test_ask_user_emits_clarify_then_pauses(self):
        # Import inside the test so any v4 import error surfaces clearly.
        from madcop.agent.react_v4 import ReActEngineV4

        ctx = _build_ctx()
        steps = list(ReActEngineV4().run(ctx))
        kinds = [s.kind for s in steps]

        # The tool ran (TOOL_START + TOOL_END) and then we emitted CLARIFY.
        self.assertIn(StepKind.TOOL_START, kinds, "tool_start must precede clarify")
        self.assertIn(StepKind.TOOL_END, kinds)
        self.assertIn(StepKind.CLARIFY, kinds, "ask_user must yield CLARIFY so the UI can render the question")

        # And the engine should pause after CLARIFY (no further turns).
        self.assertEqual(kinds[-1], StepKind.CLARIFY, f"engine must pause after CLARIFY, got tail kinds={kinds[-3:]}")

        # The CLARIFY step carries the question + options for the UI.
        clarify = next(s for s in steps if s.kind == StepKind.CLARIFY)
        self.assertEqual(clarify.question, "Which DB?")
        self.assertEqual(clarify.options, ["Postgres", "MySQL"])
        self.assertEqual(clarify.tool_name, "ask_user")

    def test_to_sse_serializes_clarify(self):
        """The SSE bridge must pass question + options to the client."""
        from madcop.agent.runtime import AgentStep

        step = AgentStep(
            kind=StepKind.CLARIFY,
            tool_name="ask_user",
            question="Which DB?",
            options=["Postgres", "MySQL"],
        )
        line = step.to_sse(event_id=42)
        self.assertIn('"kind": "clarify"', line)
        self.assertIn('"question": "Which DB?"', line)
        self.assertIn('"options": ["Postgres", "MySQL"]', line)


if __name__ == "__main__":
    unittest.main()