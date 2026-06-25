"""Tests for GrowthEngine (3-mechanism self-improvement)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from madcop.memory.store import MemoryStore
from madcop.memory.episodic import EpisodicMemory, Episode, EpisodeOutcome
from madcop.memory.semantic import SemanticMemory, FactKind
from madcop.memory.reflective import ReflectiveMemory, ReflectionKind
from madcop.memory.growth import GrowthEngine, GrowthConfig


class FakeChatClient:
    """Returns scripted responses in sequence; echoes the prompt if exhausted."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict]) -> Any:
        self.calls.append(list(messages))
        if self._responses:
            resp_text = self._responses.pop(0)
        else:
            resp_text = "[]"
        # Mimic a real ChatCompletion/message-like wrapper
        return _FakeMessage(content=resp_text)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


@pytest.fixture
def stack(tmp_path):
    db = tmp_path / "growth.db"
    s = MemoryStore(path=db)
    epi = EpisodicMemory(s)
    sem = SemanticMemory(s)
    ref = ReflectiveMemory(s)
    yield s, epi, sem, ref
    s.close()


# ---------------------------------------------------------------------------
# Mechanism 1: distillation
# ---------------------------------------------------------------------------


def test_distill_episode_parses_json_array(stack):
    _, epi, sem, _ = stack
    ep = epi.record(goal="oms spike", outcome=EpisodeOutcome.SUCCESS,
                    steps_taken=3, total_cost_usd=0.05, findings=[])
    llm = FakeChatClient([
        '[{"subject":"oms","predicate":"uses","object":"CUSUM","kind":"fact","confidence":0.9}]'
    ])
    engine = GrowthEngine(epi, sem, ReflectiveMemory(stack[0]), llm)
    facts = engine.distill_episode(ep)
    assert len(facts) == 1
    assert facts[0].subject == "oms"
    assert facts[0].predicate == "uses"
    assert facts[0].object == "CUSUM"
    # Side-effect: written to semantic memory
    assert sem.count() == 1


