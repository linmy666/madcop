"""Modular query router — picks the right retrieval strategy per query.

This is the second of the four modules in the modular RAG pattern
(query_analysis → retrieval → re-ranking → generation). It is NOT a
copy of opencode (which has no router at all — it makes the LLM
read a tool catalog and pick). Instead it is a 3-tier hybrid:

  1. Regex / keyword rules    — handles the 80% of queries that have
                                 obvious intent signals ("查询" → retrieval,
                                 "分析" → planning, "写" → generation, etc.)
                                 This is the same shape MadCop already
                                 has in task_router.py; we just make it
                                 the FIRST of three fall-throughs.
  2. Embedding cosine          — for queries with no keyword match,
                                 embed the query and the description of
                                 each candidate module and pick the
                                 nearest. The current MadCop has no
                                 embedding server, so this tier is a
                                 graceful no-op until one is wired.
  3. LLM router (structured)  — when the first two tiers are both
                                 inconclusive, ask the model to pick a
                                 module from a JSON schema. This is the
                                 opencode "describe tools as text and let
                                 the model pick" pattern, but with a
                                 constrained output schema so we can
                                 parse it deterministically.

The router outputs a typed `RouteDecision` (which module to run),
plus a confidence score and a "rewritten query" so downstream
modules can act on it.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# --------------------------------------------------------------------------- #
# Routing vocabulary — what modules the router can pick
# --------------------------------------------------------------------------- #
#
# We keep this small on purpose. Each entry has:
#   - key: short identifier used in RouteDecision.target
#   - description: short string injected into the LLM router prompt
#                 so the model knows what each module does
#   - signals: list of (regex, score) tuples for tier 1
#
# Adding a new module is one entry; no other code changes needed.
@dataclass(frozen=True)
class RouteTarget:
    key: str
    description: str
    signals: list[tuple[str, float]] = field(default_factory=list)


ROUTE_REGISTRY: list[RouteTarget] = [
    RouteTarget(
        key="memory_retrieval",
        description=(
            "Answer a factual question by searching the user's memory: "
            "past conversations, saved knowledge, preferences, and "
            "scenarios. Use when the user asks about something they "
            "previously did or said."
        ),
        signals=[
            (r"(?i)\b(?:what|when|where|who|which|recall|remember|previous|earlier|last\s+time)\b", 0.6),
            (r"(回忆|之前|上次|以前|记得|记不记得)", 0.6),
            (r"what\s+did\s+(?:i|we)\s+(?:do|say|tell|mention)", 0.7),
        ],
    ),
    RouteTarget(
        key="modular_rag",
        description=(
            "Run the full RAG pipeline: query rewriting, multi-source "
            "retrieval (episodic + semantic + reflective + web), and "
            "prompt-block rendering. Use when the user asks a question "
            "that benefits from combining multiple memory layers with "
            "external knowledge."
        ),
        signals=[
            (r"(?i)\b(?:search|find|look\s+up|investigate|explore|research|analyze|compare)\b", 0.5),
            (r"(?i)\b(?:why|how\s+does|how\s+can|how\s+should)\b", 0.3),
            (r"(怎么|为什么|如何|分析|对比|查一查|搜一搜|找一下)", 0.6),
            (r"\b(?:what's|whats)\s+the\s+(?:best|difference|relation|connection)\b", 0.6),
        ],
    ),
    RouteTarget(
        key="task_execution",
        description=(
            "Execute a concrete task that requires running tools: file "
            "writes, shell, web fetch, MCP calls. Use when the user "
            "asks the agent to do something — code, scripts, downloads, "
            "configuration changes."
        ),
        signals=[
            (r"(?i)\b(?:write|create|make|build|edit|update|delete|run|execute|test|deploy|fix|refactor)\b", 0.4),
            (r"(?i)\b(?:please\s+)?(?:add|change|remove|move|rename)\b", 0.3),
            (r"(写|创建|改|删|删除|运行|执行|跑|测试|部署|重构|修复)", 0.7),
            (r"帮我|请帮我|帮我写|帮我做", 0.6),
        ],
    ),
    RouteTarget(
        key="planning",
        description=(
            "Multi-step plan and analysis: planning, strategy, comparison, "
            "trade-offs, multi-turn conversation. Use when the user asks "
            "an open-ended question that benefits from structured reasoning."
        ),
        signals=[
            (r"(?i)\b(?:plan|strategy|compare|trade-?off|decide|should\s+i|recommend|suggest|advice|opinion)\b", 0.4),
            (r"(\?|？|怎么选|建议|推荐|方案|对比|策略|权衡|怎么决定)", 0.5),
        ],
    ),
    RouteTarget(
        key="casual",
        description=(
            "Smalltalk, greetings, or short conversational exchanges that "
            "do not need any of the above modules. Use when the user's "
            "intent is unclear and the message is short."
        ),
        signals=[
            (r"^(?:hi|hello|hey|thanks|thank\s+you|ok|okay|got\s+it|by[e])\b", 0.9),
            (r"^(?:嗨|你好|谢|好|ok|好的|再见)\b", 0.9),
        ],
    ),
]


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
@dataclass
class RouteDecision:
    """The router's single output. Carries the target module plus
    metadata so the caller can decide whether to trust the result
    or escalate to a different module.
    """
    target: str           # one of RouteTarget.key
    confidence: float      # 0.0..1.0; tier 1 / tier 2 max-scored
    tier: int              # 1, 2, or 3 — which stage picked
    rewrites: list[str]   # the keyword variants the rewriter tried
    all_scores: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Tier 1: regex
# --------------------------------------------------------------------------- #
def _regex_score(query: str) -> dict[str, float]:
    """Return the per-target best regex score (0..1). Stops at the
    first match per (regex, target) pair, so a query with multiple
    matches of the same regex doesn't double-count.
    """
    out: dict[str, float] = {}
    for target in ROUTE_REGISTRY:
        best = 0.0
        for pat, weight in target.signals:
            if re.search(pat, query):
                if weight > best:
                    best = weight
        if best > 0:
            out[target.key] = best
    return out


# --------------------------------------------------------------------------- #
# Tier 2: embedding cosine
# --------------------------------------------------------------------------- #
def _embedding_score(query: str, embed_fn) -> dict[str, float] | None:
    """Optional: if the caller provides an embed_fn, run tier 2.
    Returns None if no embed_fn is available.
    """
    if embed_fn is None:
        return None
    try:
        qv = embed_fn(query)
    except Exception:
        return None
    if qv is None:
        return None
    out: dict[str, float] = {}
    for target in ROUTE_REGISTRY:
        try:
            tv = embed_fn(target.description)
        except Exception:
            continue
        if tv is None:
            continue
        # Cosine similarity; both sides assumed non-empty vectors.
        qn = sum(x * x for x in qv) ** 0.5 or 1.0
        tn = sum(x * x for x in tv) ** 0.5 or 1.0
        dot = sum(a * b for a, b in zip(qv, tv))
        sim = dot / (qn * tn)
        out[target.key] = max(0.0, min(1.0, sim))
    return out


# --------------------------------------------------------------------------- #
# Tier 3: LLM router
# --------------------------------------------------------------------------- #
# The LLM is asked to pick exactly one of the route keys, given the
# catalog. The output is parsed leniently: a plain JSON object with
# a `target` field is enough. We don't force tool-calling here because
# we want this layer to work on any chat model, not just function-calling
# ones. If the model declines, tier 3 is skipped.
LlmRouterFn = Callable[[str], str]


_LLM_ROUTER_PROMPT = """\
You are the routing layer for an AI assistant. Pick exactly one of
the listed modules for the user's last message. Reply with a single
JSON object: {{"target": "<key>", "reason": "<one short sentence>"}}.
No other prose.

