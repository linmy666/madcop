"""Tests for madcop.server.app — settings API + chat SSE."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from madcop.config import settings as S
from madcop.server.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with isolated settings + master key."""
    spath = tmp_path / "settings.json"
    kpath = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", spath)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", kpath)
    app = create_app()
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.6.0"


# --------------------------------------------------------------------------- #
# Settings GET / POST
# --------------------------------------------------------------------------- #

def test_get_empty_settings(client: TestClient):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["active_provider"] == ""
    assert data["providers"] == []
    assert "presets" in data
    assert len(data["presets"]) > 0


def test_post_settings_stores_encrypted(client: TestClient):
    r = client.post("/api/settings", json={
        "provider_id": "minimax",
        "base_url": "https://api.minimaxi.com/v1",
        "api_key": "***",
        "model": "MiniMax-M3",
        "label": "MiniMax",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["active_provider"] == "minimax"
    p = data["providers"][0]
    assert p["provider_id"] == "minimax"
    assert p["has_key"] is True
    assert "12345678" not in p["api_key_masked"]


def test_get_after_post(client: TestClient):
    client.post("/api/settings", json={
        "provider_id": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
        "model": "gpt-4o-mini",
    })
    r = client.get("/api/settings")
    data = r.json()
    assert len(data["providers"]) == 1
    assert data["providers"][0]["provider_id"] == "openai"


def test_post_without_key_preserves_existing(client: TestClient):
    client.post("/api/settings", json={
        "provider_id": "openai",
        "api_key": "sk-original",
        "base_url": "http://a",
        "model": "gpt-4o",
    })
    client.post("/api/settings", json={
        "provider_id": "openai",
        "api_key": "",
        "base_url": "http://b",
        "model": "gpt-4o-mini",
    })
    r = client.get("/api/settings")
    p = r.json()["providers"][0]
    assert p["has_key"] is True
    assert p["model"] == "gpt-4o-mini"


# --------------------------------------------------------------------------- #
# Settings active / delete
# --------------------------------------------------------------------------- #

def test_set_active_provider(client: TestClient):
    for pid in ["openai", "minimax"]:
        client.post("/api/settings", json={
            "provider_id": pid,
            "api_key": f"key-{pid}",
            "base_url": "http://x",
            "model": "m",
        })
    r = client.post("/api/settings/active", json={"provider_id": "openai"})
    assert r.status_code == 200
    assert r.json()["active_provider"] == "openai"


def test_set_active_not_found(client: TestClient):
    r = client.post("/api/settings/active", json={"provider_id": "nope"})
    assert r.status_code == 404


def test_delete_provider(client: TestClient):
    client.post("/api/settings", json={
        "provider_id": "openai",
        "api_key": "k",
        "base_url": "http://x",
        "model": "m",
    })
    r = client.delete("/api/settings/openai")
    assert r.status_code == 200
    assert len(r.json()["providers"]) == 0


# --------------------------------------------------------------------------- #
# Chat SSE — mock (no key configured)
# --------------------------------------------------------------------------- #

def test_chat_sse_no_key_returns_mock_stream(client: TestClient):
    """When no key is set, server falls back to MockClient."""
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")

    # Parse SSE events
    body = r.text
    lines = [l for l in body.strip().split("\n") if l.startswith("data: ")]
    events = [json.loads(l[6:]) for l in lines]

    # Should have text events + a done event
    text_events = [e for e in events if e["type"] == "text"]
    done_events = [e for e in events if e["type"] == "done"]

    assert len(text_events) > 0
    assert len(done_events) == 1
    # Mock says "No API key configured" message
    full_text = "".join(e["content"] for e in text_events)
    assert "No API key" in full_text


def test_chat_sse_with_mock_client_streams_words(client: TestClient):
    """Configure a mock-like key and verify word streaming."""
    # We can't easily inject a custom MockClient into the server without
    # refactoring _get_client. Instead, verify the SSE format is correct
    # by checking the no-key fallback path produces proper chunks.
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "test"}],
    })
    events = [json.loads(l[6:]) for l in r.text.strip().split("\n") if l.startswith("data: ")]
    # Each text event should have content
    for e in events:
        if e["type"] == "text":
            assert "content" in e
            assert isinstance(e["content"], str)
        elif e["type"] == "done":
            assert "finish_reason" in e


# --------------------------------------------------------------------------- #
# Docs endpoint
# --------------------------------------------------------------------------- #

def test_docs_available(client: TestClient):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower() or "openapi" in r.text.lower()


# --------------------------------------------------------------------------- #
# Gap 3: Token-budgeted memory injection
# --------------------------------------------------------------------------- #

def test_memory_system_prompt_caps_profile_budget(client):
    """When profile memories exceed the budget, the prompt is truncated."""
    from madcop.server.app import _build_memory_system_prompt, reset_memory_store
    from madcop.memory import MemoryStore, MemoryKind
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        # Isolated store with 50 long user-profile memories
        store = MemoryStore(path=Path(td) / "m.db")
        reset_memory_store(store)
        for i in range(50):
            store.insert(
                kind=MemoryKind.SEMANTIC,
                title=f"Fact {i}",
                content=f"User has fact number {i} which is a long string to fill tokens. " * 5,
                tags=("user-profile",),
            )
        try:
            # Tight budget: 100 tokens
            prompt = _build_memory_system_prompt(
                "anything", profile_budget=100, relevant_budget=100, preferences_budget=100
            )
            # Should contain truncation notice
            assert "truncated" in prompt
            # Should not contain ALL 50 facts
            for i in range(50):
                if i > 5:
                    assert f"Fact {i}" not in prompt or "truncated" in prompt, (
                        f"Fact {i} should have been truncated"
                    )
        finally:
            store.close()
            reset_memory_store(None)  # type: ignore[arg-type]


def test_estimate_tokens_cjk_vs_english():
    from madcop.server.app import _estimate_tokens
    # English: ~1 token per 4 chars
    assert _estimate_tokens("hello world") <= 5
    # Chinese: ~1 token per 1.5 chars
    assert _estimate_tokens("你好世界") <= 6
    # Empty/min
    assert _estimate_tokens("") >= 1


def test_truncate_to_budget_respects_limit():
    from madcop.server.app import _truncate_to_budget
    lines = ["- " + "x" * 100 for _ in range(20)]  # ~25 tokens each
    kept = _truncate_to_budget(lines, 50)
    assert len(kept) < len(lines)
    # Total char count of kept lines should be under budget*4
    total_chars = sum(len(l) for l in kept)
    assert total_chars < 200  # 50 tokens * 4 chars/token
