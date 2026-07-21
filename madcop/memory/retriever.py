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
    "ModularRetriever",
    "ModularRetrievalResult",
]


# --------------------------------------------------------------------------- #
# ModularRetriever — the real RAG layer
# --------------------------------------------------------------------------- #
# Above the raw FTS5 Retriever we wrap a four-step pipeline that mirrors
# the "modular RAG" pattern (query analysis → retrieval → re-ranking →
# generation) without copying any code from opencode / DSPy / LangGraph:
#
#   1. Query rewrite     — keyword extraction so FTS5 doesn't return
#                          nothing for natural-language queries.
#   2. Local retrieval  — fan out across L2 / L3 / L4.
#   3. Confidence gate  — if the top score is below threshold AND the
#                          app provides a web_fallback callable, dispatch
#                          a web search; otherwise hand back what we have.
#   4. Formatting       — render the merged list as a prompt block
#                          grouped by layer, with provenance.

from dataclasses import dataclass, field as _field
from typing import Callable, Iterable

from .query_rewriter import expand as _expand_query


# A web_fallback signature: takes the original query, returns a list
# of `(title, snippet, url)` triples. The retriever doesn't care how
# the function gets the result — it just decides whether to call it.
WebFallback = Callable[[str], list[tuple[str, str, str]]]


@dataclass
class ModularConfig:
    """Per-call configuration for the modular pipeline."""

    episodic_limit: int = 5
    semantic_limit: int = 10
    reflective_limit: int = 5
    weight_episodic: float = 0.40
    weight_semantic: float = 0.45
    weight_reflective: float = 0.15
    half_life_days: float = 30.0
    # If the top retrieval score is below this AND a web_fallback
    # is provided, dispatch a web search. The threshold is on a
    # 0..1 score scale (we use 1 - exp(-count) so any hit counts).
    confidence_threshold: float = 0.15
    # If True and a web_fallback is provided, also call it as a
    # complement to local memory (not just as a fallback). Useful
    # for fresh-time-sensitive questions.
    always_search_web: bool = False
    web_limit: int = 4
    rewrite_query: bool = True
    call_llm: Callable[[str], str] | None = None


@dataclass
class ModularRetrievalResult:
    """The packaged output of a single modular retrieve call."""

    items: list  # list of (layer, score, text) triples sorted by score
    query_used: str          # the actual keyword query that hit
    rewrites: list          # the keyword variants the rewriter tried
    rewrote: bool           # whether the original query was rewritten
    web_hits: list = _field(default_factory=list)  # (title, snippet, url)
    confidence: float = 0.0  # 0..1, top score across all sources


