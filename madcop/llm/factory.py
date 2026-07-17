"""Build ChatClient instances from provider config + harness."""
from __future__ import annotations

from typing import Any

from madcop.llm.client import ChatClient, MockClient, OpenAICompatClient
from madcop.llm.harness import resolve_harness


def build_client_from_config(
    cfg: dict[str, Any] | None,
    *,
    timeout: float = 120.0,
    mock_message: str = "⚠️ No API key configured.",
) -> ChatClient:
    """Create the right client for a provider config dict.

    ``cfg`` is the shape returned by ``get_active_client_config`` (or a
    per-agent override with the same keys).
    """
    if not cfg or not cfg.get("api_key"):
        return MockClient(default_response=mock_message)

    api_format = (cfg.get("api_format") or "openai_chat").lower()
    runtime = (cfg.get("runtime_kind") or "").lower()
    model = cfg.get("model") or ""
    base_url = (cfg.get("base_url") or "").rstrip("/")

    # Native Anthropic Messages API when format is anthropic and endpoint
    # is official Anthropic (or empty). OpenAI-shaped Claude proxies keep
    # using OpenAICompatClient + anthropic_compatible harness.
    if api_format == "anthropic" and (
        not base_url
        or "anthropic.com" in base_url
        or runtime in ("anthropic", "anthropic_native")
    ):
        from madcop.llm.anthropic_client import AnthropicMessagesClient
        return AnthropicMessagesClient(
            api_key=cfg["api_key"],
            base_url=base_url or "https://api.anthropic.com",
            model=model or "claude-sonnet-4-20250514",
            timeout=timeout,
            default_temperature=cfg.get("temperature"),
            default_max_tokens=cfg.get("max_tokens"),
        )

    return OpenAICompatClient(
        api_key=cfg["api_key"],
        base_url=base_url or "https://api.openai.com/v1",
        model=model or "gpt-4o-mini",
        timeout=timeout,
        api_format=cfg.get("api_format"),
        auth_strategy=cfg.get("auth_strategy"),
        runtime_kind=cfg.get("runtime_kind"),
        preset_id=cfg.get("preset_id"),
        top_p=cfg.get("top_p"),
        default_temperature=cfg.get("temperature"),
        default_max_tokens=cfg.get("max_tokens"),
        harness=resolve_harness(
            model=model,
            api_format=cfg.get("api_format"),
            runtime_kind=cfg.get("runtime_kind"),
            base_url=base_url,
            preset_id=cfg.get("preset_id"),
        ),
    )


def merge_agent_routing(
    base_cfg: dict[str, Any] | None,
    routing: dict[str, Any] | None,
    agent_id: str,
) -> dict[str, Any] | None:
    """Overlay per-agent model/sampling onto the active provider config."""
    if not base_cfg:
        return None
    out = dict(base_cfg)
    if not routing:
        return out
    r = routing.get(agent_id) or {}
    if not isinstance(r, dict):
        return out
    if r.get("model"):
        out["model"] = r["model"]
    if r.get("temperature") is not None:
        out["temperature"] = r["temperature"]
    if r.get("max_tokens") is not None:
        out["max_tokens"] = r["max_tokens"]
    if r.get("api_format"):
        out["api_format"] = r["api_format"]
    if r.get("base_url"):
        out["base_url"] = r["base_url"]
    if r.get("api_key"):
        out["api_key"] = r["api_key"]
    return out
