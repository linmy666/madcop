"""Sprint 5 — tests for the proactive observer backend.

Uses a fake LLM client injected via app.state.proactive_client so the
test doesn't need an API key or network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from madcop.server.routes.proactive_routes import (
    ProactiveCheck,
    _build_proactive_prompt,
    _parse_verdict,
    router as proactive_router,
)


class FakeLLM:
    """Returns a canned JSON verdict from .chat()."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list = []

    def chat(self, messages, temperature=0.1, max_tokens=160):
        self.calls.append(messages)
        return SimpleNamespace(content=self.answer)


class TestProactiveBackend(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(proactive_router)
        self.client = TestClient(app)
        self.app = app

    def _set_client(self, answer: str) -> FakeLLM:
        fake = FakeLLM(answer)
        self.app.state.proactive_client = fake
        return fake

    def test_worth_verdict_parsed_and_returned(self):
        fake = self._set_client(
            '{"worth": true, "summary": "测试失败", "suggestion": "检查 test_a 的输入"}'
        )
        r = self.client.post("/api/proactive/check", json={
            "source": "terminal",
            "content": "FAILED test_a.py::test_create\nAssertionError",
            "workspace": "/tmp/proj",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["worth"])
        self.assertIn("测试", body["summary"])
        self.assertIn("test_a", body["suggestion"])
        # The client was actually called with the proactive prompt.
        self.assertEqual(len(fake.calls), 1)

    def test_not_worth_verdict(self):
        self._set_client(
            '{"worth": false, "summary": "正常保存", "suggestion": ""}'
        )
        r = self.client.post("/api/proactive/check", json={
            "source": "file",
            "content": "saved main.py",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["worth"])

    def test_no_client_returns_not_worth_gracefully(self):
        # No injected proactive_client and (in this env) no reachable
        # provider either → should no-op with worth=false rather than
        # 500. The reason may be "no_llm" or an "llm_error:..." — both
        # are acceptable graceful degradation; the key invariant is
        # worth=false + 200, never a crash.
        r = self.client.post("/api/proactive/check", json={
            "source": "terminal",
            "content": "anything",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["worth"])
        reason = body.get("reason", "")
        # "judged" is also valid: the v4 route's MockClient fallback
        # means a (mock) LLM actually judged and returned worth=false.
        # The invariant is graceful 200 + worth=false, never a crash.
        self.assertTrue(
            reason in ("no_llm", "judged") or reason.startswith("llm_error"),
            f"unexpected reason: {reason!r}")

    def test_prompt_contains_source_and_content(self):
        p = _build_proactive_prompt("file", "def hello(): pass", "/ws")
        self.assertIn("file", p)
        self.assertIn("def hello(): pass", p)

    def test_parse_verdict_handles_fenced_json(self):
        v = _parse_verdict('```json\n{"worth": true, "summary": "x", "suggestion": "y"}\n```')
        self.assertTrue(v["worth"])
        self.assertEqual(v["summary"], "x")

    def test_parse_verdict_handles_garbage(self):
        v = _parse_verdict("the model rambled, no json")
        self.assertFalse(v["worth"])

    def test_model_error_degrades_gracefully(self):
        class BrokenLLM:
            def chat(self, *a, **k):
                raise RuntimeError("boom")
        self.app.state.proactive_client = BrokenLLM()
        r = self.client.post("/api/proactive/check", json={
            "source": "terminal", "content": "x",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["worth"])
        self.assertIn("llm_error", body.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
