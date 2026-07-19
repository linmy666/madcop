"""Runtime introspection tools — ground truth for “what model am I?”.

Agents must call ``get_current_model`` instead of guessing model names.
"""

from __future__ import annotations

import contextvars
import json
from typing import Any

from .registry import Tool

# Request-scoped overrides set by the chat handler for this SSE turn.
_request_model: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "madcop_request_model", default=None,
)
_request_agent_mode: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "madcop_request_agent_mode", default=None,
)


def set_request_runtime(
    *,
    model: str | None = None,
    agent_mode: str | None = None,
) -> None:
    """Bind the model / mode for the current chat request (call from app.py)."""
    _request_model.set((model or "").strip() or None)
    _request_agent_mode.set((agent_mode or "").strip() or None)


def clear_request_runtime() -> None:
    _request_model.set(None)
    _request_agent_mode.set(None)


def snapshot_current_model() -> dict[str, Any]:
    """Resolve active model info without secrets (no API keys)."""
    from madcop.config.settings import get_active_client_config, load_settings

    out: dict[str, Any] = {
        "source": "settings",
        "model": None,
        "provider_id": None,
        "provider_label": None,
        "base_url": None,
        "api_format": None,
        "preset_id": None,
        "request_model_override": None,
        "effective_model": None,
        "agent_mode": _request_agent_mode.get(),
        "note": (
            "These values come from MadCop settings / this request, "
            "not from the model's self-description. Prefer this tool over guessing."
        ),
    }
    try:
        s = load_settings()
        cfg = get_active_client_config(s)
        if cfg:
            # Redact key — never return api_key
            out["model"] = cfg.get("model") or None
            out["provider_id"] = cfg.get("provider_id") or s.active_provider or None
            out["provider_label"] = cfg.get("label") or None
            out["base_url"] = cfg.get("base_url") or None
            out["api_format"] = cfg.get("api_format") or None
            out["preset_id"] = cfg.get("preset_id") or None
        else:
            out["error"] = (
                "no active provider configured (or API key missing). "
                "Open Settings → Providers and activate a model."
            )
            out["active_provider"] = getattr(s, "active_provider", None) or None
    except Exception as e:  # noqa: BLE001
        out["error"] = f"failed to load settings: {e}"

    req = _request_model.get()
    if req:
        out["request_model_override"] = req
        out["source"] = "request_override"
    # Effective = what this turn is trying to use
    out["effective_model"] = req or out.get("model")
    if not out["effective_model"] and not out.get("error"):
        out["error"] = "model id empty in active provider config"
    return out


class GetCurrentModelTool(Tool):
    """Report the real configured / request model for debugging."""

    name = "get_current_model"
    description = (
        "Return the model MadCop is actually using for this session "
        "(from Settings active provider + optional request override). "
        "Call this when the user asks which model you are, what LLM is running, "
        "or to debug model mismatches. NEVER invent a model name — always call this tool."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def __call__(self, **kwargs: Any) -> str:
        return json.dumps(snapshot_current_model(), ensure_ascii=False, default=str)


__all__ = [
    "GetCurrentModelTool",
    "set_request_runtime",
    "clear_request_runtime",
    "snapshot_current_model",
]
