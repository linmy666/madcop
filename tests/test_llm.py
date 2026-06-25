"""Tests for the LLM client."""

from __future__ import annotations

import pytest

from madcop.llm import (
    ChatClient,
    ChatResponse,
    Message,
    MockClient,
    OpenAICompatClient,
    ToolCall,
    make_client,
)


# --------------------------------------------------------------------------- #
# Message
# --------------------------------------------------------------------------- #

def test_message_to_dict_basic() -> None:
    m = Message(role="user", content="hi")
    assert m.to_dict() == {"role": "user", "content": "hi"}


def test_message_to_dict_with_tool_call_id() -> None:
    m = Message(role="tool", content="ok", tool_call_id="abc")
    d = m.to_dict()
    assert d["tool_call_id"] == "abc"
    assert "name" not in d  # not included when None


def test_message_to_dict_with_name() -> None:
    m = Message(role="assistant", content="x", name="bot")
    assert m.to_dict()["name"] == "bot"


# --------------------------------------------------------------------------- #
# MockClient
# --------------------------------------------------------------------------- #

def test_mock_default_response() -> None:
    c = MockClient()
    r = c.chat([Message("user", "hi")])
    assert r.content == "OK (mock LLM response)"
    assert r.model == "mock-model"


def test_mock_scripted_responses_consumed_in_order() -> None:
    c = MockClient(scripted=["first", "second"])
    r1 = c.chat([Message("user", "a")])
    r2 = c.chat([Message("user", "b")])
    r3 = c.chat([Message("user", "c")])
    assert r1.content == "first"
    assert r2.content == "second"
    assert r3.content == "OK (mock LLM response)"  # fallback after script exhausted


def test_mock_records_calls() -> None:
    c = MockClient()
    c.chat([Message("user", "first")])
    c.chat([Message("user", "second")])
    assert len(c.calls) == 2
    assert c.calls[1][0].content == "second"


def test_mock_passes_through_model_param() -> None:
    c = MockClient()
    r = c.chat([Message("user", "hi")], model="custom-model")
    assert r.model == "custom-model"


# --------------------------------------------------------------------------- #
# OpenAICompatClient
# --------------------------------------------------------------------------- #

def test_openai_compat_rejects_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API key"):
        OpenAICompatClient()


def test_openai_compat_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MADCOP_OPENAI_API_KEY", "test-key-123")
    monkeypatch.setenv("MADCOP_OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("MADCOP_OPENAI_MODEL", "test-model")
    client = OpenAICompatClient()
    assert client.api_key == "test-key-123"
    assert client.base_url == "https://example.com/v1"
    assert client.model == "test-model"


# --------------------------------------------------------------------------- #
# make_client factory
# --------------------------------------------------------------------------- #

def test_make_client_default_is_mock() -> None:
    c = make_client()
    assert isinstance(c, MockClient)


def test_make_client_real_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        make_client(use_real=True)


# --------------------------------------------------------------------------- #
# Abstract contract
# --------------------------------------------------------------------------- #

def test_chat_client_is_abstract() -> None:
    with pytest.raises(TypeError):
        ChatClient()  # type: ignore[abstract]