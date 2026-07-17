"""Tests for madcop.config.settings — encrypted settings store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from madcop.config import settings as S


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate settings + master key to tmp_path for each test."""
    settings_path = tmp_path / "settings.json"
    key_path = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", key_path)
    S._invalidate_settings_cache()
    yield settings_path, key_path
    S._invalidate_settings_cache()


# --------------------------------------------------------------------------- #
# Encryption
# --------------------------------------------------------------------------- #

def test_encrypt_produces_fernet_prefix(isolated_env):
    _, key_path = isolated_env
    key = S._load_or_create_master_key(key_path)
    enc = S._encrypt("my-secret-key", key)
    assert enc.startswith("fernet:")


def test_decrypt_round_trip(isolated_env):
    _, key_path = isolated_env
    key = S._load_or_create_master_key(key_path)
    original = "sk-test-abc123XYZ"
    enc = S._encrypt(original, key)
    dec = S._decrypt(enc, key)
    assert dec == original


def test_decrypt_empty_returns_empty(isolated_env):
    _, key_path = isolated_env
    key = S._load_or_create_master_key(key_path)
    assert S._decrypt("", key) == ""


def test_decrypt_invalid_token_returns_empty(isolated_env):
    _, key_path = isolated_env
    key = S._load_or_create_master_key(key_path)
    result = S._decrypt("fernet:invalidgarbage", key)
    assert result == ""


def test_master_key_created_with_chmod_600(isolated_env):
    _, key_path = isolated_env
    assert not key_path.exists()
    S._load_or_create_master_key(key_path)
    assert key_path.exists()
    assert oct(key_path.stat().st_mode)[-3:] == "600"


def test_master_key_reused_on_second_call(isolated_env):
    _, key_path = isolated_env
    key1 = S._load_or_create_master_key(key_path)
    key2 = S._load_or_create_master_key(key_path)
    assert key1 == key2


# --------------------------------------------------------------------------- #
# Masking
# --------------------------------------------------------------------------- #

def test_mask_key_long():
    masked = S._mask_key("sk-test-12345678")
    # first 3 + stars + last 4
    assert masked[:3] == "sk-"
    assert masked[-4:] == "5678"
    assert "*" in masked
    assert "test" not in masked


def test_mask_key_short():
    assert S._mask_key("abc") == "***"
    assert S._mask_key("ab") == "**"


def test_mask_key_empty():
    assert S._mask_key("") == ""


# --------------------------------------------------------------------------- #
# Upsert + Save + Load round-trip
# --------------------------------------------------------------------------- #

def test_upsert_creates_new_provider(isolated_env):
    settings = S.load_settings()
    settings = S.upsert_provider(
        settings,
        provider_id="minimax",
        base_url="https://api.minimaxi.com/v1",
        api_key="sk-my-key-12345",
        model="MiniMax-M3",
        label="MiniMax",
    )
    assert len(settings.providers) == 1
    assert settings.active_provider == "minimax"
    p = settings.providers[0]
    assert p.provider_id == "minimax"
    assert p.model == "MiniMax-M3"
    # Key must be encrypted in memory after upsert
    assert p.api_key.startswith("fernet:")
    assert "sk-my-key-12345" not in p.api_key


def test_save_then_load_preserves_data(isolated_env):
    spath, _ = isolated_env
    settings = S.upsert_provider(
        S.load_settings(),
        provider_id="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-key",
        model="gpt-4o-mini",
    )
    S.save_settings(settings, spath)

    # Verify disk has encrypted key
    raw = json.loads(spath.read_text())
    stored = raw["providers"][0]["api_key"]
    assert stored.startswith("fernet:")
    assert "sk-test-key" not in stored

    # Reload
    loaded = S.load_settings(spath)
    assert loaded.active_provider == "openai"
    assert loaded.providers[0].model == "gpt-4o-mini"


