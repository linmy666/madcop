"""Tests for L2 — RCA (knowledge graph + trace + explain)."""

from __future__ import annotations

import pytest

from madcop.anomaly.detector import AnomalyFinding
from madcop.rca.graph import (
    EDGE_TYPES,
    NODE_TYPES,
    Edge,
    KnowledgeGraph,
    Node,
    explain,
    trace,
)
from madcop.rca.seed import build_coldchain_seed


# --------------------------------------------------------------------------- #
# Node / Edge validation
# --------------------------------------------------------------------------- #

def test_node_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="unknown node type"):
        Node(id="x", type="warehouse", label="x")


def test_edge_rejects_unknown_type() -> None:
    g = KnowledgeGraph()
    g.add_node(Node(id="a", type="shipment", label="a"))
    g.add_node(Node(id="b", type="shipment", label="b"))
    with pytest.raises(ValueError, match="unknown edge type"):
        g.add_edge(Edge(src="a", dst="b", type="WAT"))


# --------------------------------------------------------------------------- #
# KnowledgeGraph basics
# --------------------------------------------------------------------------- #

def test_knowledge_graph_rejects_duplicate_node() -> None:
    g = KnowledgeGraph()
    g.add_node(Node(id="a", type="shipment", label="a"))
    with pytest.raises(ValueError, match="duplicate"):
        g.add_node(Node(id="a", type="shipment", label="a"))


def test_knowledge_graph_rejects_edge_to_unknown_node() -> None:
    g = KnowledgeGraph()
    g.add_node(Node(id="a", type="shipment", label="a"))
    with pytest.raises(ValueError, match="unknown dst"):
        g.add_edge(Edge(src="a", dst="ghost", type="CARRIED_BY"))


def test_predecessors_traverse_in_reverse() -> None:
    g = KnowledgeGraph()
    g.add_node(Node(id="ship", type="shipment", label="ship"))
    g.add_node(Node(id="sup", type="supplier", label="sup"))
    g.add_edge(Edge(src="ship", dst="sup", type="CARRIED_BY"))
    assert [n.id for n in g.predecessors("sup", "CARRIED_BY")] == ["ship"]
    assert [n.id for n in g.neighbors("ship", "CARRIED_BY")] == ["sup"]


# --------------------------------------------------------------------------- #
# Cold-chain seed
# --------------------------------------------------------------------------- #

def test_seed_builds_five_node_graph() -> None:
    g = build_coldchain_seed()
    assert g.size == 5
    types = {n.type for n in g.nodes}
    assert types == {"shipment", "supplier", "contract", "clause", "decision"}


def test_seed_clause_is_marked_passive() -> None:
    g = build_coldchain_seed()
    clause = g.get("CLAUSE-04")
    assert clause is not None
    assert clause.attributes.get("passive") is True


# --------------------------------------------------------------------------- #
# trace — the headline feature
# --------------------------------------------------------------------------- #

def test_trace_wms_breach_to_decision() -> None:
    g = build_coldchain_seed()
    finding = AnomalyFinding(
        rule_id="wms.coldchain.temperature_breach",
        subject_id="SHIP-2026-0615-CG-SH",
        timestamp="2026-06-15T14:30:00Z",
        severity=4,
        summary="temperature breach",
    )
    chain = trace(finding, g)
    # Expected: 5 nodes in the cause chain.
    # The chain is reversed so steps[0] is the **root cause** (decision)
    # and steps[-1] is the entity closest to the anomaly (shipment).
    # The product reason: "why did this happen?" reads better starting at
    # the human decision that caused it.
    assert len(chain.steps) == 5
    assert chain.steps[0][0].id == "DEC-2026-03-12-N3"
    assert chain.steps[-1][0].id == "SHIP-2026-0615-CG-SH"
    assert chain.root is not None
    assert chain.root.id == "DEC-2026-03-12-N3"


def test_trace_returns_empty_for_unknown_subject() -> None:
    g = build_coldchain_seed()
    finding = AnomalyFinding(
        rule_id="wms.coldchain.temperature_breach",
        subject_id="GHOST-SHIP",
        timestamp="2026-06-15T14:30:00Z",
        severity=4,
        summary="x",
    )
    assert trace(finding, g).steps == []


def test_trace_returns_empty_for_unknown_rule() -> None:
    g = build_coldchain_seed()
    finding = AnomalyFinding(
        rule_id="made.up.rule",
        subject_id="SHIP-2026-0615-CG-SH",
        timestamp="2026-06-15T14:30:00Z",
        severity=4,
        summary="x",
    )
    assert trace(finding, g).steps == []


def test_trace_returns_empty_when_subject_is_wrong_type() -> None:
    g = build_coldchain_seed()
    # OMS rule needs a 'decision' anchor; subject is a shipment → no match
    finding = AnomalyFinding(
        rule_id="oms.cancellation.spike",
        subject_id="SHIP-2026-0615-CG-SH",
        timestamp="2026-06-15T14:30:00Z",
        severity=4,
        summary="x",
    )
    assert trace(finding, g).steps == []


# --------------------------------------------------------------------------- #
# explain — the product-facing output
# --------------------------------------------------------------------------- #

def test_explain_empty_chain() -> None:
    from madcop.rca.graph import CausalChain
    assert "no causal chain" in explain(CausalChain(steps=[]))


def test_explain_full_chain_is_human_readable() -> None:
    g = build_coldchain_seed()
    finding = AnomalyFinding(
        rule_id="wms.coldchain.temperature_breach",
        subject_id="SHIP-2026-0615-CG-SH",
        timestamp="2026-06-15T14:30:00Z",
        severity=4,
        summary="x",
    )
    chain = trace(finding, g)
    text = explain(chain)
    # Should mention every node type in the chain
    assert "SHIP-2026-0615-CG-SH" in text
    assert "冷链速运" in text
    assert "CONT-2026-0312" in text
    assert "CLAUSE-04" in text
    assert "DEC-2026-03-12-N3" in text
