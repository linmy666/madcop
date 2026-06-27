"""L1 ConversationBuffer compaction (Gap 6).

When a conversation's token count exceeds a threshold, we summarise
the oldest messages into a single condensed entry. The summarisation
is done by the LLM (so it's smart), but with a cheap fallback to
truncation if no LLM is configured.

Public surface:
    from madcop.memory import compact_messages, CompactionConfig
    compacted = compact_messages(messages, config, llm_client=client)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..llm import ChatClient, Message


@dataclass
class CompactionConfig:
    """Knobs for message-list compaction."""
    max_tokens: int = 4000            # hard cap after compaction
    keep_recent: int = 6              # never summarise the most recent N msgs
    min_age_to_summarise: int = 4     # don't bother if fewer than this many old msgs
    summary_max_tokens: int = 300     # target length for the summary


def _estimate_tokens(text: str) -> int:
    """Same heuristic as madcop.server.app — keep in sync."""
    cjk = sum(1 for c in text if ord(c) > 0x4E00)
    return max(1, cjk // 2 + (len(text) - cjk) // 4)


def _total_tokens(messages: list[Message]) -> int:
    return sum(_estimate_tokens(m.content) for m in messages)


def _split_old_recent(
    messages: list[Message], keep_recent: int
) -> tuple[list[Message], list[Message]]:
    """Split into (old, recent) keeping the system message with recent."""
    # Always keep the first system message (if any) with the recent tail,
    # so the agent identity / memory context survives compaction.
    system_msgs = [m for m in messages if m.role == "system"]
    non_system = [m for m in messages if m.role != "system"]
    if len(non_system) <= keep_recent:
        return [], messages
    old = non_system[:-keep_recent] if keep_recent > 0 else non_system
    recent = non_system[-keep_recent:]
    return old, system_msgs + recent


def _truncate_summary(turns: list[Message], max_tokens: int) -> str:
    """Cheap fallback: take the first 2 sentences of each turn until budget."""
    lines: list[str] = []
    used = 0
    for m in turns:
        # Naive sentence split — fine for English & Chinese
        text = m.content.strip().replace("\n", " ")
        snippet = text[:120] + ("..." if len(text) > 120 else "")
        line = f"[{m.role}] {snippet}"
        cost = _estimate_tokens(line) + 1
        if used + cost > max_tokens:
            break
        lines.append(line)
        used += cost
    return " | ".join(lines)


def _llm_summarise(
    turns: list[Message],
    *,
    client: ChatClient,
    max_tokens: int,
) -> str | None:
    """Ask the LLM to summarise old turns. Returns None on failure."""
    transcript = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in turns
    )
    if not transcript.strip():
        return None
    try:
        resp = client.chat(
            [
                Message(
                    role="system",
                    content=(
                        "You are a conversation summariser. Compress the "
                        "following chat history into a concise paragraph "
                        "that preserves all important facts, decisions, "
                        "and user preferences. Stay under "
                        f"{max_tokens} tokens. Output ONLY the summary, "
                        "no preamble."
                    ),
                ),
                Message(role="user", content=transcript),
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        if resp.content and resp.content.strip():
            return resp.content.strip()
    except Exception:
        return None
    return None


def compact_messages(
    messages: list[Message],
    config: CompactionConfig | None = None,
    *,
    llm_client: ChatClient | None = None,
    summary_fn: Callable[[list[Message], int], str | None] | None = None,
) -> list[Message]:
    """Return a compacted copy of `messages`.

    Compaction rules:
    1. Always preserve the system message (memory context, agent identity).
    2. Keep the most recent `keep_recent` messages verbatim.
    3. If total tokens > `max_tokens`, summarise the older messages
       into one condensed system message. Use the LLM if available,
       otherwise fall back to a cheap truncate-and-join.
    4. The summary is inserted as a `system` message just before the
       recent block, with a `compaction_summary: True` marker in
       metadata-style content so the model knows it's a recap.
    5. Never summarise fewer than `min_age_to_summarise` messages.
    """
    if config is None:
        config = CompactionConfig()
    # Cheap copy — don't mutate the caller's list.
    out: list[Message] = list(messages)
    if _total_tokens(out) <= config.max_tokens:
        return out
    old, recent = _split_old_recent(out, config.keep_recent)
    if len(old) < config.min_age_to_summarise:
        return out  # not enough old content to be worth it

    # Build summary
    if summary_fn is not None:
        summary = summary_fn(old, config.summary_max_tokens)
    elif llm_client is not None:
        summary = _llm_summarise(old, client=llm_client, max_tokens=config.summary_max_tokens)
    else:
        summary = None
    if not summary:
        summary = _truncate_summary(old, config.summary_max_tokens)

    # Compose: [system, summary, ...recent]
    summary_msg = Message(
        role="system",
        content=(
            f"[Earlier conversation summary — {len(old)} turns compressed]\n"
            f"{summary}"
        ),
    )
    # Carry any original system messages, prepend the summary, then recent.
    system_msgs = [m for m in recent if m.role == "system"]
    non_sys_recent = [m for m in recent if m.role != "system"]
    compacted = system_msgs + [summary_msg] + non_sys_recent
    return compacted


__all__ = [
    "CompactionConfig",
    "compact_messages",
]
