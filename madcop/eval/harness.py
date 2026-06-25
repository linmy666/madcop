"""L7 — Eval harness.

AI product managers live and die by their eval harness. This module
gives you:

- `EvalCase`: one test scenario (input + expected output + scorer)
- `EvalRunner`: run N cases through a callable, score, aggregate
- `contains` and `regex_match` scorers built in

Why this matters for AI PM: you can run 50 prompts through your agent,
score each, track pass-rate over time. The single number you watch
go up.

Usage:
    cases = [
        EvalCase(name="mentions_anomaly_count",
                 prompt="...", scorer=contains("3 anomalies")),
        ...
    ]
    runner = EvalRunner(cases)
    report = runner.run(my_agent_fn)
    print(report.pass_rate)
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Callable as _Callable


# --------------------------------------------------------------------------- #
# Scorers
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Score:
    """One scorer's verdict on one case."""
    passed: bool
    detail: str = ""


def contains(needle: str, *, case_sensitive: bool = True) -> _Callable[[str], Score]:
    """Return a scorer that passes if `needle` is found in the output."""
    def _score(output: str) -> Score:
        haystack = output if case_sensitive else output.lower()
        target = needle if case_sensitive else needle.lower()
        return Score(passed=target in haystack, detail=f"contains({needle!r})")
    return _score


def regex_match(pattern: str) -> _Callable[[str], Score]:
    """Return a scorer that passes if the regex matches anywhere in output."""
    compiled = re.compile(pattern)
    def _score(output: str) -> Score:
        m = compiled.search(output)
        return Score(passed=m is not None, detail=f"regex({pattern!r})")
    return _score


def max_length(n: int) -> _Callable[[str], Score]:
    """Pass if output is at most n characters (brevity test)."""
    def _score(output: str) -> Score:
        return Score(passed=len(output) <= n, detail=f"len={len(output)}<=max={n}")
    return _score


ScorerFn = _Callable[[str], Score]


# --------------------------------------------------------------------------- #
# Cases + reports
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class EvalCase:
    """One test scenario."""
    name: str
    prompt: str                                  # user-side input
    scorer: ScorerFn                             # called on the output
    system_prompt: str | None = None             # optional override
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseResult:
    """One case's outcome."""
    case_name: str
    output: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EvalReport:
    """Aggregate over all cases."""
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: tuple[CaseResult, ...] = ()

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

@dataclass
class EvalRunner:
    """Run a set of cases through a callable.

    The callable should accept (prompt: str, system_prompt: str | None)
    and return a string output. This is the simplest possible contract;
    swap for richer agent interfaces as needed.
    """
    cases: list[EvalCase] = field(default_factory=list)

    def run(self, fn: Callable[[str, str | None], str]) -> EvalReport:
        results: list[CaseResult] = []
        for case in self.cases:
            try:
                output = fn(case.prompt, case.system_prompt)
            except Exception as e:  # noqa: BLE001
                output = f"<exception: {type(e).__name__}: {e}>"
            score = case.scorer(output)
            results.append(CaseResult(
                case_name=case.name,
                output=output,
                passed=score.passed,
                detail=score.detail,
            ))
        n_pass = sum(1 for r in results if r.passed)
        n_total = len(results)
        return EvalReport(
            total=n_total,
            passed=n_pass,
            failed=n_total - n_pass,
            pass_rate=(n_pass / n_total) if n_total else 0.0,
            results=tuple(results),
        )

    def add(self, case: EvalCase) -> None:
        self.cases.append(case)


__all__ = [
    "CaseResult",
    "EvalCase",
    "EvalReport",
    "EvalRunner",
    "Score",
    "contains",
    "max_length",
    "regex_match",
]