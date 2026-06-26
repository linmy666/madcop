"""v1.1.0 — Tests for SubprocessSandbox + BashTool."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from madcop.tools import BashTool, SandboxResult, SubprocessSandbox


# ---------------------------------------------------------------------------
# Basic run
# ---------------------------------------------------------------------------


def test_sandbox_runs_simple_command(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    result = sandbox.run(["echo", "hello"], cwd=tmp_path)
    assert result.success
    assert "hello" in result.stdout
    assert result.returncode == 0
    assert result.argv == ("echo", "hello")


def test_sandbox_string_argv_is_shlex_split(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    result = sandbox.run("echo a b c", cwd=tmp_path)
    assert result.success
    assert "a b c" in result.stdout


def test_sandbox_uses_first_allowed_dir_when_no_cwd(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    result = sandbox.run(["pwd"])
    assert result.success
    assert str(tmp_path.resolve()) in result.stdout


def test_sandbox_returns_error_on_empty_argv():
    sandbox = SubprocessSandbox()
    result = sandbox.run([])
    assert not result.success
    assert result.error is not None
    assert "empty argv" in result.error


def test_sandbox_captures_stderr(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    result = sandbox.run([sys.executable, "-c", "import sys; print('oops', file=sys.stderr)"], cwd=tmp_path)
    assert "oops" in result.stderr


# ---------------------------------------------------------------------------
# Working directory restriction
# ---------------------------------------------------------------------------


def test_sandbox_rejects_cwd_outside_allowed_dirs(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    sandbox = SubprocessSandbox(allowed_dirs=[allowed])
    result = sandbox.run(["ls"], cwd=outside)
    assert not result.success
    assert "not in allowed_dirs" in (result.error or "")


def test_sandbox_allows_cwd_inside_allowed_dirs(tmp_path: Path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    sandbox = SubprocessSandbox(allowed_dirs=[parent])
    result = sandbox.run(["pwd"], cwd=child)
    assert result.success
    # The resolved child is inside parent — should pass
    assert str(child.resolve()) in result.stdout


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_sandbox_kills_long_running_command(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path], default_timeout_s=0.2)
    result = sandbox.run([sys.executable, "-c", "import time; time.sleep(5)"], cwd=tmp_path)
    assert result.timed_out
    assert not result.success


def test_sandbox_per_call_timeout_overrides_default(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path], default_timeout_s=10.0)
    result = sandbox.run([sys.executable, "-c", "import time; time.sleep(2)"], cwd=tmp_path, timeout_s=0.2)
    assert result.timed_out


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------


def test_sandbox_truncates_huge_stdout(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path], max_output_chars=100)
    result = sandbox.run([sys.executable, "-c", "print('x' * 500)"], cwd=tmp_path)
    assert result.output_truncated
    assert len(result.stdout) <= 103  # 100 + "..."
    assert result.stdout.endswith("...")


def test_sandbox_does_not_truncate_short_output(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path], max_output_chars=1000)
    result = sandbox.run([sys.executable, "-c", "print('hi')"], cwd=tmp_path)
    assert not result.output_truncated
    assert "hi" in result.stdout


# ---------------------------------------------------------------------------
# Return code
# ---------------------------------------------------------------------------


def test_sandbox_nonzero_return_is_not_success(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    result = sandbox.run([sys.executable, "-c", "import sys; sys.exit(7)"], cwd=tmp_path)
    assert result.returncode == 7
    assert not result.success


def test_sandbox_command_not_found(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    result = sandbox.run(["definitely_not_a_real_command_xyz123"], cwd=tmp_path)
    assert not result.success
    # Could be 127 (returncode from shell) or our explicit error
    assert result.returncode != 0 or result.error is not None


# ---------------------------------------------------------------------------
# Environment filter
# ---------------------------------------------------------------------------


def test_sandbox_passes_all_env_when_no_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("MADCOP_TEST_VAR", "secret_value")
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])  # no allowed_env_vars
    result = sandbox.run([sys.executable, "-c", "import os; print(os.environ.get('MADCOP_TEST_VAR', ''))"], cwd=tmp_path)
    assert result.success
    assert "secret_value" in result.stdout


def test_sandbox_filters_env_when_allowed_list_given(tmp_path, monkeypatch):
    monkeypatch.setenv("MADCOP_ALLOWED", "yes")
    monkeypatch.setenv("MADCOP_DENIED", "no")
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path], allowed_env_vars=["MADCOP_ALLOWED"])
    code = (
        "import os; "
        "print('ALLOWED=' + os.environ.get('MADCOP_ALLOWED', 'MISSING')); "
        "print('DENIED=' + os.environ.get('MADCOP_DENIED', 'MISSING'))"
    )
    result = sandbox.run([sys.executable, "-c", code], cwd=tmp_path)
    assert "ALLOWED=yes" in result.stdout
    assert "DENIED=MISSING" in result.stdout


def test_sandbox_extras_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("MADCOP_KEY", "from_host")
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path], allowed_env_vars=["MADCOP_KEY"])
    result = sandbox.run(
        [sys.executable, "-c", "import os; print(os.environ.get('MADCOP_KEY', 'missing'))"],
        cwd=tmp_path,
        env={"MADCOP_KEY": "from_extras"},
    )
    assert "from_extras" in result.stdout


# ---------------------------------------------------------------------------
# Stdin
# ---------------------------------------------------------------------------


def test_sandbox_passes_stdin(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    result = sandbox.run(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
        cwd=tmp_path,
        input_data="hello",
    )
    assert "HELLO" in result.stdout


# ---------------------------------------------------------------------------
# BashTool wrapper
# ---------------------------------------------------------------------------


def test_bash_tool_runs_command(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    tool = BashTool(sandbox)
    out = tool(command="echo hi", cwd=str(tmp_path))
    assert out["returncode"] == 0
    assert "hi" in out["stdout"]
    assert out["error"] is None


def test_bash_tool_has_openai_schema():
    sandbox = SubprocessSandbox()
    tool = BashTool(sandbox)
    schema = tool.parameters_schema
    assert schema["type"] == "object"
    assert "command" in schema["properties"]
    assert "command" in schema["required"]


def test_bash_tool_openai_format():
    sandbox = SubprocessSandbox()
    tool = BashTool(sandbox)
    spec = tool.to_openai_schema()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "bash"
    assert "command" in spec["function"]["parameters"]["properties"]


def test_bash_tool_returns_error_dict_on_failure(tmp_path: Path):
    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path])
    tool = BashTool(sandbox)
    out = tool(command="definitely_not_a_command_xyz", cwd=str(tmp_path))
    assert out["returncode"] != 0 or out["error"] is not None


# ---------------------------------------------------------------------------
# SandboxResult
# ---------------------------------------------------------------------------


def test_sandbox_result_success_property():
    ok = SandboxResult(
        argv=("echo",), cwd="/tmp", returncode=0, stdout="", stderr="",
        duration_s=0.0, timed_out=False, output_truncated=False,
    )
    assert ok.success
    fail = SandboxResult(
        argv=("false",), cwd="/tmp", returncode=1, stdout="", stderr="",
        duration_s=0.0, timed_out=False, output_truncated=False,
    )
    assert not fail.success
    timeout = SandboxResult(
        argv=("sleep",), cwd="/tmp", returncode=-1, stdout="", stderr="",
        duration_s=0.0, timed_out=True, output_truncated=False,
    )
    assert not timeout.success
