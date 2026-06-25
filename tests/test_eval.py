"""Tests for the eval harness."""

from __future__ import annotations

import pytest

from madcop.eval import (
    CaseResult,
    EvalCase,
    EvalReport,
    EvalRunner,
    Score,
    contains,
    max_length,
    regex_match,
)


# --------------------------------------------------------------------------- #
# Scorers
# --------------------------------------------------------------------------- #

def test_contains_passes() -> None:
    s = contains("hello")("hello world")
    assert s.passed is True


def test_contains_fails() -> None:
    s = contains("xyz")("hello world")
    assert s.passed is False


def test_contains_case_insensitive() -> None:
    s = contains("HELLO", case_sensitive=False)("hello world")
    assert s.passed is True


def test_regex_match_passes() -> None:
    s = regex_match(r"\d+")("abc 123 def")
    assert s.passed is True


def test_regex_match_fails() -> None:
    s = regex_match(r"^\d+$")("abc 123 def")
    assert s.passed is False


def test_max_length_passes() -> None:
    s = max_length(10)("short")
    assert s.passed is True
    assert "len=5" in s.detail


def test_max_length_fails() -> None:
    s = max_length(3)("longer than three")
    assert s.passed is False


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def test_runner_empty() -> None:
    report = EvalRunner().run(lambda p, s: "x")
    assert report.total == 0
    assert report.pass_rate == 0.0
    assert report.all_passed is True  # vacuous


def test_runner_all_pass() -> None:
    runner = EvalRunner([
        EvalCase(name="a", prompt="x", scorer=contains("ok")),
        EvalCase(name="b", prompt="y", scorer=contains("ok")),
    ])

    def agent(p, s):
        return "this is ok"
    report = runner.run(agent)
    assert report.passed == 2
    assert report.failed == 0
    assert report.pass_rate == 1.0
    assert report.all_passed


def test_runner_partial_pass() -> None:
    runner = EvalRunner([
        EvalCase(name="a", prompt="x", scorer=contains("ok")),
        EvalCase(name="b", prompt="y", scorer=contains("nope")),
    ])

    def agent(p, s):
        return "this is ok"
    report = runner.run(agent)
    assert report.passed == 1
    assert report.failed == 1
    assert report.pass_rate == 0.5


def test_runner_handles_agent_exception() -> None:
    runner = EvalRunner([
        EvalCase(name="x", prompt="boom", scorer=contains("ok")),
    ])

    def agent(p, s):
        raise RuntimeError("kaboom")
    report = runner.run(agent)
    assert report.failed == 1
    assert "kaboom" in report.results[0].output


def test_runner_add_dynamically() -> None:
    runner = EvalRunner()
    runner.add(EvalCase(name="a", prompt="x", scorer=contains("ok")))
    assert len(runner.cases) == 1


def test_runner_results_have_details() -> None:
    runner = EvalRunner([
        EvalCase(name="x", prompt="p", scorer=contains("needle")),
    ])
    report = runner.run(lambda p, s: "needle found here")
    assert report.results[0].passed is True
    assert "needle" in report.results[0].detail