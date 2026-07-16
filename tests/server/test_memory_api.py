"""Tests for memory integration in the chat endpoint + memory CRUD API.

Covers:
- Task 1: Memory injection — system prompt includes retrieved memories.
- Task 2: Memory extraction — facts are extracted from user messages
  after the streaming response.
- Task 3: Memory CRUD endpoints (GET/POST/DELETE/search).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from madcop.config import settings as S
from madcop.llm import ChatResponse, Message, StreamChunk
from madcop.memory import (
    MemoryStore,
    EpisodicMemory,
    SemanticMemory,
    ReflectiveMemory,
    ReflectionKind,
    EpisodeOutcome,
)
from madcop.server import app as app_module
from madcop.server.app import create_app, reset_memory_store


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def parse_sse(body: str) -> list[dict]:
    """Parse SSE response body into list of event dicts."""
    lines = [l for l in body.strip().split("\n") if l.startswith("data: ")]
    return [json.loads(l[6:]) for l in lines]


class FakeClient:
    """A minimal fake LLM client for memory tests.

    - ``chat()`` returns a ChatResponse with no tool calls.
    - ``stream()`` yields the canned text in a single chunk + stop.
    - Records all calls so tests can inspect the messages sent.
    """

    def __init__(self, response: str = "Hello from madcop!"):
        self._response = response
        self.chat_calls: list[list[Message]] = []
        self.stream_calls: list[list[Message]] = []

    @property
    def all_calls(self) -> list[list[Message]]:
        """All LLM calls regardless of method (chat or stream).

        Phase-1 streaming routes the no-tool path through ``stream()``
        instead of ``chat()``, so memory tests that just want to inspect
        the system prompt should use this instead of ``chat_calls``.
        """
        return self.chat_calls or self.stream_calls

    def chat(self, messages, *, model=None, temperature=0.0,
             max_tokens=None, tools=None, effort=None):
        msgs = list(messages)
        self.chat_calls.append(msgs)
        return ChatResponse(content=self._response, model="test-model")

    def stream(self, messages, *, model=None, temperature=0.0,
               max_tokens=None, tools=None, effort=None):
        msgs = list(messages)
        self.stream_calls.append(msgs)
        yield StreamChunk(text=self._response, model="test-model")
        yield StreamChunk(finish_reason="stop", model="test-model")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with isolated settings AND isolated memory DB.

    The memory DB lives under ``tmp_path`` so tests don't pollute the
    real ``~/.madcop/memory.db``.
    """
    # Isolate settings
    spath = tmp_path / "settings.json"
    kpath = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", spath)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", kpath)

    # Isolate memory store
    db_path = tmp_path / "memory.db"
    store = MemoryStore(path=db_path)
    reset_memory_store(store)

    app = create_app()
    tc = TestClient(app)

    yield tc

    store.close()
    # Reset the module-level singleton after the test
    reset_memory_store(None)  # type: ignore[arg-type]


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    """Inject a FakeClient into the server by patching MockClient."""
    fc = FakeClient()
    monkeypatch.setattr(app_module, "MockClient", lambda **kw: fc)
    return fc


# --------------------------------------------------------------------------- #
# Task 1: Memory Injection
# --------------------------------------------------------------------------- #

def test_system_prompt_contains_identity(client: TestClient, fake_client):
    """The injected system prompt must include agent identity."""
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hello"}],
    })
    # The first message sent to the LLM should be a system prompt
    msgs = fake_client.all_calls[0]
    assert msgs[0].role == "system"
    assert "madcop" in msgs[0].content.lower()


def test_system_prompt_includes_retrieved_memory(client: TestClient, fake_client):
    """When a relevant memory exists, it should appear in the system prompt."""
    # Pre-populate semantic memory with a fact about the user's name
    store = app_module.get_memory_store()
    sem = SemanticMemory(store)
    sem.add(
        subject="user",
        predicate="is named",
        object="Alice",
        tags=("user-profile",),
    )

    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "who am I?"}],
    })

    msgs = fake_client.all_calls[0]
    sys_content = msgs[0].content
    # The fact should be retrievable via FTS and injected
    assert "Alice" in sys_content


def test_system_prompt_includes_user_preferences(client: TestClient, fake_client):
    """L4 user preferences should be injected into the system prompt."""
    store = app_module.get_memory_store()
    ref = ReflectiveMemory(store)
    ref.add(
        text="concise bullet-point summaries",
        kind=ReflectionKind.USER_PREFERENCE,
        tags=("style",),
    )

    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "summarize the news"}],
    })

    msgs = fake_client.all_calls[0]
    sys_content = msgs[0].content
    assert "preference" in sys_content.lower() or "concise" in sys_content.lower()


