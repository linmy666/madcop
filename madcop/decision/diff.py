"""L6 — Decision log + diff.

Once madcop starts recommending actions on real events, a natural
question emerges: **are humans following the advice?** This module answers
it.

- `DecisionRecord` — one row: anomaly signature + madcop's recommendation
  + the human action taken.
- `DecisionLog` — append-only collection of records.
- `DecisionDiff` — aggregate log by anomaly signature and surface the
  cases where humans keep ignoring madcop's recommendation. High ignore
  rate on the same finding is a "operator overload" signal: either the
  recommendation is bad (model retraining candidate), the operator is
  overwhelmed, or the finding is too noisy.

This is the kind of insight no off-the-shelf monitoring tool produces,
because no off-the-shelf tool owns both the *recommendation* and the
*feedback loop*.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable


# --------------------------------------------------------------------------- #
# Action labels
# --------------------------------------------------------------------------- #

class Action(str):
    """Sentinel action constants. Strings are lowercase for JSON stability."""
    ACCEPTED = "accepted"            # operator adopted madcop's recommendation
    REJECTED = "rejected"            # operator explicitly said no
    NO_ACTION_TAKEN = "no_action_taken"  # anomaly detected but operator did nothing
    DIFFERENT = "different"          # operator did something else


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DecisionRecord:
    """One row in the decision log."""
    timestamp: str                       # ISO 8601 UTC
    rule_id: str
    subject_id: str
    severity: int
    recommended_action: str             # e.g. "expedite_1h"
    actual_action: str                   # one of Action.* values

    @property
    def signature(self) -> str:
        """Stable grouping key: same finding-type on same subject."""
        return f"{self.rule_id}|{self.subject_id}"

    @property
    def was_ignored(self) -> bool:
        return self.actual_action != Action.ACCEPTED


# --------------------------------------------------------------------------- #
# Log (append-only store)
# --------------------------------------------------------------------------- #

class DecisionLog:
    """Append-only in-memory log. Replace with SQLite/JSONL for prod."""

    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []

    def append(self, record: DecisionRecord) -> None:
        self._records.append(record)

    def extend(self, records: Iterable[DecisionRecord]) -> None:
        for r in records:
            self.append(r)

    @property
    def records(self) -> tuple[DecisionRecord, ...]:
        return tuple(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()


# --------------------------------------------------------------------------- #
# Diff
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DiffRow:
    """Aggregated stats for one (rule, subject) signature."""
    signature: str
    rule_id: str
    subject_id: str
    n_occurrences: int
    n_accepted: int
    n_rejected: int
    n_no_action: int
    n_different: int
    ignore_rate: float                  # 1 - accepted/occurrences
    last_seen_at: str

    @property
    def severity(self) -> int:
        """The most recent severity (highest within the window).

        For a dashboard we usually want the worst-case severity, not an
        average, so callers can decide how prominently to flag.
        """
        # We embed the last-seen severity via the caller's record, not here.
        # This default impl returns 0; callers should compute it.
        return 0


@dataclass(frozen=True)
class DecisionDiffReport:
    """Output of `DecisionDiff.run`."""
    n_records: int
    rows: tuple[DiffRow, ...]
    ignored_recommendations: tuple[DiffRow, ...]   # rows with ignore_rate >= min_ignore_rate

    def top_ignored(self, n: int = 3) -> list[DiffRow]:
        return list(self.ignored_recommendations[:n])


def _empty_diff_row(sig: str, rule_id: str, subject_id: str, last_seen: str) -> DiffRow:
    return DiffRow(
        signature=sig,
        rule_id=rule_id,
        subject_id=subject_id,
        n_occurrences=0, n_accepted=0, n_rejected=0,
        n_no_action=0, n_different=0,
        ignore_rate=0.0, last_seen_at=last_seen,
    )


class DecisionDiff:
    """Aggregate a DecisionLog into per-signature stats + ignore signals."""

    def __init__(self, min_ignore_rate: float = 0.5, min_occurrences: int = 2):
        if not 0.0 <= min_ignore_rate <= 1.0:
            raise ValueError(f"min_ignore_rate must be in [0, 1], got {min_ignore_rate}")
        if min_occurrences < 1:
            raise ValueError(f"min_occurrences must be >= 1, got {min_occurrences}")
        self.min_ignore_rate = min_ignore_rate
        self.min_occurrences = min_occurrences

    def run(self, log: DecisionLog) -> DecisionDiffReport:
        grouped: dict[str, list[DecisionRecord]] = defaultdict(list)
        for r in log.records:
            grouped[r.signature].append(r)

        rows: list[DiffRow] = []
        for sig, recs in grouped.items():
            n = len(recs)
            n_acc = sum(1 for r in recs if r.actual_action == Action.ACCEPTED)
            n_rej = sum(1 for r in recs if r.actual_action == Action.REJECTED)
            n_no  = sum(1 for r in recs if r.actual_action == Action.NO_ACTION_TAKEN)
            n_dif = sum(1 for r in recs if r.actual_action == Action.DIFFERENT)
            ignore_rate = 1.0 - (n_acc / n) if n > 0 else 0.0
            last_seen = max(r.timestamp for r in recs)
            rows.append(DiffRow(
                signature=sig,
                rule_id=recs[0].rule_id,
                subject_id=recs[0].subject_id,
                n_occurrences=n,
                n_accepted=n_acc,
                n_rejected=n_rej,
                n_no_action=n_no,
                n_different=n_dif,
                ignore_rate=ignore_rate,
                last_seen_at=last_seen,
            ))

        # Sort: most-occurring + highest-ignore first (operational priority)
        rows.sort(key=lambda r: (-r.n_occurrences, -r.ignore_rate))

        ignored = tuple(
            r for r in rows
            if r.n_occurrences >= self.min_occurrences
            and r.ignore_rate >= self.min_ignore_rate
        )

        return DecisionDiffReport(
            n_records=len(log.records),
            rows=tuple(rows),
            ignored_recommendations=ignored,
        )


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

import json
from pathlib import Path


def load_decision_log(path: str | Path) -> DecisionLog:
    """Load a JSONL file of decision records."""
    log = DecisionLog()
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            log.append(DecisionRecord(
                timestamp=data["timestamp"],
                rule_id=data["rule_id"],
                subject_id=data["subject_id"],
                severity=data["severity"],
                recommended_action=data["recommended_action"],
                actual_action=data["actual_action"],
            ))
    return log


def append_decision_record_jsonl(
    log: DecisionLog, path: str | Path,
) -> None:
    """Append all records in the log to a JSONL file."""
    p = Path(path)
    with p.open("a", encoding="utf-8") as f:
        for r in log.records:
            f.write(json.dumps({
                "timestamp": r.timestamp,
                "rule_id": r.rule_id,
                "subject_id": r.subject_id,
                "severity": r.severity,
                "recommended_action": r.recommended_action,
                "actual_action": r.actual_action,
            }, ensure_ascii=False) + "\n")