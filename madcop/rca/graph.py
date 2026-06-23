"""L2 — Root cause analysis (RCA).

Turns an `AnomalyFinding` into a causal chain that ends at a **decision**
or a **contract clause** — the place where a human chose (or failed to
choose) something that made the anomaly possible.

Design:

- The world is a typed property graph: nodes are entities, edges are relations.
  We do NOT pull in a graph database; the world is small (one shipment, one
  contract, a handful of clauses), so a dict-of-dicts is the right data
  structure. This is **explicit**: if you want Neo4j later, port it.
- The graph is built from a `KnowledgeGraph` that ships with a static seed
  (the cold-chain scenario) but can be extended by adapters in W5+.
- `trace(anomaly)` walks the graph backwards from the anomaly's `subject_id`
  following **reverse edges** of type `CAUSED_BY`, `SIGNED_WITH`,
  `GOVERNED_BY`. It returns a `CausalChain` (a list of nodes + edges).
- `explain(chain)` turns the chain into a human-readable paragraph. This is
  what humans actually see; the chain is the structure, the explanation is
  the product.

Why this matters (PM framing): an alert without a cause is a notification.
An alert with a cause is a **decision prompt**. madcop's job is to bridge
the two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..anomaly.detector import AnomalyFinding


# --------------------------------------------------------------------------- #
# Node and edge types
# --------------------------------------------------------------------------- #

NODE_TYPES = ("shipment", "supplier", "contract", "clause", "decision", "anomaly")
EDGE_TYPES = (
    "CARRIED_BY",      # shipment -> supplier
    "SIGNED_WITH",     # contract -> supplier
    "GOVERNED_BY",     # contract -> clause
    "CAUSED_BY",       # anomaly -> shipment (or clause)
    "DECIDED_BY",      # clause -> decision
)


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    label: str
    attributes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in NODE_TYPES:
            raise ValueError(f"unknown node type: {self.type!r}")


@dataclass(frozen=True)
class Edge:
    src: str           # node id
    dst: str           # node id
    type: str          # one of EDGE_TYPES

    def __post_init__(self) -> None:
        if self.type not in EDGE_TYPES:
            raise ValueError(f"unknown edge type: {self.type!r}")


# --------------------------------------------------------------------------- #
# Knowledge graph
# --------------------------------------------------------------------------- #

class KnowledgeGraph:
    """A tiny in-memory property graph.

    Nodes are stored by id. Edges are stored as forward and reverse adjacency
    lists so both `neighbors(node, edge_type)` and `predecessors(node, edge_type)`
    are O(degree), not O(|E|).
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._fwd: dict[tuple[str, str], list[str]] = {}   # (src, type) -> [dst]
        self._rev: dict[tuple[str, str], list[str]] = {}   # (dst, type) -> [src]

    # -- mutators --

    def add_node(self, node: Node) -> None:
        if node.id in self._nodes:
            raise ValueError(f"duplicate node id: {node.id!r}")
        self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        if edge.src not in self._nodes:
            raise ValueError(f"unknown src: {edge.src!r}")
        if edge.dst not in self._nodes:
            raise ValueError(f"unknown dst: {edge.dst!r}")
        self._fwd.setdefault((edge.src, edge.type), []).append(edge.dst)
        self._rev.setdefault((edge.dst, edge.type), []).append(edge.src)

    # -- queries --

    def get(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def neighbors(self, node_id: str, edge_type: str) -> list[Node]:
        return [self._nodes[d] for d in self._fwd.get((node_id, edge_type), [])]

    def predecessors(self, node_id: str, edge_type: str) -> list[Node]:
        return [self._nodes[s] for s in self._rev.get((node_id, edge_type), [])]

    @property
    def nodes(self) -> Iterable[Node]:
        return self._nodes.values()

    @property
    def size(self) -> int:
        return len(self._nodes)


# --------------------------------------------------------------------------- #
# Causal chain
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CausalChain:
    """A sequence of (node, via_edge) steps from anomaly to root cause.

    Convention: `steps[0]` is the **root cause** (a decision), `steps[-1]`
    is the entity closest to the anomaly (a shipment). See `trace()`.
    """
    steps: list[tuple[Node, Edge | None]]

    @property
    def root(self) -> Node | None:
        return self.steps[0][0] if self.steps else None


# --------------------------------------------------------------------------- #
# Tracing
# --------------------------------------------------------------------------- #

# (anomaly_rule_id, subject_id_prefix) -> (anchor_node_id, edge_type)
# This maps a finding back to a graph node. In a real system, anomalies
# would carry the subject's primary key directly. For the v0 demo we use
# a small lookup table.
_ANCHOR_RULES: dict[str, tuple[str, str]] = {
    # rule_id: (edge_type, node_type_to_find)
    "wms.coldchain.temperature_breach": ("CAUSED_BY", "shipment"),
    "wms.coldchain.sustained_breach":   ("CAUSED_BY", "shipment"),
    "tms.leadtime.overrun":             ("CAUSED_BY", "shipment"),
    "bms.supplier.score_drop":          ("CAUSED_BY", "supplier"),
    "oms.cancellation.spike":           ("CAUSED_BY", "decision"),
}


def trace(finding: AnomalyFinding, graph: KnowledgeGraph) -> CausalChain:
    """Walk the graph from the anomaly back to a root-cause node.

    The cause chain is a path through typed edges. Each step has a *direction*
    (forward or reverse) that we choose based on the current node's type:

        shipment -[CARRIED_BY fwd]-> supplier
        supplier -[SIGNED_WITH rev]-> contract   # contract points TO supplier
        contract -[GOVERNED_BY fwd]-> clause
        clause   -[DECIDED_BY fwd]->  decision

    The path is **causal** in the business sense: a decision in the past
    shaped a clause, which shaped a contract, which signed a supplier, who
    carried a shipment, where the anomaly was observed. We traverse that
    chain in the natural graph order, then reverse before returning so that
    `steps[0]` is the entity closest to the anomaly.
    """
    if finding.rule_id not in _ANCHOR_RULES:
        return CausalChain(steps=[])

    _, anchor_type = _ANCHOR_RULES[finding.rule_id]
    anchor = graph.get(finding.subject_id)
    if anchor is None or anchor.type != anchor_type:
        return CausalChain(steps=[])

    forward_steps: list[tuple[Node, Edge | None]] = [(anchor, None)]
    current = anchor

    # (current_type, edge_type, direction, next_type)
    plan = [
        ("shipment", "CARRIED_BY",  "fwd", "supplier"),
        ("supplier", "SIGNED_WITH", "rev", "contract"),
        ("contract", "GOVERNED_BY", "fwd", "clause"),
        ("clause",   "DECIDED_BY",  "fwd", "decision"),
    ]
    for from_type, edge_type, direction, to_type in plan:
        if current.type != from_type:
            continue
        if direction == "fwd":
            nxts = graph.neighbors(current.id, edge_type)
            edge = Edge(src=current.id, dst=None, type=edge_type)  # dst filled below
        else:
            nxts = graph.predecessors(current.id, edge_type)
            edge = Edge(src=None, dst=current.id, type=edge_type)
        if not nxts:
            break
        nxt = nxts[0]
        if direction == "fwd":
            edge = Edge(src=current.id, dst=nxt.id, type=edge_type)
        else:
            edge = Edge(src=nxt.id, dst=current.id, type=edge_type)
        forward_steps.append((nxt, edge))
        current = nxt

    forward_steps.reverse()
    return CausalChain(steps=forward_steps)


# --------------------------------------------------------------------------- #
# Explanation
# --------------------------------------------------------------------------- #

def explain(chain: CausalChain) -> str:
    """Turn a chain into a human paragraph.

    Narrative order is **root cause → effect**, matching how a post-mortem
    is written: "The decision (made by X) let clause Y be passive; the
    contract was signed with supplier Z, who carried shipment W, where the
    anomaly fired."

    The chain is structured so `steps[0]` is the root cause (decision) and
    `steps[-1]` is the entity closest to the anomaly (shipment). We walk
    the chain in that order.
    """
    if not chain.steps:
        return "(no causal chain found — knowledge graph may be incomplete)"

    by_type: dict[str, Node] = {n.type: n for n, _ in chain.steps}
    parts: list[str] = []
    if "decision" in by_type:
        attrs = by_type["decision"].attributes
        who = attrs.get("decided_by", "")
        why = attrs.get("rationale", "")
        head = f"decision [bold]{by_type['decision'].label}[/bold]"
        if who:
            head += f" (by [italic]{who}[/italic])"
        if why:
            head += f" — rationale: [italic]{why}[/italic]"
        parts.append(head)
    if "clause" in by_type:
        attrs = by_type["clause"].attributes
        clause_text = attrs.get("text", by_type["clause"].label)
        passive = attrs.get("passive")
        marker = " [reverse-video]PASSIVE[/reverse-video]" if passive else ""
        parts.append(
            f"shaped clause [bold]{by_type['clause'].label}[/bold]{marker} (\"{clause_text}\")"
        )
    if "contract" in by_type:
        parts.append(f"under contract [bold]{by_type['contract'].label}[/bold]")
    if "supplier" in by_type:
        parts.append(f"carried by [bold]{by_type['supplier'].label}[/bold]")
    if "shipment" in by_type:
        parts.append(f"on shipment [bold]{by_type['shipment'].label}[/bold]")
    return " → ".join(parts)
