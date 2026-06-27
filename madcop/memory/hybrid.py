"""Hybrid retrieval: FTS5 keyword + lightweight TF-IDF semantic score (Gap 8).

Why a custom TF-IDF instead of sentence-transformers / sklearn:
- No extra deps (no 400MB model download, no sklearn/numpy compat issues)
- Good enough for the user-memory + episodic-recall use case
- Easy to test and reason about

Public surface:
    from madcop.memory.hybrid import hybrid_search
    results = hybrid_search(store, query, limit=10, alpha=0.5)
        # alpha=0.0 → pure FTS5; alpha=1.0 → pure semantic; 0.5 → balanced
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .store import MemoryStore


_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Tokenize: English words split on whitespace, Chinese per-character.

    Mixed input like '上海weather' → ['上', '海', 'weather'].
    """
    if not text:
        return []
    tokens: list[str] = []
    for match in _WORD_RE.finditer(text):
        chunk = match.group()
        # Chinese: split per char
        if any("\u4e00" <= c <= "\u9fff" for c in chunk):
            for c in chunk:
                if "\u4e00" <= c <= "\u9fff":
                    tokens.append(c)
        # English / alphanum: keep whole word
        else:
            tokens.append(chunk.lower())
    return tokens


def _term_freq(tokens: list[str]) -> Counter:
    return Counter(tokens)


def _build_idf(documents: list[list[str]]) -> dict[str, float]:
    """Inverse document frequency for each term. log(N / df) + 1 smoothed."""
    n = max(1, len(documents))
    df: Counter = Counter()
    for doc in documents:
        for term in set(doc):
            df[term] += 1
    return {
        term: math.log(n / (count + 1)) + 1.0
        for term, count in df.items()
    }


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = _term_freq(tokens)
    if not tf:
        return {}
    # Normalise by max term frequency (length-independent)
    max_tf = max(tf.values())
    vec = {
        term: (count / max_tf) * idf.get(term, 1.0)
        for term, count in tf.items()
    }
    return vec


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _fetch_candidates(
    store: MemoryStore, query: str, limit: int = 50,
) -> list[dict]:
    """Fetch candidate docs from FTS5 + LIKE fallback.

    We combine FTS5 (precise keyword match) with a broad LIKE scan
    so that simple high-quality matches (e.g. "Shanghai") aren't
    filtered out by bm25 noise. The hybrid score below reranks.
    """
    rows: list[dict] = []
    seen_ids: set[str] = set()
    # FTS5 candidate pool (ranked by bm25)
    words = [w for w in query.split() if len(w) > 1][:5]
    if words:
        fts_query = " OR ".join(f'"{w}"' for w in words)
        try:
            cur = store._conn.execute(
                "SELECT id, kind, title, content, tags, created_at "
                "FROM memory_fts WHERE memory_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, limit),
            )
            for r in cur.fetchall():
                d = dict(r)
                rows.append(d)
                seen_ids.add(d["id"])
        except Exception:
            pass
    # LIKE-based fallback — catches what FTS5 bm25 may have missed
    if len(rows) < limit:
        try:
            like = f"%{query}%"
            cur = store._conn.execute(
                "SELECT id, kind, title, content, tags, created_at "
                "FROM memory_records "
                "WHERE content LIKE ? OR title LIKE ? OR tags LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (like, like, like, limit),
            )
            for r in cur.fetchall():
                d = dict(r)
                if d["id"] not in seen_ids:
                    rows.append(d)
                    seen_ids.add(d["id"])
        except Exception:
            pass
    # Final fallback: if we still have very few candidates, pad with
    # most-recent memories so hybrid can at least rank *something*.
    if len(rows) < limit // 2:
        try:
            cur = store._conn.execute(
                "SELECT id, kind, title, content, tags, created_at "
                "FROM memory_records ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            for r in cur.fetchall():
                d = dict(r)
                if d["id"] not in seen_ids:
                    rows.append(d)
                    seen_ids.add(d["id"])
        except Exception:
            pass
    return rows


def hybrid_search(
    store: MemoryStore,
    query: str,
    limit: int = 10,
    *,
    alpha: float = 0.5,
    candidate_limit: int = 50,
) -> list[dict]:
    """Hybrid FTS5 + TF-IDF cosine search.

    Each candidate gets a combined score:
        score = (1 - alpha) * fts_score + alpha * semantic_score
    Returns the top-`limit` candidates, each enriched with `score`.

    `fts_score` is normalised to [0, 1] by dividing by the max FTS5 score
    in the candidate set. `semantic_score` is cosine similarity, also
    in [0, 1].
    """
    candidates = _fetch_candidates(store, query, limit=candidate_limit)
    if not candidates:
        return []
    # Build TF-IDF vectors
    query_tokens = _tokenize(query)
    doc_tokens_list = [_tokenize(c.get("content", "") + " " + c.get("title", ""))
                       for c in candidates]
    idf = _build_idf([query_tokens] + doc_tokens_list)
    query_vec = _tfidf_vector(query_tokens, idf)
    doc_vecs = [_tfidf_vector(tokens, idf) for tokens in doc_tokens_list]

    # Semantic score: raw cosine in [0, 1]. No rescaling — values
    # < 0.05 are essentially "no semantic match" and get filtered
    # by the alpha weighting below.
    sem_scores = [_cosine(query_vec, dv) for dv in doc_vecs]

    # FTS5 position score: 1.0 for first candidate, 0.0 for last.
    # Position is a weak signal; FTS5 bm25 ordering is unreliable for
    # this use-case (prefers short docs or docs with repeated terms).
    n = len(candidates)
    pos_scores = [1.0 - (i / max(1, n - 1)) if n > 1 else 1.0
                  for i in range(n)]

    for i, c in enumerate(candidates):
        c["score"] = (1 - alpha) * pos_scores[i] + alpha * sem_scores[i]

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:limit]


__all__ = ["hybrid_search", "_tokenize", "_tfidf_vector", "_cosine"]
