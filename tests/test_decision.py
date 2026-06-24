"""Tests for the decision log + diff."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from madcop.decision import (
    Action,
    DecisionDiff,
    DecisionDiffReport,
    DecisionLog,
    DecisionRecord,
    DiffRow,
    append_decision_record_jsonl,
    load_decision_log,
)


# --------------------------------------------------------------------------- #
# DecisionRecord
# --------------------------------------------------------------------------- #

def test_record_signature_is_rule_plus_subject() -> None:
    r = DecisionRecord(
        timestamp="2026-06-15T10:00:00Z",
        rule_id="tms.leadtime.overrun", subject_id="SHIP-7",
        severity=4, recommended_action="expedite_1h",
        actual_action=Action.ACCEPTED,
    )
    assert r.signature == "tms.leadtime.overrun|SHIP-7"


def test_record_was_ignored_true_when_rejected() -> None:
    r = DecisionRecord(
        timestamp="2026-06-15T10:00:00Z",
        rule_id="x", subject_id="y", severity=3,
        recommended_action="a", actual_action=Action.REJECTED,
    )
    assert r.was_ignored is True


def test_record_was_ignored_false_when_accepted() -> None:
    r = DecisionRecord(
        timestamp="2026-06-15T10:00:00Z",
        rule_id="x", subject_id="y", severity=3,
        recommended_action="a", actual_action=Action.ACCEPTED,
    )
    assert r.was_ignored is False


def test_record_was_ignored_true_when_no_action() -> None:
    r = DecisionRecord(
        timestamp="2026-06-15T10:00:00Z",
        rule_id="x", subject_id="y", severity=3,
        recommended_action="a", actual_action=Action.NO_ACTION_TAKEN,
    )
    assert r.was_ignored is True


def test_record_is_frozen() -> None:
    r = DecisionRecord(
        timestamp="t", rule_id="x", subject_id="y", severity=1,
        recommended_action="a", actual_action="accepted",
    )
    with pytest.raises(Exception):
        r.severity = 5  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# DecisionLog
# --------------------------------------------------------------------------- #

def test_log_empty() -> None:
    log = DecisionLog()
    assert len(log) == 0
    assert log.records == ()


def test_log_append_and_extend() -> None:
    log = DecisionLog()
    log.append(DecisionRecord(
        timestamp="t1", rule_id="x", subject_id="y", severity=1,
        recommended_action="a", actual_action=Action.ACCEPTED,
    ))
    log.extend([
        DecisionRecord(
            timestamp="t2", rule_id="x", subject_id="y", severity=2,
            recommended_action="a", actual_action=Action.REJECTED,
        ),
    ])
    assert len(log) == 2


def test_log_clear() -> None:
    log = DecisionLog()
    log.append(DecisionRecord(
        timestamp="t", rule_id="x", subject_id="y", severity=1,
        recommended_action="a", actual_action=Action.ACCEPTED,
    ))
    log.clear()
    assert len(log) == 0


# --------------------------------------------------------------------------- #
# DecisionDiff
# --------------------------------------------------------------------------- #

def test_diff_invalid_args() -> None:
    with pytest.raises(ValueError):
        DecisionDiff(min_ignore_rate=1.5)
    with pytest.raises(ValueError):
        DecisionDiff(min_occurrences=0)


def test_diff_empty_log() -> None:
    rep = DecisionDiff().run(DecisionLog())
    assert rep.n_records == 0
    assert rep.rows == ()
    assert rep.ignored_recommendations == ()


def test_diff_aggregates_by_signature() -> None:
    log = DecisionLog()
    log.extend([
        DecisionRecord(
            timestamp="2026-06-15T10:00:00Z",
            rule_id="tms.leadtime.overrun", subject_id="SHIP-7",
            severity=4, recommended_action="expedite_1h",
            actual_action=Action.ACCEPTED,
        ),
        DecisionRecord(
            timestamp="2026-06-15T11:00:00Z",
            rule_id="tms.leadtime.overrun", subject_id="SHIP-7",
            severity=4, recommended_action="expedite_1h",
            actual_action=Action.NO_ACTION_TAKEN,
        ),
        DecisionRecord(
            timestamp="2026-06-15T12:00:00Z",
            rule_id="oms.cancellation.spike", subject_id="STORE-A",
            severity=5, recommended_action="reroute",
            actual_action=Action.ACCEPTED,
        ),
    ])
    rep = DecisionDiff(min_occurrences=2, min_ignore_rate=0.4).run(log)
    assert rep.n_records == 3
    # Two distinct signatures
    assert len(rep.rows) == 2
    # SHIP-7: 2 occ, 1 accepted → ignore_rate 50% → triggers ignored filter
    sig_ship7 = "tms.leadtime.overrun|SHIP-7"
    rows_by_sig = {r.signature: r for r in rep.rows}
    assert rows_by_sig[sig_ship7].ignore_rate == pytest.approx(0.5)
    # STORE-A: only 1 occ → below min_occurrences → NOT in ignored
    assert "oms.cancellation.spike|STORE-A" not in {r.signature for r in rep.ignored_recommendations}


def test_diff_top_ignored_returns_sorted() -> None:
    log = DecisionLog()
    # SHIP-7: 10 occurrences, 1 accepted → 90% ignore
    for i in range(10):
        log.append(DecisionRecord(
            timestamp=f"2026-06-{(i % 28) + 1:02d}T10:00:00Z",
            rule_id="tms.leadtime.overrun", subject_id="SHIP-7",
            severity=4, recommended_action="expedite_1h",
            actual_action=Action.ACCEPTED if i == 0 else Action.NO_ACTION_TAKEN,
        ))
    # SHIP-8: 3 occurrences, 2 accepted → 33% ignore (below 50%)
    for i in range(3):
        log.append(DecisionRecord(
            timestamp=f"2026-06-{(i % 28) + 1:02d}T11:00:00Z",
            rule_id="tms.leadtime.overrun", subject_id="SHIP-8",
            severity=4, recommended_action="expedite_1h",
            actual_action=Action.ACCEPTED if i < 2 else Action.NO_ACTION_TAKEN,
        ))
    rep = DecisionDiff(min_ignore_rate=0.5).run(log)
    top = rep.top_ignored(3)
    assert len(top) >= 1
    # SHIP-7 should be first (most occurrences + highest ignore)
    assert top[0].signature == "tms.leadtime.overrun|SHIP-7"


def test_diff_records_last_seen() -> None:
    log = DecisionLog()
    log.extend([
        DecisionRecord(
            timestamp="2026-06-15T10:00:00Z",
            rule_id="x", subject_id="y", severity=1,
            recommended_action="a", actual_action=Action.ACCEPTED,
        ),
        DecisionRecord(
            timestamp="2026-06-20T10:00:00Z",
            rule_id="x", subject_id="y", severity=1,
            recommended_action="a", actual_action=Action.ACCEPTED,
        ),
    ])
    rep = DecisionDiff().run(log)
    assert rep.rows[0].last_seen_at == "2026-06-20T10:00:00Z"


# --------------------------------------------------------------------------- #
# JSONL I/O
# --------------------------------------------------------------------------- #

def test_append_then_load_roundtrip(tmp_path: Path) -> None:
    log = DecisionLog()
    log.extend([
        DecisionRecord(
            timestamp="2026-06-15T10:00:00Z",
            rule_id="x", subject_id="y", severity=1,
            recommended_action="a", actual_action=Action.ACCEPTED,
        ),
        DecisionRecord(
            timestamp="2026-06-15T11:00:00Z",
            rule_id="x", subject_id="y", severity=1,
            recommended_action="a", actual_action=Action.NO_ACTION_TAKEN,
        ),
    ])
    p = tmp_path / "decisions.jsonl"
    append_decision_record_jsonl(log, p)
    log2 = load_decision_log(p)
    assert len(log2) == 2
    assert log2.records[0].subject_id == "y"


def test_load_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "decisions.jsonl"
    lines = [
        json.dumps({
            "timestamp": "2026-06-15T10:00:00Z",
            "rule_id": "x", "subject_id": "y", "severity": 1,
            "recommended_action": "a", "actual_action": "accepted",
        }),
        "",
        json.dumps({
            "timestamp": "2026-06-15T11:00:00Z",
            "rule_id": "x", "subject_id": "y", "severity": 1,
            "recommended_action": "a", "actual_action": "no_action_taken",
        }),
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    log = load_decision_log(p)
    assert len(log) == 2