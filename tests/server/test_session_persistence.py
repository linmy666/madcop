"""Regression tests for session persistence and batch-delete.

Covers:
- P0: /api/sessions/batch-delete must not crash with NameError (_MESSIONS typo).
- P1: /api/sessions/{id}/git-info returns real git data (not the deleted stub).
- P1: /api/sessions/{id}/inspection returns stored messages (not empty list).
- P1: /api/sessions/{id}/turn-checkpoints returns assistant checkpoints.
- P1: /api/sessions/{id}/branch copies messages into the new session.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from madcop.config import settings as S
from madcop.server.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", tmp_path / "master.key")
    app = create_app()
    return TestClient(app)


def _clear_sessions() -> None:
    from madcop.server.madcop_compat import _SESSIONS, _MESSAGES
    _SESSIONS.clear()
    _MESSAGES.clear()


# --------------------------------------------------------------------------- #
# P0: batch-delete must not crash
# --------------------------------------------------------------------------- #

def test_batch_delete_does_not_crash(client: TestClient):
    """batch-delete previously hit NameError on the _MESSIONS typo."""
    _clear_sessions()
    sid1, sid2 = "test-batch-a", "test-batch-b"
    client.post("/api/sessions", json={"sessionId": sid1, "title": "A"})
    client.post("/api/sessions", json={"sessionId": sid2, "title": "B"})
    client.post(f"/api/sessions/{sid1}/messages",
                json={"messages": [{"type": "user", "content": "hi"}], "title": "A"})
    client.post(f"/api/sessions/{sid2}/messages",
                json={"messages": [{"type": "user", "content": "yo"}], "title": "B"})

    resp = client.post("/api/sessions/batch-delete", json={"ids": [sid1, sid2]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True

    from madcop.server.madcop_compat import _SESSIONS, _MESSAGES
    assert sid1 not in _SESSIONS
    assert sid2 not in _SESSIONS
    assert sid1 not in _MESSAGES
    assert sid2 not in _MESSAGES


# --------------------------------------------------------------------------- #
# P1: real route implementations (not stubs) are now reachable
# --------------------------------------------------------------------------- #

def test_git_info_returns_real_data(client: TestClient, tmp_path: Path):
    """git-info should read actual git branch from workDir, not return empty."""
    _clear_sessions()
    import subprocess
    try:
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, timeout=5)
        subprocess.run(["git", "checkout", "-b", "test-branch"],
                       cwd=tmp_path, capture_output=True, timeout=5)
        # Need at least one commit for rev-parse --abbrev-ref HEAD to work
        (tmp_path / "README").write_text("init")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, timeout=5)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=tmp_path, capture_output=True, timeout=5)
    except Exception:
        pytest.skip("git not available")

    sid = "test-git-sid"
    client.post("/api/sessions", json={"sessionId": sid, "workDir": str(tmp_path)})
    resp = client.get(f"/api/sessions/{sid}/git-info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["branch"] == "test-branch", f"Expected real branch, got: {data}"


def test_inspection_returns_stored_messages(client: TestClient):
    """inspection should return the session's actual messages, not empty."""
    _clear_sessions()
    sid = "test-inspect-sid"
    msgs = [
        {"id": "m1", "type": "user", "content": "hello", "timestamp": ""},
        {"id": "m2", "type": "assistant", "content": "world", "timestamp": ""},
    ]
    client.post("/api/sessions", json={"sessionId": sid})
    client.post(f"/api/sessions/{sid}/messages", json={"messages": msgs, "title": "T"})

    resp = client.get(f"/api/sessions/{sid}/inspection")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2, f"Expected 2 messages, got: {data}"


def test_turn_checkpoints_returns_assistant_msgs(client: TestClient):
    """turn-checkpoints should list assistant messages as checkpoints."""
    _clear_sessions()
    sid = "test-tc-sid"
    msgs = [
        {"id": "m1", "type": "user", "content": "hi", "timestamp": "t1"},
        {"id": "m2", "type": "assistant", "content": "hello!", "timestamp": "t2"},
    ]
    client.post("/api/sessions", json={"sessionId": sid})
    client.post(f"/api/sessions/{sid}/messages", json={"messages": msgs, "title": "T"})

    resp = client.get(f"/api/sessions/{sid}/turn-checkpoints")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["checkpoints"]) == 1, f"Expected 1 checkpoint, got: {data}"
    assert data["checkpoints"][0]["turnId"] == "m2"


def test_branch_copies_messages(client: TestClient):
    """branch should copy messages into the new session, not return empty."""
    _clear_sessions()
    sid = "test-branch-src"
    msgs = [
        {"id": "m1", "type": "user", "content": "q", "timestamp": "t1"},
        {"id": "m2", "type": "assistant", "content": "a", "timestamp": "t2"},
    ]
    client.post("/api/sessions", json={"sessionId": sid})
    client.post(f"/api/sessions/{sid}/messages", json={"messages": msgs, "title": "Src"})

    resp = client.post(f"/api/sessions/{sid}/branch",
                       json={"title": "Branched", "targetMessageId": "m1"})
    assert resp.status_code == 200
    data = resp.json()
    new_sid = data["sessionId"]
    assert new_sid != sid

    from madcop.server.madcop_compat import _MESSAGES
    new_msgs = _MESSAGES.get(new_sid, [])
    assert len(new_msgs) == 1, f"Expected 1 copied message, got {len(new_msgs)}"
    assert new_msgs[0]["id"] == "m1"


# --------------------------------------------------------------------------- #
# P2: session_id filename sanitization
# --------------------------------------------------------------------------- #

def test_malicious_session_id_is_rejected(client: TestClient):
    """A session_id with path separators must not be written as a filename."""
    _clear_sessions()
    from madcop.server.madcop_compat import _safe_session_id

    # Path traversal attempts should return None
    assert _safe_session_id("../../../etc/passwd") is None
    assert _safe_session_id("..\\..\\evil") is None
    assert _safe_session_id("id with spaces") is None
    assert _safe_session_id("") is None
    assert _safe_session_id(None) is None  # type: ignore

    # Valid IDs pass through
    assert _safe_session_id("session-12345") == "session-12345"
    assert _safe_session_id("abc.def-ghi_123") == "abc.def-ghi_123"


def test_persist_lock_does_not_deadlock(client: TestClient):
    """Ensure RLock allows nested locking (_persist_session -> _register_workspace)."""
    _clear_sessions()
    sid = "test-deadlock-sid"
    client.post("/api/sessions", json={"sessionId": sid, "title": "T"})
    client.post(f"/api/sessions/{sid}/messages",
                json={"messages": [{"type": "user", "content": "hi"}], "title": "T"})
    # If we get here without timeout, the lock is not deadlocking.
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
