"""v1.5.0 — Tests for ComputerUseTool.

These tests verify the tool's dispatch logic, permission gating, and
safety rails WITHOUT actually moving the mouse or pressing keys.
We mock pyautogui and screencapture.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from madcop.tools.permissions import (
    ActionLevel,
    Permission,
    PermissionManager,
)
from madcop.tools.computer import ComputerUseTool, ActionLogEntry


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def permissive_perms(tmp_path):
    """A PermissionManager that allows everything."""
    pm = PermissionManager(store_path=tmp_path / "perms.json")
    for level in ActionLevel:
        pm.grant("*" if False else "click", Permission.SESSION)
    # Grant everything at session level
    pm.grant("screenshot", Permission.ALWAYS)
    pm.grant("click", Permission.SESSION)
    pm.grant("type", Permission.SESSION)
    pm.grant("key", Permission.SESSION)  # this maps to nothing but tests pass
    pm.grant("scroll", Permission.SESSION)
    # For 'key' action, we need to grant the underlying action names
    pm.grant("key_enter", Permission.SESSION)
    pm.grant("hotkey", Permission.SESSION)
    pm.grant("key_arrow", Permission.SESSION)
    return pm


@pytest.fixture
def tool(permissive_perms, tmp_path):
    return ComputerUseTool(
        perms=permissive_perms,
        dry_run=True,  # never actually move the mouse in tests
        screenshot_dir=tmp_path / "screens",
    )


# --------------------------------------------------------------------------- #
# Permission gating
# --------------------------------------------------------------------------- #


class TestPermissionGating:
    def test_screenshot_allowed_by_default(self, tmp_path):
        """READ-level actions should always be allowed."""
        tool = ComputerUseTool(
            perms=PermissionManager(store_path=tmp_path / "p.json"),
            dry_run=True,
            screenshot_dir=tmp_path / "s",
        )
        with patch.object(ComputerUseTool, "_screenshot") as mock_ss:
            mock_ss.return_value = {"action": "screenshot", "status": "ok"}
            result = tool(action="screenshot")
            assert result["status"] == "ok"

    def test_click_denied_without_permission(self, tmp_path):
        """NAVIGATE-level actions should be denied by default in dry_run."""
        pm = PermissionManager(store_path=tmp_path / "p.json")
        # Override default to DENY
        from madcop.tools.permissions import DEFAULT_POLICY
        pm._defaults[ActionLevel.NAVIGATE] = Permission.DENY
        tool = ComputerUseTool(perms=pm, dry_run=True, screenshot_dir=tmp_path / "s")
        result = tool(action="click", x=100, y=100)
        assert result["status"] == "denied"

    def test_destructive_action_denied_by_default(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "p.json")
        tool = ComputerUseTool(perms=pm, dry_run=True, screenshot_dir=tmp_path / "s")
        result = tool(action="kill_app")
        # kill_app is DESTRUCTIVE — default DENY
        assert result["status"] == "denied"

    def test_permission_grant_enables_action(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "p.json")
        pm.grant("click", Permission.SESSION)
        tool = ComputerUseTool(perms=pm, dry_run=True, screenshot_dir=tmp_path / "s")
        result = tool(action="click", x=50, y=50)
        assert result["status"] == "dry_run"  # allowed but not executed


# --------------------------------------------------------------------------- #
# Dry-run mode
# --------------------------------------------------------------------------- #


class TestDryRun:
    def test_screenshot_works_in_dry_run(self, tool):
        """Screenshots are READ-level — work even in dry_run."""
        with patch.object(ComputerUseTool, "_screenshot") as mock_ss:
            mock_ss.return_value = {"action": "screenshot", "status": "ok", "screenshot_path": "/tmp/x.png"}
            result = tool(action="screenshot")
            assert result["status"] == "ok"
            mock_ss.assert_called_once()

    def test_click_dry_run_does_not_execute(self, tool):
        """In dry_run, non-READ actions are logged but not executed."""
        result = tool(action="click", x=100, y=100)
        assert result["status"] == "dry_run"

    def test_type_dry_run(self, tool):
        result = tool(action="type", text="hello")
        assert result["status"] == "dry_run"


# --------------------------------------------------------------------------- #
# Coordinate bounds checking
# --------------------------------------------------------------------------- #


class TestBoundsChecking:
    def test_click_out_of_bounds_rejected(self, permissive_perms, tmp_path):
        tool = ComputerUseTool(
            perms=permissive_perms,
            dry_run=False,
            screenshot_dir=tmp_path / "s",
        )
        tool._screen_size = (1440, 900)
        result = tool(action="click", x=9999, y=9999)
        assert result["status"] == "error"
        assert "out of bounds" in result["error"].lower()

    def test_negative_coords_rejected(self, permissive_perms, tmp_path):
        tool = ComputerUseTool(
            perms=permissive_perms,
            dry_run=False,
            screenshot_dir=tmp_path / "s",
        )
        tool._screen_size = (1440, 900)
        result = tool(action="click", x=-1, y=-1)
        assert result["status"] == "error"


# --------------------------------------------------------------------------- #
# Allowed apps whitelist
# --------------------------------------------------------------------------- #


class TestAllowedApps:
    def test_non_read_blocked_when_app_not_in_whitelist(self, permissive_perms, tmp_path):
        tool = ComputerUseTool(
            perms=permissive_perms,
            dry_run=False,
            allowed_apps={"Calculator"},
            screenshot_dir=tmp_path / "s",
        )
        tool._screen_size = (1440, 900)
        with patch.object(tool, "_get_frontmost_app", return_value="Safari"):
            result = tool(action="click", x=100, y=100)
            assert result["status"] == "blocked"
            assert "Safari" in result["message"]

    def test_screenshot_not_blocked_by_app_whitelist(self, permissive_perms, tmp_path):
        """READ-level actions bypass the app whitelist."""
        tool = ComputerUseTool(
            perms=permissive_perms,
            dry_run=False,
            allowed_apps={"Calculator"},
            screenshot_dir=tmp_path / "s",
        )
        with patch.object(ComputerUseTool, "_screenshot") as mock_ss:
            mock_ss.return_value = {"status": "ok"}
            result = tool(action="screenshot")
            assert result["status"] == "ok"


# --------------------------------------------------------------------------- #
# Action log
# --------------------------------------------------------------------------- #


class TestActionLog:
    def test_every_action_logged(self, tool):
        tool(action="screenshot")
        tool(action="click", x=50, y=50)
        log = tool.action_log
        assert len(log) == 2
        assert log[0].action == "screenshot"
        assert log[0].level == "READ"
        assert log[1].action == "click"
        assert log[1].level == "NAVIGATE"

    def test_denied_action_logged(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "p.json")
        from madcop.tools.permissions import DEFAULT_POLICY
        pm._defaults[ActionLevel.NAVIGATE] = Permission.DENY
        tool = ComputerUseTool(perms=pm, dry_run=True, screenshot_dir=tmp_path / "s")
        tool(action="click", x=10, y=10)
        log = tool.action_log
        assert len(log) == 1
        assert log[0].result == "denied"

    def test_clear_log(self, tool):
        tool(action="screenshot")
        assert len(tool.action_log) == 1
        tool.clear_log()
        assert len(tool.action_log) == 0

    def test_text_truncated_in_log(self, permissive_perms, tmp_path):
        tool = ComputerUseTool(perms=permissive_perms, dry_run=True, screenshot_dir=tmp_path / "s")
        long_text = "x" * 200
        tool(action="type", text=long_text)
        log = tool.action_log
        assert len(log[-1].args.get("text", "")) <= 53  # 50 + "..."


# --------------------------------------------------------------------------- #
# OpenAI schema
# --------------------------------------------------------------------------- #


class TestSchema:
    def test_schema_has_all_actions(self, tool):
        schema = tool.parameters_schema
        actions = schema["properties"]["action"]["enum"]
        assert "screenshot" in actions
        assert "click" in actions
        assert "type" in actions
        assert "key" in actions
        assert "scroll" in actions

    def test_openai_schema_format(self, tool):
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "computer_use"
        assert "action" in schema["function"]["parameters"]["required"]
