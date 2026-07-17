"""Shared dependencies for route modules."""
from __future__ import annotations

from madcop.memory import MemoryStore

_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Return (and lazily create) the global MemoryStore singleton."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


def reset_memory_store(store: MemoryStore | None = None) -> None:
    """Replace the global store — used by tests for isolation."""
    global _memory_store
    _memory_store = store
