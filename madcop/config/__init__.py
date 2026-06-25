"""v0.7.1 — User config loader for ~/.madcop/config.yaml.

Provides:
  - Config dataclass with sensible defaults
  - load_config() — read from ~/.madcop/config.yaml, return Config
  - save_default_config() — write a default config to ~/.madcop/config.yaml
  - resolve_provider() — turn a config entry into a runtime OpenAICompatClient

The config is deliberately simple YAML — no nested includes, no env
templating, no inheritance. If you want a "real" config system, file
an issue. For personal use, 30 lines beats a config framework.

YAML schema (see DEFAULT_CONFIG_DICT for a complete example):

  providers:
    primary:
      base_url: https://api.openai.com/v1
      api_key: $OPENAI_API_KEY
      model: gpt-4o-mini
    fast:
      base_url: https://integrate.api.nvidia.com/v1
      api_key: $NVIDIA_API_KEY
      model: minimax/mistral-7b-instruct-v0.3

  router:
    mode: auto          # auto | manual
    manual_tier:
      T1: primary
      T2: primary
      T3: fast

  cost:
    budget_per_run_usd: 5.0   # hard stop

  memory:
    path: ~/.madcop/memory.db
    growth_enabled: true
    auto_distill: true         # call LLM on each completed episode
    auto_feedback: true
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Default config path. Can be overridden by $MADCOP_CONFIG.
DEFAULT_CONFIG_PATH = Path(os.environ.get("MADCOP_CONFIG", "~/.madcop/config.yaml")).expanduser()


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str          # may be "$ENV_VAR" — resolved lazily
    model: str


@dataclass
class RouterConfig:
    mode: str = "auto"             # "auto" or "manual"
    manual_tier: dict[str, str] = field(default_factory=lambda: {"T1": "primary", "T2": "primary", "T3": "fast"})


@dataclass
class CostConfig:
    budget_per_run_usd: float = 5.0


@dataclass
class MemoryConfig:
    path: str = "~/.madcop/memory.db"
    growth_enabled: bool = True
    auto_distill: bool = True
    auto_feedback: bool = True


@dataclass
class Config:
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    router: RouterConfig = field(default_factory=RouterConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    config_path: Path | None = None

    def provider(self, name: str) -> ProviderConfig | None:
        return self.providers.get(name)


# ---------------------------------------------------------------------------
# Default config dict (used by save_default_config)
# ---------------------------------------------------------------------------


DEFAULT_CONFIG_DICT: dict[str, Any] = {
    "providers": {
        "primary": {
            "base_url": "https://api.openai.com/v1",
            "api_key": "$OPENAI_API_KEY",
            "model": "gpt-4o-mini",
        },
        "fast": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": "$NVIDIA_API_KEY",
            "model": "minimax/mistral-7b-instruct-v0.3",
        },
    },
    "router": {
        "mode": "auto",
        "manual_tier": {"T1": "primary", "T2": "primary", "T3": "fast"},
    },
    "cost": {"budget_per_run_usd": 5.0},
    "memory": {
        "path": "~/.madcop/memory.db",
        "growth_enabled": True,
        "auto_distill": True,
        "auto_feedback": True,
    },
}


# ---------------------------------------------------------------------------
# YAML loader — minimal, no PyYAML dependency
# ---------------------------------------------------------------------------


_ENV_VAR_RE = re.compile(r"^\$([A-Z_][A-Z0-9_]*)$")


def _resolve_env(value: str) -> str:
    """Resolve "$ENV_VAR" → value of that env var, or leave as-is."""
    if not isinstance(value, str):
        return value
    m = _ENV_VAR_RE.match(value.strip())
    if m and m.group(1) in os.environ:
        return os.environ[m.group(1)]
    return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the subset of YAML we support. PyYAML-free.

    Supported:
      - top-level keys with scalar values
      - nested mappings (2 levels deep, dict)
      - lists of dicts NOT supported (we don't use them)
      - comments starting with `#`

    If the file is malformed, we raise ValueError with a line number.
    """
    root: dict[str, Any] = {}
    # Stack: (indent_level, container)
    stack: list[tuple[int, dict]] = [(-1, root)]

    lines = text.splitlines()
    for lineno, raw in enumerate(lines, 1):
        # Strip comments + whitespace
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if "\t" in line:
            raise ValueError(f"line {lineno}: tabs not allowed, use spaces")
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if not stripped or stripped.startswith("- "):
            continue  # skip list items; we don't use them

        if ":" not in stripped:
            raise ValueError(f"line {lineno}: expected 'key: value', got: {raw!r}")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        # Pop stack to find the right parent
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent_indent, parent = stack[-1]

        if not value:
            # New nested mapping
            new_dict: dict[str, Any] = {}
            parent[key] = new_dict
            stack.append((indent, new_dict))
        else:
            # Scalar value (strip surrounding quotes if present)
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            parent[key] = value

    return root


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(path: Path | str | None = None) -> Config:
    """Load ~/.madcop/config.yaml (or path). Returns Config with defaults.

    Missing file → returns Config with DEFAULT_CONFIG_DICT values.
    Malformed file → raises ValueError.
    """
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return _config_from_dict(DEFAULT_CONFIG_DICT, path)
    text = path.read_text(encoding="utf-8")
    try:
        raw = _parse_simple_yaml(text)
    except ValueError as e:
        raise ValueError(f"failed to parse {path}: {e}") from e
    return _config_from_dict(raw, path)


