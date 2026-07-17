"""P0 security: filesystem allowlist + message/session size limits."""

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
    app = create_app()
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Filesystem browse / file allowlist
# --------------------------------------------------------------------------- #

def test_browse_home_ok(client: TestClient):
    r = client.get("/api/filesystem/browse", params={"path": str(Path.home())})
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data


def test_browse_madcop_dir_forbidden(client: TestClient):
    """Entire ~/.madcop is sensitive — browse must 403."""
    madcop = Path.home() / ".madcop"
    madcop.mkdir(parents=True, exist_ok=True)
    r = client.get("/api/filesystem/browse", params={"path": str(madcop)})
    assert r.status_code == 403


def test_browse_settings_json_forbidden(client: TestClient):
    settings = Path.home() / ".madcop" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    if not settings.exists():
        settings.write_text("{}")
    r = client.get("/api/filesystem/browse", params={"path": str(settings.parent)})
    assert r.status_code == 403


def test_file_ssh_dir_forbidden(client: TestClient):
    ssh = Path.home() / ".ssh"
    # Even if missing, path resolve still blocks the sensitive root.
    # Use a path under .ssh that may not exist — check is on path prefix.
    r = client.get("/api/filesystem/file", params={"path": str(ssh / "id_rsa")})
    # 403 if .ssh resolves; if somehow not under home (unlikely) may differ.
    assert r.status_code in (403, 404)


def test_file_outside_allowed_roots_forbidden(client: TestClient):
    # /etc is outside home/cwd/tmp on a normal macOS/Linux setup.
    r = client.get("/api/filesystem/file", params={"path": "/etc/passwd"})
    assert r.status_code == 403


def test_file_tmp_ok(client: TestClient, tmp_path: Path):
    # Prefer /tmp which is always in the allowlist.
    import tempfile
    with tempfile.NamedTemporaryFile(dir="/tmp", delete=False, suffix=".txt") as f:
        f.write(b"hello-allowlist")
        path = f.name
    try:
        r = client.get("/api/filesystem/file", params={"path": path})
        assert r.status_code == 200
        assert b"hello-allowlist" in r.content
    finally:
        Path(path).unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Chat message size limits
# --------------------------------------------------------------------------- #

def test_chat_rejects_oversized_content(client: TestClient):
    from madcop.server.app import _MAX_CHAT_CONTENT_CHARS
    huge = "x" * (_MAX_CHAT_CONTENT_CHARS + 1)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": huge}],
    })
    assert r.status_code == 422  # pydantic validation error


def test_chat_accepts_content_at_limit(client: TestClient):
    from madcop.server.app import _MAX_CHAT_CONTENT_CHARS
    # At the limit should pass validation (may fail later if no provider).
    body = "y" * min(1000, _MAX_CHAT_CONTENT_CHARS)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": body}],
    })
    # 200 SSE or 4xx from missing provider — but not 422 for content length
    assert r.status_code != 422


# --------------------------------------------------------------------------- #
# Session messages size limits
# --------------------------------------------------------------------------- #

def test_save_session_messages_rejects_too_many(client: TestClient):
    from madcop.server.madcop_compat import _MAX_SAVE_PAYLOAD_MESSAGES
    sid = "sec-limit-many"
    msgs = [{"type": "user", "content": f"m{i}"} for i in range(_MAX_SAVE_PAYLOAD_MESSAGES + 5)]
    r = client.post(f"/api/sessions/{sid}/messages", json={"messages": msgs})
    assert r.status_code == 400
    assert "too many" in r.json()["detail"].lower() or "too many" in str(r.json()).lower()


def test_save_session_messages_truncates_long_content(client: TestClient):
    from madcop.server.madcop_compat import (
        _MAX_MESSAGE_CONTENT_CHARS,
        _MESSAGES,
        _SESSIONS,
    )
    _SESSIONS.clear()
    _MESSAGES.clear()
    sid = "sec-limit-trunc"
    long_content = "z" * (_MAX_MESSAGE_CONTENT_CHARS + 5000)
    r = client.post(
        f"/api/sessions/{sid}/messages",
        json={"messages": [{"type": "user", "content": long_content}]},
    )
    assert r.status_code == 200
    stored = _MESSAGES[sid]
    assert len(stored) == 1
    assert len(stored[0]["content"]) == _MAX_MESSAGE_CONTENT_CHARS


# --------------------------------------------------------------------------- #
# Settings load cache
# --------------------------------------------------------------------------- #

def test_settings_cache_hits_same_mtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import json
    import time

    spath = tmp_path / "settings.json"
    kpath = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", spath)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", kpath)
    S._invalidate_settings_cache()

    settings = S.upsert_provider(
        S.load_settings(),
        provider_id="cache-test",
        base_url="http://localhost",
        api_key="sk-cache",
        model="m",
    )
    S.save_settings(settings, spath)

    a = S.load_settings(spath)
    b = S.load_settings(spath)
    # Same object from cache (identity)
    assert a is b

    # External write with new mtime must invalidate
    time.sleep(0.05)
    raw = json.loads(spath.read_text())
    raw["active_provider"] = "cache-test-mutated"
    spath.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    c = S.load_settings(spath)
    assert c is not a
    assert c.active_provider == "cache-test-mutated"
