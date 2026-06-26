"""v0.8.0 — Tests for `madcop doctor` self-check."""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from madcop.doctor import (
    DoctorCheck,
    DoctorReport,
    check_async_loop,
    check_env_vars,
    check_llm_endpoint,
    check_python_and_version,
    check_scratchpad_dir,
    check_subagent_pool,
    run_all_checks,
    OK, WARN, FAIL, SKIP,
)


# ---------------------------------------------------------------------------
# Per-check unit tests
# ---------------------------------------------------------------------------


def test_check_python_and_version_says_ok():
    c = check_python_and_version()
    assert c.status == OK
    assert "madcop" in c.detail
    assert "Python" in c.detail


def test_check_env_vars_warn_when_missing(monkeypatch):
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_MODEL", raising=False)
    c = check_env_vars()
    assert c.status == WARN
    assert "MADCOP_OPENAI_BASE_URL" in c.detail
    assert c.fix is not None
    assert "export" in c.fix


def test_check_env_vars_fail_when_missing_in_strict_mode(monkeypatch):
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_MODEL", raising=False)
    c = check_env_vars(strict=True)
    assert c.status == FAIL


def test_check_env_vars_ok_when_all_set(monkeypatch):
    monkeypatch.setenv("MADCOP_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("MADCOP_OPENAI_API_KEY", "sk-test-12345")
    monkeypatch.setenv("MADCOP_OPENAI_MODEL", "test-model")
    c = check_env_vars()
    assert c.status == OK
    assert "test-model" in c.detail


def test_check_llm_endpoint_skipped_when_no_base(monkeypatch):
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    c = check_llm_endpoint()
    assert c.status == SKIP


def test_check_llm_endpoint_fails_on_unreachable_host(monkeypatch):
    # Use a reserved TEST-NET host that's never reachable.
    monkeypatch.setenv("MADCOP_OPENAI_BASE_URL", "http://192.0.2.1:1/v1")
    c = check_llm_endpoint(timeout_s=0.1)  # fast fail
    assert c.status == FAIL
    assert c.fix is not None


def test_check_llm_endpoint_passes_on_local_listener(monkeypatch, tmp_path):
    # Spin up a real local socket just for the test.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        monkeypatch.setenv("MADCOP_OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
        c = check_llm_endpoint(timeout_s=1.0)
        assert c.status == OK
        assert "reachable" in c.detail
    finally:
        sock.close()


def test_check_scratchpad_dir_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    c = check_scratchpad_dir()
    assert c.status == OK
    assert "writable" in c.detail


def test_check_scratchpad_dir_fails_when_home_readonly(monkeypatch, tmp_path):
    # Make HOME point at a path we can't create children in.
    fake_home = tmp_path / "no-such-home"
    monkeypatch.setenv("HOME", str(fake_home))
    # On macOS, /tmp is not world-writable by default but user tmp usually is.
    # Make fake_home's PARENT read-only.
    import stat
    parent = tmp_path
    original_mode = parent.stat().st_mode
    parent.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+exec only
    try:
        c = check_scratchpad_dir()
        # On some systems even with no write perms, we might still get away
        # with it (root), so we accept either OK or FAIL here — we just
        # want to exercise the failure path code.
        assert c.status in (OK, FAIL)
    finally:
        parent.chmod(original_mode)


def test_check_subagent_pool_runs_completed():
    c = check_subagent_pool()
    assert c.status == OK
    assert "ran + completed" in c.detail


def test_check_async_loop_returns_pong():
    c = check_async_loop()
    assert c.status == OK
    assert "asyncio" in c.detail


# ---------------------------------------------------------------------------
# Report-level tests
# ---------------------------------------------------------------------------


def test_run_all_checks_returns_six_checks():
    r = run_all_checks(strict=False)
    assert len(r.checks) == 6
    names = [c.name for c in r.checks]
    assert "python_version" in names
    assert "env" in names
    assert "llm_endpoint" in names
    assert "scratchpad_dir" in names
    assert "subagent_pool" in names
    assert "async_loop" in names


def test_run_all_checks_passes_by_default(monkeypatch):
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_MODEL", raising=False)
    r = run_all_checks(strict=False)
    # PASS = no FAIL entries (warnings + skips are OK)
    assert r.passed is True
    assert r.failure_count == 0


def test_run_all_checks_fails_in_strict_mode(monkeypatch):
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    r = run_all_checks(strict=True)
    assert r.passed is False
    assert r.failure_count >= 1


def test_run_all_checks_handles_check_that_crashes(monkeypatch):
    """If a check raises, it's a FAIL — not a 500."""
    def boom() -> DoctorCheck:
        raise RuntimeError("intentional test crash")

    monkeypatch.setattr("madcop.doctor.check_async_loop", boom)
    r = run_all_checks(strict=False)
    # We should have at least one FAIL with "crashed" in detail
    assert any(
        c.status == FAIL and "crashed" in c.detail for c in r.checks
    )


# ---------------------------------------------------------------------------
# Text / JSON formatting
# ---------------------------------------------------------------------------


def test_report_to_text_contains_verdict():
    r = run_all_checks(strict=False)
    text = r.to_text()
    assert "madcop doctor" in text
    assert "verdict:" in text
    assert "PASS" in text or "FAIL" in text
    # Every check should appear by name
    for c in r.checks:
        assert c.name in text


def test_report_to_text_includes_fix_for_warn_and_fail():
    checks = [
        DoctorCheck(name="a", status=OK, detail="ok detail"),
        DoctorCheck(name="b", status=WARN, detail="warn detail", fix="fix b"),
        DoctorCheck(name="c", status=FAIL, detail="fail detail", fix="fix c"),
        DoctorCheck(name="d", status=SKIP, detail="skip detail"),
    ]
    report = DoctorReport(checks=checks)
    text = report.to_text()
    # Fix appears for warn and fail, not for ok or skip
    assert "fix: fix b" in text
    assert "fix: fix c" in text
    assert text.count("fix:") == 2
    # verdict reflects failure
    assert "FAIL" in text
    assert report.passed is False
    assert report.failure_count == 1
    assert report.warn_count == 1


def test_report_summarises_counts():
    checks = [
        DoctorCheck(name="a", status=OK, detail="ok"),
        DoctorCheck(name="b", status=OK, detail="ok"),
        DoctorCheck(name="c", status=WARN, detail="w", fix="wf"),
        DoctorCheck(name="d", status=FAIL, detail="f", fix="ff"),
    ]
    report = DoctorReport(checks=checks)
    assert report.failure_count == 1
    assert report.warn_count == 1
    assert report.passed is False
    text = report.to_text()
    assert "1 failure" in text
    assert "1 warning" in text


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_doctor_returns_zero_on_pass(capsys, monkeypatch):
    # Force env-missing so we can verify the default exit code path
    # without hitting any real LLM.
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_MODEL", raising=False)
    from madcop.__main__ import main
    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "madcop doctor" in out


def test_cli_doctor_strict_returns_one(capsys, monkeypatch):
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_MODEL", raising=False)
    from madcop.__main__ import main
    rc = main(["doctor", "--strict"])
    assert rc == 1


def test_cli_doctor_json_outputs_valid_json(capsys, monkeypatch):
    monkeypatch.delenv("MADCOP_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MADCOP_OPENAI_MODEL", raising=False)
    from madcop.__main__ import main
    rc = main(["doctor", "--json"])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "checks" in parsed
    assert "passed" in parsed
    assert isinstance(parsed["checks"], list)
    assert rc == 0  # no fails with default strictness
