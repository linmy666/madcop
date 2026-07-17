"""Cron-style scheduled task runner for MadCop.

Tasks live in ``~/.madcop/scheduled_tasks.json``; runs in
``~/.madcop/scheduled_task_runs.json``. The FastAPI lifespan loop calls
``tick()`` every ~30s; the REST layer uses the same helpers.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TASKS_FILE = Path.home() / ".madcop" / "scheduled_tasks.json"
_RUNS_FILE = Path.home() / ".madcop" / "scheduled_task_runs.json"
_LOCK = threading.RLock()
_MAX_RUNS = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_ts() -> float:
    return time.time()


def load_tasks() -> dict[str, dict[str, Any]]:
    with _LOCK:
        try:
            if _TASKS_FILE.exists():
                data = json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return {t["id"]: t for t in data if isinstance(t, dict) and t.get("id")}
                if isinstance(data, dict):
                    return {k: v for k, v in data.items() if isinstance(v, dict)}
        except Exception as e:
            logger.debug("load scheduled tasks: %s", e)
        return {}


def save_tasks(tasks: dict[str, dict[str, Any]]) -> None:
    with _LOCK:
        try:
            _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _TASKS_FILE.write_text(
                json.dumps(list(tasks.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug("save scheduled tasks: %s", e)


def load_runs() -> list[dict[str, Any]]:
    with _LOCK:
        try:
            if _RUNS_FILE.exists():
                data = json.loads(_RUNS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data[-_MAX_RUNS:]
        except Exception as e:
            logger.debug("load scheduled runs: %s", e)
        return []


def save_runs(runs: list[dict[str, Any]]) -> None:
    with _LOCK:
        try:
            _RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _RUNS_FILE.write_text(
                json.dumps(runs[-_MAX_RUNS:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug("save scheduled runs: %s", e)


def append_run(run: dict[str, Any]) -> None:
    runs = load_runs()
    runs.append(run)
    save_runs(runs)


def next_run_ts(cron_expr: str, base: float | None = None) -> float | None:
    """Return next fire time (unix) for a 5-field cron expression."""
    try:
        from croniter import croniter
    except ImportError:
        return None
    base = base if base is not None else _now_ts()
    try:
        it = croniter(cron_expr, base)
        return float(it.get_next(float))
    except Exception as e:
        logger.debug("cron parse failed %r: %s", cron_expr, e)
        return None


def is_due(task: dict[str, Any], now: float | None = None) -> bool:
    """Whether an enabled task should fire now."""
    if not task.get("enabled", True):
        return False
    cron = (task.get("cron") or task.get("schedule") or "").strip()
    if not cron:
        return False
    now = now if now is not None else _now_ts()
    last = task.get("lastRunAt") or task.get("lastFiredAt")
    last_ts: float | None = None
    if isinstance(last, (int, float)):
        last_ts = float(last)
    elif isinstance(last, str) and last:
        try:
            # support ISO or unix-as-string
            if last.isdigit():
                last_ts = float(last)
            else:
                last_ts = datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp()
        except Exception:
            last_ts = None
    # Fire if next occurrence after last run is <= now.
    # Special case: a task that has never run is "due now" regardless of
    # the cron's next schedule slot (otherwise `* * * * *` would wait up
    # to a full minute for a freshly created task). Also avoids a
    # croniter 6.x edge where the next minute boundary is strictly after
    # `now`.
    if last_ts is None:
        return True
    nxt = next_run_ts(cron, last_ts)
    if nxt is None:
        return False
    # Also require we haven't run in the last 45s (avoid double-fire)
    if last_ts is not None and (now - last_ts) < 45:
        return False
    return nxt <= now + 1


def execute_task(task: dict[str, Any], *, source: str = "manual") -> dict[str, Any]:
    """Run a task prompt through the active LLM (or mock). Returns a run record."""
    import time as _t

    tid = task.get("id") or "unknown"
    name = task.get("name") or tid
    prompt = (task.get("prompt") or "").strip()
    started = _now_iso()
    t0 = _t.time()
    run: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "taskId": tid,
        "taskName": name,
        "status": "running",
        "startedAt": started,
        "prompt": prompt,
        "source": source,
    }
    if not prompt:
        run.update({
            "status": "failed",
            "error": "empty prompt",
            "completedAt": _now_iso(),
            "finishedAt": _now_iso(),
            "durationMs": 0,
        })
        append_run(run)
        return run

    try:
        from madcop.config import settings as settings_store
        from madcop.llm.factory import build_client_from_config
        from madcop.llm.client import Message

        s = settings_store.load_settings()
        cfg = settings_store.get_active_client_config(s)
        client = build_client_from_config(
            cfg,
            timeout=90.0,
            mock_message="[No API key — scheduled task skipped]",
        )
        system = (
            "You are MadCop's scheduled task runner. Complete the user's scheduled "
            "prompt concisely and helpfully. If the task is ambiguous, state assumptions."
        )
        resp = client.chat(
            [
                Message(role="system", content=system),
                Message(role="user", content=prompt),
            ],
            temperature=0.4,
            max_tokens=int(task.get("max_tokens") or 2048),
        )
        content = (getattr(resp, "content", None) or "").strip()
        run.update({
            "status": "completed",
            "output": content[:50_000],
            "model": getattr(resp, "model", "") or (cfg or {}).get("model", ""),
            "completedAt": _now_iso(),
            "finishedAt": _now_iso(),
            "durationMs": int((_t.time() - t0) * 1000),
        })
    except Exception as e:
        logger.warning("scheduled task %s failed: %s", tid, e)
        run.update({
            "status": "failed",
            "error": str(e)[:500],
            "completedAt": _now_iso(),
            "finishedAt": _now_iso(),
            "durationMs": int((_t.time() - t0) * 1000),
        })

    append_run(run)

    # Update lastRunAt / nextRunAt on the task
    tasks = load_tasks()
    if tid in tasks:
        tasks[tid]["lastRunAt"] = _now_ts()
        tasks[tid]["lastFiredAt"] = _now_iso()
        cron = tasks[tid].get("cron") or tasks[tid].get("schedule") or ""
        nxt = next_run_ts(cron) if cron else None
        if nxt is not None:
            tasks[tid]["nextRunAt"] = nxt
        save_tasks(tasks)

    return run


def tick() -> list[dict[str, Any]]:
    """Check all enabled tasks; fire due ones. Returns list of run records."""
    now = _now_ts()
    tasks = load_tasks()
    fired: list[dict[str, Any]] = []
    for tid, task in list(tasks.items()):
        try:
            if is_due(task, now):
                logger.info("scheduler: firing task %s (%s)", tid, task.get("name"))
                run = execute_task(task, source="cron")
                fired.append(run)
        except Exception as e:
            logger.warning("scheduler tick error for %s: %s", tid, e)
    return fired
