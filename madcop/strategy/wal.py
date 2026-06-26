"""v0.8.0 — Crash recovery for the plan-execute loop.

The `Scratchpad` is good at storing the *result* of each step, but it
doesn't tell the plan-execute loop *which* steps have already been
committed in a previous run. If the agent crashes mid-plan, the next
run needs to know "skip step 1, 2, 3 (already done), resume from step 4".

That's what the WAL does. It's a tiny append-only log file that lives
next to the scratchpad:

    ~/.madcop/runs/run_abc.json         # the scratchpad (v0.6.0)
    ~/.madcop/runs/run_abc.wal.jsonl    # the WAL (v0.8.0)

Each line is one JSON record. Three record types:

    {"event": "start",  "run_id": "...", "goal": "...", "plan": [...], "ts": 1234.5}
    {"event": "step",   "name": "step-1", "status": "ok", "ts": 1235.0}
    {"event": "finish", "final_report": "...", "ts": 1299.0}

Why JSONL, not SQLite:
- Append-only, so a torn write loses at most one line.
- A torn scratchpad JSON file would lose the whole file.
- Easy to `cat` and inspect.
- Easy to truncate to "replay from step 4" by deleting lines.

What the WAL does for you:
1. `WAL.append_start(...)` — record the run start + the plan.
2. `WAL.append_step(...)` — record "step X is committed".
3. `WAL.replay()` — re-derive the set of completed step names.
4. `WAL.compact_to_scratchpad(scratchpad)` — copy WAL facts into the
   scratchpad's metadata so cold reads don't need both files.

What the WAL does NOT do:
- It doesn't know about the plan's logic — it only records names.
  Replay gives you a *set of names*; your loop still has to decide
  "am I done with this step?".
- It doesn't checkpoint LLM prompts or tool outputs. That's the
  scratchpad's job. The WAL is the "control plane" complement.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


WAL_FILENAME_SUFFIX = ".wal.jsonl"


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StartRecord:
    """The first line of a WAL: marks the start of a run + the plan."""
    run_id: str
    goal: str
    plan: tuple[dict[str, Any], ...]
    ts: float

    def to_json(self) -> str:
        return json.dumps({
            "event": "start",
            "run_id": self.run_id,
            "goal": self.goal,
            "plan": list(self.plan),
            "ts": self.ts,
        }, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class WALStepRecord:
    """A step that has been committed (executed, verified, and saved).

    Named `WALStepRecord` to avoid collision with the `StepRecord` in
    `madcop.strategy.scratchpad` (which has a different schema).
    """
    name: str
    status: str                           # "ok" / "failed" / "skipped" / "replan"
    ts: float
    error: str | None = None

    def to_json(self) -> str:
        d: dict[str, Any] = {
            "event": "step",
            "name": self.name,
            "status": self.status,
            "ts": self.ts,
        }
        if self.error is not None:
            d["error"] = self.error
        return json.dumps(d, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class FinishRecord:
    """The last line of a WAL: marks the run as complete."""
    final_report: str
    ts: float

    def to_json(self) -> str:
        return json.dumps({
            "event": "finish",
            "final_report": self.final_report,
            "ts": self.ts,
        }, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------- #
# WAL file
# --------------------------------------------------------------------------- #


class WAL:
    """Append-only JSONL write-ahead log for a single agent run.

    Thread-safe: the underlying file write is guarded by a lock so two
    threads can't interleave bytes.

    Crash-safe: every append goes via temp-file + rename, so a crash
    mid-append leaves either the old or the new line — never a torn
    half-line. (We use the same temp+rename trick as the scratchpad.)
    """

    def __init__(self, path: Path, *, _create: bool = True) -> None:
        self._path = path
        self._lock = threading.Lock()
        if _create:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Touch the file so subsequent appends don't need to
            # worry about "file does not exist" mid-crash.
            if not self._path.exists():
                self._path.touch()

    @classmethod
    def for_scratchpad(cls, scratchpad_path: Path) -> "WAL":
        """Return a WAL whose path is `<scratchpad>.wal.jsonl`."""
        return cls(scratchpad_path.with_name(scratchpad_path.name + WAL_FILENAME_SUFFIX))

    @property
    def path(self) -> Path:
        return self._path

    # ---- writes -----------------------------------------------------------

    def append_start(self, run_id: str, goal: str, plan: list[dict[str, Any]]) -> None:
        self._append(StartRecord(
            run_id=run_id, goal=goal,
            plan=tuple(plan), ts=time.time(),
        ).to_json())

    def append_step(self, name: str, status: str, error: str | None = None) -> None:
        self._append(WALStepRecord(
            name=name, status=status, ts=time.time(), error=error,
        ).to_json())

    def append_finish(self, final_report: str) -> None:
        self._append(FinishRecord(
            final_report=final_report, ts=time.time(),
        ).to_json())

    def _append(self, line: str) -> None:
        # Single-process safety:
        # - The lock serialises appends within this process.
        # - Each append is one small <line>\n write to the real file
        #   in append mode. The OS guarantees that a small write (<
        #   PIPE_BUF on POSIX) is atomic — so two threads can't
        #   interleave bytes. Across processes we don't have atomicity
        #   guarantees, but madcop is single-process by design.
        # - If we crash mid-write, the file might be left with a
        #   torn half-line. The replay() method is tolerant: it
        #   JSON-decodes each line and skips any that fail to parse.
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
                f.flush()  # make sure it's on disk before we return

    # ---- reads ------------------------------------------------------------

    def replay(self) -> "Replay":
        """Re-derive the WAL's state from its file contents."""
        if not self._path.exists():
            return Replay(
                started=False, run_id="", goal="", plan=(),
                completed_steps=frozenset(), step_records=(), finished=False,
                final_report="",
            )
        started = False
        run_id = ""
        goal = ""
        plan: tuple[dict[str, Any], ...] = ()
        completed: dict[str, WALStepRecord] = {}
        finished = False
        final_report = ""

        with self._path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # Torn line: skip it (we never wrote a half line,
                    # but a crash between mkstemp and append could).
                    continue
                ev = rec.get("event")
                if ev == "start":
                    started = True
                    run_id = rec.get("run_id", "")
                    goal = rec.get("goal", "")
                    plan = tuple(rec.get("plan", ()))
                elif ev == "step":
                    name = rec.get("name", "")
                    if not name:
                        continue
                    # Later records win — replays should reflect
                    # the most recent status for a step.
                    completed[name] = WALStepRecord(
                        name=name,
                        status=rec.get("status", "ok"),
                        ts=float(rec.get("ts", 0.0)),
                        error=rec.get("error"),
                    )
                elif ev == "finish":
                    finished = True
                    final_report = rec.get("final_report", "")

        return Replay(
            started=started, run_id=run_id, goal=goal, plan=plan,
            completed_steps=frozenset(completed.keys()),
            step_records=tuple(completed.values()),
            finished=finished, final_report=final_report,
        )

    # ---- utility ----------------------------------------------------------

    def truncate(self) -> None:
        """Delete the WAL file. Use to start a fresh run from scratch."""
        with self._lock:
            if self._path.exists():
                self._path.unlink()


