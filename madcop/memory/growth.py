"""The "growth" engine — 3 mechanisms that make madcop grow with use.

M1. Episodic → Semantic distillation
    After every task: turn the L2 episode into 3-5 reusable L3 facts
    (via a single LLM call). Capped to a small number to avoid noise.

M2. Reflective feedback loop
    After every user rating: turn the rating + comment into L4 reflection
    (via a single LLM call). One reflection per rating event.

M3. Self-improvement meta-pattern mining
    After every N (default 5) episodes: ask the LLM to find patterns
    across them. The LLM extracts 0-3 META_STRATEGY reflections.

This module is pure orchestration — it calls the LLM via the supplied
ChatClient and writes into the three memory layers. The actual
distillation prompt lives in `madcop/llm/prompts.py` (v0.5.0 module,
extended in v0.6.0).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Sequence

from .episodic import EpisodicMemory, Episode, EpisodeOutcome
from .semantic import SemanticMemory, Fact, FactKind
from .reflective import ReflectiveMemory, Reflection, ReflectionKind

# Imported lazily to avoid a circular import (madcop.llm imports madcop.memory
# in some user code; if we import it eagerly here we get a cycle).
def _import_llm():
    from ..llm import ChatClient, Message
    return ChatClient, Message


@dataclass
class GrowthConfig:
    """Tuning knobs for the growth engine."""

    # M1: distillation
    distillation_min_facts: int = 1   # minimum facts to extract per episode
    distillation_max_facts: int = 5   # hard cap

    # M3: meta-pattern mining
    meta_min_episodes: int = 5         # don't run until we have N episodes
    meta_max_patterns: int = 3         # cap per mining run

    # General
    enabled: bool = True


class GrowthEngine:
    """Orchestrates the 3 growth mechanisms.

    Used by the agent loop (plan_execute.py). The engine is stateless
    except for the LLM client + memory handles it holds.
    """

    def __init__(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        reflective: ReflectiveMemory,
        llm,                               # ChatClient from madcop.llm
        config: GrowthConfig | None = None,
    ) -> None:
        self._episodic = episodic
        self._semantic = semantic
        self._reflective = reflective
        self._llm = llm
        self._config = config or GrowthConfig()

    @property
    def config(self) -> GrowthConfig:
        return self._config

    # ---- Mechanism 1: episodic → semantic ----------------------------------

    def distill_episode(self, episode: Episode) -> list[Fact]:
        """M1: turn one episode into 0-N facts. Returns the facts written.

        The LLM is asked to extract reusable knowledge from the episode.
        Output is parsed as JSON; if parsing fails, we log and return [].
        """
        if not self._config.enabled:
            return []

        # Build the prompt
        prompt = self._distillation_prompt(episode)

        # Call LLM (T1 by default — distillation is reasoning)
        try:
            response = self._llm.chat([
                {"role": "system", "content": _DISTILL_SYSTEM},
                {"role": "user", "content": prompt},
            ])
            content = response.content if hasattr(response, "content") else str(response)
        except Exception:
            return []

        # Parse JSON list of facts
        facts_data = self._parse_json_list(content)
        if not facts_data:
            return []

        # Cap and write
        written: list[Fact] = []
        for fd in facts_data[: self._config.distillation_max_facts]:
            try:
                subject = str(fd.get("subject", "")).strip()
                predicate = str(fd.get("predicate", "")).strip()
                object_ = str(fd.get("object", "")).strip()
                if not (subject and predicate and object_):
                    continue
                kind = FactKind(fd.get("kind", "fact"))
                confidence = float(fd.get("confidence", 0.7))
                confidence = max(0.0, min(1.0, confidence))
                tags = tuple(fd.get("tags", []))
                fact = self._semantic.add(
                    subject=subject,
                    predicate=predicate,
                    object=object_,
                    kind=kind,
                    source_episode=episode.id,
                    confidence=confidence,
                    tags=tags,
                )
                written.append(fact)
            except Exception:
                # Skip malformed fact but keep going
                continue

        # Pad the count to ensure we hit min_facts
        if len(written) < self._config.distillation_min_facts:
            # Refuse to invent facts if LLM didn't return enough; ok.
            pass

        return written

    # ---- Mechanism 2: reflective feedback ---------------------------------

    def record_feedback(
        self,
        episode: Episode,
        rating: int,
        comment: str = "",
    ) -> Reflection | None:
        """M2: turn a user rating (1-5) into a reflection."""
        if not self._config.enabled:
            return None
        if not (1 <= rating <= 5):
            raise ValueError(f"rating must be 1-5, got {rating}")

        # Build the prompt
        prompt = self._feedback_prompt(episode, rating, comment)

        # Call LLM
        try:
            response = self._llm.chat([
                {"role": "system", "content": _FEEDBACK_SYSTEM},
                {"role": "user", "content": prompt},
            ])
            content = response.content if hasattr(response, "content") else str(response)
        except Exception:
            return None

        # Parse JSON reflection
        ref_data = self._parse_json_object(content)
        if not ref_data:
            return None

        text = str(ref_data.get("text", "")).strip()
        if not text:
            return None
        kind_str = str(ref_data.get("kind", "lesson_learned"))
        try:
            kind = ReflectionKind(kind_str)
        except ValueError:
            kind = ReflectionKind.LESSON_LEARNED
        confidence = float(ref_data.get("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))
        tags = tuple(ref_data.get("tags", []))

        return self._reflective.add(
            text=text,
            kind=kind,
            source_episode=episode.id,
            source_rating=rating,
            confidence=confidence,
            tags=tags,
        )

    # ---- Mechanism 3: meta-pattern mining ---------------------------------

    def mine_meta_patterns(
        self,
        episodes: Sequence[Episode] | None = None,
    ) -> list[Reflection]:
        """M3: ask the LLM to find patterns across recent episodes.

        Returns 0-3 META_STRATEGY reflections.
        """
        if not self._config.enabled:
            return []

        if episodes is None:
            episodes = self._episodic.list_recent(limit=self._config.meta_min_episodes + 5)

        if len(episodes) < self._config.meta_min_episodes:
            return []  # not enough data

        prompt = self._meta_prompt(episodes)

        try:
            response = self._llm.chat([
                {"role": "system", "content": _META_SYSTEM},
                {"role": "user", "content": prompt},
            ])
            content = response.content if hasattr(response, "content") else str(response)
        except Exception:
            return []

        patterns = self._parse_json_list(content)
        if not patterns:
            return []

        written: list[Reflection] = []
        for p in patterns[: self._config.meta_max_patterns]:
            text = str(p.get("text", "")).strip()
            if not text:
                continue
            confidence = float(p.get("confidence", 0.7))
            confidence = max(0.0, min(1.0, confidence))
            tags = tuple(p.get("tags", []))
            try:
                ref = self._reflective.add(
                    text=text,
                    kind=ReflectionKind.META_STRATEGY,
                    source_episode=None,
                    source_rating=None,
                    confidence=confidence,
                    tags=tags,
                )
                written.append(ref)
            except Exception:
                continue
        return written

    # ---- internal helpers -------------------------------------------------

    def _distillation_prompt(self, episode: Episode) -> str:
        findings_text = json.dumps(episode.findings, ensure_ascii=False)[:1000]
        return (
            f"Episode completed.\n"
            f"Goal: {episode.goal}\n"
            f"Outcome: {episode.outcome.value}\n"
            f"Steps: {episode.steps_taken}\n"
            f"Findings: {findings_text}\n"
            f"Final report (truncated): {(episode.final_report or '')[:500]}\n\n"
            f"Extract 1-5 reusable facts as a JSON array. Each fact = "
            f'{{"subject": "...", "predicate": "...", "object": "...", '
            f'"kind": "fact|concept|relation|pattern", "confidence": 0.0-1.0, '
            f'"tags": ["..."]}}. Output ONLY the JSON array.'
        )

    def _feedback_prompt(self, episode: Episode, rating: int, comment: str) -> str:
        return (
            f"User rated this episode {rating}/5.\n"
            f"Comment: {comment or '(no comment)'}\n"
            f"Goal: {episode.goal}\n"
            f"Outcome: {episode.outcome.value}\n"
            f"Steps: {episode.steps_taken}\n\n"
            f"Extract a single reflection as JSON: "
            f'{{"text": "...", "kind": "user_preference|user_dislike|'
            f'meta_strategy|lesson_learned|working_note", "confidence": 0.0-1.0, '
            f'"tags": ["..."]}}. Output ONLY the JSON object.'
        )

    def _meta_prompt(self, episodes: Sequence[Episode]) -> str:
        lines = []
        for i, ep in enumerate(episodes[:20]):
            lines.append(
                f"#{i+1}: goal='{ep.goal[:80]}' outcome={ep.outcome.value} "
                f"steps={ep.steps_taken} cost=${ep.total_cost_usd:.4f}"
            )
        ep_text = "\n".join(lines)
        return (
            f"Analyse these {len(episodes)} recent agent runs and extract "
            f"0-3 meta-strategies (rules that would have made these runs "
            f"better/faster/cheaper).\n\n"
            f"{ep_text}\n\n"
            f'Output a JSON array of {{"text": "...", "confidence": 0.0-1.0, '
            f'"tags": ["..."]}}. Each text should be a concrete rule like '
            f'"if task keyword is X, use tool Y first". Output ONLY the JSON array.'
        )

    @staticmethod
    def _parse_json_list(text: str) -> list:
        """Best-effort extract a JSON array from LLM output."""
        text = text.strip()
        if not text:
            return []
        # Find the first '[' and last ']'
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _parse_json_object(text: str) -> dict | None:
        text = text.strip()
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


# Prompts for the LLM. Kept here (not in madcop.llm.prompts) to keep the
# memory module self-contained. v0.7.0 can move these if the LLM module
# gets too big.
_DISTILL_SYSTEM = (
    "You are a knowledge extraction engine. You turn agent task history "
    "into reusable, atomic facts. Each fact must be:\n"
    "  - atomic (one piece of knowledge, not a paragraph)\n"
    "  - reusable (would be useful for a future, similar task)\n"
    "  - falsifiable (could be wrong, could be verified)\n"
    "Output JSON only. No commentary."
)

_FEEDBACK_SYSTEM = (
    "You extract lessons from user feedback. The user just rated an agent "
    "run 1-5 stars. Distil one concrete lesson — either a user preference, "
    "a dislike, a working note, or a meta-strategy. Be specific. "
    "Output JSON only."
)

_META_SYSTEM = (
    "You mine patterns from past agent runs. Look for:\n"
    "  - tasks that always succeed vs always fail (and why)\n"
    "  - common wasted steps\n"
    "  - tool-use patterns that consistently help\n"
    "Each meta-strategy should be a concrete 'if X, then Y' rule. "
    "Output JSON only."
)


__all__ = [
    "GrowthEngine",
    "GrowthConfig",
]
