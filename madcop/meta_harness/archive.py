"""Filesystem archive of harness candidates (Meta-Harness D).

Layout under ``~/.madcop/meta_harness/archive/``::

    archive/
      0001_baseline/
        harness.json
        score.json
        traces/case_*.txt
      0002_...
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from madcop.meta_harness.task_harness import ChatTaskHarness, ensure_root


@dataclass
class CandidateRecord:
    id: str
    harness: ChatTaskHarness
    pass_rate: float
    total: int
    passed: int
    failed: int
    created_at: float = field(default_factory=time.time)
    parent_id: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "harness": self.harness.to_dict(),
            "pass_rate": self.pass_rate,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "created_at": self.created_at,
            "parent_id": self.parent_id,
            "notes": self.notes,
        }


class HarnessArchive:
    def __init__(self, root: Path | None = None) -> None:
        base = ensure_root() if root is None else Path(root)
        self.root = base / "archive"
        self.root.mkdir(parents=True, exist_ok=True)

    def _next_id(self) -> str:
        existing = sorted(p.name for p in self.root.iterdir() if p.is_dir())
        n = 1
        if existing:
            try:
                n = int(existing[-1].split("_", 1)[0]) + 1
            except ValueError:
                n = len(existing) + 1
        return f"{n:04d}"

    def write(
        self,
        harness: ChatTaskHarness,
        *,
        pass_rate: float,
        total: int,
        passed: int,
        failed: int,
        parent_id: str | None = None,
        notes: str = "",
        case_traces: dict[str, str] | None = None,
        name_suffix: str | None = None,
    ) -> CandidateRecord:
        cid = self._next_id()
        suffix = name_suffix or harness.name or "candidate"
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in suffix)[:40]
        dirname = f"{cid}_{safe}"
        path = self.root / dirname
        path.mkdir(parents=True, exist_ok=True)
        rec = CandidateRecord(
            id=dirname,
            harness=harness,
            pass_rate=pass_rate,
            total=total,
            passed=passed,
            failed=failed,
            parent_id=parent_id,
            notes=notes,
        )
        (path / "harness.json").write_text(
            json.dumps(harness.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (path / "score.json").write_text(
            json.dumps(rec.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if case_traces:
            tdir = path / "traces"
            tdir.mkdir(exist_ok=True)
            for name, text in case_traces.items():
                safe_n = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60]
                (tdir / f"{safe_n}.txt").write_text(text or "", encoding="utf-8")
        # index line for grepping (proposer-friendly)
        index = self.root / "INDEX.jsonl"
        with index.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        return rec

    def list_candidates(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in sorted(self.root.iterdir()):
            if not p.is_dir():
                continue
            score = p / "score.json"
            if score.exists():
                try:
                    out.append(json.loads(score.read_text(encoding="utf-8")))
                except Exception:
                    out.append({"id": p.name})
        return out

    def best(self) -> dict[str, Any] | None:
        cands = self.list_candidates()
        if not cands:
            return None
        return max(cands, key=lambda c: (c.get("pass_rate") or 0, c.get("passed") or 0))
