"""Tests for the provider registry."""
from __future__ import annotations

import os
import pytest

from madcop.strategy.providers import (
    ProviderSpec,
    ProviderRegistry,
    DEFAULT_PROVIDERS,
    register_default_providers,
)


def test_default_providers_includes_nvidia_and_zhipu():
    names = {p.name for p in DEFAULT_PROVIDERS}
    assert "nvidia_nim" in names
    assert "nvidia_glm" in names
    assert "zhipu" in names
    assert "openai" in names
    assert "deepseek" in names


def test_provider_spec_is_immutable():
    """ProviderSpec is frozen — accidental mutation would corrupt the registry."""
    p = DEFAULT_PROVIDERS[0]
    with pytest.raises((AttributeError, Exception)):
        p.base_url = "http://attacker.example.com"  # type: ignore[misc]


def test_provider_resolves_api_key_from_env(monkeypatch):
    monkeypatch.setenv("MADCOP_TEST_KEY", "sk-test-abc123")
    p = ProviderSpec(
        name="test_provider",
        base_url="https://example.com/v1",
        api_key_env="MADCOP_TEST_KEY",
        default_model="test-model",
        tier_default="T2",
    )
    assert p.resolve_api_key() == "sk-test-abc123"


def test_provider_returns_none_when_env_missing(monkeypatch):
    monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
    p = ProviderSpec(
        name="test_provider",
        base_url="https://example.com/v1",
        api_key_env="NONEXISTENT_KEY",
        default_model="test-model",
        tier_default="T2",
    )
    assert p.resolve_api_key() is None


def test_registry_get_known_provider():
    reg = ProviderRegistry()
    p = reg.get("nvidia_nim")
    assert p.base_url.startswith("https://")
    assert p.default_model  # non-empty


def test_registry_get_unknown_provider_raises():
    reg = ProviderRegistry()
    with pytest.raises(KeyError, match="Unknown provider"):
        reg.get("nonexistent_provider")


def test_registry_by_tier_returns_first_match():
    reg = ProviderRegistry()
    t1 = reg.by_tier("T1")
    t2 = reg.by_tier("T2")
    t3 = reg.by_tier("T3")
    assert t1 is not None
    assert t1.tier_default == "T1"
    assert t2 is not None
    assert t2.tier_default == "T2"
    assert t3 is None  # no default provider is T3 (T3 is local, no API)


def test_registry_register_new_provider():
    reg = ProviderRegistry()
    custom = ProviderSpec(
        name="my_local_llm",
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        default_model="llama3.1",
        tier_default="T2",
    )
    reg.register(custom)
    assert reg.get("my_local_llm").base_url == "http://localhost:11434/v1"


def test_registry_register_duplicate_raises_without_overwrite():
    reg = ProviderRegistry()
    with pytest.raises(ValueError, match="already registered"):
        reg.register(DEFAULT_PROVIDERS[0])


def test_registry_register_duplicate_with_overwrite_succeeds():
    reg = ProviderRegistry()
    replacement = ProviderSpec(
        name="nvidia_nim",  # same name
        base_url="https://different.example.com/v1",
        api_key_env="DIFFERENT_KEY",
        default_model="different-model",
        tier_default="T2",
    )
    reg.register(replacement, overwrite=True)
    assert reg.get("nvidia_nim").base_url == "https://different.example.com/v1"


def test_registry_cost_per_million():
    reg = ProviderRegistry()
    in_cost, out_cost = reg.cost_per_million("nvidia_nim")
    assert in_cost > 0
    assert out_cost > 0
    assert out_cost >= in_cost  # output always more expensive than input


def test_register_default_providers_into_empty_registry():
    """register_default_providers() into a fresh registry should populate it."""
    reg = ProviderRegistry(providers=())
    register_default_providers(reg)
    assert len(reg.all()) == len(DEFAULT_PROVIDERS)


def test_register_default_providers_is_idempotent():
    """Calling register_default_providers twice should not duplicate."""
    reg = ProviderRegistry()
    register_default_providers(reg)
    n = len(reg.all())
    register_default_providers(reg)
    assert len(reg.all()) == n
