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


@dataclass
class Settings:
    """Root settings object."""
    active_provider: str = ""  # provider_id of the active entry
    providers: list[ProviderSettings] = field(default_factory=list)


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
        ))
    return Settings(
        active_provider=raw.get("active_provider", ""),
        providers=providers,
    )


def load_settings(path: Path | str | None = None) -> Settings:
    """Load settings from ~/.madcop/settings.json. Returns empty Settings if missing."""
    path = Path(path) if path else DEFAULT_SETTINGS_PATH
    if not path.exists():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Settings()
    return _settings_from_dict(raw)


def save_settings(settings: Settings, path: Path | str | None = None) -> Path:
    """Persist settings to ~/.madcop/settings.json with chmod 600."""
    path = Path(path) if path else DEFAULT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "active_provider": settings.active_provider,
        "providers": [asdict(p) for p in settings.providers],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


# --------------------------------------------------------------------------- #
# API-facing helpers
# --------------------------------------------------------------------------- #

def settings_to_public_dict(settings: Settings) -> dict[str, Any]:
    """Build the dict returned by GET /api/settings.

    Keys are MASKED — never expose plaintext to the frontend.
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
        })
    return {
        "active_provider": settings.active_provider,
        "providers": providers_out,
        "presets": PROVIDER_PRESETS,
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
) -> Settings:
    """Add or update a provider entry. Returns the mutated Settings.

    If api_key is empty, preserves the existing key (so users can
    update model without re-entering the key).
    """
    existing: ProviderSettings | None = None
    for p in settings.providers:
        if p.provider_id == provider_id:
            existing = p
            break

    if existing:
        existing.base_url = base_url or existing.base_url
        existing.model = model or existing.model
        existing.label = label or existing.label
        if api_key:
            existing.api_key = _encrypt(api_key)
    else:
        settings.providers.append(ProviderSettings(
            provider_id=provider_id,
            base_url=base_url,
            api_key=_encrypt(api_key) if api_key else "",
            model=model,
            label=label or provider_id,
        ))

    if make_active:
        settings.active_provider = provider_id

    return settings


def get_active_client_config(settings: Settings) -> dict[str, str] | None:
    """Return {api_key, base_url, model} for the active provider.

    Returns None if no active provider or no key configured.
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
]