class ModularRetriever:
    """The four-step pipeline wrapper around the raw FTS5 Retriever.

    The "modular" name comes from the standard modular-RAG layout
    (query analysis → retrieval → re-ranking → generation). The
    generation step happens outside the retriever (the chat handler
    consumes our output). Re-ranking is folded into the Retriever's
    existing per-layer weighted score.
    """

    def __init__(
        self,
        retriever: Retriever,
        web_fallback: WebFallback | None = None,
    ) -> None:
        self._retriever = retriever
        self._web_fallback = web_fallback

    def retrieve(
        self,
        query: str,
        config: ModularConfig | None = None,
    ) -> ModularRetrievalResult:
        if config is None:
            config = ModularConfig()

        # 1. Query rewrite (cheap; if LLM call is given, optionally
        # delegate to it via the rewriter's LLM-hook). The original
        # query is always included as the last fallback — the rewriter
        # may strip a word that's actually the key noun (e.g. "Shanghai"
        # in "where does the user live").
        if config.rewrite_query:
            variants = _expand_query(query, config.call_llm)
        else:
            variants = [query]
        if not variants or variants[-1] != query:
            variants = list(variants) + [query]

        # 1a. Sanitize: FTS5's MATCH grammar treats `?`, `(`, `)`, `:`,
        # `"`, `*`, `+`, `-`, `^` as syntax. Strip anything that isn't
        # a letter / digit / CJK / whitespace before passing to FTS5.
        import re as _re_sanitize
        _SANITIZE = _re_sanitize.compile(r"[^\w\s\u4e00-\u9fff]+", _re_sanitize.UNICODE)

        def _sanitize(v: str) -> str:
            return _SANITIZE.sub(" ", v).strip()

        # 1b. FTS5 prefix matching: the memory_fts table is created
        # without an explicit `prefix=` option, so unprefixed tokens
        # only match exact spellings. To catch "Shanghai" when the
        # user asks about "shanghai weather" we also search a
        # per-token-prefix OR'd query — FTS5's default AND would miss
        # terms that aren't present in the data.
        def _prefix_tokens_or(v: str) -> str:
            tokens = [t for t in v.split() if t]
            return " OR ".join(t + "*" for t in tokens)

        sanitized = [_sanitize(v) for v in variants]
        sanitized = [v for v in sanitized if v]
        prefix_variants = [_prefix_tokens_or(v) for v in sanitized]
        variants = sanitized + prefix_variants

        # 2. Local retrieval — fan out across layers; merge.
        results: list = []
        per_layer_text: dict[str, list[str]] = {}
        per_layer_score: dict[str, list[float]] = {}
        for v in variants:
            r = self._retriever.retrieve(
                v,
                RetrievalConfig(
                    episodic_limit=config.episodic_limit,
                    semantic_limit=config.semantic_limit,
                    reflective_limit=config.reflective_limit,
                    weight_episodic=config.weight_episodic,
                    weight_semantic=config.weight_semantic,
                    weight_reflective=config.weight_reflective,
                    half_life_days=config.half_life_days,
                ),
            )
            for item in r:
                # Each RetrievalResult is (item, layer, score, source_kind)
                # per the existing dataclass. We keep the score.
                layer = item.layer
                score = item.score
                text = self._format_hit(item)
                if not text:
                    continue
                results.append((layer, score, text))
                per_layer_text.setdefault(layer, []).append(text)
                per_layer_score.setdefault(layer, []).append(score)

        # 3. Confidence gate — web fallback if top score is low.
        confidence = max((s for _, s, _ in results), default=0.0)
        web_hits: list = []
        should_web = (
            self._web_fallback is not None
            and (config.always_search_web or confidence < config.confidence_threshold)
        )
        if should_web:
            try:
                web_hits = self._web_fallback(query)[: config.web_limit]
            except Exception:
                web_hits = []

        # 4. Format — local + web in a prompt-block-friendly shape.
        items = sorted(results, key=lambda x: x[1], reverse=True)
        return ModularRetrievalResult(
            items=items,
            query_used=variants[0] if variants else query,
            rewrites=variants,
            rewrote=len(variants) > 1 or (variants and variants[0] != query),
            web_hits=web_hits,
            confidence=confidence,
        )

    def format_prompt_block(self, result: ModularRetrievalResult) -> str:
        """Render the retrieval result as the prompt block injected
        into the chat handler. Grouped by layer for readability.
        """
        if not result.items and not result.web_hits:
            return ""
        lines: list[str] = ["## Memory context"]
        per_layer: dict[str, list[str]] = {}
        for layer, score, text in result.items:
            per_layer.setdefault(layer, []).append(text)
        for layer, texts in per_layer.items():
            for i, t in enumerate(texts, 1):
                lines.append(f"### {layer} #{i}\n{t}")
        if result.web_hits:
            lines.append("### Web")
            for i, (title, snippet, url) in enumerate(result.web_hits, 1):
                lines.append(f"{i}. **{title}** — {snippet}\n   {url}")
        return "\n\n".join(lines)

    @staticmethod
    def _format_hit(item) -> str:
        """Best-effort extract of a hit's text content regardless of
        which memory tier it came from. The layer-specific classes
        expose different attributes (Episode has goal/outcome,
        Fact has subject/predicate/object, Reflection has kind/content);
        we normalise to a short readable paragraph.
        """
        ep = item.item
        # Episode
        if hasattr(ep, "goal") and hasattr(ep, "outcome") and hasattr(ep, "findings"):
            findings = ep.findings or ""
            if isinstance(findings, (list, dict)):
                findings = str(findings)[:200]
            return f"任务: {ep.goal}\n结果: {ep.outcome}\n关键: {findings}"
        # Fact
        if hasattr(ep, "subject") and hasattr(ep, "predicate") and hasattr(ep, "object"):
            return f"{ep.subject} {ep.predicate} {ep.object}"
        # Reflection
        if hasattr(ep, "kind") and hasattr(ep, "content"):
            return f"({ep.kind}) {ep.content}"
        # Generic fallback
        return getattr(ep, "content", None) or getattr(ep, "text", None) or str(ep)[:200]


# --------------------------------------------------------------------------- #
# Compatibility: the function name `format_for_prompt` keeps the old
# interface that plan_execute.py uses, but the formatting now uses the
# modular pipeline.
# --------------------------------------------------------------------------- #

def format_for_prompt(
    retriever: Retriever,
    query: str,
    config: RetrievalConfig | None = None,
    max_lines: int = 24,
) -> str:
    """Backward-compatible helper used by the planner.

    Returns a single string that can be appended to the system
    prompt. The line cap is a defensive limit; the retriever's own
    `episodic_limit` / `semantic_limit` / `reflective_limit` already
    keep the output bounded.
    """
    if config is None:
        config = RetrievalConfig()
    results = retriever.retrieve(query, config)
    if not results:
        return ""
    lines: list[str] = [f"## Memory context (top {min(len(results), max_lines)} hits)"]
    for i, r in enumerate(results[:max_lines], 1):
        ep = r.item
        # Same text extraction as ModularRetriever
        text = ModularRetriever._format_hit(r)
        lines.append(f"{i}. [{r.layer} score={r.score:.2f}] {text}")
    return "\n".join(lines)
