"""Sprint 6 — brain_graph route tests (lightweight, no app import)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Use the brain_graph router in isolation to avoid app.py's
# import-time side effects (background tasks, file paths, etc.)
from madcop.server.routes.brain_graph import router as brain_graph_router


class TestBrainGraphRoute(unittest.TestCase):
    def setUp(self):
        # Build a minimal app just for this router.
        app = FastAPI()
        app.include_router(brain_graph_router)
        self.client = TestClient(app)

    def test_graph_endpoint_returns_nodes_and_edges(self):
        r = self.client.get("/api/brain/graph")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsInstance(body, dict)
        self.assertIn("nodes", body)
        self.assertIn("edges", body)
        self.assertIsInstance(body["nodes"], list)
        self.assertIsInstance(body["edges"], list)

    def test_create_link_endpoint(self):
        # add_link requires both endpoints to exist first — create them.
        for slug in ("a", "b"):
            self.client.post(
                "/api/brain/node",
                json={"slug": slug, "title": slug.upper(), "body": "test"},
            )
        r = self.client.post(
            "/api/brain/link",
            params={"from_slug": "a", "to_slug": "b", "context": "test"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("from"), "a")
        self.assertEqual(body.get("to"), "b")
        # Clean up so the graph test stays deterministic.
        for slug in ("a", "b"):
            self.client.delete(f"/api/brain/node/{slug}")

    def test_delete_node_endpoint(self):
        r = self.client.delete("/api/brain/node/whatever")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("slug"), "whatever")

    def test_create_node(self):
        """Sprint 6 — POST /node creates a node, GET /node/{slug} reads it."""
        slug = "canvas-test-create"
        r = self.client.post(
            "/api/brain/node",
            json={
                "slug": slug,
                "title": "Canvas Test Node",
                "body": "A node created from the canvas.",
                "tags": ["test"],
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        node = body["node"]
        self.assertEqual(node["slug"], slug)
        self.assertEqual(node["title"], "Canvas Test Node")
        self.assertIn("test", node["tags"])

        # Read it back.
        got = self.client.get(f"/api/brain/node/{slug}")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["node"]["slug"], slug)

        # Reject an invalid type.
        bad = self.client.post(
            "/api/brain/node",
            json={"slug": "bad-type", "title": "x", "type": "not-a-real-type"},
        )
        self.assertEqual(bad.status_code, 400)

        # Cleanup.
        self.client.delete(f"/api/brain/node/{slug}")
        self.client.delete("/api/brain/node/bad-type")

    def test_graph_with_links(self):
        """Sprint 6 — a link between two nodes appears in the graph edges."""
        slugs = ["canvas-g-a", "canvas-g-b"]
        for s in slugs:
            self.client.post("/api/brain/node", json={"slug": s, "title": s, "body": "x"})
        self.client.post(
            "/api/brain/link",
            params={"from_slug": slugs[0], "to_slug": slugs[1], "context": "related"},
        )
        r = self.client.get("/api/brain/graph")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        node_ids = {n["id"] for n in body["nodes"]}
        self.assertIn(slugs[0], node_ids)
        self.assertIn(slugs[1], node_ids)
        edge_ids = {e["id"] for e in body["edges"]}
        self.assertIn(f"{slugs[0]}->{slugs[1]}", edge_ids)
        for s in slugs:
            self.client.delete(f"/api/brain/node/{s}")


if __name__ == "__main__":
    unittest.main()
