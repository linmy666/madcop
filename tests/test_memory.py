"""Tests for conversation memory."""

from __future__ import annotations

from madcop.llm import Message
from madcop.memory import ConversationBuffer


def test_buffer_empty() -> None:
    buf = ConversationBuffer()
    assert len(buf) == 0
    assert buf.messages() == []


def test_buffer_add_one() -> None:
    buf = ConversationBuffer()
    buf.add(Message("user", "hi"))
    assert len(buf) == 1
    assert buf.messages()[0].content == "hi"


def test_buffer_fifo_eviction() -> None:
    buf = ConversationBuffer(max_messages=3)
    for i in range(5):
        buf.add(Message("user", f"m{i}"))
    contents = [m.content for m in buf.messages()]
    assert contents == ["m2", "m3", "m4"]


def test_buffer_system_message_protected() -> None:
    buf = ConversationBuffer(max_messages=2)
    buf.add(Message("system", "SYSTEM"))
    buf.add(Message("user", "m1"))
    buf.add(Message("user", "m2"))
    buf.add(Message("user", "m3"))
    # System stays, oldest user evicted
    msgs = buf.messages()
    assert msgs[0].content == "SYSTEM"
    assert msgs[1].content == "m3"


def test_buffer_clear() -> None:
    buf = ConversationBuffer()
    buf.add(Message("user", "x"))
    buf.clear()
    assert len(buf) == 0


def test_buffer_extend() -> None:
    buf = ConversationBuffer()
    buf.extend([Message("user", "a"), Message("user", "b")])
    assert len(buf) == 2


def test_buffer_token_cap_evicts_oldest_non_system() -> None:
    # max_tokens tight enough to force eviction
    buf = ConversationBuffer(max_messages=100, max_tokens=10)
    buf.add(Message("system", "system prompt"))  # ~3 tokens at 4 chars/token
    buf.add(Message("user", "a" * 200))            # ~50 tokens
    # System should remain; user messages evicted as needed
    msgs = buf.messages()
    assert msgs[0].role == "system"


def test_buffer_only_system_remains_is_stable() -> None:
    buf = ConversationBuffer(max_messages=1)
    buf.add(Message("system", "SYS"))
    buf.add(Message("user", "drop me"))
    # System cannot be evicted
    assert len(buf) == 1
    assert buf.messages()[0].role == "system"