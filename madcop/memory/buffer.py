"""L7 — Conversation memory (short-term buffer).

Keeps the most recent `max_messages` chat messages and trims older
ones. This is the simplest memory strategy; for longer conversations
swap in a vector-DB-backed memory (out of scope for v0.5).

Design choice: FIFO with optional token-budget cap. Both are useful:
- Message count cap is predictable (no surprise context explosion).
- Token budget is a closer proxy for LLM cost / context-window limits.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..llm import Message


@dataclass
class ConversationBuffer:
    """FIFO message buffer with optional token cap.

    The first message is always a system prompt (if present); we never
    evict it once added, even if newer messages overflow the budget.
    """

    max_messages: int = 50
    max_tokens: int | None = None          # rough: len(content) / 4
    _messages: deque[Message] = field(default_factory=deque)

    def add(self, msg: Message) -> None:
        """Append a message, evicting the oldest non-system message if needed."""
        self._messages.append(msg)
        self._evict()

    def extend(self, msgs: list[Message]) -> None:
        for m in msgs:
            self.add(m)

    def messages(self) -> list[Message]:
        """Return the current buffer as a list (snapshot)."""
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def _evict(self) -> None:
        # Count-based eviction
        while len(self._messages) > self.max_messages:
            self._evict_oldest_non_system()
        # Token-based eviction
        if self.max_tokens is not None:
            while self._token_count() > self.max_tokens and len(self._messages) > 1:
                if not self._evict_oldest_non_system():
                    break  # only system left

    def _evict_oldest_non_system(self) -> bool:
        for i, m in enumerate(self._messages):
            if m.role != "system":
                del self._messages[i]
                return True
        return False  # only system messages left

    def _token_count(self) -> int:
        """Cheap token estimate: ~1 token per 4 chars."""
        return sum(len(m.content) for m in self._messages) // 4


__all__ = ["ConversationBuffer"]