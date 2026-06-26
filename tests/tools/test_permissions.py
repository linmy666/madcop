"""v1.5.0 — Tests for the permission system (action levels + manager)."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from madcop.tools.permissions import (
    ActionLevel,
    ACTION_LEVELS,
    level_for_action,
    Permission,
    DEFAULT_POLICY,
    PermissionEntry,
    PermissionManager,
)


# --------------------------------------------------------------------------- #
# ActionLevel
# --------------------------------------------------------------------------- #


class TestActionLevel:
    def test_ordering_is_monotonic(self):
        assert ActionLevel.READ < ActionLevel.NAVIGATE
        assert ActionLevel.NAVIGATE < ActionLevel.INPUT
        assert ActionLevel.INPUT < ActionLevel.DESTRUCTIVE

    def test_from_str(self):
        assert ActionLevel.from_str("READ") == ActionLevel.READ
        assert ActionLevel.from_str("navigate") == ActionLevel.NAVIGATE
        assert ActionLevel.from_str("Input") == ActionLevel.INPUT
        assert ActionLevel.from_str("DESTRUCTIVE") == ActionLevel.DESTRUCTIVE

    def test_from_str_invalid(self):
        with pytest.raises(ValueError):
            ActionLevel.from_str("bogus")

    def test_level_for_known_actions(self):
        assert level_for_action("screenshot") == ActionLevel.READ
        assert level_for_action("click") == ActionLevel.NAVIGATE
        assert level_for_action("type") == ActionLevel.INPUT
        assert level_for_action("kill_app") == ActionLevel.DESTRUCTIVE

    def test_level_for_unknown_defaults_to_destructive(self):
        assert level_for_action("rm_dash_rf_slash") == ActionLevel.DESTRUCTIVE


# --------------------------------------------------------------------------- #
# PermissionManager basics
# --------------------------------------------------------------------------- #


class TestPermissionManager:
    def test_default_read_is_allowed(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "perms.json")
        assert pm.is_allowed("screenshot")
        assert pm.check("screenshot") == Permission.ALWAYS

    def test_default_navigate_is_once(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "perms.json")
        # ONCE is "allowed" but not persisted
        assert pm.check("click") == Permission.ONCE
        assert Permission.is_allowed(pm.check("click"))

    def test_default_destructive_is_denied(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "perms.json")
        assert pm.check("kill_app") == Permission.DENY
        assert not pm.is_allowed("kill_app")

    def test_session_grant(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "perms.json")
        pm.grant("click", Permission.SESSION)
        assert pm.check("click") == Permission.SESSION
        assert pm.is_allowed("click")

    def test_always_grant(self, tmp_path):
        store = tmp_path / "perms.json"
        pm = PermissionManager(store_path=store)
        pm.grant("type", Permission.ALWAYS)
        assert pm.check("type") == Permission.ALWAYS
        # Persisted
        assert store.exists()
        data = json.loads(store.read_text())
        assert any(e["action"] == "type" for e in data["always"])

    def test_always_survives_restart(self, tmp_path):
        store = tmp_path / "perms.json"
        pm1 = PermissionManager(store_path=store)
        pm1.grant("click", Permission.ALWAYS)
        pm1.grant("type", Permission.ALWAYS)
        del pm1

        pm2 = PermissionManager(store_path=store)
        assert pm2.is_allowed("click")
        assert pm2.is_allowed("type")
        assert pm2.check("click") == Permission.ALWAYS

    def test_once_does_not_persist(self, tmp_path):
        store = tmp_path / "perms.json"
        pm = PermissionManager(store_path=store)
        pm.grant("click", Permission.ONCE)
        # ONCE is not stored — next check goes back to default
        assert pm.check("click") == Permission.ONCE  # default for NAVIGATE
        # No file written
        assert not store.exists()

    def test_revoke(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "perms.json")
        pm.grant("click", Permission.SESSION)
        assert pm.is_allowed("click")
        pm.revoke("click")
        assert pm.check("click") == Permission.ONCE  # back to default

    def test_revoke_always(self, tmp_path):
        store = tmp_path / "perms.json"
        pm = PermissionManager(store_path=store)
        pm.grant("type", Permission.ALWAYS)
        pm.revoke("type")
        # After revoke, should fall back to default
        assert pm.check("type") == Permission.ONCE  # default for INPUT

    def test_reset(self, tmp_path):
        store = tmp_path / "perms.json"
        pm = PermissionManager(store_path=store)
        pm.grant("click", Permission.ALWAYS)
        pm.grant("type", Permission.SESSION)
        pm.reset()
        assert pm.check("click") == Permission.ONCE
        assert pm.check("type") == Permission.ONCE
        # File should be cleared
        if store.exists():
            data = json.loads(store.read_text())
            assert data["always"] == []

    def test_session_does_not_persist_to_file(self, tmp_path):
        store = tmp_path / "perms.json"
        pm = PermissionManager(store_path=store)
        pm.grant("click", Permission.SESSION)
        assert not store.exists() or not json.loads(store.read_text())["always"]


# --------------------------------------------------------------------------- #
# PermissionManager with custom prompt_fn
# --------------------------------------------------------------------------- #


class TestPermissionRequest:
    def test_request_auto_prompt_grants_once(self, tmp_path):
        decisions = ["once"]
        def prompt(action, ctx):
            return decisions.pop(0)
        pm = PermissionManager(store_path=tmp_path / "perms.json", prompt_fn=prompt)
        result = pm.request("click", context="user wants to click button")
        assert result == Permission.ONCE

    def test_request_auto_prompt_grants_session(self, tmp_path):
        decisions = ["session"]
        def prompt(action, ctx):
            return decisions.pop(0)
        pm = PermissionManager(store_path=tmp_path / "perms.json", prompt_fn=prompt)
        result = pm.request("click")
        assert result == Permission.SESSION
        # Subsequent requests should be auto-allowed
        assert pm.request("click") == Permission.SESSION

    def test_request_auto_prompt_grants_always(self, tmp_path):
        decisions = ["always"]
        def prompt(action, ctx):
            return decisions.pop(0)
        pm = PermissionManager(store_path=tmp_path / "perms.json", prompt_fn=prompt)
        result = pm.request("type")
        assert result == Permission.ALWAYS

    def test_request_denied(self, tmp_path):
        decisions = ["no"]
        def prompt(action, ctx):
            return decisions.pop(0)
        pm = PermissionManager(store_path=tmp_path / "perms.json", prompt_fn=prompt)
        result = pm.request("kill_app")
        assert result == Permission.DENY

    def test_request_does_not_prompt_if_already_allowed(self, tmp_path):
        prompt_calls = []
        def prompt(action, ctx):
            prompt_calls.append(action)
            return "always"
        pm = PermissionManager(store_path=tmp_path / "perms.json", prompt_fn=prompt)
        pm.grant("click", Permission.SESSION)
        result = pm.request("click")
        assert result == Permission.SESSION
        assert len(prompt_calls) == 0  # no prompt needed

    def test_request_read_never_prompts(self, tmp_path):
        prompt_calls = []
        def prompt(action, ctx):
            prompt_calls.append(action)
            return "deny"
        pm = PermissionManager(store_path=tmp_path / "perms.json", prompt_fn=prompt)
        result = pm.request("screenshot")
        assert result == Permission.ALWAYS
        assert len(prompt_calls) == 0


# --------------------------------------------------------------------------- #
# Summary / introspection
# --------------------------------------------------------------------------- #


class TestSummary:
    def test_summary_shows_rules(self, tmp_path):
        pm = PermissionManager(store_path=tmp_path / "perms.json")
        pm.grant("click", Permission.SESSION)
        pm.grant("type", Permission.ALWAYS)
        summary = pm.summary()
        assert len(summary["session_rules"]) >= 1
        assert len(summary["always_rules"]) >= 1
        assert "defaults" in summary
