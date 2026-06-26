"""v1.2.0 — Tracing: record every step of an agent run to a JSONL file.

When an agent does 100 things, you want to be able to look at what
happened afterwards without re-running it. Production frameworks
send this data to Langfuse / LangSmith; we write to a local
JSONL file. Cheap, offline, no third-party account.

What we record (one record per `event`):

  {
    "ts": 1234567890.123,
    "event": "plan_start" | "step_start" | "step_end" | "llm_call"
           | "tool_call" | "directive" | "halt" | "error",
    "run_id": "r-abc123",
    "step_name": "load_data",          # may be null
    "data": { ... }                    # event-specific payload
  }

The file format is JSONL (one JSON object per line). You can:
- `tail -f trace.jsonl` to watch in real time
- `jq '.data' trace.jsonl` to extract structured fields
- load it back with `read_traces(path)` for programmatic analysis

We provide:
- `Tracer`: the writer (with thread-safe append, JSONL per-line)
- `TraceMiddleware`: hooks into the v1.0 middleware chain to auto-record
  every step
- `read_traces(path)`: load traces back as a list of dicts
- `print_summary(traces)`: pretty-print a summary to stdout
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_REPLAN,
    HOOK_STEP_END,
    HOOK_STEP_START,
    HookContext,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Tracer (writer)
# --------------------------------------------------------------------------- #


class Tracer:
    """Append-only JSONL writer for agent traces.

    Thread-safe: a single lock serialises writes (small overhead).
    Crash-safe: every line is `flush()`ed before the write returns, so
    a crash doesn't lose buffered events.
    """

    def __init__(self, path: str | Path, *, run_id: str | None = None) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.run_id = run_id or f"r-{uuid.uuid4().hex[:8]}"
        # Create parent dir + touch the file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        # If the file is fresh, write nothing. Otherwise we just append.
        logger.info("[trace] writing to %s (run_id=%s)", self.path, self.run_id)

    def record(
        self,
        event: str,
        *,
        step_name: str | None = None,
        data: dict | None = None,
    ) -> None:
        """Append one event to the trace file.

        Args:
            event: One of "plan_start" / "step_start" / "step_end" /
                "llm_call" / "tool_call" / "directive" / "halt" / "error".
                Free-form strings are also accepted (e.g. "custom").
            step_name: Optional plan step name.
            data: Event-specific structured payload.
        """
        rec = {
            "ts": time.time(),
            "event": event,
            "run_id": self.run_id,
        }
        if step_name is not None:
            rec["step_name"] = step_name
        if data is not None:
            rec["data"] = data
        line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()

    def close(self) -> None:
        """No-op for now; file is closed on every flush."""
        # If we ever add an in-memory buffer, drain it here.


# --------------------------------------------------------------------------- #
# TraceMiddleware (auto-record via the v1.0 chain)
# --------------------------------------------------------------------------- #


class TraceMiddleware:
    """A middleware that auto-records every hook to a Tracer.

    Drop it into your `MiddlewareChain` to get end-to-end traces
    without touching your plan-execute loop.
    """

    name = "trace"

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook == HOOK_PLAN_START:
            self._tracer.record("plan_start", data={"goal": ctx.goal})
        elif ctx.hook == HOOK_STEP_START:
            step = ctx.step
            self._tracer.record("step_start", step_name=getattr(step, "name", None), data={
                "action": getattr(step, "action", ""),
            })
        elif ctx.hook == HOOK_STEP_END:
            step = ctx.step
            outcome = ctx.outcome
            self._tracer.record("step_end", step_name=getattr(step, "name", None), data={
                "success": getattr(outcome, "success", None),
                "cost_usd": getattr(outcome, "cost_usd", None),
                "duration_s": getattr(outcome, "duration_s", None),
                "error": getattr(outcome, "error", None),
                "output_preview": (getattr(outcome, "output", "") or "")[:200],
            })
        elif ctx.hook == HOOK_REPLAN:
            self._tracer.record("replan", data={"plan_steps": len(ctx.plan.steps) if ctx.plan else 0})
        elif ctx.hook == HOOK_PLAN_END:
            self._tracer.record("plan_end", data={
                "step_count": ctx.shared.get("step_count", 0),
            })
        # Always log any directives too
        for d in ctx.directives:
            self._tracer.record("directive", data={"kind": d.kind, "detail": d.detail})


# --------------------------------------------------------------------------- #
# Reading traces back
# --------------------------------------------------------------------------- #


def read_traces(path: str | Path) -> list[dict[str, Any]]:
    """Read all trace records from a JSONL file. Skips malformed lines."""
    out: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return out
    with p.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Tolerate torn last line (crash mid-write)
                continue
    return out


# --------------------------------------------------------------------------- #
# Summary printing
# --------------------------------------------------------------------------- #


def print_summary(traces: list[dict[str, Any]], *, file: Any = None) -> None:
    """Pretty-print a summary of the traces to stdout (or a file).

    The summary is intentionally simple — counts per event type,
    the list of step names, the first/last timestamps. For deeper
    analysis, load the JSONL directly with `read_traces()` and
    run your own queries.
    """
    if file is None:
        from rich.console import Console
        console = Console()
        out = console
    else:
        out = file

    if not traces:
        out.print("[yellow]no traces found[/]")
        return

    # Per-event counts
    counts: dict[str, int] = {}
    step_names: list[str] = []
    for r in traces:
        ev = r.get("event", "?")
        counts[ev] = counts.get(ev, 0) + 1
        sn = r.get("step_name")
        if sn and ev in ("step_start", "step_end"):
            step_names.append(sn)

    run_id = traces[0].get("run_id", "?")
    t_first = traces[0].get("ts", 0)
    t_last = traces[-1].get("ts", 0)
    duration = t_last - t_first if t_first and t_last else 0

    out.print(f"[bold]madcop trace summary[/]  (run_id: {run_id})")
    out.print(f"  events:   {len(traces)}")
    out.print(f"  duration: {duration:.2f}s")
    out.print(f"  steps:    {len(set(step_names))}")
    out.print("  by event:")
    for ev, n in sorted(counts.items()):
        out.print(f"    {ev:20s} {n}")
    if step_names:
        seen = set()
        unique = [s for s in step_names if not (s in seen or seen.add(s))]
        out.print(f"  step order: {' → '.join(unique)}")


__all__ = [
    "Tracer",
    "TraceMiddleware",
    "read_traces",
    "print_summary",
]
