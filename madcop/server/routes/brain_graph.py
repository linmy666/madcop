"""Sprint 6 — Brain Graph API for the Knowledge Canvas (知识画布).

Exposes the PageDB knowledge graph as ``{nodes, edges}`` and supports
CRUD over nodes/edges so the canvas can render, link, create, edit and
delete knowledge pages.

A single PageDB instance lives at ``~/.madcop/brain.db`` (see
``PageDB.default()``) — this is the same path the CLI, the ingest
pipeline and ``UnifiedConfig`` use, so the canvas reads exactly what
the rest of the system writes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from madcop.brain.markdown import VALID_TYPES
from madcop.brain.store import PageDB

router = APIRouter(prefix="/api/brain", tags=["brain"])

# Page types the canvas can create directly. "concept" is the sensible
# default for free-form notes a user types by hand.
_DEFAULT_PAGE_TYPE = "concept"


def _page_to_node(page: Any) -> dict[str, Any]:
    """Serialize a ``Page`` dataclass into a JSON-safe canvas node.

    ``compiled_truth`` is the canonical body text; we surface a short
    preview + the full text so the detail drawer can show it without a
    second round-trip.
    """
    body = (getattr(page, "compiled_truth", "") or "").strip()
    return {
        "id": page.slug,
        "slug": page.slug,
        "label": page.title,
        "title": page.title,
        "type": page.type,
        "tags": list(getattr(page, "tags", []) or []),
        "body": body,
        "preview": (body[:280] + "…") if len(body) > 280 else body,
        "updatedAt": getattr(page, "updated_at", ""),
        "createdAt": getattr(page, "created_at", ""),
        "staleAfterDays": getattr(page, "stale_after_days", None),
        "lastAccessedAt": getattr(page, "last_accessed_at", None),
    }


def _link_to_edge(source_slug: str, other_slug: str, context: str, direction: str) -> dict[str, Any]:
    """Turn a ``(other_slug, context)`` link tuple into a canvas edge.

    ``PageDB.get_links`` returns ``(other_slug, context)`` tuples rather
    than link objects, so we reconstruct the directed edge here.
    ``direction`` is "out" (source -> other) or "in" (other -> source).
    """
    if direction == "in":
        src, dst = other_slug, source_slug
    else:
        src, dst = source_slug, other_slug
    return {
        "id": f"{src}->{dst}",
        "source": src,
        "target": dst,
        # Keep legacy "from"/"to" aliases so older clients keep working.
        "from": src,
        "to": dst,
        "label": context or "",
        "context": context or "",
        "direction": direction,
    }


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class NodeSave(BaseModel):
    """Create or update a knowledge node."""

    slug: str = Field(..., description="URL-safe slug, [a-z0-9][a-z0-9_-]*")
    title: str
    body: str = ""
    type: str = _DEFAULT_PAGE_TYPE
    tags: list[str] = Field(default_factory=list)
    staleAfterDays: int | None = None


def _db(workspace: str = "") -> PageDB:
    """Resolve the PageDB instance. The canvas passes the active workspace
    DIRECTORY, not a file — only an existing *.db file is honored as a
    custom DB location; anything else falls back to the canonical DB
    (~/.madcop/brain.db). Previously a directory hit sqlite3.connect and
    500'd the whole graph endpoint."""
    if workspace:
        try:
            p = Path(workspace).expanduser()
            if p.suffix == ".db" and p.is_file():
                return PageDB(str(p))
        except Exception:  # noqa: BLE001
            pass
    return PageDB.default()


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/graph")
def get_graph(workspace: str = "") -> dict[str, Any]:
    """Return the full page graph (nodes + edges) for the canvas.

    We query out-edges only (not "both") so each directed link appears
    exactly once with the correct source→target orientation. Querying
    "both" would emit every link twice (once per endpoint) and lose the
    direction, producing duplicate/backwards edges on the canvas.
    """
    db = _db(workspace)
    try:
        pages = db.list_all() if hasattr(db, "list_all") else db.search("", limit=200)
        nodes = [_page_to_node(p) for p in pages]
        edges: list[dict[str, Any]] = []
        seen_edge_ids: set[str] = set()
        for p in pages:
            for other_slug, ctx in db.get_links(p.slug, direction="out"):
                edge = _link_to_edge(p.slug, other_slug, ctx, "out")
                if edge["id"] in seen_edge_ids:
                    continue
                seen_edge_ids.add(edge["id"])
                edges.append(edge)
        return {"nodes": nodes, "edges": edges}
    finally:
        db.close()


@router.post("/node")
def save_node(node: NodeSave, workspace: str = "") -> dict[str, Any]:
    """Create or update a knowledge node (canvas double-click → new node)."""
    if node.type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"type must be one of {sorted(VALID_TYPES)} (got {node.type!r})",
        )
    db = _db(workspace)
    try:
        page = db.save(
            slug=node.slug,
            title=node.title,
            page_type=node.type,
            compiled_truth=node.body,
            tags=node.tags,
            source="canvas",
            saved_by="user",
            stale_after_days=node.staleAfterDays,
        )
        return {"ok": True, "node": _page_to_node(page)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        db.close()


@router.get("/node/{slug}")
def get_node(slug: str, workspace: str = "") -> dict[str, Any]:
    """Fetch a single node's full detail for the NodeDetail drawer."""
    db = _db(workspace)
    try:
        page = db.get(slug)
        if page is None:
            raise HTTPException(status_code=404, detail=f"node {slug!r} not found")
        inbound = [(s, c) for s, c in db.get_links(slug, direction="in")]
        outbound = [(s, c) for s, c in db.get_links(slug, direction="out")]
        node = _page_to_node(page)
        node["linksIn"] = [{"slug": s, "context": c} for s, c in inbound]
        node["linksOut"] = [{"slug": s, "context": c} for s, c in outbound]
        return {"node": node}
    finally:
        db.close()


@router.post("/link")
def create_link(from_slug: str, to_slug: str, context: str = "") -> dict[str, Any]:
    """Add a directed edge between two existing nodes."""
    db = _db()
    try:
        db.add_link(from_slug, to_slug, context, source="canvas")
    except KeyError:
        return {
            "ok": False,
            "error": f"节点不存在：无法链接 {from_slug!r} → {to_slug!r}（请先创建这两个节点）",
        }
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    finally:
        db.close()
    return {"ok": True, "from": from_slug, "to": to_slug, "context": context}


@router.delete("/link")
def delete_link(from_slug: str, to_slug: str) -> dict[str, Any]:
    """Remove a directed edge between two nodes. Idempotent."""
    db = _db()
    try:
        db.delete_link(from_slug, to_slug)
    finally:
        db.close()
    return {"ok": True, "from": from_slug, "to": to_slug}


@router.delete("/node/{slug}")
def delete_node(slug: str) -> dict[str, Any]:
    """Delete a node. Idempotent — deleting a missing node is still ok=True."""
    db = _db()
    try:
        db.delete(slug, source="canvas")
    finally:
        db.close()
    return {"ok": True, "slug": slug}
