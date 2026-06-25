"""Tests for SemanticMemory (L3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from madcop.memory.store import MemoryStore
from madcop.memory.semantic import SemanticMemory, Fact, FactKind


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(path=tmp_path / "semantic.db")
    yield SemanticMemory(s)
    s.close()


def test_add_creates_fact(memory):
    fact = memory.add(
        subject="OMS",
        predicate="uses",
        object="CUSUM threshold 4.78",
        kind=FactKind.FACT,
        source_episode="ep-001",
        confidence=0.9,
        tags=("oms", "monitoring"),
    )
    assert fact.id
    assert fact.subject == "OMS"
    assert fact.predicate == "uses"
    assert fact.object == "CUSUM threshold 4.78"
    assert fact.kind == FactKind.FACT
    assert fact.confidence == 0.9


def test_get_roundtrips(memory):
    fact = memory.add(subject="X", predicate="is", object="Y", kind=FactKind.CONCEPT)
    fetched = memory.get(fact.id)
    assert fetched is not None
    assert fetched.id == fact.id
    assert fetched.subject == "X"
    assert fetched.object == "Y"


def test_get_nonexistent(memory):
    assert memory.get("nope") is None


def test_find_by_subject(memory):
    memory.add(subject="OMS", predicate="a", object="1")
    memory.add(subject="OMS", predicate="b", object="2")
    memory.add(subject="WMS", predicate="c", object="3")
    related = memory.find_by_subject("OMS")
    assert len(related) >= 1


def test_search_finds_by_text(memory):
    memory.add(subject="X", predicate="p", object="CUSUM threshold")
    memory.add(subject="Y", predicate="p", object="temperature breach")
    results = memory.search("CUSUM")
    assert any("CUSUM" in f.object for f in results)


def test_count_reflects_adds(memory):
    assert memory.count() == 0
    memory.add(subject="x", predicate="y", object="z")
    memory.add(subject="a", predicate="b", object="c")
    memory.add(subject="d", predicate="e", object="f")
    assert memory.count() == 3


def test_fact_kind_enum_values():
    assert FactKind.FACT.value == "fact"
    assert FactKind.CONCEPT.value == "concept"
    assert FactKind.RELATION.value == "relation"
    assert FactKind.PATTERN.value == "pattern"
