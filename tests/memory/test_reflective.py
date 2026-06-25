"""Tests for ReflectiveMemory (L4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from madcop.memory.store import MemoryStore
from madcop.memory.reflective import ReflectiveMemory, Reflection, ReflectionKind


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(path=tmp_path / "reflective.db")
    yield ReflectiveMemory(s)
    s.close()


def test_add_creates_reflection(memory):
    ref = memory.add(
        text="User prefers concise reports",
        kind=ReflectionKind.USER_PREFERENCE,
        source_episode="ep-001",
        source_rating=5,
        confidence=0.95,
        tags=("style",),
    )
    assert ref.id
    assert ref.text == "User prefers concise reports"
    assert ref.kind == ReflectionKind.USER_PREFERENCE
    assert ref.source_episode == "ep-001"
    assert ref.source_rating == 5
    assert ref.confidence == 0.95


def test_get_roundtrips(memory):
    ref = memory.add(text="ABC", kind=ReflectionKind.LESSON_LEARNED, source_episode=None, source_rating=None)
    fetched = memory.get(ref.id)
    assert fetched is not None
    assert fetched.id == ref.id
    assert fetched.text == "ABC"


def test_list_recent(memory):
    for i in range(4):
        memory.add(text=f"lesson {i}", kind=ReflectionKind.META_STRATEGY, source_episode=None, source_rating=None)
    recent = memory.list_recent(limit=2)
    assert len(recent) == 2


def find_meta_patterns_hit(memory):
    memory.add(text="if cold, check freezer first", kind=ReflectionKind.META_STRATEGY, source_episode=None, source_rating=None, tags=("cold",))
    memory.add(text="if cancel, check CUSUM", kind=ReflectionKind.META_STRATEGY, source_episode=None, source_rating=None, tags=("oms",))
    patterns = memory.find_meta_patterns("cold")
    assert any("freezer" in p.text for p in patterns)


def test_count_reflects_adds(memory):
    assert memory.count() == 0
    memory.add(text="a", kind=ReflectionKind.LESSON_LEARNED, source_episode=None, source_rating=None)
    memory.add(text="b", kind=ReflectionKind.WORKING_NOTE, source_episode=None, source_rating=None)
    assert memory.count() == 2


def test_reflection_kind_enum_values():
    assert ReflectionKind.USER_PREFERENCE.value == "user_preference"
    assert ReflectionKind.USER_DISLIKE.value == "user_dislike"
    assert ReflectionKind.META_STRATEGY.value == "meta_strategy"
    assert ReflectionKind.LESSON_LEARNED.value == "lesson_learned"
    assert ReflectionKind.WORKING_NOTE.value == "working_note"
