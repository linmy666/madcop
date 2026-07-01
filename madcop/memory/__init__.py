"""v2.6.0 memory layer — 5-tier growing memory.

Public surface for the memory layer:

    from madcop.memory import (
        MemoryStore,         # unified SQLite + FTS5 backend
        EpisodicMemory,      # L0: raw task history
        SemanticMemory,      # L1: distilled facts
        ScenarioMemory,      # L2: mid-tier themed scenarios
        PersonaMemory,       # L3: long-form user persona
        InsightMemory,       # L4: cross-session meta-patterns
        Retriever,           # cross-layer query
        GrowthEngine,        # the "成长" engine
    )

Layer model (mirrors TencentDB Agent Memory's 4-tier pyramid, extended
to 5 tiers with an explicit cross-pattern insight layer):

    L0  Episodic   — every task we've done
    L1  Semantic   — distilled facts / concepts / relations
    L2  Scenario   — per-session themed aggregations
    L3  Persona    — long-term user profile (persona.md)
    L4  Insight    — cross-session meta-patterns (insights.md)

Sub-modules:
- store.py:        SQLite + FTS5 backend
- episodic.py:     L0 — task history
- semantic.py:     L1 — distilled knowledge
- scenario.py:     L2 — themed scenario blocks
- persona.py:      L3 — user persona
- insight.py:      L4 — cross-session meta-patterns
- retriever.py:    cross-layer keyword search via FTS5
- growth.py:       3 mechanisms (episodic→semantic, feedback, meta mining)
"""
from __future__ import annotations

from .store import MemoryStore, MemoryRecord, MemoryKind
from .episodic import EpisodicMemory, Episode, EpisodeOutcome
from .semantic import SemanticMemory, Fact, FactKind
from .reflective import ReflectiveMemory, Reflection, ReflectionKind
from .scenario import ScenarioMemory, Scenario
from .persona import PersonaMemory, PersonaTrait
from .insight import InsightMemory, Insight
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
    "ScenarioMemory", "Scenario",
    "PersonaMemory", "PersonaTrait",
    "InsightMemory", "Insight",
    "Retriever", "RetrievalResult",
    "GrowthEngine", "GrowthConfig",
    "CompactionConfig", "compact_messages",
    "ConversationBuffer",
]
