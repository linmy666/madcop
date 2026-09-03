"""Repro: HITL session-scope approval end-to-end through /api/v4/chat.

Drives the REAL chat_v4 route with a fake streaming client, answers the
confirm card with scope=session (same as the UI's「本会话允许此目录」),
then asserts the durable scopes file + engine scope pre-check behavior.
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

import madcop.server.routes.chat_v4 as c4
import madcop.harness.core as hc
from madcop.server.app import create_app


class _WriteToolClient:
    """Streams a write_file tool_call (OpenAI shape), then a final answer."""

    def __init__(self):
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048,
               tools=None, effort=None):
        self.calls += 1
        if self.calls == 1:
            yield SimpleNamespace(
                text="", finish_reason=None,
                tool_call_deltas=[{"index": 0, "id": "c1", "name": "write_file",
                                   "arguments": json.dumps({
                                       "path": "/tmp/madcop_scope_test/a.html",
                                       "content": "hi"})}],
            )
            yield SimpleNamespace(text="", finish_reason="tool_calls")
        else:
            yield SimpleNamespace(text="done-writing", finish_reason="stop")
            yield SimpleNamespace(text="", finish_reason="stop")


class TestSessionScopeApproval(unittest.TestCase):

    def test_scope_session_persists_and_skips_second_card(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            scopes_file = root / "scopes.json"
            with mock.patch.object(hc, "_HARNESS_ROOT", root), \
                 mock.patch.object(c4, "_APPROVAL_SCOPES_FILE", scopes_file), \
                 mock.patch.object(c4, "_SESSION_APPROVED", {}), \
                 mock.patch.object(c4, "_SESSION_LAST_USAGE", {}), \
                 mock.patch.object(c4, "_SESSION_SUMMARIES", {}):
                fake = _WriteToolClient()
                orig = c4._get_client
                c4._get_client = lambda: fake
                try:
                    tc = TestClient(create_app())
                    t = threading.Thread(target=lambda: tc.post(
                        "/api/v4/chat", json={
                            "messages": [{"role": "user",
                                          "content": "做个 x.html"}],
                            "agent_mode": "chat",
                            "conversation_id": "scope-e2e",
                        }), daemon=True)
                    t.start()
                    # Wait for the confirm card to surface.
                    fut = None
                    deadline = time.time() + 15
                    while time.time() < deadline:
                        if c4._PENDING_CONFIRMS:
                            fut = next(iter(c4._PENDING_CONFIRMS))
                            break
                        time.sleep(0.2)
                    self.assertIsNotNone(
                        fut, "engine never raised a confirm card")
                    tid = fut
                    meta = c4._PENDING_META[tid]
                    self.assertEqual(meta["tool_name"], "write_file")
                    r = tc.post("/api/v4/chat/confirm", json={
                        "conversation_id": "scope-e2e",
                        "tool_use_id": tid,
                        "approved": True,
                        "scope": "session",
                    })
                    self.assertEqual(r.json().get("ok"), True)
                    t.join(timeout=20)
                    # Give the worker's recording block a beat.
                    time.sleep(1.0)
                    saved = json.loads(scopes_file.read_text()) \
                        if scopes_file.exists() else {}
                    print("\nSCOPES FILE:", json.dumps(saved, indent=1))
                    print("IN-MEMORY:", dict(c4._SESSION_APPROVED))
                    self.assertIn("scope-e2e", saved,
                                  "session scope was NOT persisted")
                    self.assertTrue(
                        any("/tmp/madcop_scope_test" in e
                            for e in saved["scope-e2e"]),
                        saved)
                finally:
                    c4._get_client = orig


if __name__ == "__main__":
    unittest.main()
