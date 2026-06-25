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
    "EvalTrend",
    "RobustnessProbe",
    "AdversarialChecker",
]


# --------------------------------------------------------------------------- #
# v0.6.0 extensions: trend + robustness + adversarial
# --------------------------------------------------------------------------- #
#
# Inspired by DeerFlow 2.0's per-trace correlation + Langfuse dashboards
# (see ~/.hermes/skills/research/deerflow-architecture-reference.md).
# madcop's take: small, local, file-backed — no Langfuse dependency.


@dataclass(frozen=True)
class TrendPoint:
    """One run's score, recorded for trend tracking."""
    run_id: str
    timestamp: float
    pass_rate: float
    n_total: int
    n_passed: int
    label: str = ""


@dataclass(frozen=True)
class TrendDelta:
    """Result of comparing two TrendPoints."""
    pass_rate_change: float      # current - previous
    direction: str               # "up" / "down" / "flat"
    n_total_change: int
    is_regression: bool          # pass_rate dropped by more than threshold


class EvalTrend:
    """Track eval pass-rate across runs.

    Persists to a JSON-lines file so trends survive across sessions
    (deerflow keeps traces in Langfuse; madcop keeps them in ~/.madcop/trends.jsonl).
    """

    REGRESSION_THRESHOLD = 0.05   # 5pp drop = regression

    def __init__(self, log_path) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._points: list[TrendPoint] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        import json as _json
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = _json.loads(line)
                self._points.append(TrendPoint(**d))
            except Exception:
                continue

    def record(self, report: EvalReport, run_id: str = "", label: str = "") -> TrendPoint:
        import time as _time
        import json as _json
        run_id = run_id or f"run-{int(_time.time())}"
        point = TrendPoint(
            run_id=run_id,
            timestamp=_time.time(),
            pass_rate=report.pass_rate,
            n_total=report.total,
            n_passed=report.passed,
            label=label,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(point.__dict__) + "\n")
        self._points.append(point)
        return point

    def history(self, last_n: int = 20) -> list[TrendPoint]:
        return self._points[-last_n:]

    def delta(self) -> TrendDelta | None:
        """Compare the last two points."""
        if len(self._points) < 2:
            return None
        prev, curr = self._points[-2], self._points[-1]
        change = curr.pass_rate - prev.pass_rate
        if abs(change) < 0.001:
            direction = "flat"
        elif change > 0:
            direction = "up"
        else:
            direction = "down"
        return TrendDelta(
            pass_rate_change=change,
            direction=direction,
            n_total_change=curr.n_total - prev.n_total,
            is_regression=change <= -self.REGRESSION_THRESHOLD,
        )

    def moving_average(self, window: int = 5) -> float | None:
        if len(self._points) < window:
            return None
        recent = self._points[-window:]
        return sum(p.pass_rate for p in recent) / window


# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PerturbationResult:
    """One perturbation's outcome."""
    name: str
    mutated_prompt: str
    output: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RobustnessReport:
    """Result of probing a function with input perturbations."""
    base_passed: bool
    base_output: str
    perturbations: tuple[PerturbationResult, ...] = ()
    n_robust: int = 0            # how many perturbations matched base verdict
    total_perturbations: int = 0
    robustness_score: float = 0.0  # n_robust / total_perturbations


# A small library of free-form mutations — each is a function from
# (prompt, system_prompt) -> (mutated_prompt, mutated_system)
PerturbationFn = _Callable[[str, str | None], tuple[str, str | None]]


def _trim_whitespace(p: str, s: str | None) -> tuple[str, str | None]:
    """Strip all whitespace from the prompt."""
    return ("".join(p.split()), s)


def _add_typos(p: str, s: str | None) -> tuple[str, str | None]:
    """Replace every 5th character with a neighbour key (qwerty-style)."""
    neighbours = {
        "a": "s", "s": "a", "d": "f", "f": "d", "g": "h", "h": "g",
        "j": "k", "k": "j", "l": "k", "e": "r", "r": "e", "t": "y",
        "y": "t", "u": "i", "i": "u", "o": "p", "p": "o", "n": "m", "m": "n",
    }
    out: list[str] = []
    for idx, ch in enumerate(p):
        if idx > 0 and idx % 5 == 0 and ch.lower() in neighbours:
            repl = neighbours[ch.lower()]
            out.append(repl.upper() if ch.isupper() else repl)
        else:
            out.append(ch)
    return ("".join(out), s)


