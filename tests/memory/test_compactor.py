"""Tests for conversation compaction (Gap 6)."""

from __future__ import annotations

from madcop.llm import Message, ChatResponse
from madcop.memory import compact_messages, CompactionConfig


def _long_msg(text: str, role: str = "user") -> Message:
    return Message(role=role, content=text)


def test_no_compaction_under_budget():
    """Short messages are returned unchanged."""
    msgs = [
        _long_msg("hi", "user"),
        _long_msg("hello", "assistant"),
    ]
    out = compact_messages(msgs, CompactionConfig(max_tokens=10000))
    assert out == msgs


def test_compaction_summarises_old_messages():
    """Long conversation triggers compaction of old messages."""
    msgs = (
        [_long_msg("You are helpful.", "system")]
        + [_long_msg(f"turn {i}: " + "x" * 500, "user" if i % 2 == 0 else "assistant")
           for i in range(20)]
    )
    out = compact_messages(
        msgs,
        CompactionConfig(
            max_tokens=2000,  # tight budget to force compaction
            keep_recent=4,
            min_age_to_summarise=2,
            summary_max_tokens=200,
        ),
    )
    # Recent 4 (non-system) preserved verbatim
    assert msgs[-4:] in [out[-4:]] or all(
        m.content in [o.content for o in out[-4:]] for m in msgs[-4:]
    )
    # Summary message present
    summary_msgs = [m for m in out if m.content.startswith("[Earlier conversation summary")]
    assert summary_msgs, "compaction should add a summary message"
    # Number of messages should drop
    assert len(out) < len(msgs)


def test_compaction_preserves_system_message():
    """The original system message stays in the compacted list."""
    msgs = [
        _long_msg("CRITICAL SYSTEM: you are X", "system"),
        _long_msg("turn 1: " + "y" * 600, "user"),
        _long_msg("turn 2: " + "y" * 600, "assistant"),
        _long_msg("turn 3: " + "y" * 600, "user"),
        _long_msg("turn 4: " + "y" * 600, "assistant"),
        _long_msg("turn 5: " + "y" * 600, "user"),
        _long_msg("turn 6: " + "y" * 600, "assistant"),
        _long_msg("turn 7: " + "y" * 600, "user"),
        _long_msg("turn 8: " + "y" * 600, "assistant"),
    ]
    out = compact_messages(
        msgs,
        CompactionConfig(max_tokens=500, keep_recent=4, min_age_to_summarise=2),
    )
    system_msgs = [m for m in out if m.role == "system" and "CRITICAL" in m.content]
    assert system_msgs, "Original system message must survive compaction"


def test_compaction_min_age_guard():
    """If there are fewer than min_age_to_summarise old messages, skip."""
    msgs = [
        _long_msg("sys", "system"),
        _long_msg("turn 1: " + "x" * 500, "user"),
        _long_msg("turn 2: " + "x" * 500, "assistant"),
        _long_msg("turn 3: " + "x" * 500, "user"),
    ]
    out = compact_messages(
        msgs,
        CompactionConfig(max_tokens=100, keep_recent=2, min_age_to_summarise=10),
    )
    # No compaction triggered
    assert len(out) == len(msgs)


def test_compaction_fallback_uses_truncate():
    """Without an LLM client, fallback to truncate-and-join."""
    msgs = [
        _long_msg("sys", "system"),
        _long_msg("First user question about cats", "user"),
        _long_msg("First answer about cats", "assistant"),
        _long_msg("Second user question about dogs", "user"),
        _long_msg("Second answer about dogs", "assistant"),
        _long_msg("Third question about birds", "user"),
        _long_msg("Third answer about birds", "assistant"),
        _long_msg("Fourth question", "user"),
        _long_msg("Fourth answer", "assistant"),
    ]
    out = compact_messages(
        msgs,
        CompactionConfig(max_tokens=10, keep_recent=4, min_age_to_summarise=2,
                         summary_max_tokens=100),
    )
    # Summary should exist and contain keywords from old messages
    summary_msgs = [m for m in out if m.content.startswith("[Earlier conversation summary")]
    assert summary_msgs
    body = summary_msgs[0].content
    # Fallback uses [role] prefix markers
    assert "[user]" in body or "[assistant]" in body


def test_compaction_with_llm_client():
    """With an LLM client, the summary comes from the LLM (mocked)."""

    from madcop.llm import ChatClient

    class FakeClient(ChatClient):
        def __init__(self, summary: str = "User asked about cats. Assistant explained."):
            self._summary = summary

        def chat(self, messages, *, model=None, temperature=0.0, max_tokens=None, tools=None):
            return ChatResponse(content=self._summary, model="fake")

    msgs = [
        _long_msg("sys", "system"),
        _long_msg("Tell me about cats", "user"),
        _long_msg("Cats are mammals", "assistant"),
        _long_msg("What about dogs", "user"),
        _long_msg("Dogs are also mammals", "assistant"),
        _long_msg("Birds?", "user"),
        _long_msg("Birds have feathers", "assistant"),
        _long_msg("Fish?", "user"),
        _long_msg("Fish live in water", "assistant"),
    ]
    out = compact_messages(
        msgs,
        CompactionConfig(max_tokens=10, keep_recent=4, min_age_to_summarise=2,
                         summary_max_tokens=200),
        llm_client=FakeClient(),
    )
    summary_msgs = [m for m in out if m.content.startswith("[Earlier conversation summary")]
    assert summary_msgs
    assert "User asked about cats" in summary_msgs[0].content
