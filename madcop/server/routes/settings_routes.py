"""Settings / provider CRUD routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from madcop.config import settings as settings_store
from madcop.server.models import ProviderInput, SetActiveRequest

router = APIRouter(tags=["settings"])


@router.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    s = settings_store.load_settings()
    return settings_store.settings_to_public_dict(s)


@router.post("/api/settings")
async def post_settings(body: ProviderInput) -> dict[str, Any]:
    s = settings_store.load_settings()
    s = settings_store.upsert_provider(
        s,
        provider_id=body.provider_id,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        label=body.label,
        make_active=body.make_active,
        preset_id=body.preset_id,
        api_format=body.api_format,
        auth_strategy=body.auth_strategy,
        runtime_kind=body.runtime_kind,
        tool_search_enabled=body.tool_search_enabled,
        notes=body.notes,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        top_p=body.top_p,
        auto_compact_window=body.auto_compact_window,
        model_params=body.model_params,
    )
    settings_store.save_settings(s)
    return settings_store.settings_to_public_dict(s)


@router.get("/api/settings/agent-routing")
async def get_agent_routing() -> dict[str, Any]:
    s = settings_store.load_settings()
    return {"agent_routing": s.agent_routing}


@router.put("/api/settings/agent-routing")
async def put_agent_routing(body: dict) -> dict[str, Any]:
    """Persist per-agent model routing.

    Validates that each `model` value is reachable in the active
    provider's /v1/models list (cached for 5 min via /api/models).
    Rejects the whole request with 400 if any model is unknown —
    silently saving an invalid model (e.g. from a typo or a model
    that was removed upstream) caused every deep-mode run to fail
    with 'model not found' before this check was added.
    """
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a dict of agent_id → {model: '...'}")
    s = settings_store.load_settings()
    # Load the live model list (5-min cache) once for the active
    # provider so we can validate everything in one shot.
    from madcop.server.madcop_compat import fetch_provider_models
    cfg = settings_store.get_active_client_config(s)
    available: set[str] = set()
    if cfg and cfg.get("api_key"):
        try:
            for m in fetch_provider_models(cfg["base_url"], cfg["api_key"]):
                mid = m.get("id")
                if mid:
                    available.add(mid)
        except Exception:
            # If the upstream call fails, don't block the user from
            # saving — the LLM call later will surface the real error.
            pass
    # Validate every model. Empty string / null is allowed (means
    # 'use the agent's default model').
    unknown: list[str] = []
    for agent_id, cfg in body.items():
        if not isinstance(cfg, dict):
            raise HTTPException(400, f"agent {agent_id!r} config must be a dict")
        model = cfg.get("model")
        if not model:
            continue
        if available and model not in available:
            unknown.append(f"{agent_id}={model!r}")
    if unknown:
        raise HTTPException(
            400,
            "model(s) not available in active provider: "
            + ", ".join(unknown)
            + " (active provider = "
            + (s.active_provider or "(none)")
            + ")",
        )
    s.agent_routing = body
    settings_store.save_settings(s)
    return {"agent_routing": s.agent_routing}


@router.post("/api/settings/active")
async def set_active_provider(body: SetActiveRequest) -> dict[str, Any]:
    s = settings_store.load_settings()
    ids = [p.provider_id for p in s.providers]
    if body.provider_id not in ids:
        raise HTTPException(404, f"provider '{body.provider_id}' not found")
    s.active_provider = body.provider_id
    settings_store.save_settings(s)
    return settings_store.settings_to_public_dict(s)


@router.delete("/api/settings/{provider_id}")
async def delete_provider(provider_id: str) -> dict[str, Any]:
    s = settings_store.load_settings()
    s.providers = [p for p in s.providers if p.provider_id != provider_id]
    if s.active_provider == provider_id:
        s.active_provider = s.providers[0].provider_id if s.providers else ""
    settings_store.save_settings(s)
    return settings_store.settings_to_public_dict(s)


@router.get("/api/providers/capabilities")
async def provider_capabilities(force: bool = False, live: bool = False) -> dict[str, Any]:
    """Return capability report for the active provider.

    ``live=true`` runs a minimal chat probe (uses API key / tokens).
    """
    from dataclasses import asdict
    from madcop.llm.capabilities import detect_capabilities, probe_live
    s = settings_store.load_settings()
    cfg = settings_store.get_active_client_config(s) or {}
    if live and cfg.get("api_key"):
        report = probe_live(
            api_key=str(cfg.get("api_key") or ""),
            model=str(cfg.get("model") or ""),
            base_url=str(cfg.get("base_url") or ""),
            api_format=str(cfg.get("api_format") or "openai_chat"),
        )
    else:
        report = detect_capabilities(
            model=str(cfg.get("model") or ""),
            base_url=str(cfg.get("base_url") or ""),
            api_format=str(cfg.get("api_format") or "openai_chat"),
            runtime_kind=str(cfg.get("runtime_kind") or ""),
            preset_id=str(cfg.get("preset_id") or ""),
            force_refresh=bool(force),
        )
    return {
        "capabilities": asdict(report),
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
        "live": bool(live),
    }

