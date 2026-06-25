"""Tests for v0.7.1 config loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from madcop.config import (
    Config,
    CostConfig,
    DEFAULT_CONFIG_DICT,
    DEFAULT_CONFIG_PATH,
    MemoryConfig,
    ProviderConfig,
    RouterConfig,
    _parse_simple_yaml,
    _resolve_env,
    load_config,
    resolve_provider,
    save_default_config,
)


# ---------------------------------------------------------------------------
# Env var resolution
# ---------------------------------------------------------------------------


def test_resolve_env_keeps_literal_strings():
    assert _resolve_env("hello") == "hello"
    assert _resolve_env("sk-1234") == "sk-1234"


def test_resolve_env_substitutes_set_var(monkeypatch):
    monkeypatch.setenv("MADCOP_TEST_KEY", "secret-abc")
    assert _resolve_env("$MADCOP_TEST_KEY") == "secret-abc"


def test_resolve_env_passes_through_unset_var():
    assert _resolve_env("$MADCOP_DEFINITELY_UNSET_XYZ") == "$MADCOP_DEFINITELY_UNSET_XYZ"


# ---------------------------------------------------------------------------
# YAML parser
# ---------------------------------------------------------------------------


def test_yaml_parser_flat():
    raw = _parse_simple_yaml("name: alice\nage: 30\n")
    assert raw == {"name": "alice", "age": "30"}


def test_yaml_parser_nested():
    raw = _parse_simple_yaml("""
providers:
  primary:
    base_url: https://api.openai.com/v1
    api_key: $OPENAI_API_KEY
  fast:
    base_url: https://other/v1
""")
    assert raw["providers"]["primary"]["base_url"] == "https://api.openai.com/v1"
    assert raw["providers"]["primary"]["api_key"] == "$OPENAI_API_KEY"
    assert raw["providers"]["fast"]["base_url"] == "https://other/v1"


def test_yaml_parser_strips_quotes():
    raw = _parse_simple_yaml('name: "alice"\n')
    assert raw["name"] == "alice"


def test_yaml_parser_strips_comments():
    raw = _parse_simple_yaml("# top comment\nname: alice  # inline\n")
    assert raw == {"name": "alice"}


def test_yaml_parser_rejects_tabs():
    with pytest.raises(ValueError, match="tabs"):
        _parse_simple_yaml("name:\tvalue\n")


def test_yaml_parser_raises_on_missing_colon():
    with pytest.raises(ValueError):
        _parse_simple_yaml("name alice\n")


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_returns_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "does-not-exist.yaml")
    assert isinstance(cfg, Config)
    # Defaults should be applied
    assert "primary" in cfg.providers
    assert "fast" in cfg.providers
    assert cfg.router.mode == "auto"
    assert cfg.cost.budget_per_run_usd == 5.0
    assert cfg.memory.growth_enabled is True


def test_load_config_reads_custom_file(tmp_path):
    path = tmp_path / "my-config.yaml"
    path.write_text("""
providers:
  my_provider:
    base_url: https://my.api/v1
    api_key: sk-xyz
    model: my-model
router:
  mode: manual
  manual_tier:
    T1: my_provider
    T2: my_provider
    T3: my_provider
cost:
  budget_per_run_usd: 1.0
memory:
  path: /tmp/my-mem.db
  growth_enabled: false
  auto_distill: false
  auto_feedback: true
""", encoding="utf-8")
    cfg = load_config(path)
    assert "my_provider" in cfg.providers
    p = cfg.provider("my_provider")
    assert p.base_url == "https://my.api/v1"
    assert p.api_key == "sk-xyz"
    assert p.model == "my-model"
    assert cfg.router.mode == "manual"
    assert cfg.router.manual_tier["T1"] == "my_provider"
    assert cfg.cost.budget_per_run_usd == 1.0
    assert cfg.memory.path == "/tmp/my-mem.db"
    assert cfg.memory.growth_enabled is False


def test_load_config_raises_on_malformed(tmp_path):
    path = tmp_path / "bad-config.yaml"
    path.write_text("name: alice\n\t\tno tabs allowed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="failed to parse"):
        load_config(path)


# ---------------------------------------------------------------------------
# resolve_provider
# ---------------------------------------------------------------------------


def test_resolve_provider_resolves_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_TEST_KEY", "resolved-123")
    path = tmp_path / "cfg.yaml"
    path.write_text("""
providers:
  p:
    base_url: https://x
    api_key: $MY_TEST_KEY
    model: m
""", encoding="utf-8")
    cfg = load_config(path)
    p = resolve_provider(cfg, "p")
    assert p.api_key == "resolved-123"


def test_resolve_provider_raises_on_unknown(tmp_path):
    path = tmp_path / "cfg.yaml"
    # Use a real provider so the load doesn't trip on the empty mapping
    path.write_text("providers:\n  dummy:\n    base_url: x\n    api_key: y\n    model: z\n", encoding="utf-8")
    cfg = load_config(path)
    with pytest.raises(KeyError, match="not in config"):
        resolve_provider(cfg, "ghost")


# ---------------------------------------------------------------------------
# save_default_config
# ---------------------------------------------------------------------------


def test_save_default_config_creates_file(tmp_path):
    path = tmp_path / "subdir" / "config.yaml"
    out = save_default_config(path)
    assert out == path
    assert path.exists()
    content = path.read_text()
    assert "providers:" in content
    assert "primary" in content
    assert "fast" in content


def test_save_default_config_does_not_overwrite(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("# MY CUSTOM CONFIG\n", encoding="utf-8")
    save_default_config(path)  # no overwrite
    assert path.read_text() == "# MY CUSTOM CONFIG\n"


def test_save_default_config_with_overwrite(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("# OLD\n", encoding="utf-8")
    save_default_config(path, overwrite=True)
    assert "providers:" in path.read_text()


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_default_config_dict_has_required_sections():
    for key in ("providers", "router", "cost", "memory"):
        assert key in DEFAULT_CONFIG_DICT
    # At least one provider with all 3 fields
    for name, p in DEFAULT_CONFIG_DICT["providers"].items():
        assert "base_url" in p
        assert "api_key" in p
        assert "model" in p


def test_default_config_path_points_to_madcop_dir():
    assert ".madcop" in str(DEFAULT_CONFIG_PATH)
    assert str(DEFAULT_CONFIG_PATH).endswith("config.yaml")


def test_dataclasses_are_mutable_for_easy_user_edits():
    """Users will mutate these directly; ensure they're not frozen."""
    cfg = Config()
    cfg.cost.budget_per_run_usd = 0.5
    assert cfg.cost.budget_per_run_usd == 0.5
