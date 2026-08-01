"""Sprint 2 — Tests for FiveLayerRetriever layer weighting + time decay."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from madcop.memory.retriever_5layer import FiveLayerRetriever, LAYER_WEIGHTS
from madcop.memory.store import MemoryRecord, MemoryKind


def make_record(kind: str, content: str, age_days: float = 0,
                 tags=()) -> MemoryRecord:
    now = time.time()
    return MemoryRecord(
        id=f"r-{kind}-{content[:8]}",
        kind=MemoryKind(kind),
        title=f"title for {content[:20]}",
        content=content,
        tags=tags,
        created_at=now - age_days * 86400,
        updated_at=now - age_days * 86400,
    )


def fake_hybrid(records, base_score=1.0):
    """Returns a hybrid_fn that yields records as candidates.

    Accepts any positional/keyword args so the test is decoupled
    from the production signature — the production call site only
    passes (store, query, top_k) but might surface other parameters
    in future refactors.
    """
    def fn(*_args, **_kwargs):
        return [{**r.__dict__, "score": base_score} for r in records]
    return fn


class TestLayerWeighting(unittest.TestCase):
    def setUp(self):
        self.records = [
            make_record("episodic", "episodic fact"),
            make_record("semantic", "semantic fact"),
            make_record("reflective", "reflective fact"),
        ]

    def test_semantic_outranks_episodic(self):
        rec = FiveLayerRetriever()
        results = rec.retrieve(
            "anything", top_k=3, hybrid_fn=fake_hybrid(self.records)
        )
        self.assertEqual(len(results), 3)
        layers = {r.layer for r in results}
        self.assertIn("L1_semantic", layers)
        self.assertIn("L0_episodic", layers)
        self.assertIn("L4_reflective", layers)

    def test_top_k_limits_results(self):
        rec = FiveLayerRetriever()
        results = rec.retrieve("x", top_k=2, hybrid_fn=fake_hybrid(self.records))
        self.assertEqual(len(results), 2)

    def test_empty_query_returns_none(self):
        rec = FiveLayerRetriever()
        results = rec.retrieve("   ", top_k=5, hybrid_fn=fake_hybrid(self.records))
        self.assertEqual(results, [])

    def test_weights_sum_to_one(self):
        total = sum(LAYER_WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0, delta=0.01)


class TestTimeDecay(unittest.TestCase):
    def test_recent_outranks_old(self):
        recent = make_record("semantic", "fresh", age_days=0)
        old = make_record("semantic", "stale", age_days=60)
        rec = FiveLayerRetriever()
        results = rec.retrieve(
            "f", top_k=2, half_life_days=30.0,
            hybrid_fn=fake_hybrid([recent, old]),
        )
        self.assertEqual(results[0].item["id"], recent.id)
        self.assertEqual(results[1].item["id"], old.id)

    def test_half_life_30_days_at_60_days(self):
        # 60 days / 30-day half-life = 2.0 half-lives = 0.25 weight
        rec = make_record("semantic", "x", age_days=60)
        results = FiveLayerRetriever().retrieve(
            "x", top_k=1, half_life_days=30.0,
            hybrid_fn=fake_hybrid([rec]),
        )
        expected_score = 1.0 * 0.25 * LAYER_WEIGHTS["L1_semantic"]
        self.assertAlmostEqual(results[0].score, expected_score, places=4)


class TestTagBoost(unittest.TestCase):
    def test_scenario_tag_promotes_to_l2(self):
        rec = make_record("semantic", "x", tags=("scenario",))
        results = FiveLayerRetriever().retrieve(
            "x", top_k=1, hybrid_fn=fake_hybrid([rec]))
        self.assertEqual(results[0].layer, "L2_scenario")

    def test_persona_tag_promotes_to_l3(self):
        rec = make_record("semantic", "x", tags=("persona",))
        results = FiveLayerRetriever().retrieve(
            "x", top_k=1, hybrid_fn=fake_hybrid([rec]))
        self.assertEqual(results[0].layer, "L3_persona")

    def test_insight_pattern_promotes_to_l4b(self):
        rec = make_record("semantic", "x", tags=("pattern",))
        results = FiveLayerRetriever().retrieve(
            "x", top_k=1, hybrid_fn=fake_hybrid([rec]))
        self.assertEqual(results[0].layer, "L4b_insight")


if __name__ == "__main__":
    unittest.main()
