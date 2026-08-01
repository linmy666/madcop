"""Sprint 2 — 5-layer memory retriever with hybrid search."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .reflective import ReflectiveMemory
from .persona import PersonaMemory
from .insight import InsightMemory
from .scenario import ScenarioMemory

from .hybrid import hybrid_search
from .store import MemoryStore


LAYER_WEIGHTS = {
    "L0_episodic": 0.25,
    "L1_semantic": 0.30,
    "L2_scenario": 0.15,
    "L3_persona": 0.10,
    "L4_reflective": 0.10,
    "L4b_insight": 0.10,
}


@dataclass
class RecallResult:
    item: object
    layer: str
    score: float


class FiveLayerRetriever:
    """5-layer hybrid retriever (Episodic/Semantic/Reflective/Persona/Scenario/Insight)."""

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        episodic: Optional[EpisodicMemory] = None,
        semantic: Optional[SemanticMemory] = None,
        reflective: Optional[ReflectiveMemory] = None,
        persona: Optional[PersonaMemory] = None,
        insight: Optional[InsightMemory] = None,
        scenario: Optional[ScenarioMemory] = None,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self._episodic = episodic
        self._semantic = semantic
        self._reflective = reflective
        self._persona = persona
        self._insight = insight
        self._scenario = scenario
        self._now = now_fn

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        half_life_days: float = 30.0,
        hybrid_fn = None,
    ) -> list[RecallResult]:
        if not query.strip():
            return []
        # Allow tests to inject a custom hybrid fn (avoids module-global
        # monkey-patching in unit tests).
        if hybrid_fn is None:
            hybrid_fn = hybrid_search
        candidates = hybrid_fn(self.store, query, top_k * 3)
        now = self._now()
        scored: list[RecallResult] = []
        for c in candidates:
            kind = c.get("kind", "")
            layer_id = {
                "episodic": "L0_episodic",
                "semantic": "L1_semantic",
                "reflective": "L4_reflective",
            }.get(kind, "L1_semantic")
            base_weight = LAYER_WEIGHTS.get(layer_id, 0.10)
            age_days = max(0.0, (now - c.get("updated_at", now)) / 86400.0)
            decay = 0.5 ** (age_days / half_life_days) if half_life_days > 0 else 1.0
            score = c.get("_score", 0.0) * base_weight * decay
            tags = set(c.get("tags", []) or [])
            if "scenario" in tags:
                layer_id = "L2_scenario"
                score = c.get("_score", 0.0) * LAYER_WEIGHTS["L2_scenario"] * decay
            elif "persona" in tags:
                layer_id = "L3_persona"
                score = c.get("_score", 0.0) * LAYER_WEIGHTS["L3_persona"] * decay
            elif "insight" in tags or "pattern" in tags:
                layer_id = "L4b_insight"
                score = c.get("_score", 0.0) * LAYER_WEIGHTS["L4b_insight"] * decay
            scored.append(RecallResult(item=c, layer=layer_id, score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
