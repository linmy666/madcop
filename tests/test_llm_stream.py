"""Tests for ChatClient.stream() — token-level streaming.

Covers:
- MockClient.stream: word-level splitting + final stop chunk
- MockClient.stream: scripted responses consumed in order
- OpenAICompatClient.stream: mocked SDK stream yields chunks
- OpenAICompatClient.stream: missing finish_reason gets synthesised
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from madcop.llm import (
    ChatClient,
    Message,
    MockClient,
    OpenAICompatClient,
    StreamChunk,
)


# --------------------------------------------------------------------------- #
# MockClient.stream
# --------------------------------------------------------------------------- #

def test_mock_stream_splits_words_and_ends_with_stop() -> None:
    c = MockClient(default_response="hello world foo")
    chunks = list(c.stream([Message("user", "hi")]))
    texts = [ch.text for ch in chunks]
    # Should split into 3 word-chunks + 1 final stop chunk
    assert len(chunks) == 4
    assert texts[0] == "hello"
    assert texts[1] == " world"
    assert texts[2] == " foo"
    # Last chunk is finish-only
    assert chunks[-1].text == ""
    assert chunks[-1].finish_reason == "stop"
    # Model passed through
    assert all(ch.model == "mock-model" for ch in chunks)


def test_mock_stream_uses_scripted_response() -> None:
    c = MockClient(scripted=["first scripted response"])
    chunks = list(c.stream([Message("user", "q")]))
    texts = "".join(ch.text for ch in chunks)
    assert texts == "first scripted response"
    assert chunks[-1].finish_reason == "stop"


def test_mock_stream_records_call_telemetry() -> None:
    c = MockClient(default_response="ok")
    list(c.stream([Message("user", "ping")]))
    assert len(c.calls) == 1
    assert c.calls[0][0].content == "ping"


def test_mock_stream_respects_model_override() -> None:
    c = MockClient(default_response="x")
    chunks = list(c.stream([Message("user", "hi")], model="gpt-custom"))
    assert all(ch.model == "gpt-custom" for ch in chunks)


def test_mock_stream_single_word() -> None:
    """Edge case: response with no spaces."""
    c = MockClient(default_response="hi")
    chunks = list(c.stream([Message("user", "?")]))
    assert len(chunks) == 2  # one word chunk + stop
    assert chunks[0].text == "hi"
    assert chunks[1].finish_reason == "stop"


# --------------------------------------------------------------------------- #
# OpenAICompatClient.stream (mocked SDK)
# --------------------------------------------------------------------------- #

@dataclass
class _FakeDelta:
    content: str | None
    role: str | None = None


@dataclass
class _FakeChoice:
    delta: _FakeDelta
    finish_reason: str | None = None
    index: int = 0


@dataclass
class _FakeChunk:
    choices: list[_FakeChoice]
    model: str = "test-model"


def _make_fake_stream(chunks_data: list[tuple[str, str | None]]) -> list[_FakeChunk]:
    """Build a list of fake SDK chunks from (text, finish_reason) pairs."""
    result = []
    for text, finish in chunks_data:
        result.append(_FakeChunk(
            choices=[_FakeChoice(
                delta=_FakeDelta(content=text),
                finish_reason=finish,
            )],
        ))
    return result


def test_openai_stream_yields_chunks_from_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock the OpenAI SDK to verify stream() yields per-chunk text."""
    monkeypatch.setenv("MADCOP_OPENAI_API_KEY", "test-key")

    client = OpenAICompatClient()

    fake_chunks = _make_fake_stream([
        ("Hello", None),
        (" world", None),
        ("!", "stop"),
    ])

    mock_create = MagicMock(return_value=iter(fake_chunks))
    client._client.chat.completions.create = mock_create  # type: ignore

    chunks = list(client.stream([Message("user", "hi")]))
    assert len(chunks) == 3
    assert chunks[0].text == "Hello"
    assert chunks[1].text == " world"
    assert chunks[2].text == "!"
    assert chunks[2].finish_reason == "stop"
    # Verify stream=True was passed
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["stream"] is True


def test_openai_stream_synthesises_finish_if_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If SDK never sends finish_reason, we synthesise 'stop'."""
    monkeypatch.setenv("MADCOP_OPENAI_API_KEY", "test-key")
    client = OpenAICompatClient()

    fake_chunks = _make_fake_stream([
        ("Hi", None),
        (" there", None),
        # no finish_reason on any chunk
    ])
    client._client.chat.completions.create = MagicMock(
        return_value=iter(fake_chunks),
    )

    chunks = list(client.stream([Message("user", "hello")]))
    # Original 2 chunks + 1 synthesised stop
    assert len(chunks) == 3
    assert chunks[-1].finish_reason == "stop"


def test_openai_stream_handles_empty_content_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chunks with None/empty content should be skipped (text='')."""
    monkeypatch.setenv("MADCOP_OPENAI_API_KEY", "test-key")
    client = OpenAICompatClient()

    fake_chunks = [
        _FakeChunk(choices=[_FakeChoice(delta=_FakeDelta(content=None))]),
        _FakeChunk(choices=[_FakeChoice(delta=_FakeDelta(content="real"))]),
        _FakeChunk(choices=[_FakeChoice(
            delta=_FakeDelta(content=""), finish_reason="stop",
        )]),
    ]
    client._client.chat.completions.create = MagicMock(
        return_value=iter(fake_chunks),
    )

    chunks = list(client.stream([Message("user", "x")]))
    assert len(chunks) == 3
    # First chunk has empty text (None -> "")
    assert chunks[0].text == ""
    assert chunks[1].text == "real"
    assert chunks[2].finish_reason == "stop"


def test_openai_stream_passes_model_and_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify model/temperature kwargs are forwarded to the SDK."""
    monkeypatch.setenv("MADCOP_OPENAI_API_KEY", "test-key")
    client = OpenAICompatClient()

    mock_create = MagicMock(return_value=iter(_make_fake_stream([
        ("ok", "stop"),
    ])))
    client._client.chat.completions.create = mock_create

    list(client.stream(
        [Message("user", "hi")],
        model="custom-model",
        temperature=0.7,
    ))
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["model"] == "custom-model"
    assert call_kwargs["temperature"] == 0.7