def test_no_memory_still_has_identity(client: TestClient, fake_client):
    """With an empty memory DB, the system prompt still has identity."""
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hello"}],
    })
    msgs = fake_client.all_calls[0]
    assert msgs[0].role == "system"
    assert "madcop" in msgs[0].content.lower()
    # Should NOT have memory context section
    assert "Memory context" not in msgs[0].content


def test_existing_system_prompt_is_replaced(client: TestClient, fake_client):
    """If the client sends a system message, it's replaced (not duplicated)."""
    client.post("/api/chat", json={
        "messages": [
            {"role": "system", "content": "You are a pirate."},
            {"role": "user", "content": "hello"},
        ],
    })
    msgs = fake_client.all_calls[0]
    # Only one system message, and it should be madcop's, not the pirate
    sys_msgs = [m for m in msgs if m.role == "system"]
    assert len(sys_msgs) == 1
    assert "madcop" in sys_msgs[0].content.lower()
    assert "pirate" not in sys_msgs[0].content.lower()


# --------------------------------------------------------------------------- #
# Task 2: Memory Extraction
# --------------------------------------------------------------------------- #

def test_extract_name_english(client: TestClient, fake_client):
    """User says 'my name is X' → fact is extracted and stored."""
    from madcop.server.app import _store_extracted_facts
    from madcop.llm import Message
    msgs = [Message(role="user", content="My name is John.")]
    _store_extracted_facts(msgs)
    store = app_module.get_memory_store()
    sem = SemanticMemory(store)
    facts = sem.search("John")
    assert len(facts) >= 1
    assert any("John" in f.object for f in facts)


def test_extract_name_chinese(client: TestClient, fake_client):
    """User says '我叫X' → fact is extracted."""
    from madcop.server.app import _store_extracted_facts
    from madcop.llm import Message
    msgs = [Message(role="user", content="你好，我叫小明。")]
    _store_extracted_facts(msgs)
    store = app_module.get_memory_store()
    sem = SemanticMemory(store)
    facts = sem.search("小明")
    assert len(facts) >= 1


def test_extract_preference_english(client: TestClient, fake_client):
    """User says 'I like X' → preference fact is stored."""
    from madcop.server.app import _store_extracted_facts
    from madcop.llm import Message
    msgs = [Message(role="user", content="I like dark mode.")]
    _store_extracted_facts(msgs)
    store = app_module.get_memory_store()
    sem = SemanticMemory(store)
    facts = sem.search("dark")
    assert len(facts) >= 1
    assert any("dark" in f.object.lower() for f in facts)


def test_extract_preference_chinese(client: TestClient, fake_client):
    """User says '我喜欢X' → preference fact is stored."""
    from madcop.server.app import _store_extracted_facts
    from madcop.llm import Message
    msgs = [Message(role="user", content="我喜欢Python编程。")]
    _store_extracted_facts(msgs)
    store = app_module.get_memory_store()
    sem = SemanticMemory(store)
    # FTS5 may not tokenize "Python" from Chinese-mixed content,
    # so search by tag instead.
    facts = sem.search("preference")
    assert len(facts) >= 1


def test_no_extraction_for_plain_message(client: TestClient, fake_client):
    """A message with no name/preference pattern should not store anything."""
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "What is the weather?"}],
    })
    store = app_module.get_memory_store()
    sem = SemanticMemory(store)
    assert sem.count() == 0


def test_extract_facts_unit():
    """Unit test for the extraction helper directly."""
    from madcop.server.app import _extract_facts_from_text

    # English name
    facts = _extract_facts_from_text("Hi, my name is Alice!")
    assert len(facts) >= 1
    assert any("Alice" in f["content"] for f in facts)

    # Chinese name
    facts = _extract_facts_from_text("你好，我叫小红。")
    assert len(facts) >= 1
    assert any("小红" in f["content"] for f in facts)

    # Preference (English)
    facts = _extract_facts_from_text("I like dark themes.")
    assert len(facts) >= 1
    assert any("dark" in f["content"].lower() for f in facts)

    # No match
    facts = _extract_facts_from_text("The weather is nice today.")
    assert facts == []


# --------------------------------------------------------------------------- #
# Task 3: Memory CRUD API
# --------------------------------------------------------------------------- #

def test_list_memory_empty(client: TestClient):
    """GET /api/memory on empty DB returns empty groups."""
    r = client.get("/api/memory")
    assert r.status_code == 200
    data = r.json()
    assert data["episodic"] == []
    assert data["semantic"] == []
    assert data["reflective"] == []
    assert data["total"] == 0


