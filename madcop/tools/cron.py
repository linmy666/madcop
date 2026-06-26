"""v1.6.0 — Cron scheduler for periodic agent tasks.

A minimal cron-like system that lets the user schedule recurring
plan-execute runs. Stored in SQLite (reuses the brain's DB or a
separate file).

Each cron job has:
  - id: unique identifier (slug)
  - goal: the goal text to pass to the plan-execute loop
  - schedule: a cron expression (``*/5 * * * *``) or interval string
  - mode: flash / standard / pro
  - enabled: bool
  - last_run: timestamp of last execution
  - next_run: computed from schedule

The scheduler runs in a background thread. When a job fires, it
builds a plan-execute run (mock or real LLM) and logs the outcome.

Design (Qian control theory):
  - 稳定性: background thread is daemon, exits on main process exit
  - 可控性: jobs can be paused (enabled=False) without deletion
  - 层次化: cron → plan_execute → middleware → brain (each layer independent)
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Cron expression parser (minimal — supports */N and fixed values)
# --------------------------------------------------------------------------- #


def parse_cron(expr: str) -> dict[str, Any]:
    """Parse a cron expression into a dict of field values.

    Supports: ``*``, ``*/N``, and exact integers.
    Does NOT support ranges (1-5), lists (1,3,5), or L/W modifiers.

    Fields: minute hour day-of-month month day-of-week
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"cron expression must have 5 fields, got {len(parts)}: {expr!r}")

    fields = ["minute", "hour", "dom", "month", "dow"]
    result: dict[str, Any] = {}

    for name, val in zip(fields, parts):
        if val == "*":
            result[name] = "*"
        elif val.startswith("*/"):
            result[name] = ("every", int(val[2:]))
        else:
            result[name] = int(val)

    return result


def should_run(cron_dict: dict[str, Any], t: time.struct_time) -> bool:
    """Check if a cron schedule should fire at time ``t``.

    ``t`` is a ``time.struct_time`` (tm_min, tm_hour, tm_mday, tm_mon, tm_wday).
    """
    checks = [
        ("minute", t.tm_min),
        ("hour", t.tm_hour),
        ("dom", t.tm_mday),
        ("month", t.tm_mon),
        ("dow", t.tm_wday),  # Monday=0 in struct_time, Sunday=0 in cron
    ]

    for field_name, current_val in checks:
        spec = cron_dict.get(field_name)
        if spec == "*":
            continue
        elif isinstance(spec, tuple) and spec[0] == "every":
            step = spec[1]
            if current_val % step != 0:
                return False
        elif isinstance(spec, int):
            # dow: cron Sunday=0, struct_time Monday=0 → Sunday=6
            if field_name == "dow":
                cron_dow = (current_val + 1) % 7  # convert struct_time to cron
                if spec != cron_dow:
                    return False
            elif spec != current_val:
                return False

    return True


def next_run_seconds(cron_dict: dict[str, Any], from_ts: float | None = None) -> int:
    """Estimate seconds until the next fire (approximate).

    For ``*/N minute``, returns N*60. For fixed times, finds the next match.
    """
    minute_spec = cron_dict.get("minute")
    if isinstance(minute_spec, tuple) and minute_spec[0] == "every":
        return minute_spec[1] * 60
    if minute_spec == "*":
        return 60  # every minute
    # Fixed minute — find next matching minute in this hour
    now = time.localtime(from_ts) if from_ts else time.localtime()
    target_min = int(minute_spec)
    delta = target_min - now.tm_min
    if delta <= 0:
        delta += 60
    return delta * 60


# --------------------------------------------------------------------------- #
# CronJob dataclass
# --------------------------------------------------------------------------- #


@dataclass
class CronJob:
    """A scheduled agent task."""
    id: str                          # unique slug
    goal: str                        # goal text for plan-execute
    schedule: str                    # cron expression
    mode: str = "standard"           # flash/standard/pro
    enabled: bool = True
    last_run: str | None = None
    run_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# CronStore — SQLite-backed persistence
