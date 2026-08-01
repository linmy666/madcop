"""Sprint 6 — Brain Graph API skeleton.

Returns the page+link graph from PageDB as {nodes, edges}.
Skeleton — full CRUD for nodes/edges is a follow-up.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from madcop.brain.store import PageDB

router = APIRouter(prefix="/api/brain", tags=["brain"])


def _page_to_node(page) -> dict[str, Any]:
    return {
        "id": page.slug,
        "label": page.title,
        "type": page.type,
        "tags": page.tags,
        "updatedAt": page.updated_at,
    }


def _link_to_edge(link) -> dict[str, Any]:
    return {
        "id": f"{link.from_slug}->{link.to_slug}",
        "from": link.from_slug,
        "to": link.to_slug,
        "label": link.context,
    }


@router.get("/graph")
def get_graph(workspace: str = "") -> dict[str, Any]:
    """Return the page graph (nodes + edges) for the current workspace."""
    db = PageDB(workspace) if workspace else PageDB.default()
    pages = db.list_all() if hasattr(db, "list_all") else db.search("", limit=200)
    nodes = [_page_to_node(p) for p in pages]
    edges: list[dict[str, Any]] = []
    for p in pages:
        for link in db.get_links(p.slug):
            edges.append(_link_to_edge(link))
    return {"nodes": nodes, "edges": edges}


@router.post("/link")
def create_link(from_slug: str, to_slug: str, context: str = "") -> dict[str, Any]:
    """Add an edge between two pages."""
    db = PageDB.default()
    db.add_link(from_slug, to_slug, context)
    return {"ok": True, "from": from_slug, "to": to_slug}


@router.delete("/node/{slug}")
def delete_node(slug: str) -> dict[str, Any]:
    """Delete a page node (and its edges)."""
    db = PageDB.default()
    db.delete(slug)
    return {"ok": True, "slug": slug}