def test_add_memory_semantic(client: TestClient):
    """POST /api/memory adds a semantic record."""
    r = client.post("/api/memory", json={
        "kind": "semantic",
        "title": "Test fact",
        "content": "The sky is blue.",
        "tags": ["test"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["kind"] == "semantic"
    assert data["title"] == "Test fact"
    assert "test" in data["tags"]
    assert data["id"]

    # Verify it appears in list
    r2 = client.get("/api/memory")
    assert r2.status_code == 200
    assert len(r2.json()["semantic"]) == 1
    assert r2.json()["total"] == 1


def test_add_memory_reflective(client: TestClient):
    """POST /api/memory with kind=reflective."""
    r = client.post("/api/memory", json={
        "kind": "reflective",
        "title": "User likes brevity",
        "content": "User prefers short answers.",
        "tags": ["style"],
    })
    assert r.status_code == 200
    assert r.json()["kind"] == "reflective"


def test_add_memory_invalid_kind(client: TestClient):
    """POST /api/memory with invalid kind returns 400."""
    r = client.post("/api/memory", json={
        "kind": "bogus",
        "title": "x",
    })
    assert r.status_code == 400


def test_delete_memory(client: TestClient):
    """DELETE /api/memory/{id} removes the record."""
    # Add one
    r = client.post("/api/memory", json={
        "kind": "semantic",
        "title": "To be deleted",
        "content": "temp",
    })
    mem_id = r.json()["id"]

    # Delete it
    r2 = client.delete(f"/api/memory/{mem_id}")
    assert r2.status_code == 200
    assert r2.json()["deleted"] is True

    # List should be empty again
    r3 = client.get("/api/memory")
    assert r3.json()["total"] == 0


def test_delete_memory_not_found(client: TestClient):
    """DELETE with non-existent ID returns 404."""
    r = client.delete("/api/memory/nonexistent-id")
    assert r.status_code == 404


def test_search_memory(client: TestClient):
    """GET /api/memory/search?q=... finds matching records."""
    client.post("/api/memory", json={
        "kind": "semantic",
        "title": "Python is great",
        "content": "Python is a programming language.",
        "tags": ["tech"],
    })
    client.post("/api/memory", json={
        "kind": "semantic",
        "title": "Rust memory safety",
        "content": "Rust provides memory safety guarantees.",
        "tags": ["tech"],
    })

    r = client.get("/api/memory/search", params={"q": "Python"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    titles = [res["title"] for res in data["results"]]
    assert any("Python" in t for t in titles)


def test_search_memory_no_results(client: TestClient):
    """Search with no matches returns empty results."""
    r = client.get("/api/memory/search", params={"q": "nonexistent12345"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_memory_persists_across_requests(client: TestClient):
    """Memory added in one request is visible in subsequent requests."""
    client.post("/api/memory", json={
        "kind": "semantic",
        "title": "Persistent fact",
        "content": "This should persist.",
    })

    # Different request — memory should still be there
    r = client.get("/api/memory")
    assert r.json()["total"] == 1


def test_list_memory_groups_correctly(client: TestClient):
    """Memories are correctly grouped by kind in the response."""
    client.post("/api/memory", json={
        "kind": "semantic", "title": "S1", "content": "semantic fact",
    })
    client.post("/api/memory", json={
        "kind": "reflective", "title": "R1", "content": "reflection",
    })
    client.post("/api/memory", json={
        "kind": "episodic", "title": "E1", "content": "episode",
    })

    r = client.get("/api/memory")
    data = r.json()
    assert len(data["semantic"]) == 1
    assert len(data["reflective"]) == 1
    assert len(data["episodic"]) == 1
    assert data["total"] == 3


# --------------------------------------------------------------------------- #
# Integration: memory injection + extraction in one flow
# --------------------------------------------------------------------------- #

def test_cross_session_memory_flow(client: TestClient, fake_client):
    """End-to-end: user states name in session 1, it's available in session 2."""
    # Session 1: user introduces themselves.
    # Use the sync extraction path so session 2 sees the fact immediately
    # (the async pipeline has a debounce window which we don't want to
    # wait on in a unit test).
    from madcop.server.app import _store_extracted_facts
    from madcop.llm import Message
    _store_extracted_facts([Message(role="user", content="My name is Bob.")])

    # Session 2: ask "who am I?" — memory should be injected
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "who am I?"}],
    })

    msgs = fake_client.all_calls[-1]  # last call (session 2)
    sys_content = msgs[0].content
    assert "Bob" in sys_content