def test_distill_episode_respects_max_cap(stack):
    _, epi, sem, _ = stack
    ep = epi.record(goal="test", outcome=EpisodeOutcome.SUCCESS,
                    steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient([
        '[{"subject":"a","predicate":"b","object":"1","kind":"fact","confidence":0.5},'
        ' {"subject":"c","predicate":"d","object":"2","kind":"fact","confidence":0.5},'
        ' {"subject":"e","predicate":"f","object":"3","kind":"fact","confidence":0.5}]'
    ])
    cfg = GrowthConfig(distillation_max_facts=2)
    engine = GrowthEngine(epi, sem, ReflectiveMemory(stack[0]), llm, config=cfg)
    facts = engine.distill_episode(ep)
    assert len(facts) == 2  # capped


def test_distill_episode_handles_garbage_gracefully(stack):
    _, epi, sem, _ = stack
    ep = epi.record(goal="x", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient(["this is not json"])
    engine = GrowthEngine(epi, sem, ReflectiveMemory(stack[0]), llm)
    facts = engine.distill_episode(ep)
    assert facts == []
    assert sem.count() == 0


def test_distill_episode_disabled_returns_empty(stack):
    _, epi, sem, _ = stack
    ep = epi.record(goal="x", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient(['[{"subject":"a","predicate":"b","object":"c","kind":"fact","confidence":0.9}]'])
    cfg = GrowthConfig(enabled=False)
    engine = GrowthEngine(epi, sem, ReflectiveMemory(stack[0]), llm, config=cfg)
    facts = engine.distill_episode(ep)
    assert facts == []


# ---------------------------------------------------------------------------
# Mechanism 2: feedback reflection
# ---------------------------------------------------------------------------


def test_record_feedback_creates_reflection(stack):
    _, epi, _, _ = stack
    ep = epi.record(goal="oms", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient([
        '{"text":"user likes concise reports","kind":"user_preference","confidence":0.9,"tags":["style"]}'
    ])
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm)
    ref = engine.record_feedback(ep, rating=5, comment="good but verbose")
    assert ref is not None
    assert ref.text == "user likes concise reports"
    assert ref.kind == ReflectionKind.USER_PREFERENCE
    assert ref.source_rating == 5


def test_record_feedback_invalid_rating_raises(stack):
    _, epi, _, _ = stack
    ep = epi.record(goal="x", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient(["[]"])
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm)
    with pytest.raises(ValueError):
        engine.record_feedback(ep, rating=10)
    with pytest.raises(ValueError):
        engine.record_feedback(ep, rating=0)


def test_record_feedback_handles_unknown_kind_gracefully(stack):
    """If LLM returns an unknown kind string, we fall back to LESSON_LEARNED."""
    _, epi, _, _ = stack
    ep = epi.record(goal="x", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient([
        '{"text":"some lesson","kind":"definitely-not-real","confidence":0.7}'
    ])
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm)
    ref = engine.record_feedback(ep, rating=3)
    assert ref is not None
    assert ref.kind == ReflectionKind.LESSON_LEARNED  # fallback


def test_record_feedback_disabled_returns_none(stack):
    _, epi, _, _ = stack
    ep = epi.record(goal="x", outcome=EpisodeOutcome.SUCCESS, steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient(["{}"])
    cfg = GrowthConfig(enabled=False)
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm, config=cfg)
    ref = engine.record_feedback(ep, rating=3)
    assert ref is None


# ---------------------------------------------------------------------------
# Mechanism 3: meta-pattern mining
# ---------------------------------------------------------------------------


def test_mine_meta_patterns_requires_options_min(stack):
    _, epi, _, _ = stack
    for i in range(3):  # less than default min_episodes=5
        epi.record(goal=f"task {i}", outcome=EpisodeOutcome.SUCCESS,
                   steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient(['[{"text":"a pattern","confidence":0.8}]'])
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm)
    patterns = engine.mine_meta_patterns()
    assert patterns == []  # not enough data


def test_mine_meta_patterns_returns_reflections(stack):
    ref_layer = ReflectiveMemory(stack[0])
    _, epi, _, _ = stack
    for i in range(6):  # ≥ meta_min_episodes=5
        epi.record(goal=f"task {i}", outcome=EpisodeOutcome.SUCCESS,
                   steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient([
        '[{"text":"if cancel spike, check CUSUM first","confidence":0.85,"tags":["oms"]},'
        ' {"text":"always include cost summary in final report","confidence":0.7,"tags":["format"]}]'
    ])
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ref_layer, llm)
    patterns = engine.mine_meta_patterns()
    assert len(patterns) == 2
    assert all(p.kind == ReflectionKind.META_STRATEGY for p in patterns)


def test_mine_meta_patterns_respects_max_cap(stack):
    _, epi, _, _ = stack
    for i in range(6):
        epi.record(goal=f"task {i}", outcome=EpisodeOutcome.SUCCESS,
                   steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient([
        '[{"text":"a","confidence":0.7},'
        ' {"text":"b","confidence":0.7},'
        ' {"text":"c","confidence":0.7},'
        ' {"text":"d","confidence":0.7}]'
    ])
    cfg = GrowthConfig(meta_max_patterns=2)
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm, config=cfg)
    patterns = engine.mine_meta_patterns()
    assert len(patterns) == 2


def test_mine_meta_patterns_uses_supplied_episodes(stack):
    """If episodes list is passed in, ignore list_recent and use that."""
    _, epi, _, _ = stack
    llm = FakeChatClient(['[{"text":"forced pattern","confidence":0.6}]'])
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm)
    # Pass exactly 6 fake episodes (well over default min)
    fake_eps = [
        epi.record(goal=f"x{i}", outcome=EpisodeOutcome.SUCCESS,
                   steps_taken=1, total_cost_usd=0.0)
        for i in range(6)
    ]
    patterns = engine.mine_meta_patterns(episodes=fake_eps)
    assert len(patterns) == 1
    assert "forced pattern" in patterns[0].text


def test_mine_meta_patterns_handles_empty_response(stack):
    _, epi, _, _ = stack
    for i in range(6):
        epi.record(goal=f"x{i}", outcome=EpisodeOutcome.SUCCESS,
                   steps_taken=1, total_cost_usd=0.0)
    llm = FakeChatClient(["[]"])
    engine = GrowthEngine(epi, SemanticMemory(stack[0]), ReflectiveMemory(stack[0]), llm)
    patterns = engine.mine_meta_patterns()
    assert patterns == []


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def test_parse_json_list_extracts_from_surrounding_text():
    llm_text = 'Some commentary\n```json\n[{"a":1}, {"b":2}]\n```\nMore text'
    result = GrowthEngine._parse_json_list(llm_text)
    assert result == [{"a": 1}, {"b": 2}]


def test_parse_json_list_handles_empty():
    assert GrowthEngine._parse_json_list("") == []
    assert GrowthEngine._parse_json_list("no brackets here") == []


def test_parse_json_object_extracts_from_surrounding_text():
    text = 'Here is the result:\n{"key": "value"}\nDone.'
    result = GrowthEngine._parse_json_object(text)
    assert result == {"key": "value"}


def test_parse_json_object_returns_none_for_garbage():
    assert GrowthEngine._parse_json_object("") is None
    assert GrowthEngine._parse_json_object("not json") is None
