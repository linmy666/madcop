"""Tests for Retriever (cross-layer query interface)."""
from __future__ import annotations

from pathlib import Path

import pytest

from madcop.memory.store import MemoryStore
from madcop.memory.episodic import EpisodicMemory, Episode, EpisodeOutcome
from madcop.memory.semantic import SemanticMemory, FactKind
from madcop.memory.reflective import ReflectiveMemory, ReflectionKind
from madcop.memory.retriever import Retriever, RetrievalConfig


@pytest.fixture
def stack(tmp_path):
    """A triple of memory layers + one retriever on a fixed clock."""
    db = tmp_path / "stack.db"
    s = MemoryStore(path=db)
    epi = EpisodicMemory(s)
    sem = SemanticMemory(s)
    ref = ReflectiveMemory(s)
    # Frozen clock for deterministic time-decay tests
    ret = Retriever(epi, sem, ref, now_fn=lambda: 1_000_000_000.0)
    yield ret, epi, sem, ref
    s.close()


# ---------------------------------------------------------------------------
# Empty-state + cross-layer fan-out
# ---------------------------------------------------------------------------


def test_retrieve_empty_returns_empty(stack):
    ret, *_ = stack
    assert ret.retrieve("nothing in store yet") == []


def test_retrieve_fans_out_across_all_three_layers(stack):
    _, epi, sem, ref = stack
    epi.record(goal="Diagnose cancel spike", outcome=EpisodeOutcome.SUCCESS,
               steps_taken=3, total_cost_usd=0.05,
               findings=[{"rule": "CUSUM"}])
    sem.add(subject="CUSUM", predicate="threshold", object="cancel spike 4.78",
            kind=FactKind.FACT, confidence=0.9)
    ref.add(text="Always check baseline before alerting on cancel spike",
            kind=ReflectionKind.META_STRATEGY, source_episode=None,
            source_rating=None, confidence=0.8)

    results = Retriever(epi, sem, ref).retrieve("cancel spike")
    kinds_seen = {r.source_kind for r in results}
    assert {"episodic", "semantic", "reflective"} == kinds_seen


def test_retrieve_results_sorted_by_score_desc(stack):
    _, epi, sem, ref = stack
    epi.record(goal="oms spike diagnosis", outcome=EpisodeOutcome.SUCCESS,
               steps_taken=3, total_cost_usd=0.05, findings=[])
    sem.add(subject="oms", predicate="uses", object="CUSUM rule",
            kind=FactKind.FACT, confidence=0.95)
    ref.add(text="always cross-check cancel reason code",
            kind=ReflectionKind.LESSON_LEARNED, source_episode=None,
            source_rating=5, confidence=0.9)

    results = Retriever(epi, sem, ref).retrieve("oms cancel spike")
    # Scores must be descending
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Score weights and limits
# ---------------------------------------------------------------------------


def test_config_default_limits_respected(stack):
    _, epi, sem, ref = stack
    for i in range(20):
        epi.record(goal=f"oms task{i}", outcome=EpisodeOutcome.SUCCESS,
                   steps_taken=1, total_cost_usd=0.0)
    for i in range(20):
        sem.add(subject="oms", predicate="p", object=f"obj{i}",
                kind=FactKind.FACT)
    results = Retriever(epi, sem, ref, now_fn=lambda: 1_000_000_000.0).retrieve("oms")
    # episodic_limit=5 by default; should not return 20
    episodic_count = sum(1 for r in results if r.source_kind == "episodic")
    assert episodic_count <= 5


def test_custom_config_overrides(stack):
    _, epi, sem, ref = stack
    for i in range(8):
        sem.add(subject="common", predicate=f"p{i}", object=f"obj{i}",
                kind=FactKind.FACT, confidence=0.5)
    cfg = RetrievalConfig(semantic_limit=3)
    results = Retriever(epi, sem, ref).retrieve("common", config=cfg)
    semantic_count = sum(1 for r in results if r.source_kind == "semantic")
    assert semantic_count == 3


def test_semantic_layer_higher_weight_in_results(stack):
    _, epi, sem, ref = stack
    epi.record(goal="cancel spike", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    sem.add(subject="cancel spike", predicate="p", object="very impressive fact",
            kind=FactKind.FACT, confidence=0.99)
    results = Retriever(epi, sem, ref).retrieve("cancel spike")
    # Top result should be from semantic (weight 0.45 vs 0.40 vs 0.15)
    assert results[0].source_kind == "semantic"


# ---------------------------------------------------------------------------
# Time decay
# ---------------------------------------------------------------------------


def test_no_decay_when_halflife_zero(stack):
    _, epi, sem, ref = stack
    # Use a "now()" safely in the future of any created_at
    ancient_now = 2_000_000_000.0
    very_far_future = ancient_now + 365 * 86400
    epi.record(goal="oms", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)

    cfg = RetrievalConfig(half_life_days=0.0)
    results = Retriever(epi, sem, ref, now_fn=lambda: very_far_future).retrieve("oms", config=cfg)
    assert len(results) > 0  # not decayed


def test_decay_reduces_old_ancient_scores(stack):
    _, epi, sem, ref = stack
    # Pick a "now()" that's safely in the future of any created_at (created_at
    # uses time.time() ≈ 1.78e9 currently). Use 2e9 to be future-safe.
    ancient_now = 2_000_000_000.0
    very_far_future = ancient_now + 365 * 86400  # 1 year after ancient_now
    epi.record(goal="oms cancel spike", outcome=EpisodeOutcome.SUCCESS,
               steps_taken=1, total_cost_usd=0.0)

    # with no time elapsed = full score
    fresh = Retriever(epi, sem, ref, now_fn=lambda: ancient_now).retrieve("oms cancel spike")

    # with default 30-day half-life and now=1 year later
    cfg_default = RetrievalConfig()
    decayed = Retriever(epi, sem, ref, now_fn=lambda: very_far_future).retrieve("oms cancel spike", config=cfg_default)

    assert fresh
    assert decayed
    fresh_score = next(r.score for r in fresh if r.source_kind == "episodic")
    decayed_score = next(r.score for r in decayed if r.source_kind == "episodic")
    assert decayed_score < fresh_score


# ---------------------------------------------------------------------------
# format_for_prompt
# ---------------------------------------------------------------------------


def test_format_for_prompt_empty_returns_empty_string(stack):
    ret, *_ = stack
    assert ret.format_for_prompt([]) == ""


def test_format_for_prompt_includes_layers(stack):
    _, epi, sem, ref = stack
    epi.record(goal="cancel spike", outcome=EpisodeOutcome.SUCCESS,
               steps_taken=1, total_cost_usd=0.0)
    sem.add(subject="cancel-spike", predicate="uses", object="CUSUM rule",
            kind=FactKind.FACT)
    ref.add(text="user prefers concise output during cancel spike reviews",
            kind=ReflectionKind.USER_PREFERENCE, source_episode=None,
            source_rating=5)
    results = Retriever(epi, sem, ref).retrieve("cancel spike")

    formatted = Retriever(epi, sem, ref).format_for_prompt(results)
    assert "[L2 episode" in formatted
    assert "[L3 fact" in formatted
    assert "[L4 reflection" in formatted
    # Need at least 3 results to show all layers
    assert len(results) >= 3


def test_retrieval_result_has_required_fields(stack):
    _, epi, sem, ref = stack
    sem.add(subject="x", predicate="y", object="z", kind=FactKind.FACT)
    results = Retriever(epi, sem, ref).retrieve("x")
    assert results
    r = results[0]
    assert r.source_kind
    assert r.item
    assert r.score > 0
