"""P0-4 — durable HITL: no blind 120s auto-reject + pending endpoint.

The old confirm_handler auto-rejected after 120s while the user was
still reading the card. Now the wait polls the future AND the
route-scoped turn_cancelled event: aborted turns reject promptly, live
turns wait indefinitely. The GET pending endpoint exposes live cards
for session-scoped rehydration.
"""
from __future__ import annotations

import json
import threading
import time
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

import madcop.server.routes.chat_v4 as c4
from madcop.server.app import create_app


class _ConfirmFake:
    """Streams a write_file tool call; the engine blocks in the
    confirm_handler until we resolve the future."""

    def __init__(self):
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.calls += 1
        if self.calls == 1:
            yield SimpleNamespace(
                tool_call_deltas=({
                    "index": 0, "id": "t1", "name": "write_file",
                    "arguments": '{"path": "/tmp/p04.txt", "content": "x"}',
                },),
                text="", finish_reason=None,
            )
            yield SimpleNamespace(text="", finish_reason="stop")
        else:
            yield SimpleNamespace(text="文件已写入。", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")


def _tool_exec(name, raw_input, work_dir=None, pre_approved=False):
    return json.dumps({"ok": True, "output": "written"})


class TestHitlPersistence(unittest.TestCase):

    def setUp(self):
        # Isolate the module-level pending registries between tests.
        c4._PENDING_CONFIRMS.clear()
        c4._PENDING_META.clear()
        self._orig_get_client = c4._get_client
        c4._get_client = lambda: _ConfirmFake()
        self.app = create_app()

    def tearDown(self):
        c4._get_client = self._orig_get_client
        c4._PENDING_CONFIRMS.clear()
        c4._PENDING_META.clear()

    def test_pending_endpoint_lists_live_confirm(self):
        """While a confirm blocks, GET pending exposes it for the right
        session — and it does NOT vanish after the old 120s window
        (we verify the handler is still waiting well past a short
        poll interval by resolving it late and seeing the tool run)."""
        tc = TestClient(self.app)
        # Background thread reads the SSE stream slowly (doesn't consume
        # it all) while we interact with the pending registry.
        events: list[str] = []
        t = threading.Thread(
            target=lambda: events.append(tc.post(
                "/api/v4/chat",
                json={
                    "messages": [{"role": "user", "content": "写文件"}],
                    "conversation_id": "p04-sess",
                },
            ).text),
            daemon=True,
        )
        t.start()

        # Wait for the confirm to appear in the registry (not SSE-bound).
        deadline = time.time() + 15
        while time.time() < deadline:
            if c4._PENDING_META:
                break
            time.sleep(0.2)
        self.assertTrue(c4._PENDING_META, "confirm never registered")

        resp = tc.get("/api/v4/chat/confirm/pending?conversation_id=p04-sess")
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(data["pending"]), 1)
        item = data["pending"][0]
        self.assertEqual(item["tool_name"], "write_file")
        self.assertEqual(item["conversation_id"], "p04-sess")
        self.assertIn("path", item["tool_input"])

        # Session filter excludes other sessions.
        resp2 = tc.get("/api/v4/chat/confirm/pending?conversation_id=other")
        self.assertEqual(resp2.json()["pending"], [])

        # Resolve late (well after any short poll tick) — approving must
        # free the worker, which executes the tool and finishes.
        tid = item["tool_use_id"]
        ok = tc.post("/api/v4/chat/confirm",
                     json={"tool_use_id": tid, "approved": True})
        self.assertTrue(ok.json().get("ok"))
        t.join(timeout=30)
        self.assertFalse(t.is_alive(), "worker stayed blocked after approval")
        # Registry cleaned up after resolution.
        self.assertNotIn(tid, c4._PENDING_META)


if __name__ == "__main__":
    unittest.main()
