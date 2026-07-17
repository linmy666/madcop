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
    s = settings_store.load_settings()
    s.agent_routing = body if isinstance(body, dict) else {}
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

