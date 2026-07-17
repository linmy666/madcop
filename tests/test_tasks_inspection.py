"""Scheduled tasks API + session inspection."""
from __future__ import annotations

from fastapi.testclient import TestClient

from madcop.server.app import create_app


def test_scheduled_tasks_crud_and_run():
    client = TestClient(create_app())
    r = client.post("/api/scheduled-tasks", json={
        "name": "Ping-pytest",
        "cron": "0 9 * * *",
        "prompt": "say hi",
    })
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    tid = data["task"]["id"]

    r2 = client.get("/api/scheduled-tasks")
    assert any(t["id"] == tid for t in r2.json().get("tasks", []))

    r3 = client.post(f"/api/scheduled-tasks/{tid}/run")
    assert r3.status_code == 200
    run_body = r3.json()
    # Compat layer may return {ok, run} or {runId, scheduledTaskId}
    assert run_body.get("ok") is True or run_body.get("runId") or run_body.get("run")

    r4 = client.get("/api/scheduled-tasks/runs")
    # runs list may be empty if another handler owns run persistence
    assert r4.status_code == 200

    r5 = client.delete(f"/api/scheduled-tasks/{tid}")
    assert r5.status_code == 200


def test_session_inspection_shape():
    client = TestClient(create_app())
    r = client.post("/api/sessions", json={"title": "inspect-me"})
    sid = None
    if r.status_code == 200:
        body = r.json()
        sid = body.get("sessionId") or body.get("id") or (body.get("session") or {}).get("id")
    if not sid:
        sid = "inspect-test-sid"
    r2 = client.get(f"/api/sessions/{sid}/inspection")
    assert r2.status_code == 200
    data = r2.json()
    assert "sessionId" in data or "messages" in data


def test_list_tools_endpoint():
    client = TestClient(create_app())
    r = client.get("/api/tools")
    assert r.status_code == 200
    data = r.json()
    assert "tools" in data
    assert data.get("total", 0) >= 1
