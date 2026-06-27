"""v0.6.0 memory layer — 4-layer growing memory.

Public surface for the memory layer:

    from madcop.memory import (
        MemoryStore,         # unified SQLite + FTS5 backend
        EpisodicMemory,      # L2: task history
        SemanticMemory,      # L3: distilled knowledge
        ReflectiveMemory,    # L4: feedback & meta
        Retriever,           # cross-layer query
        GrowthEngine,        # the "成长" engine
    )

Sub-modules:
- store.py:        SQLite + FTS5 backend (one row = one memory record)
- episodic.py:     L2 — task-level history
- semantic.py:     L3 — distilled knowledge (facts / concepts / relations)
- reflective.py:   L4 — feedback & meta (user prefs + meta-strategies)
- retriever.py:    cross-layer keyword search via FTS5
- growth.py:       3 mechanisms (episodic→semantic, feedback, meta mining)
"""
from __future__ import annotations

from .store import MemoryStore, MemoryRecord, MemoryKind
from .episodic import EpisodicMemory, Episode, EpisodeOutcome
from .semantic import SemanticMemory, Fact, FactKind
from .reflective import ReflectiveMemory, Reflection, ReflectionKind
from .retriever import Retriever, RetrievalResult
from .growth import GrowthEngine, GrowthConfig
from .compactor import CompactionConfig, compact_messages
# v0.5.0 legacy: keep L1 in-memory ConversationBuffer exportable
from .buffer import ConversationBuffer  # noqa: F401  (backward compat)

__all__ = [
    "MemoryStore", "MemoryRecord", "MemoryKind",
    "EpisodicMemory", "Episode", "EpisodeOutcome",
    "SemanticMemory", "Fact", "FactKind",
    "ReflectiveMemory", "Reflection", "ReflectionKind",
    "Retriever", "RetrievalResult",
    "GrowthEngine", "GrowthConfig",
    "CompactionConfig", "compact_messages",
    "ConversationBuffer",
]
