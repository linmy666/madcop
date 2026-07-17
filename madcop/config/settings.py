"""WebUI settings store — provider/api_key/model persisted to disk.

Stored at ~/.madcop/settings.json with chmod 600.
API keys are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using
a master key stored separately at ~/.madcop/master.key (also chmod 600).

Threat model:
- Protects against casual disk scans (grep, Time Machine, stolen laptop
  without SSH access). The master key and settings file live in the same
  directory; an attacker with read access to both can decrypt.
- For higher security, store master.key on a separate volume or HSM.

GET /api/settings returns masked keys (sk-...last4).
POST /api/settings accepts plaintext and stores encrypted.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_SETTINGS_PATH = Path(
    os.environ.get("MADCOP_SETTINGS", "~/.madcop/settings.json")
).expanduser()
DEFAULT_MASTER_KEY_PATH = Path(
    os.environ.get("MADCOP_MASTER_KEY", "~/.madcop/master.key")
).expanduser()

# Process-local cache so hot paths (each chat request loads settings 7+
# times) don't re-read + decrypt the JSON on every call. Invalidated on
# save, or when the on-disk mtime changes (external edit).
_settings_cache: Any = None
_settings_cache_path: Path | None = None
_settings_cache_mtime: float | None = None
_settings_cache_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Encryption (Fernet = AES-128-CBC + HMAC-SHA256)
# --------------------------------------------------------------------------- #

def _load_or_create_master_key(path: Path | None = None) -> bytes:
    """Load the Fernet master key, creating it on first run.

    The key file is created with chmod 600. If the file already exists
    we just read it.
    """
    path = path or DEFAULT_MASTER_KEY_PATH
    if path.exists():
        return path.read_bytes().strip()
    # Generate a new key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def _encrypt(plaintext: str, master_key: bytes | None = None) -> str:
    """Encrypt plaintext with Fernet. Returns a 'fernet:' prefixed token."""
    if not plaintext:
        return ""
    key = master_key or _load_or_create_master_key()
    token = Fernet(key).encrypt(plaintext.encode("utf-8"))
    return "fernet:" + token.decode("ascii")


def _decrypt(stored: str, master_key: bytes | None = None) -> str:
    """Decrypt a fernet: prefixed token. Returns plaintext or empty string.

    For backward compatibility, also accepts legacy 'b64:' prefixed values
    (base64 decode only). Plain un-prefixed strings are returned as-is.
    """
    if not stored:
        return ""
    key = master_key or _load_or_create_master_key()
    if stored.startswith("fernet:"):
        try:
            return Fernet(key).decrypt(stored[7:].encode("ascii")).decode("utf-8")
        except (InvalidToken, Exception):
            return ""
    # Legacy base64 fallback
    if stored.startswith("b64:"):
        import base64
        try:
            return base64.b64decode(stored[4:]).decode("utf-8")
        except Exception:
            return ""
    # Legacy plaintext
    return stored


def _mask_key(key: str) -> str:
    """Mask an API key for display: show first 3 + last 4, rest asterisks."""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:3] + "*" * (len(key) - 7) + key[-4:]


# --------------------------------------------------------------------------- #
# Settings schema
# --------------------------------------------------------------------------- #

# Known provider presets — gives the UI a dropdown with sane defaults.
PROVIDER_PRESETS: list[dict[str, str]] = [
    {"id": "openai",      "label": "OpenAI",       "base_url": "https://api.openai.com/v1",          "default_model": "gpt-4o-mini"},
    {"id": "anthropic",   "label": "Anthropic",    "base_url": "https://api.anthropic.com/v1",        "default_model": "claude-sonnet-4-20250514"},
    {"id": "minimax",     "label": "MiniMax",      "base_url": "https://api.minimaxi.com/v1",         "default_model": "MiniMax-M3"},
    {"id": "deepseek",    "label": "DeepSeek",     "base_url": "https://api.deepseek.com/v1",         "default_model": "deepseek-chat"},
    {"id": "zhipu",       "label": "智谱 GLM",     "base_url": "https://open.bigmodel.cn/api/paas/v4", "default_model": "glm-4-flash"},
    {"id": "nvidia",      "label": "NVIDIA NIM",   "base_url": "https://integrate.api.nvidia.com/v1",  "default_model": "minimaxai/minimax-m2.7"},
    {"id": "custom",      "label": "自定义",        "base_url": "",                                     "default_model": ""},
]


@dataclass
class ProviderSettings:
    """One provider configuration entry."""
    provider_id: str = ""       # e.g. "minimax", "openai", "custom"
    base_url: str = ""          # e.g. "https://api.minimaxi.com/v1"
    api_key: str = ""           # stored ENCRYPTED (fernet:...) on disk
    model: str = ""             # e.g. "MiniMax-M3"
    label: str = ""             # display label, e.g. "MiniMax"
    # v2.6.0: extended fields for full SavedProvider round-trip
    preset_id: str = ""         # e.g. "nvidia", "openai", "minimax"
    api_format: str = "openai_chat"  # anthropic | openai_chat | openai_responses
    auth_strategy: str = "api_key"   # api_key | auth_token | dual
    runtime_kind: str = ""     # anthropic_compatible | openai_oauth
    tool_search_enabled: bool = True
    notes: str = ""
    # Sampling parameters — per-provider defaults. The chat request can
    # still override these per-call, but without persisted defaults every
    # request was hardcoded to temperature=0.7 / max_tokens=8192.
    temperature: float = 0.7
    max_tokens: int = 8192
    top_p: float = 1.0
    auto_compact_window: int = 0   # 0 = disabled
    # Per-model parameter overrides: { "deepseek-reasoner": {"temperature": 0.6}, ... }
    # When the active model matches a key here, its values win over the
    # provider-level defaults above. Lets users tune R1 vs V3 differently.
    model_params: dict = field(default_factory=dict)


@dataclass
class Settings:
    """Root settings object."""
    active_provider: str = ""  # provider_id of the active entry
    providers: list[ProviderSettings] = field(default_factory=list)
    # Per-agent model routing for deep mode: { "planner": {"model": "glm-5.2"}, ... }
    # When empty, each builtin agent uses its own hardcoded model field.
    agent_routing: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Disk I/O
# --------------------------------------------------------------------------- #

def _settings_from_dict(raw: dict[str, Any]) -> Settings:
    """Parse settings from a dict (loaded from JSON)."""
    providers_raw = raw.get("providers", []) or []
    providers = []
    for p in providers_raw:
        providers.append(ProviderSettings(
            provider_id=p.get("provider_id", ""),
            base_url=p.get("base_url", ""),
            api_key=p.get("api_key", ""),  # stays encrypted on disk
            model=p.get("model", ""),
            label=p.get("label", ""),
            preset_id=p.get("preset_id", "") or p.get("provider_id", ""),
            api_format=p.get("api_format", "openai_chat"),
            auth_strategy=p.get("auth_strategy", "api_key"),
            runtime_kind=p.get("runtime_kind", ""),
            tool_search_enabled=p.get("tool_search_enabled", True),
            notes=p.get("notes", ""),
            temperature=p.get("temperature", 0.7),
            max_tokens=p.get("max_tokens", 8192),
            top_p=p.get("top_p", 1.0),
            auto_compact_window=p.get("auto_compact_window", 0),
            model_params=p.get("model_params", {}) or {},
        ))
    return Settings(
        active_provider=raw.get("active_provider", ""),
        providers=providers,
        agent_routing=raw.get("agent_routing", {}) or {},
    )


def _invalidate_settings_cache() -> None:
    """Drop the process-local settings cache (call after save)."""
    global _settings_cache, _settings_cache_path, _settings_cache_mtime
    with _settings_cache_lock:
        _settings_cache = None
        _settings_cache_path = None
        _settings_cache_mtime = None


def load_settings(path: Path | str | None = None) -> Settings:
    """Load settings from ~/.madcop/settings.json. Returns empty Settings if missing.

    Results are cached in-process and refreshed when the file mtime changes.
    """
    global _settings_cache, _settings_cache_path, _settings_cache_mtime
    path = Path(path) if path else DEFAULT_SETTINGS_PATH
    try:
        mtime = path.stat().st_mtime if path.exists() else None
    except OSError:
        mtime = None

    with _settings_cache_lock:
        if (
            _settings_cache is not None
            and _settings_cache_path == path
            and _settings_cache_mtime == mtime
        ):
            return _settings_cache

    if not path.exists():
        result = Settings()
    else:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            result = _settings_from_dict(raw)
        except (json.JSONDecodeError, OSError):
            result = Settings()

    with _settings_cache_lock:
        _settings_cache = result
        _settings_cache_path = path
        _settings_cache_mtime = mtime
    return result


def save_settings(settings: Settings, path: Path | str | None = None) -> Path:
    """Persist settings to ~/.madcop/settings.json with chmod 600."""
    path = Path(path) if path else DEFAULT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "active_provider": settings.active_provider,
        "providers": [asdict(p) for p in settings.providers],
        "agent_routing": settings.agent_routing,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    _invalidate_settings_cache()
    # Warm the cache with the just-written value so the next load is free.
    global _settings_cache, _settings_cache_path, _settings_cache_mtime
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    with _settings_cache_lock:
        _settings_cache = settings
        _settings_cache_path = path
        _settings_cache_mtime = mtime
    return path


# --------------------------------------------------------------------------- #
# API-facing helpers
# --------------------------------------------------------------------------- #

def settings_to_public_dict(settings: Settings) -> dict[str, Any]:
    """Build the dict returned by GET /api/settings.

    Keys are MASKED — never expose plaintext to the frontend. All
    extended fields (sampling params, api_format, etc.) are returned so
    the settings UI can round-trip them on edit.
    """
    providers_out = []
    for p in settings.providers:
        plaintext_key = _decrypt(p.api_key)
        providers_out.append({
            "provider_id": p.provider_id,
            "label": p.label,
            "base_url": p.base_url,
            "model": p.model,
            "api_key_masked": _mask_key(plaintext_key),
            "has_key": bool(plaintext_key),
            # Extended fields — needed for the edit form to show current values.
            "preset_id": p.preset_id,
            "api_format": p.api_format,
            "auth_strategy": p.auth_strategy,
            "runtime_kind": p.runtime_kind,
            "tool_search_enabled": p.tool_search_enabled,
            "notes": p.notes,
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "top_p": p.top_p,
            "auto_compact_window": p.auto_compact_window,
            "model_params": p.model_params,
        })
    return {
        "active_provider": settings.active_provider,
        "providers": providers_out,
        "presets": PROVIDER_PRESETS,
        "agent_routing": settings.agent_routing,
    }


def upsert_provider(
    settings: Settings,
    *,
    provider_id: str,
    base_url: str,
    api_key: str,      # PLAINTEXT from POST body
    model: str,
    label: str = "",
    make_active: bool = True,
    # Extended fields — all optional, None means "leave unchanged".
    preset_id: str | None = None,
    api_format: str | None = None,
    auth_strategy: str | None = None,
    runtime_kind: str | None = None,
    tool_search_enabled: bool | None = None,
    notes: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    auto_compact_window: int | None = None,
    model_params: dict | None = None,
) -> Settings:
    """Add or update a provider entry. Returns the mutated Settings.

    If api_key is empty, preserves the existing key (so users can
    update model without re-entering the key). Extended fields that
    are None on update are left unchanged.
    """
    existing: ProviderSettings | None = None
    for p in settings.providers:
        if p.provider_id == provider_id:
            existing = p
            break

    def _apply(p: ProviderSettings) -> None:
        """Write all provided fields onto a provider entry."""
        p.base_url = base_url or p.base_url
        p.model = model or p.model
        p.label = label or p.label
        if api_key:
            p.api_key = _encrypt(api_key)
        # Extended fields — only overwrite when a real value was passed.
        if preset_id is not None:
            p.preset_id = preset_id
        if api_format is not None:
            p.api_format = api_format
        if auth_strategy is not None:
            p.auth_strategy = auth_strategy
        if runtime_kind is not None:
            p.runtime_kind = runtime_kind
        if tool_search_enabled is not None:
            p.tool_search_enabled = tool_search_enabled
        if notes is not None:
            p.notes = notes
        if temperature is not None:
            p.temperature = temperature
        if max_tokens is not None:
            p.max_tokens = max_tokens
        if top_p is not None:
            p.top_p = top_p
        if auto_compact_window is not None:
            p.auto_compact_window = auto_compact_window
        if model_params is not None:
            p.model_params = model_params

    if existing:
        _apply(existing)
    else:
        new_p = ProviderSettings(
            provider_id=provider_id,
            base_url=base_url,
            api_key=_encrypt(api_key) if api_key else "",
            model=model,
            label=label or provider_id,
            preset_id=preset_id or provider_id,
            api_format=api_format or "openai_chat",
            auth_strategy=auth_strategy or "api_key",
            runtime_kind=runtime_kind or "",
            tool_search_enabled=tool_search_enabled if tool_search_enabled is not None else True,
            notes=notes or "",
            temperature=temperature if temperature is not None else 0.7,
            max_tokens=max_tokens if max_tokens is not None else 8192,
            top_p=top_p if top_p is not None else 1.0,
            auto_compact_window=auto_compact_window if auto_compact_window is not None else 0,
            model_params=model_params or {},
        )
        settings.providers.append(new_p)

    if make_active:
        settings.active_provider = provider_id

    return settings


def get_active_client_config(settings: Settings) -> dict[str, Any] | None:
    """Return the active provider's config for building a client.

    Includes sampling defaults (temperature, max_tokens, top_p) and the
    per-model override table so callers can resolve the right params for
    the model actually in use. Returns None if no active/key configured.
    """
    if not settings.active_provider:
        return None
    for p in settings.providers:
        if p.provider_id == settings.active_provider:
            plaintext_key = _decrypt(p.api_key)
            if not plaintext_key:
                return None
            return {
                "api_key": plaintext_key,
                "base_url": p.base_url,
                "model": p.model,
                "temperature": p.temperature,
                "max_tokens": p.max_tokens,
                "top_p": p.top_p,
                "auto_compact_window": p.auto_compact_window,
                "model_params": p.model_params,
                # Harness metadata — lets the LLM client adapt per vendor
                "api_format": p.api_format,
                "auth_strategy": p.auth_strategy,
                "runtime_kind": p.runtime_kind,
                "preset_id": p.preset_id,
                "provider_id": p.provider_id,
                "label": p.label,
            }
    return None


__all__ = [
    "PROVIDER_PRESETS",
    "ProviderSettings",
    "Settings",
    "DEFAULT_SETTINGS_PATH",
    "DEFAULT_MASTER_KEY_PATH",
    "load_settings",
    "save_settings",
    "settings_to_public_dict",
    "upsert_provider",
    "get_active_client_config",
    "_invalidate_settings_cache",
]