def _config_from_dict(raw: dict[str, Any], path: Path) -> Config:
    providers_raw = raw.get("providers", {}) or {}
    providers: dict[str, ProviderConfig] = {}
    for name, p in providers_raw.items():
        providers[name] = ProviderConfig(
            name=name,
            base_url=p.get("base_url", ""),
            api_key=p.get("api_key", ""),
            model=p.get("model", ""),
        )
    router_raw = raw.get("router", {}) or {}
    router = RouterConfig(
        mode=router_raw.get("mode", "auto"),
        manual_tier=dict(router_raw.get("manual_tier", {"T1": "primary", "T2": "primary", "T3": "fast"})),
    )
    cost_raw = raw.get("cost", {}) or {}
    cost = CostConfig(
        budget_per_run_usd=float(cost_raw.get("budget_per_run_usd", 5.0)),
    )
    memory_raw = raw.get("memory", {}) or {}
    memory = MemoryConfig(
        path=memory_raw.get("path", "~/.madcop/memory.db"),
        growth_enabled=_parse_bool(memory_raw.get("growth_enabled", True)),
        auto_distill=_parse_bool(memory_raw.get("auto_distill", True)),
        auto_feedback=_parse_bool(memory_raw.get("auto_feedback", True)),
    )
    return Config(providers=providers, router=router, cost=cost, memory=memory, config_path=path)


def _parse_bool(value: Any) -> bool:
    """Parse a YAML scalar as bool. Accepts bool, str ('true'/'false'/'yes'/'no'/1/0)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "yes", "1", "on"):
            return True
        if s in ("false", "no", "0", "off", ""):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return bool(value)


def save_default_config(path: Path | str | None = None, *, overwrite: bool = False) -> Path:
    """Write the default config to ~/.madcop/config.yaml.

    Existing file is preserved unless overwrite=True.
    Returns the path that was written.
    """
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    lines: list[str] = []
    lines.append("# madcop config — generated by `madcop config init`")
    lines.append("# Edit freely. See docs/ for the schema.")
    lines.append("")
    lines.append("providers:")
    for name, p in DEFAULT_CONFIG_DICT["providers"].items():
        lines.append(f"  {name}:")
        for k, v in p.items():
            lines.append(f"    {k}: {v}")
    lines.append("")
    lines.append("router:")
    lines.append(f"  mode: {DEFAULT_CONFIG_DICT['router']['mode']}")
    lines.append("  manual_tier:")
    for tier, name in DEFAULT_CONFIG_DICT["router"]["manual_tier"].items():
        lines.append(f"    {tier}: {name}")
    lines.append("")
    lines.append("cost:")
    lines.append(f"  budget_per_run_usd: {DEFAULT_CONFIG_DICT['cost']['budget_per_run_usd']}")
    lines.append("")
    lines.append("memory:")
    for k, v in DEFAULT_CONFIG_DICT["memory"].items():
        if isinstance(v, str):
            lines.append(f"  {k}: {v}")
        else:
            lines.append(f"  {k}: {'true' if v else 'false'}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def resolve_provider(cfg: Config, name: str) -> ProviderConfig:
    """Look up a provider by name, with env-var resolution baked in."""
    p = cfg.provider(name)
    if p is None:
        available = list(cfg.providers.keys())
        raise KeyError(f"provider {name!r} not in config. available: {available}")
    return ProviderConfig(
        name=p.name,
        base_url=p.base_url,
        api_key=_resolve_env(p.api_key),
        model=p.model,
    )


__all__ = [
    "Config",
    "ProviderConfig",
    "RouterConfig",
    "CostConfig",
    "MemoryConfig",
    "DEFAULT_CONFIG_DICT",
    "DEFAULT_CONFIG_PATH",
    "load_config",
    "save_default_config",
    "resolve_provider",
]
