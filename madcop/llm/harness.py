"""Multi-LLM harness profiles.

Different providers claim "OpenAI-compatible" but diverge on:
  - max token field name (max_tokens vs max_completion_tokens)
  - temperature / top_p support (o1/o3 often reject temperature)
  - reasoning controls (reasoning_effort, thinking, enable_thinking)
  - auth headers (Bearer vs x-api-key + anthropic-version)
  - tool-call quirks (parallel tools, tool_choice values)

``ProviderHarness`` encapsulates these differences so the chat client
and agent loop don't hard-code vendor names everywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class ProviderHarness:
    """One provider/model family's API quirks."""

    name: str = "openai_chat"
    # Request shape
    max_tokens_field: str = "max_tokens"  # or max_completion_tokens
    supports_temperature: bool = True
    supports_top_p: bool = True
    supports_tools: bool = True
    supports_parallel_tools: bool = True
    # Reasoning / thinking
    reasoning_mode: str = "none"  # none | openai_effort | deepseek_thinking | minimax
    # Auth / headers beyond Authorization: Bearer
    extra_headers: dict[str, str] = field(default_factory=dict)
    # Prefer streaming tool deltas (False for some broken proxies)
    stream_tool_calls: bool = True
    # Optional default context window hint (tokens)
    default_context_window: int | None = None

    def build_chat_kwargs(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None,
        max_tokens: int | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        top_p: float | None,
        effort: str | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Assemble kwargs for openai.chat.completions.create (or compatible)."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if self.supports_temperature and temperature is not None:
            kwargs["temperature"] = temperature
        if self.supports_top_p and top_p is not None:
            kwargs["top_p"] = top_p
        if max_tokens is not None:
            kwargs[self.max_tokens_field] = max_tokens
        if tools and self.supports_tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
            if not self.supports_parallel_tools:
                # Best-effort: many gateways honor this OpenAI field.
                kwargs["parallel_tool_calls"] = False
        extra_body = self._reasoning_extra_body(effort, model)
        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    def _reasoning_extra_body(self, effort: str | None, model: str) -> dict[str, Any] | None:
        if not effort or effort == "auto":
            return None
        if self.reasoning_mode == "openai_effort":
            level_map = {"low": "low", "medium": "medium", "high": "high", "max": "xhigh"}
            return {"reasoning_effort": level_map.get(effort, "medium")}
        if self.reasoning_mode == "deepseek_thinking":
            # DeepSeek R1 / many China gateways
            return {"thinking": {"type": "enabled"}}
        if self.reasoning_mode == "minimax":
            # MiniMax reasoning models often use extra_body.reasoning
            return {"reasoning_split": True}
        return None


# --- Profile library -------------------------------------------------------- #

_OPENAI_CHAT = ProviderHarness(
    name="openai_chat",
    default_context_window=128_000,
)

_OPENAI_REASONING = ProviderHarness(
    name="openai_reasoning",
    max_tokens_field="max_completion_tokens",
    supports_temperature=False,
    supports_top_p=False,
    reasoning_mode="openai_effort",
    default_context_window=200_000,
)

_DEEPSEEK = ProviderHarness(
    name="deepseek",
    reasoning_mode="deepseek_thinking",
    default_context_window=64_000,
)

_ANTHROPIC_COMPAT = ProviderHarness(
    name="anthropic_compatible",
    # Many Claude proxies still speak OpenAI chat schema on /v1
    extra_headers={"anthropic-version": "2023-06-01"},
    default_context_window=200_000,
)

_MINIMAX = ProviderHarness(
    name="minimax",
    reasoning_mode="minimax",
    default_context_window=200_000,
)

_GLM = ProviderHarness(
    name="glm",
    supports_parallel_tools=False,  # some GLM endpoints are flaky with parallel tools
    default_context_window=128_000,
)

_QWEN = ProviderHarness(
    name="qwen",
    default_context_window=128_000,
)

_DEFAULT = _OPENAI_CHAT


def resolve_harness(
    *,
    model: str | None = None,
    api_format: str | None = None,
    runtime_kind: str | None = None,
    base_url: str | None = None,
    preset_id: str | None = None,
) -> ProviderHarness:
    """Pick the best harness from provider metadata + model id."""
    model_l = (model or "").lower()
    fmt = (api_format or "openai_chat").lower()
    runtime = (runtime_kind or "").lower()
    url = (base_url or "").lower()
    preset = (preset_id or "").lower()

    # Explicit format / runtime wins
    if fmt == "anthropic" or runtime in ("anthropic_compatible", "anthropic"):
        return _ANTHROPIC_COMPAT
    if fmt == "openai_responses":
        # Still use chat path but reasoning-friendly defaults
        return replace(_OPENAI_REASONING, name="openai_responses")

    # Model-id heuristics
    if re.search(r"(?:^|/)(o1|o3|o4)[-_a-z0-9]*$|gpt-5", model_l):
        return _OPENAI_REASONING
    if "deepseek" in model_l or "deepseek" in url or "deepseek" in preset:
        return _DEEPSEEK
    if "minimax" in model_l or "minimax" in url or "minimax" in preset:
        return _MINIMAX
    if "glm" in model_l or "zhipu" in url or "bigmodel" in url:
        return _GLM
    if "qwen" in model_l or "dashscope" in url or "aliyun" in url:
        return _QWEN
    if "claude" in model_l or "anthropic" in url:
        return _ANTHROPIC_COMPAT

    return _DEFAULT


def infer_context_window(model: str | None, harness: ProviderHarness | None = None) -> int:
    """Best-effort context window for UI/budgeting."""
    m = (model or "").lower()
    table = {
        "gpt-4o": 128_000,
        "gpt-4.1": 1_047_576,
        "gpt-4-turbo": 128_000,
        "gpt-3.5": 16_385,
        "o1": 200_000,
        "o3": 200_000,
        "claude-3": 200_000,
        "claude-sonnet": 200_000,
        "claude-opus": 200_000,
        "deepseek": 64_000,
        "minimax": 200_000,
        "glm-4": 128_000,
        "qwen": 128_000,
        "gemini": 1_000_000,
    }
    for key, val in table.items():
        if key in m:
            return val
    if harness and harness.default_context_window:
        return harness.default_context_window
    return 128_000
