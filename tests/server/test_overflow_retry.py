"""P1-6 acceptance — worker overflow retry path.

The overflow-retry loop in chat_v4's worker had NO dedicated test (it
caused a full-stream regression during development and was caught only
by the suite). This pins the contract: a provider context-length
ERROR on the first engine run force-compacts the context and reruns
the engine ONCE; the second run's answer reaches the client.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

import madcop.server.routes.chat_v4 as c4
import madcop.harness.core as hc
from madcop.server.app import create_app


class _OverflowThenAnswer:
    """Call 1: stream raises context-length. Call 2+: answer normally."""

    def __init__(self):
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError(
                "This model's maximum context length is 4096 tokens. "
                "However, your messages resulted in 98765 tokens.")
        yield SimpleNamespace(text="压缩后我记住了：项目代号 Phoenix。", finish_reason=None)
        yield SimpleNamespace(text="", finish_reason="stop")


class TestOverflowRetry(unittest.TestCase):

    def test_overflow_compacts_and_retries_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with mock.patch.object(hc, "_HARNESS_ROOT", root), \
                 mock.patch.object(c4, "_SESSION_LAST_USAGE", {}), \
                 mock.patch.object(c4, "_SESSION_SUMMARIES", {}):
                fake = _OverflowThenAnswer()
                orig = c4._get_client
                c4._get_client = lambda: fake
                try:
                    tc = TestClient(create_app())
                    r = tc.post("/api/v4/chat", json={
                        "messages": [{"role": "user",
                                      "content": "我的项目代号是 Phoenix " + "x" * 30000}],
                        "agent_mode": "chat",
                        "conversation_id": "ovf-test",
                    })
                finally:
                    c4._get_client = orig

                self.assertEqual(r.status_code, 200)
                data_lines = [l[6:] for l in r.text.split("\n")
                              if l.startswith("data: ")]
                kinds = [json.loads(l).get("kind") for l in data_lines]
                # First run ERRORED (overflow), retry produced the answer.
                self.assertIn("error", kinds)
                self.assertIn("text_delta", kinds)
                self.assertIn("done", kinds)
                texts = "".join(json.loads(l).get("content", "")
                                for l in data_lines
                                if json.loads(l).get("kind") == "text_delta")
                self.assertIn("Phoenix", texts)
                self.assertEqual(fake.calls, 2)  # exactly one retry


if __name__ == "__main__":
    unittest.main()
