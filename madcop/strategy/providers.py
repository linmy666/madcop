"""L3 — Provider registry.

A "provider" is any HTTP service that speaks the OpenAI Chat Completions API.
This includes:
- OpenAI (api.openai.com)
- NVIDIA NIM (integrate.api.nvidia.com/v1)
- 智谱 GLM (open.bigmodel.cn/api/paas/v4)
- DeepSeek (api.deepseek.com/v1)
- Qwen / 通义千问 (dashscope.aliyuncs.com/compatible-mode/v1)
- Any self-hosted vLLM / llama.cpp / Ollama OpenAI-compat endpoint

The registry holds provider specs (URL, key env-var, default model, cost).
The agent asks the registry "for tier T1, give me the configured provider
and the call kwargs". v0.6.0 keeps this dumb — no fallback chains, no
retry, no circuit breaker. Those are v0.7.0.

Multi-provider support is the "no vendor lock-in" promise from the PRD.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ProviderSpec:
    """One provider's static config. Immutable.

    Attributes:
        name: short identifier ("nvidia", "zhipu", "openai", ...).
        base_url: full OpenAI-compat base URL (NO trailing slash).
        api_key_env: env-var holding the API key (never the key itself).
        default_model: model id to call when the user doesn't override.
        tier_default: which tier this provider is the default for.
        input_cost_per_million: USD per 1M input tokens (for cost tracking).
        output_cost_per_million: USD per 1M output tokens.
    """

    name: str
    base_url: str
    api_key_env: str
    default_model: str
    tier_default: str  # "T1" / "T2" / "T3" (string, not enum, to avoid cycle)
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0
    notes: str = ""

    def resolve_api_key(self) -> str | None:
        """Read API key from env. Returns None if not set."""
        return os.environ.get(self.api_key_env)


# Default providers registered out of the box.
# The user can override defaults via ~/.madcop/config.yaml later.
DEFAULT_PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="nvidia_nim",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="NVIDIA_NIM_API_KEY",
        default_model="minimax/minimax-m3",
        tier_default="T2",
        input_cost_per_million=0.10,
        output_cost_per_million=0.30,
        notes="NVIDIA NIM hosted models. OpenAI-compat. Default T2 (fast).",
    ),
    ProviderSpec(
        name="nvidia_glm",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="NVIDIA_NIM_API_KEY",
        default_model="zhipu/glm-5",
        tier_default="T1",
        input_cost_per_million=0.50,
        output_cost_per_million=1.50,
        notes="GLM 5 hosted on NVIDIA NIM. Strong model for planning.",
    ),
    ProviderSpec(
        name="zhipu",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPUAI_API_KEY",
        default_model="glm-5",
        tier_default="T1",
        input_cost_per_million=0.50,
        output_cost_per_million=1.50,
        notes="智谱 GLM direct. Strong Chinese-model option.",
    ),
    ProviderSpec(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        tier_default="T2",
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        notes="OpenAI. Use gpt-4o for T1, gpt-4o-mini for T2.",
    ),
    ProviderSpec(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        tier_default="T2",
        input_cost_per_million=0.14,
        output_cost_per_million=0.28,
        notes="DeepSeek. Cheap, good at code.",
    ),
)


class ProviderRegistry:
    """Holds provider specs and resolves them by tier or by name."""

    def __init__(
        self,
        providers: tuple[ProviderSpec, ...] = DEFAULT_PROVIDERS,
    ) -> None:
        self._providers: dict[str, ProviderSpec] = {p.name: p for p in providers}

    def get(self, name: str) -> ProviderSpec:
        if name not in self._providers:
            raise KeyError(f"Unknown provider: {name!r}. Known: {list(self._providers)}")
        return self._providers[name]

    def by_tier(self, tier: str) -> ProviderSpec | None:
        """Return the first provider whose `tier_default` matches. None if none."""
        for p in self._providers.values():
            if p.tier_default == tier:
                return p
        return None

    def all(self) -> tuple[ProviderSpec, ...]:
        return tuple(self._providers.values())

    def register(self, spec: ProviderSpec, overwrite: bool = False) -> None:
        if spec.name in self._providers and not overwrite:
            raise ValueError(
                f"Provider {spec.name!r} already registered. Pass overwrite=True to replace."
            )
        self._providers[spec.name] = spec

    # ------------------------------------------------------------------
    # Cost lookup helpers
    # ------------------------------------------------------------------

    def cost_per_million(self, provider_name: str) -> tuple[float, float]:
        spec = self.get(provider_name)
        return (spec.input_cost_per_million, spec.output_cost_per_million)


def register_default_providers(
    registry: ProviderRegistry | None = None,
) -> ProviderRegistry:
    """Convenience: create a fresh registry with defaults."""
    if registry is None:
        return ProviderRegistry()
    for p in DEFAULT_PROVIDERS:
        try:
            registry.register(p, overwrite=False)
        except ValueError:
            pass  # already there
    return registry


__all__ = [
    "ProviderSpec",
    "ProviderRegistry",
    "DEFAULT_PROVIDERS",
    "register_default_providers",
]
