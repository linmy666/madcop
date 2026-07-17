"""Shared chat runtime helpers for SSE and WebSocket paths.

Centralizes settings/sampling resolution and session message persistence
so both transports stay behaviorally aligned.
"""
from __future__ import annotations

import logging
from typing import Any

from madcop.config import settings as settings_store
from madcop.server.session_persist import (
    append_assistant,
    append_user_and_ensure,
    ensure_session,
)

logger = logging.getLogger(__name__)


def load_chat_context() -> tuple[Any, dict[str, Any]]:
    """Return (settings, active_provider_client_config)."""
    try:
        s = settings_store.load_settings()
        cfg = settings_store.get_active_client_config(s) or {}
        return s, cfg
    except Exception as e:
        logger.warning("chat_runtime: load settings failed: %s", e)
        return None, {}


def apply_sampling_defaults(
    *,
    temperature: float | None,
    max_tokens: int | None,
    model: str | None,
    prov_cfg: dict[str, Any],
) -> tuple[float, int]:
    """Resolve temperature/max_tokens from provider config."""
    t = temperature
    m = max_tokens
    if prov_cfg:
        model_name = (model or prov_cfg.get("model") or "").lower()
        overrides = (prov_cfg.get("model_params") or {}).get(model_name, {})
        if overrides:
            t = overrides.get("temperature", t)
            if overrides.get("max_tokens"):
                m = overrides["max_tokens"]
        else:
            t = prov_cfg.get("temperature", t)
            if prov_cfg.get("max_tokens"):
                m = prov_cfg["max_tokens"]
    if m is None:
        m = (prov_cfg or {}).get("max_tokens") or 8192
    if t is None:
        t = (prov_cfg or {}).get("temperature") or 0.7
    return float(t), int(m)


def active_provider_label(settings: Any) -> str:
    if settings is None:
        return ""
    try:
        pub = settings_store.settings_to_public_dict(settings)
        aid = pub.get("active_provider")
        ap = next((p for p in pub.get("providers", []) if p.get("provider_id") == aid), None)
        if ap:
            return ap.get("label") or ap.get("model") or ""
    except Exception as e:
        logger.debug("chat_runtime: label resolve: %s", e)
    return ""


# Re-export persist helpers for a single import surface
__all__ = [
    "load_chat_context",
    "apply_sampling_defaults",
    "active_provider_label",
    "append_assistant",
    "append_user_and_ensure",
    "ensure_session",
]