def test_settings_file_chmod_600(isolated_env):
    spath, _ = isolated_env
    settings = S.upsert_provider(
        S.load_settings(),
        provider_id="test",
        base_url="http://localhost",
        api_key="key",
        model="m",
    )
    S.save_settings(settings, spath)
    assert oct(spath.stat().st_mode)[-3:] == "600"


# --------------------------------------------------------------------------- #
# Public dict (GET /api/settings)
# --------------------------------------------------------------------------- #

def test_public_dict_masks_keys(isolated_env):
    settings = S.upsert_provider(
        S.load_settings(),
        provider_id="minimax",
        base_url="https://api.minimaxi.com/v1",
        api_key="sk-test-12345678",
        model="MiniMax-M3",
    )
    pub = S.settings_to_public_dict(settings)
    assert pub["active_provider"] == "minimax"
    p = pub["providers"][0]
    assert p["provider_id"] == "minimax"
    assert p["has_key"] is True
    # Masked key must not contain the real key
    assert "12345678" not in p["api_key_masked"]
    # Must show last 4
    assert p["api_key_masked"][-4:] == "5678"
    # Full public dict must not leak plaintext
    assert "sk-test-12345678" not in json.dumps(pub)


def test_public_dict_includes_presets(isolated_env):
    pub = S.settings_to_public_dict(S.load_settings())
    assert "presets" in pub
    ids = [p["id"] for p in pub["presets"]]
    assert "openai" in ids
    assert "minimax" in ids
    assert "custom" in ids


# --------------------------------------------------------------------------- #
# Update without key preserves existing
# --------------------------------------------------------------------------- #

def test_update_without_key_preserves_existing(isolated_env):
    settings = S.upsert_provider(
        S.load_settings(),
        provider_id="minimax",
        base_url="https://api.minimaxi.com/v1",
        api_key="sk-original-key",
        model="MiniMax-M3",
    )
    # Update model only, no api_key
    settings = S.upsert_provider(
        settings,
        provider_id="minimax",
        base_url="",
        api_key="",
        model="MiniMax-M2",
    )
    pub = S.settings_to_public_dict(settings)
    assert pub["providers"][0]["has_key"] is True
    assert pub["providers"][0]["model"] == "MiniMax-M2"


# --------------------------------------------------------------------------- #
# get_active_client_config
# --------------------------------------------------------------------------- #

def test_get_active_client_config_returns_plaintext(isolated_env):
    settings = S.upsert_provider(
        S.load_settings(),
        provider_id="minimax",
        base_url="https://api.minimaxi.com/v1",
        api_key="sk-secret-12345",
        model="MiniMax-M3",
    )
    cfg = S.get_active_client_config(settings)
    assert cfg is not None
    assert cfg["api_key"] == "sk-secret-12345"
    assert cfg["base_url"] == "https://api.minimaxi.com/v1"
    assert cfg["model"] == "MiniMax-M3"


def test_get_active_client_config_returns_none_if_no_key(isolated_env):
    settings = S.upsert_provider(
        S.load_settings(),
        provider_id="minimax",
        base_url="https://api.minimaxi.com/v1",
        api_key="",  # no key
        model="MiniMax-M3",
    )
    cfg = S.get_active_client_config(settings)
    assert cfg is None


def test_get_active_client_config_returns_none_if_empty():
    cfg = S.get_active_client_config(S.Settings())
    assert cfg is None


# --------------------------------------------------------------------------- #
# Multiple providers
# --------------------------------------------------------------------------- #

def test_multiple_providers_and_switch_active(isolated_env):
    s = S.load_settings()
    s = S.upsert_provider(s, provider_id="openai", base_url="http://a", api_key="key-a", model="gpt")
    s = S.upsert_provider(s, provider_id="minimax", base_url="http://b", api_key="key-b", model="m3")

    assert len(s.providers) == 2
    # Last upsert becomes active by default
    assert s.active_provider == "minimax"

    cfg = S.get_active_client_config(s)
    assert cfg["api_key"] == "key-b"

    # Switch active
    s.active_provider = "openai"
    cfg = S.get_active_client_config(s)
    assert cfg["api_key"] == "key-a"