# --------------------------------------------------------------------------- #


class CronStore:
    """SQLite store for cron jobs.

    Uses a simple table in the same DB as the brain (or a separate file).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                schedule TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'standard',
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run TEXT,
                run_count INTEGER NOT NULL DEFAULT 0,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
        """)
        self._conn.commit()

    def add(self, job: CronJob) -> None:
        import json
        self._conn.execute(
            "INSERT OR REPLACE INTO cron_jobs "
            "(id, goal, schedule, mode, enabled, last_run, run_count, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job.id, job.goal, job.schedule, job.mode,
             int(job.enabled), job.last_run, job.run_count,
             json.dumps(job.metadata)),
        )
        self._conn.commit()

    def remove(self, job_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM cron_jobs WHERE id=?", (job_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get(self, job_id: str) -> CronJob | None:
        row = self._conn.execute(
            "SELECT * FROM cron_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_all(self) -> list[CronJob]:
        rows = self._conn.execute(
            "SELECT * FROM cron_jobs ORDER BY id"
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def list_enabled(self) -> list[CronJob]:
        rows = self._conn.execute(
            "SELECT * FROM cron_jobs WHERE enabled=1 ORDER BY id"
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update_after_run(self, job_id: str, timestamp: str) -> None:
        self._conn.execute(
            "UPDATE cron_jobs SET last_run=?, run_count=run_count+1 WHERE id=?",
            (timestamp, job_id),
        )
        self._conn.commit()

    def set_enabled(self, job_id: str, enabled: bool) -> None:
        self._conn.execute(
            "UPDATE cron_jobs SET enabled=? WHERE id=?",
            (int(enabled), job_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> CronJob:
        import json
        return CronJob(
            id=row["id"],
            goal=row["goal"],
            schedule=row["schedule"],
            mode=row["mode"],
            enabled=bool(row["enabled"]),
            last_run=row["last_run"],
            run_count=row["run_count"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def close(self) -> None:
        self._conn.close()


# --------------------------------------------------------------------------- #
# CronScheduler — background thread that fires jobs
# --------------------------------------------------------------------------- #


class CronScheduler:
    """Background scheduler that fires cron jobs.

    Runs in a daemon thread. Every 60 seconds, checks if any enabled
    job should fire based on its cron expression.

    Args:
        store: A CronStore instance.
        on_fire: Callback called when a job fires. Receives the job.
            The callback is where you'd build a plan-execute run.
        check_interval: Seconds between checks (default 60).
    """

    def __init__(
        self,
        store: CronStore,
        on_fire: Callable[[CronJob], None],
        *,
        check_interval: int = 60,
    ) -> None:
        self._store = store
        self._on_fire = on_fire
        self._check_interval = check_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="madcop-cron",
        )
        self._thread.start()
        logger.info("CronScheduler started (interval=%ds)", self._check_interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("CronScheduler stopped")

    def _run_loop(self) -> None:
        last_minute = -1
        while not self._stop_event.is_set():
            now = time.localtime()
            # Only check once per minute (at the top of the minute)
            if now.tm_min != last_minute:
                last_minute = now.tm_min
                self._check_and_fire(now)
            self._stop_event.wait(self._check_interval)

    def _check_and_fire(self, now: time.struct_time) -> None:
        jobs = self._store.list_enabled()
        for job in jobs:
            try:
                cron_dict = parse_cron(job.schedule)
                if should_run(cron_dict, now):
                    logger.info("Cron job firing: %s", job.id)
                    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    self._store.update_after_run(job.id, ts)
                    try:
                        self._on_fire(job)
                    except Exception as e:
                        logger.warning("Cron job %s callback failed: %s", job.id, e)
            except Exception as e:
                logger.warning("Cron check failed for %s: %s", job.id, e)


__all__ = [
    "CronJob",
    "CronStore",
    "CronScheduler",
    "parse_cron",
    "should_run",
    "next_run_seconds",
]
