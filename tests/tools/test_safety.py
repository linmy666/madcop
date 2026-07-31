"""Tests for tool input validation (security-critical)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from madcop.tools.safety import WriteFileInput, EditFileInput, ReadFileInput, BashInput


class TestWriteFileInput:
    """Path guardrails for WriteFileTool."""

    @pytest.mark.parametrize("path", [
        "/etc/passwd",
        "/System/Library/test",
        "/home/user/.ssh/id_rsa",
        "/home/user/.aws/credentials",
        "/home/user/.kube/config",
        "/home/user/.netrc",
        "/home/user/.gnupg/gpg.conf",
        "/home/user/.madcop/master.key",
        "/home/user/.madcop/settings.json",
        "/home/user/.docker/config.json",
    ])
    def test_blocked_paths(self, path: str):
        with pytest.raises((ValidationError, ValueError)):
            WriteFileInput(path=path, content="test")

    @pytest.mark.parametrize("path", [
        "/tmp/test.py",
        "/home/user/project/src/main.py",
        "/Users/me/code/app.ts",
    ])
    def test_allowed_paths(self, path: str):
        obj = WriteFileInput(path=path, content="test")
        assert obj.path == path

    def test_empty_path_rejected(self):
        with pytest.raises(ValidationError):
            WriteFileInput(path="", content="test")

    def test_content_too_long(self):
        with pytest.raises(ValidationError):
            WriteFileInput(path="/tmp/x", content="x" * 2_000_000)


class TestEditFileInput:
    """Path guardrails for EditFileTool (same as WriteFile)."""

    @pytest.mark.parametrize("path", [
        "/etc/passwd",
        "/home/user/.ssh/config",
        "/home/user/.aws/credentials",
        "/home/user/.madcop/master.key",
    ])
    def test_blocked_paths(self, path: str):
        with pytest.raises((ValidationError, ValueError)):
            EditFileInput(path=path, old_string="x", new_string="y")

    def test_allowed_paths(self):
        obj = EditFileInput(path="/tmp/test.py", old_string="a", new_string="b")
        assert obj.path == "/tmp/test.py"


class TestBashInput:
    """Command guardrails."""

    def test_basic_command(self):
        obj = BashInput(command="ls -la")
        assert obj.command == "ls -la"

    def test_sudo_blocked(self):
        with pytest.raises((ValidationError, ValueError)):
            BashInput(command="sudo rm -rf /")

    def test_rm_rf_root_blocked(self):
        with pytest.raises((ValidationError, ValueError)):
            BashInput(command="rm -rf /")

    def test_normal_rm_allowed(self):
        obj = BashInput(command="rm -rf node_modules/")
        assert obj.command == "rm -rf node_modules/"
