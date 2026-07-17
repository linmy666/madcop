"""Unit tests for cron scheduler helpers."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from madcop.server import task_scheduler as ts


@pytest.fixture()
def tmp_sched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ts, "_TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(ts, "_RUNS_FILE", tmp_path / "runs.json")
    yield tmp_path


def test_is_due_and_cooldown(tmp_sched):
    task = {
        "id": "a",
        "name": "every minute",
        "cron": "* * * * *",
        "prompt": "hi",
        "enabled": True,
    }
    assert ts.is_due(task) is True
    task["lastRunAt"] = time.time()
    assert ts.is_due(task) is False


def test_disabled_not_due(tmp_sched):
    task = {
        "id": "b",
        "cron": "* * * * *",
        "prompt": "x",
        "enabled": False,
    }
    assert ts.is_due(task) is False


def test_execute_empty_prompt_fails(tmp_sched):
    run = ts.execute_task({"id": "c", "name": "empty", "prompt": ""}, source="test")
    assert run["status"] == "failed"
    assert run.get("error")


def test_execute_uses_client(tmp_sched, monkeypatch):
    from madcop.llm.client import ChatResponse, MockClient, Message

    class FixedClient(MockClient):
        def chat(self, messages, **kwargs):
            return ChatResponse(content="ok from mock", model="mock")

    monkeypatch.setattr(
        "madcop.llm.factory.build_client_from_config",
        lambda *a, **k: FixedClient(),
    )
    monkeypatch.setattr(
        "madcop.config.settings.get_active_client_config",
        lambda s: {"api_key": "x", "model": "m", "base_url": "http://x"},
    )
    monkeypatch.setattr(
        "madcop.config.settings.load_settings",
        lambda: object(),
    )
    run = ts.execute_task(
        {"id": "d", "name": "ping", "prompt": "Reply with exactly: ok"},
        source="test",
    )
    assert run["status"] == "completed"
    assert "ok" in (run.get("output") or "")
    runs = ts.load_runs()
    assert any(r["id"] == run["id"] for r in runs)


def test_tick_fires_due_task(tmp_sched, monkeypatch):
    def fake_exec(task, source="cron"):
        return {
            "id": "run1",
            "taskId": task["id"],
            "taskName": task.get("name"),
            "status": "completed",
            "source": source,
        }

    monkeypatch.setattr(ts, "execute_task", fake_exec)
    tasks = {
        "e": {
            "id": "e",
            "name": "tick-me",
            "cron": "* * * * *",
            "prompt": "say hi",
            "enabled": True,
        }
    }
    ts.save_tasks(tasks)
    fired = ts.tick()
    assert len(fired) >= 1
    assert fired[0]["taskId"] == "e"