def _wrap_in_fluff(p: str, s: str | None) -> tuple[str, str | None]:
    """Wrap the real prompt in conversational padding."""
    fluff = "Hey, hope you're doing well! Could you please take a look at this: "
    return (fluff + p + " Thanks so much!", s)


def _translate_zh(p: str, s: str | None) -> tuple[str, str | None]:
    """Naive CN → EN 'translation' (replaces a few common words)."""
    replacements = {
        "取消": "cancel", "订单": "order", "激增": "spike",
        "温度": "temperature", "异常": "anomaly", "为什么": "why",
    }
    out = p
    for zh, en in replacements.items():
        out = out.replace(zh, en)
    return (out, s)


class RobustnessProbe:
    """Probe a function's stability under input perturbations.

    The base case (no perturbation) establishes the expected verdict;
    a perturbation "passes" if its scorer's verdict matches the base.
    """

    DEFAULT_PERTURBATIONS: dict[str, PerturbationFn] = {
        "trim_whitespace": _trim_whitespace,
        "typos_qwerty": _add_typos,
        "wrap_in_fluff": _wrap_in_fluff,
        "translate_zh_naive": _translate_zh,
    }

    def __init__(self, perturbations: dict[str, PerturbationFn] | None = None):
        self._perturbs = perturbations or self.DEFAULT_PERTURBATIONS

    def probe(
        self,
        case: EvalCase,
        fn: Callable[[str, str | None], str],
    ) -> RobustnessReport:
        # Base run
        try:
            base_output = fn(case.prompt, case.system_prompt)
        except Exception as e:  # noqa: BLE001
            base_output = f"<exception: {type(e).__name__}: {e}>"
        base_score = case.scorer(base_output)
        base_passed = base_score.passed

        # Perturbations
        results: list[PerturbationResult] = []
        for name, pfn in self._perturbs.items():
            mp = case.prompt
            ms = case.system_prompt
            try:
                mp, ms = pfn(case.prompt, case.system_prompt)
                out = fn(mp, ms)
            except Exception as e:  # noqa: BLE001
                out = f"<exception: {type(e).__name__}: {e}>"
            score = case.scorer(out)
            results.append(PerturbationResult(
                name=name,
                mutated_prompt=mp,
                output=out,
                passed=score.passed,
                detail=score.detail,
            ))

        n_robust = sum(1 for r in results if r.passed == base_passed)
        total = len(results)
        return RobustnessReport(
            base_passed=base_passed,
            base_output=base_output,
            perturbations=tuple(results),
            n_robust=n_robust,
            total_perturbations=total,
            robustness_score=(n_robust / total) if total else 0.0,
        )


# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AdversarialCase:
    """A known-bad input — the agent must REFUSE / HANDLE gracefully."""
    name: str
    prompt: str
    system_prompt: str | None = None
    # Output must contain ALL of these to be considered "safely handled"
    must_contain: tuple[str, ...] = ()
    # Output must contain NONE of these
    must_not_contain: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdversarialResult:
    case_name: str
    output: str
    safe: bool
    missing_required: tuple[str, ...] = ()
    forbidden_found: tuple[str, ...] = ()


class AdversarialChecker:
    """Run known-bad inputs and check the agent handles them safely.

    Not a full red-team suite — this is the L7 "did we ship the safety
    guardrails?" smoke test.
    """

    def __init__(self, cases: list[AdversarialCase] | None = None):
        self.cases: list[AdversarialCase] = cases or []

    def add(self, case: AdversarialCase) -> None:
        self.cases.append(case)

    def run(self, fn: Callable[[str, str | None], str]) -> tuple[AdversarialResult, ...]:
        results: list[AdversarialResult] = []
        for case in self.cases:
            try:
                output = fn(case.prompt, case.system_prompt)
            except Exception as e:  # noqa: BLE001
                output = f"<exception: {type(e).__name__}: {e}>"

            lower = output.lower()
            missing = tuple(s for s in case.must_contain if s.lower() not in lower)
            forbidden = tuple(s for s in case.must_not_contain if s.lower() in lower)
            safe = not missing and not forbidden
            results.append(AdversarialResult(
                case_name=case.name,
                output=output,
                safe=safe,
                missing_required=missing,
                forbidden_found=forbidden,
            ))
        return tuple(results)

    def all_safe(self, results: tuple[AdversarialResult, ...]) -> bool:
        return all(r.safe for r in results)


# Re-export Path lazily so we don't need a top-level import
from pathlib import Path  # noqa: E402