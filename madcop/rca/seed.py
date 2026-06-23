"""L2 — Knowledge graph seed for the cold-chain scenario.

This is the graph that backs the W3 demo. It encodes ONE real-world story:

- Shipment SHIP-2026-0615-CG-SH was a cold-chain 广州→上海 run.
- It was carried by supplier SUP-CG-007 ("冷链速运").
- The service contract is CONT-2026-0312.
- One clause in that contract — CLAUSE-04 — says "温控异常时,
  承运商应在 30 分钟内书面通知甲方, 逾期每日扣 0.5% 服务费".
  This clause is a **passive** clause: it punishes a breach but does not
  *prevent* one. The decision that let it be passive is DEC-2026-03-12-N3
  ("甲方 BD 接受了乙方'罚款即免责'的让步").

The madcop RCA walks the chain:
    temperature_breach (anomaly)
    → SHIP-2026-0615-CG-SH (shipment)
    → SUP-CG-007 (supplier, CARRIED_BY)
    → CONT-2026-0312 (contract, SIGNED_WITH)
    → CLAUSE-04 (clause, GOVERNED_BY)
    → DEC-2026-03-12-N3 (decision, DECIDED_BY)

The **PM takeaway**: the root cause is a *negotiation decision* made 3 months
before the shipment. The product implication is that madcop should suggest
counter-proposals for "passive" clauses (W6 territory).
"""

from __future__ import annotations

from .graph import Edge, KnowledgeGraph, Node


def build_coldchain_seed() -> KnowledgeGraph:
    """Build the knowledge graph for the cold-chain W3 demo."""
    g = KnowledgeGraph()

    # Nodes
    g.add_node(Node(
        id="SHIP-2026-0615-CG-SH", type="shipment",
        label="SHIP-2026-0615-CG-SH (广州→上海, 冷链, 2026-06-15)",
    ))
    g.add_node(Node(
        id="SUP-CG-007", type="supplier",
        label="冷链速运",
        attributes={"region": "华东", "tier": "B"},
    ))
    g.add_node(Node(
        id="CONT-2026-0312", type="contract",
        label="CONT-2026-0312 (冷链速运 / 2026 年度框架)",
        attributes={"signed_at": "2026-03-12", "value_cny": 1_200_000},
    ))
    g.add_node(Node(
        id="CLAUSE-04", type="clause",
        label="CLAUSE-04 (温控异常通知条款)",
        attributes={
            "text": "温控异常时, 承运商应在 30 分钟内书面通知甲方, 逾期每日扣 0.5% 服务费",
            "passive": True,   # the demo's punchline: this clause punishes but does not prevent
        },
    ))
    g.add_node(Node(
        id="DEC-2026-03-12-N3", type="decision",
        label="DEC-2026-03-12-N3 (BD 接受乙方'罚款即免责'让步)",
        attributes={"decided_by": "BD-Lin", "rationale": "Q1 降本压力"},
    ))

    # Edges
    g.add_edge(Edge(src="SHIP-2026-0615-CG-SH", dst="SUP-CG-007", type="CARRIED_BY"))
    g.add_edge(Edge(src="CONT-2026-0312",     dst="SUP-CG-007", type="SIGNED_WITH"))
    g.add_edge(Edge(src="CONT-2026-0312",     dst="CLAUSE-04",  type="GOVERNED_BY"))
    g.add_edge(Edge(src="CLAUSE-04",          dst="DEC-2026-03-12-N3", type="DECIDED_BY"))

    return g
