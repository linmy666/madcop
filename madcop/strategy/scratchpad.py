"""L3 — Disk-backed agent scratchpad.

The scratchpad is the agent's persistent working state across steps.
Every step in plan → execute → verify → replan reads/writes here, so a
crash mid-run can be resumed from the last committed step.

File format: JSON on disk. Each step is a record. Concurrency model:
single-writer (the agent process), no concurrent access. v0.7.0 may add
SQLite if write contention becomes a real issue.

Why JSON, not SQLite:
- Trivially debuggable (`cat scratchpad.json` and see exactly what happened)
- Atomic write via temp-file + rename
- Schema is small and stable
- No SQL injection surface

Path convention: `~/.madcop/runs/<run_id>.json` by default. Override with
  `Scratchpad(path=Path("/tmp/foo.json"))`.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StepRecord:
    """One step in the agent loop."""

    step_index: int
    step_name: str                  # "plan" / "execute" / "verify" / "reflect" / "aggregate"
    tier: str                       # "T1" / "T2" / "T3"
    provider: str
    model: str
    input_summary: str              # truncated to 500 chars
    output_summary: str             # truncated to 500 chars
    input_tokens: int
    output_tokens: int
    cost_usd: float
    wallclock_ms: int
    status: str = "ok"              # "ok" / "failed" / "skipped" / "replan"
    error: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ScratchpadState:
    """The full scratchpad serialised to JSON."""

    run_id: str
    goal: str
    started_at: float
    updated_at: float
    steps: list[StepRecord] = field(default_factory=list)
    plan: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    final_report: str | None = None
    budget_usd: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "steps": [asdict(s) for s in self.steps],
            "plan": self.plan,
            "findings": self.findings,
            "final_report": self.final_report,
            "budget_usd": self.budget_usd,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScratchpadState":
        steps = [StepRecord(**s) for s in d.get("steps", [])]
        return cls(
            run_id=d["run_id"],
            goal=d["goal"],
            started_at=d["started_at"],
            updated_at=d["updated_at"],
            steps=steps,
            plan=d.get("plan", []),
            findings=d.get("findings", []),
            final_report=d.get("final_report"),
            budget_usd=d.get("budget_usd"),
            metadata=d.get("metadata", {}),
        )


# Limits to keep scratchpad files reasonable
MAX_SUMMARY_CHARS = 500
MAX_STEPS_RETENTION = 5000  # if more, oldest get truncated


def _truncate(s: str | None, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 3] + "..."


class Scratchpad:
    """JSON-backed persistent agent state with crash recovery.

    Usage:
        sp = Scratchpad.create(goal="diagnose OMS spike")
        sp.append_step(StepRecord(...))
        sp.set_plan([...])
        # crash here is fine; on next start:
        sp = Scratchpad.load(path)
        # continues from last state
    """

    def __init__(self, state: ScratchpadState, path: Path) -> None:
        self._state = state
        self._path = path
        self._dirty = False

    # ---- factories --------------------------------------------------------

    @classmethod
    def create(
        cls,
        goal: str,
        path: Path | None = None,
        budget_usd: float | None = None,
    ) -> "Scratchpad":
        if path is None:
            path = cls._default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        state = ScratchpadState(
            run_id=uuid.uuid4().hex[:12],
            goal=goal,
            started_at=now,
            updated_at=now,
            budget_usd=budget_usd,
        )
        sp = cls(state, path)
        sp._save()
        return sp

    @classmethod
    def load(cls, path: Path) -> "Scratchpad":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        state = ScratchpadState.from_dict(data)
        return cls(state, path)

    @staticmethod
    def _default_path() -> Path:
        run_id = uuid.uuid4().hex[:8]
        return Path.home() / ".madcop" / "runs" / f"run_{run_id}.json"

    # ---- state accessors ---------------------------------------------------

    @property
    def state(self) -> ScratchpadState:
        return self._state

    @property
    def path(self) -> Path:
        return self._path

    @property
    def run_id(self) -> str:
        return self._state.run_id

    @property
    def step_count(self) -> int:
        return len(self._state.steps)

    def steps(self) -> list[StepRecord]:
        return list(self._state.steps)

    # ---- mutations --------------------------------------------------------

    def append_step(self, step: StepRecord) -> None:
        # Truncate heavy fields to keep file small
        step.input_summary = _truncate(step.input_summary)
        step.output_summary = _truncate(step.output_summary)
        self._state.steps.append(step)
        # Cap retention
        if len(self._state.steps) > MAX_STEPS_RETENTION:
            self._state.steps = self._state.steps[-MAX_STEPS_RETENTION:]
        self._save()

    def set_plan(self, plan: list[dict[str, Any]]) -> None:
        self._state.plan = list(plan)
        self._save()

    def add_finding(self, finding: dict[str, Any]) -> None:
        self._state.findings.append(finding)
        self._save()

    def set_final_report(self, report: str) -> None:
        self._state.final_report = report
        self._save()

    def update_metadata(self, **kwargs: Any) -> None:
        self._state.metadata.update(kwargs)
        self._save()

    # ---- persistence ------------------------------------------------------

    def _save(self) -> None:
        self._state.updated_at = time.time()
        # Atomic write: write to temp file, then rename
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".scratchpad-",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._state.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
            self._dirty = False
        except Exception:
            # Clean up temp on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def save(self) -> None:
        """Force a flush to disk. Usually not needed — mutations auto-save."""
        self._save()


__all__ = [
    "Scratchpad",
    "ScratchpadState",
    "StepRecord",
    "MAX_SUMMARY_CHARS",
]
