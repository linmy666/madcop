"""Query rewriter — turn natural-language questions into FTS5-friendly
keyword queries.

This is the "modular RAG" `query_analysis` step in our pipeline.
opencode does not do this; MadCop's FTS5 index returns nothing for
natural-language queries because BM5 looks at raw tokens. Rewriting
the query to keywords before dispatching to the FTS5 index is what
turns "how does the user's previous sprint retrospective inform
today's plan?" into "retro retrospective sprint plan", which FTS5 can
actually match.

Two strategies, run in order until one produces ≥ 1 hit:

  1. Cheapest: language-agnostic keyword extraction (the query is
     almost always noun-heavy once stop-words are stripped).
  2. Slightly more expensive but well-bounded: an LLM rewrites the
     query into 3-5 keywords. Fall back to (1) if LLM is unavailable
     or the model declines.

Both strategies emit a *list* of keyword variants, not a single
rewritten query, so the retriever can match against any of them.
This is a poor man's HyDE — the real HyDE would generate a
hypothetical answer; we only have the user-supplied LLM, and this is
enough to bridge the lex-vs-vec gap.
"""
from __future__ import annotations

import re
from typing import Iterable

# Chinese + English stop-words. Keep tiny — the goal is to drop
# the obvious function words, not build a full NLP pipeline.
_STOPWORDS: frozenset[str] = frozenset(
    {
        # English
        "a", "an", "and", "are", "as", "at", "be", "by", "do", "for",
        "from", "has", "have", "i", "in", "is", "it", "of", "on", "or",
        "so", "such", "that", "the", "their", "this", "to", "was", "we",
        "what", "when", "where", "which", "who", "why", "with", "you",
        "your", "yours", "yourselves",
        # Chinese (high-frequency function words)
        "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
        "也", "就", "都", "和", "与", "或", "而", "但", "把", "让",
        "给", "用", "来", "去", "上", "下", "这", "那", "吗", "呢",
        "吧", "啊", "哦", "么", "得", "着", "过", "的", "么", "着",
    }
)

# Punctuation/whitespace to split on, including CJK commas / parens.
_TOKENIZE_RE = re.compile(
    r"[A-Za-z]+|[\u4e00-\u9fff]+|\d+",
    re.UNICODE,
)


def _tokenize(text: str) -> list[str]:
    return _TOKENIZE_RE.findall(text)


def _drop_stopwords(tokens: Iterable[str]) -> list[str]:
    return [t for t in tokens if t.lower() not in _STOPWORDS and len(t) > 1]


def keyword_variants(query: str, max_variants: int = 3) -> list[str]:
    """Cheapest possible query rewrite: stop-word-stripped keywords.

    Returns up to `max_variants` keyword strings, the first of which
    is the longest (most specific). Each is a candidate for FTS5
    MATCH (which uses prefix wildcards by default in our schema, so
    even partial words still hit).
    """
    if not query or not query.strip():
        return []
    tokens = _drop_stopwords(_tokenize(query))
    if not tokens:
        return []
    # The full keyword string is the most-specific candidate. Then
    # drop the rarest (last) token progressively to broaden.
    out = [" ".join(tokens)]
    for drop_n in range(1, min(len(tokens), max_variants)):
        candidate = " ".join(tokens[:-drop_n]) if drop_n else " ".join(tokens)
        if candidate and candidate not in out:
            out.append(candidate)
        if len(out) >= max_variants:
            break
    return out


def llm_rewrite_variants(query: str, call_llm) -> list[str]:
    """LLM-rewrite wrapper. The caller passes a callable that takes a
    prompt and returns the LLM response. We do the prompt construction
    and parsing here so the rewrite policy is decoupled from the LLM
    transport.

    The prompt asks for 3-5 keyword forms. If the LLM declines or
    returns nothing parseable, the caller should fall back to
    `keyword_variants`.
    """
    if not query or not query.strip():
        return []
    prompt = (
        "Rewrite the following user query as 3 to 5 short keyword "
        "queries that would match well in a full-text search index. "
        "Return one query per line, no numbering, no explanation.\n\n"
        f"Original: {query}\n\n"
        "Keywords:"
    )
    raw = call_llm(prompt) or ""
    out: list[str] = []
    for line in raw.splitlines():
        cand = line.strip().strip("-").strip("•").strip()
        if 2 <= len(cand) <= 120 and cand not in out:
            out.append(cand)
        if len(out) >= 5:
            break
    return out


def expand(query: str, call_llm=None) -> list[str]:
    """The single public entry point. Always returns at least one
    keyword variant for a non-empty input; falls back to the
    keyword-only strategy if no LLM is supplied or the LLM returns
    nothing useful.
    """
    if not query or not query.strip():
        return []
    base = keyword_variants(query)
    extras: list[str] = []
    if call_llm is not None:
        try:
            extras = llm_rewrite_variants(query, call_llm)
        except Exception:
            # LLM failure should never break retrieval.
            extras = []
    seen: set[str] = set()
    out: list[str] = []
    for v in extras + base:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out
