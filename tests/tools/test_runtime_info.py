"""Tests for get_current_model tool."""

from __future__ import annotations

import json
from unittest.mock import patch

from madcop.tools.runtime_info import (
    GetCurrentModelTool,
    clear_request_runtime,
    set_request_runtime,
    snapshot_current_model,
)


def test_tool_name_and_schema():
    t = GetCurrentModelTool()
    assert t.name == "get_current_model"
    assert t.parameters_schema["required"] == []


def test_snapshot_uses_settings_without_leaking_key():
    fake_cfg = {
        "api_key": "sk-secret-should-not-appear",
        "base_url": "https://api.example.com/v1",
        "model": "Sensenova-6.7-Flash-Lite",
        "provider_id": "p1",
        "label": "Sensenova",
        "api_format": "openai_chat",
        "preset_id": "custom",
    }
    with patch("madcop.config.settings.load_settings"):
        with patch(
            "madcop.config.settings.get_active_client_config",
            return_value=fake_cfg,
        ):
            clear_request_runtime()
            data = snapshot_current_model()
    assert data["effective_model"] == "Sensenova-6.7-Flash-Lite"
    assert data["provider_label"] == "Sensenova"
    assert data["base_url"] == "https://api.example.com/v1"
    blob = json.dumps(data)
    assert "sk-secret" not in blob
    assert "api_key" not in data


def test_request_override_wins_as_effective():
    fake_cfg = {
        "api_key": "x",
        "model": "settings-model",
        "provider_id": "p1",
        "label": "Lab",
        "base_url": "http://localhost",
    }
    with patch("madcop.config.settings.load_settings"):
        with patch(
            "madcop.config.settings.get_active_client_config",
            return_value=fake_cfg,
        ):
            set_request_runtime(model="ui-selected-model", agent_mode="standard")
            data = snapshot_current_model()
            clear_request_runtime()
    assert data["request_model_override"] == "ui-selected-model"
    assert data["effective_model"] == "ui-selected-model"
    assert data["agent_mode"] == "standard"
    assert data["source"] == "request_override"


def test_tool_call_returns_json():
    with patch(
        "madcop.tools.runtime_info.snapshot_current_model",
        return_value={"effective_model": "m1", "provider_id": "p"},
    ):
        out = json.loads(GetCurrentModelTool()())
    assert out["effective_model"] == "m1"


def test_default_registry_includes_tool():
    from madcop.tools import default_registry

    reg = default_registry()
    assert "get_current_model" in reg.names()
