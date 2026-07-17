"""Global session search API shape used by GlobalSearchModal."""

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


def test_search_sessions_returns_results_shape(client: TestClient):
    _clear()
    sid = "search-sid-1"
    client.post("/api/sessions", json={"sessionId": sid, "title": "Alpha Project"})
    client.post(
        f"/api/sessions/{sid}/messages",
        json={
            "messages": [
                {"id": "m1", "type": "user", "content": "hello unique-token-xyz"},
                {"id": "m2", "type": "assistant", "content": "world reply"},
            ],
            "title": "Alpha Project",
        },
    )

    r = client.post("/api/search/sessions", json={"query": "unique-token-xyz", "limit": 20})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert data["total"] >= 1
    hit = data["results"][0]
    assert hit["sessionId"] == sid
    assert hit["matchCount"] >= 1
    assert hit["matches"][0]["snippet"]
    assert hit["matches"][0]["highlights"]


def test_search_sessions_title_only(client: TestClient):
    _clear()
    sid = "search-sid-2"
    client.post("/api/sessions", json={"sessionId": sid, "title": "Zebra Special Title"})
    client.post(
        f"/api/sessions/{sid}/messages",
        json={"messages": [{"id": "m1", "type": "user", "content": "noop"}], "title": "Zebra Special Title"},
    )

    r = client.post("/api/search/sessions", json={"query": "Zebra Special"})
    assert r.status_code == 200
    data = r.json()
    assert any(x["sessionId"] == sid for x in data["results"])


def test_search_sessions_empty_query(client: TestClient):
    r = client.post("/api/search/sessions", json={"query": "  "})
    assert r.status_code == 200
    assert r.json() == {"results": [], "total": 0, "truncated": False}