Modules:
{catalog}

User message:
\"\"\"{query}\"\"\"
"""


def _llm_route(query: str, call_llm: LlmRouterFn) -> dict[str, float] | None:
    """Optional tier 3. If the LLM declines or returns garbage, return
    None so the caller can fall through to its own default.
    """
    if call_llm is None:
        return None
    catalog = "\n".join(f"- {t.key}: {t.description}" for t in ROUTE_REGISTRY)
    prompt = _LLM_ROUTER_PROMPT.format(catalog=catalog, query=query)
    try:
        raw = call_llm(prompt) or ""
    except Exception:
        return None
    # Extract JSON object from the response, even if there's surrounding
    # prose ("Sure — { ... }"). The last JSON object wins.
    import re as _re
    matches = _re.findall(r"\{[^{}]*\"target\"[^{}]*\}", raw, _re.DOTALL)
    if not matches:
        return None
    import json as _json
    try:
        parsed = _json.loads(matches[-1])
    except Exception:
        return None
    target = parsed.get("target")
    if not isinstance(target, str):
        return None
    valid = {t.key for t in ROUTE_REGISTRY}
    if target not in valid:
        return None
    return {target: 0.9}  # 0.9 confidence — LLM tier is high-trust when it answers.


# --------------------------------------------------------------------------- #
# Top-level
# --------------------------------------------------------------------------- #
@dataclass
class RouterConfig:
    """How the three tiers interact."""

    # If the top tier-1 score is below this, fall through to tier 2.
    tier1_threshold: float = 0.6
    # Same for tier 2.
    tier2_threshold: float = 0.55
    # The LLM tier only fires if the previous two tiers were both
    # below their thresholds (cheaper tiers run first).
    use_llm_tier: bool = False
    # Optional embed_fn for tier 2; pass None to skip.
    embed_fn: Callable[[str], list[float]] | None = None
    # Optional LLM router for tier 3.
    call_llm: LlmRouterFn | None = None


def route(query: str, config: RouterConfig | None = None) -> RouteDecision:
    """The 3-tier hybrid router. The cheapest tier that yields a
    confident match wins; lower tiers are tried only if the higher
    tier is ambiguous.
    """
    if config is None:
        config = RouterConfig()

    rewrites: list[str] = [query]

    # Tier 1: regex (free)
    t1 = _regex_score(query)
    if t1:
        best_key = max(t1, key=t1.get)  # type: ignore[arg-type]
        best_score = t1[best_key]
        if best_score >= config.tier1_threshold:
            return RouteDecision(
                target=best_key, confidence=best_score, tier=1,
                rewrites=rewrites, all_scores=t1,
            )

    # Tier 2: embedding cosine
    t2 = _embedding_score(query, config.embed_fn)
    if t2 is not None:
        if t2:
            best_key = max(t2, key=t2.get)  # type: ignore[arg-type]
            best_score = t2[best_key]
            # Combine tier 1 + tier 2 if both exist
            if t1:
                combined = {k: max(t1.get(k, 0.0), t2.get(k, 0.0)) for k in {*t1, *t2}}
            else:
                combined = t2
            if best_score >= config.tier2_threshold:
                return RouteDecision(
                    target=best_key, confidence=best_score, tier=2,
                    rewrites=rewrites, all_scores=combined,
                )
    else:
        combined = t1 or {}

    # Tier 3: LLM router (only if previous tiers were both low)
    if config.use_llm_tier and config.call_llm is not None:
        t3 = _llm_route(query, config.call_llm)
        if t3:
            best_key = max(t3, key=t3.get)  # type: ignore[arg-type]
            return RouteDecision(
                target=best_key,
                confidence=t3[best_key],
                tier=3,
                rewrites=rewrites,
                all_scores={**combined, **t3},
            )

    # No tier produced a confident answer. Fall back to memory_retrieval
    # as the safest default — it never hurts to check, and the chat
    # handler can override based on the agent's own judgment.
    return RouteDecision(
        target="memory_retrieval",
        confidence=0.0,
        tier=0,
        rewrites=rewrites,
        all_scores=combined,
    )


__all__ = [
    "ROUTE_REGISTRY",
    "RouteTarget",
    "RouteDecision",
    "RouterConfig",
    "route",
    "LlmRouterFn",
]


# --------------------------------------------------------------------------- #
# Pydantic schemas — constrained LLM router output (module 5)
# --------------------------------------------------------------------------- #
# opencode uses tool-calling for routing, but MadCop's chat models
# are not all guaranteed to support tool-calling. We constrain the LLM
# to a single JSON object via the prompt; the schema here documents
# the contract and gives the agent (or tests) a stable type.
try:
    from pydantic import BaseModel, Field  # type: ignore
except Exception:  # pragma: no cover — pydantic always present in deps
    BaseModel = object  # type: ignore
    Field = lambda *a, **kw: None  # type: ignore


class LlmRouterOutput(BaseModel):
    """The contract the LLM must satisfy when it picks a route.

    The router runs only when tier 1 + tier 2 are both inconclusive;
    the LLM is asked to choose a route key from the registry. We
    parse the output leniently (regex) and validate against this
    schema when pydantic is present. A failed validation is treated
    as "model declined" and the router falls through.
    """

    target: str = Field(..., min_length=1, description="The route key")
    reason: str = Field("", description="One-sentence justification")


# --------------------------------------------------------------------------- #
# Pydantic-aware LLM router wrapper
# --------------------------------------------------------------------------- #
def llm_route_validated(query: str, call_llm) -> dict[str, float] | None:
    """Same as _llm_route but uses LlmRouterOutput for validation
    when pydantic is available. The raw-output regex parse is kept
    as a fallback so a model that returns a non-standard shape
    still gets routed.
    """
    if call_llm is None:
        return None
    raw = (call_llm(_llm_route_prompt_for(query)) or "") if False else \
        _llm_route_call(call_llm, query)
    import json as _json
    import re as _re
    matches = _re.findall(r"\{[^{}]*\"target\"[^{}]*\}", raw, _re.DOTALL)
    if not matches:
        return None
    for blob in matches:
        try:
            parsed = LlmRouterOutput.model_validate(_json.loads(blob))  # type: ignore[attr-defined]
        except Exception:
            continue
        if parsed.target in {t.key for t in ROUTE_REGISTRY}:
            return {parsed.target: 0.9}
    return None


def _llm_route_prompt_for(query: str) -> str:
    catalog = "\n".join(f"- {t.key}: {t.description}" for t in ROUTE_REGISTRY)
    return _LLM_ROUTER_PROMPT.format(catalog=catalog, query=query)


def _llm_route_call(call_llm, query: str) -> str:
    try:
        return call_llm(_llm_route_prompt_for(query)) or ""
    except Exception:
        return ""