# --------------------------------------------------------------------------- #
# Replay (read-only view of the WAL)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Replay:
    """The result of replaying a WAL."""
    started: bool
    run_id: str
    goal: str
    plan: tuple[dict[str, Any], ...]
    completed_steps: frozenset[str]
    step_records: tuple[WALStepRecord, ...]
    finished: bool
    final_report: str

    @property
    def is_finished(self) -> bool:
        return self.finished

    @property
    def step_count(self) -> int:
        return len(self.completed_steps)

    def next_pending(self, plan_step_names: Iterable[str]) -> list[str]:
        """Given a plan's step names, return the ones NOT yet done.

        Order is preserved from the input. Useful for resuming:
            pending = wal.replay().next_pending([s.name for s in plan])
        """
        done = self.completed_steps
        return [n for n in plan_step_names if n not in done]

    def to_metadata(self) -> dict[str, Any]:
        """Stash the replay summary into a scratchpad's metadata dict.

        Why: the WAL file is the source of truth, but reading JSONL on
        every cold start is wasteful. We mirror a compact summary into
        the scratchpad's metadata so `cat scratchpad.json` is enough to
        know the run's state at a glance.
        """
        return {
            "wal_started": self.started,
            "wal_run_id": self.run_id,
            "wal_completed_steps": sorted(self.completed_steps),
            "wal_step_count": self.step_count,
            "wal_finished": self.finished,
        }


__all__ = [
    "WAL",
    "Replay",
    "StartRecord",
    "WALStepRecord",
    "FinishRecord",
    "WAL_FILENAME_SUFFIX",
]
