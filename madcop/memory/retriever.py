"""Cross-layer retriever.

Single entry point for "given a query, return relevant memories from any
or all layers". Used by the planner (plan_execute.py) to inject context.

Why one unified retriever instead of calling each layer separately:
  - Centralised FTS5 query syntax (escaping, ranking, limits)
  - Cross-layer result merging with per-layer weights
  - Time-decay scoring (newer memories score higher)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .episodic import EpisodicMemory, Episode
from .semantic import SemanticMemory, Fact
from .reflective import ReflectiveMemory, Reflection


@dataclass
class RetrievalResult:
    """A single memory hit with relevance score."""

    item: object       # Episode | Fact | Reflection
    layer: str         # "L2" / "L3" / "L4"
    score: float       # 0.0 - 1.0
    source_kind: str   # "episodic" / "semantic" / "reflective"


@dataclass
class RetrievalConfig:
    """How the retriever weights and limits hits."""

    episodic_limit: int = 5
    semantic_limit: int = 10
    reflective_limit: int = 5
    # Score weights — sum should be ~1.0 for predictable behaviour
    weight_episodic: float = 0.40      # recent experience is highly relevant
    weight_semantic: float = 0.45      # distilled knowledge is most useful
    weight_reflective: float = 0.15    # preferences + meta-strategies
    # Time decay half-life in days. 0 = no decay.
    half_life_days: float = 30.0


class Retriever:
    """Unified cross-layer query interface.

    The planner calls `retrieve(query, config)` once at the start of each
    step; the returned items are injected into the prompt.
    """

    def __init__(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        reflective: ReflectiveMemory,
        now_fn=time.time,
    ) -> None:
        self._episodic = episodic
        self._semantic = semantic
        self._reflective = reflective
        self._now = now_fn

    def retrieve(
        self,
        query: str,
        config: RetrievalConfig | None = None,
    ) -> list[RetrievalResult]:
        """Query all three layers, score with time-decay, merge, return sorted."""
        if config is None:
            config = RetrievalConfig()

        results: list[RetrievalResult] = []

        # L2: episodic
        try:
            episodes = self._episodic.find_similar(query, limit=config.episodic_limit)
        except Exception:
            episodes = []
        for ep in episodes:
            score = self._decay_score(ep.created_at, config.half_life_days)
            results.append(RetrievalResult(
                item=ep, layer="L2", score=score * config.weight_episodic,
                source_kind="episodic",
            ))

        # L3: semantic
        facts = self._semantic.search(query, limit=config.semantic_limit)
        for f in facts:
            score = self._decay_score(f.created_at, config.half_life_days)
            # Facts with explicit confidence are weighted higher
            score *= f.confidence
            results.append(RetrievalResult(
                item=f, layer="L3", score=score * config.weight_semantic,
                source_kind="semantic",
            ))

        # L4: reflective
        reflections = self._reflective.search(query, limit=config.reflective_limit)
        for r in reflections:
            score = self._decay_score(r.created_at, config.half_life_days)
            score *= r.confidence
            results.append(RetrievalResult(
                item=r, layer="L4", score=score * config.weight_reflective,
                source_kind="reflective",
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _decay_score(self, created_at: float, half_life_days: float) -> float:
        """Exponential decay: 1.0 at t=0, 0.5 at t=half_life_days."""
        if half_life_days <= 0:
            return 1.0
        age_seconds = max(0.0, self._now() - created_at)
        age_days = age_seconds / 86_400
        # 0.5 ^ (age / half_life)
        return 0.5 ** (age_days / half_life_days)

    def format_for_prompt(self, results: list[RetrievalResult]) -> str:
        """Render the top-N results as a context block for the LLM prompt."""
        if not results:
            return ""
        lines = ["# Memory context (relevant past experience)\n"]
        for r in results:
            layer = r.layer
            item = r.item
            if layer == "L2" and isinstance(item, Episode):
                lines.append(
                    f"- [L2 episode, score={r.score:.2f}] "
                    f"goal='{item.goal}' outcome={item.outcome.value} "
                    f"steps={item.steps_taken} cost=${item.total_cost_usd:.4f}"
                )
            elif layer == "L3" and isinstance(item, Fact):
                lines.append(
                    f"- [L3 fact, score={r.score:.2f}] "
                    f"{item.subject} {item.predicate} {item.object} "
                    f"(confidence={item.confidence:.2f})"
                )
            elif layer == "L4" and isinstance(item, Reflection):
                lines.append(
                    f"- [L4 reflection, score={r.score:.2f}, kind={item.kind.value}] "
                    f"{item.text}"
                )
        return "\n".join(lines)


__all__ = [
    "Retriever",
    "RetrievalResult",
    "RetrievalConfig",
]
