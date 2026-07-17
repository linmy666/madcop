"""Probe and cache what an endpoint can do.

Results live in ``~/.madcop/provider_capabilities.json`` keyed by
``base_url|model|api_format``.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from madcop.llm.harness import ProviderHarness, infer_context_window, resolve_harness

logger = logging.getLogger(__name__)

_CACHE_PATH = Path.home() / ".madcop" / "provider_capabilities.json"
_CACHE_TTL_S = 7 * 24 * 3600


@dataclass
class CapabilityReport:
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_temperature: bool = True
    max_tokens_field: str = "max_tokens"
    reasoning_mode: str = "none"
    context_window: int = 128_000
    probed_at: float = field(default_factory=time.time)
    source: str = "heuristic"  # heuristic | cache


def _cache_key(base_url: str, model: str, api_format: str) -> str:
    return f"{base_url.rstrip('/')}|{model}|{api_format}"


def _load_cache() -> dict[str, Any]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug("capability cache write failed: %s", e)


def detect_capabilities(
    *,
    model: str = "",
    base_url: str = "",
    api_format: str = "openai_chat",
    runtime_kind: str = "",
    preset_id: str = "",
    force_refresh: bool = False,
) -> CapabilityReport:
    """Return capabilities from cache or harness heuristics (no live call)."""
    key = _cache_key(base_url, model, api_format)
    if not force_refresh:
        cache = _load_cache()
        hit = cache.get(key)
        if hit and (time.time() - float(hit.get("probed_at", 0))) < _CACHE_TTL_S:
            try:
                return CapabilityReport(**{**hit, "source": "cache"})
            except TypeError:
                pass

    h: ProviderHarness = resolve_harness(
        model=model,
        api_format=api_format,
        runtime_kind=runtime_kind,
        base_url=base_url,
        preset_id=preset_id,
    )
    report = CapabilityReport(
        supports_tools=h.supports_tools,
        supports_streaming=True,
        supports_vision=_model_likely_vision(model),
        supports_temperature=h.supports_temperature,
        max_tokens_field=h.max_tokens_field,
        reasoning_mode=h.reasoning_mode,
        context_window=infer_context_window(model, h),
        source="heuristic",
    )
    cache = _load_cache()
    cache[key] = asdict(report)
    _save_cache(cache)
    return report


def _model_likely_vision(model: str) -> bool:
    m = (model or "").lower()
    needles = (
        "gpt-4o", "gpt-4.1", "gpt-4-turbo", "claude-3", "claude-sonnet",
        "claude-opus", "gemini", "vision", "vl-", "-vl",
    )
    return any(n in m for n in needles)


def image_content_block(
    *,
    data_url: str | None = None,
    media_type: str = "image/png",
    url: str | None = None,
    api_format: str = "openai_chat",
) -> dict[str, Any]:
    """Build a multimodal image block for the given API family."""
    fmt = (api_format or "openai_chat").lower()
    if fmt == "anthropic":
        if data_url and data_url.startswith("data:"):
            header, b64 = data_url.split(",", 1) if "," in data_url else ("", data_url)
            mt = media_type
            if "image/" in header:
                mt = header.split(";")[0].replace("data:", "")
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": mt, "data": b64},
            }
        if url:
            return {"type": "image", "source": {"type": "url", "url": url}}
        raise ValueError("image requires data_url or url")

    if data_url:
        return {"type": "image_url", "image_url": {"url": data_url}}
    if url:
        return {"type": "image_url", "image_url": {"url": url}}
    raise ValueError("image requires data_url or url")


def text_content_block(text: str, api_format: str = "openai_chat") -> dict[str, Any]:
    return {"type": "text", "text": text}
