"""Message id stability: client ids must round-trip into _MESSAGES for branch."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from madcop.config import settings as S
from madcop.server.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", tmp_path / "master.key")
    S._invalidate_settings_cache()
    return TestClient(create_app())


def _clear() -> None:
    from madcop.server.madcop_compat import _SESSIONS, _MESSAGES
    _SESSIONS.clear()
    _MESSAGES.clear()


def test_session_persist_helper_keeps_client_id():
    from madcop.server.session_persist import append_user_and_ensure, append_assistant
    from madcop.server.madcop_compat import _MESSAGES

    _clear()
    sid = "id-align-1"
    u = append_user_and_ensure(sid, "hello", msg_id="client-user-abc")
    a = append_assistant(sid, "world", msg_id="client-asst-xyz", model="m")
    assert u["id"] == "client-user-abc"
    assert a["id"] == "client-asst-xyz"
    assert [m["id"] for m in _MESSAGES[sid]] == ["client-user-abc", "client-asst-xyz"]


def test_branch_finds_client_message_id(client: TestClient):
    _clear()
    sid = "id-align-branch"
    from madcop.server.session_persist import append_user_and_ensure, append_assistant

    append_user_and_ensure(sid, "q1", msg_id="u1", title_hint="T")
    append_assistant(sid, "a1", msg_id="a1")
    append_user_and_ensure(sid, "q2", msg_id="u2")
    append_assistant(sid, "a2", msg_id="a2")

    r = client.post(f"/api/sessions/{sid}/branch", json={"targetMessageId": "a1", "title": "Fork"})
    assert r.status_code == 200
    new_sid = r.json()["sessionId"]
    from madcop.server.madcop_compat import _MESSAGES
    # Branch should include messages up to and including a1 (2 messages)
    ids = [m["id"] for m in _MESSAGES[new_sid]]
    assert ids == ["u1", "a1"]


def test_chat_accepts_message_id_field(client: TestClient):
    """Pydantic model accepts optional id on ChatMessage (no 422)."""
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi", "id": "frontend-msg-1"}],
        "conversation_id": "cid-1",
    })
    # Mock stream or missing provider — must not be validation error
    assert r.status_code != 422
