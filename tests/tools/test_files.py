"""v1.6.0 — Tests for file read/write/edit tools."""
from __future__ import annotations

import pytest
from pathlib import Path

from madcop.tools.files import ReadFileTool, WriteFileTool, EditFileTool


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def workspace(tmp_path):
    """Create a temp workspace with some files."""
    (tmp_path / "existing.txt").write_text("line1\nline2\nline3\nline4\nline5\n")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.py").write_text("print('hello')\n")
    return tmp_path


# --------------------------------------------------------------------------- #
# ReadFileTool
# --------------------------------------------------------------------------- #


class TestReadFileTool:
    def test_read_existing(self, workspace):
        tool = ReadFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "existing.txt"))
        assert result.get("path")
        assert "line1" in result["content"]
        assert result["lines"] == 6  # 5 lines + trailing newline

    def test_read_with_offset(self, workspace):
        tool = ReadFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "existing.txt"), offset=3, limit=2)
        assert "line3" in result["content"]
        assert "line4" in result["content"]
        assert "line1" not in result["content"]
        assert result["offset"] == 3

    def test_read_nested(self, workspace):
        tool = ReadFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "subdir" / "nested.py"))
        assert "print" in result["content"]

    def test_read_missing_file(self, workspace):
        tool = ReadFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "ghost.txt"))
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_read_outside_allowlist(self, workspace):
        tool = ReadFileTool(allowed_dirs=[workspace])
        result = tool(path="/etc/passwd")
        assert "error" in result
        assert "outside" in result["error"].lower() or "not allowed" in result["error"].lower()

    def test_read_missing_path_param(self, workspace):
        tool = ReadFileTool(allowed_dirs=[workspace])
        result = tool()
        assert "error" in result

    def test_truncation_flag(self, workspace):
        tool = ReadFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "existing.txt"), limit=2)
        assert result["truncated"] is True
        assert result["total_lines"] == 6


# --------------------------------------------------------------------------- #
# WriteFileTool
# --------------------------------------------------------------------------- #


class TestWriteFileTool:
    def test_write_new_file(self, workspace):
        tool = WriteFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "new.txt"), content="hello world")
        assert result["status"] == "ok"
        assert (workspace / "new.txt").read_text() == "hello world"

    def test_write_overwrites(self, workspace):
        tool = WriteFileTool(allowed_dirs=[workspace])
        tool(path=str(workspace / "existing.txt"), content="replaced")
        assert (workspace / "existing.txt").read_text() == "replaced"

    def test_write_creates_parent_dirs(self, workspace):
        tool = WriteFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "newdir" / "file.txt"), content="nested")
        assert result["status"] == "ok"
        assert (workspace / "newdir" / "file.txt").read_text() == "nested"

    def test_write_outside_allowlist(self, workspace):
        tool = WriteFileTool(allowed_dirs=[workspace])
        result = tool(path="/etc/madcop_test", content="bad")
        assert "error" in result

    def test_write_too_large(self, workspace):
        tool = WriteFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "big.txt"), content="x" * 600_000)
        assert "error" in result
        assert "too large" in result["error"].lower()

    def test_write_empty_content_is_ok(self, workspace):
        """Writing empty string is valid (creates empty file)."""
        tool = WriteFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "empty.txt"), content="")
        assert result["status"] == "ok"

    def test_missing_path(self, workspace):
        tool = WriteFileTool(allowed_dirs=[workspace])
        result = tool(content="no path")
        assert "error" in result


# --------------------------------------------------------------------------- #
# EditFileTool
# --------------------------------------------------------------------------- #


class TestEditFileTool:
    def test_edit_replaces_text(self, workspace):
        tool = EditFileTool(allowed_dirs=[workspace])
        result = tool(
            path=str(workspace / "existing.txt"),
            old_text="line2",
            new_text="LINE TWO",
        )
        assert result["status"] == "ok"
        content = (workspace / "existing.txt").read_text()
        assert "LINE TWO" in content
        assert "line2" not in content

    def test_edit_first_match_only(self, workspace):
        """Only the first occurrence should be replaced."""
        (workspace / "multi.txt").write_text("aaa bbb aaa bbb")
        tool = EditFileTool(allowed_dirs=[workspace])
        tool(path=str(workspace / "multi.txt"), old_text="aaa", new_text="XXX")
        assert (workspace / "multi.txt").read_text() == "XXX bbb aaa bbb"

    def test_edit_old_text_not_found(self, workspace):
        tool = EditFileTool(allowed_dirs=[workspace])
        result = tool(
            path=str(workspace / "existing.txt"),
            old_text="nonexistent",
            new_text="whatever",
        )
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_edit_missing_file(self, workspace):
        tool = EditFileTool(allowed_dirs=[workspace])
        result = tool(path=str(workspace / "ghost"), old_text="a", new_text="b")
        assert "error" in result

    def test_edit_outside_allowlist(self, workspace):
        tool = EditFileTool(allowed_dirs=[workspace])
        result = tool(path="/etc/hosts", old_text="a", new_text="b")
        assert "error" in result
