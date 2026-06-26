"""v0.8.0 — Load sub-agent specs from YAML / TOML / JSON files.

Users can now define their own sub-agents without writing Python:

    # subagents/code-reviewer.yaml
    name: code-reviewer
    description: Reviews pull requests for style and correctness
    system_prompt: |
      You are a careful code reviewer. Look for bugs, style issues,
      and missing tests. Be specific in your feedback.
    tools: [read, bash, grep]
    skills: [python-style, security]
    max_turns: 30
    timeout_seconds: 600

Then load them at runtime:

    from madcop.agent.subagent.loader import load_subagent_specs
    specs = load_subagent_specs("subagents/")  # directory or single file
    for spec in specs:
        executor.register(spec)

Three formats are auto-detected by extension:

- `.yaml` / `.yml` — YAML (uses `PyYAML` if installed, else raises a
  helpful error pointing to `pip install pyyaml`).
- `.toml` — TOML (stdlib `tomllib` on Python 3.11+, `tomli` on 3.10).
- `.json` — JSON (stdlib).

Format detection on a directory: a `madcop-subagents.yaml` is checked
first, then `.toml`, then per-file extension. If the directory has
neither, all `*.yaml`/`*.yml`/`*.toml`/`*.json` files inside are
loaded in alphabetical order.

Validation:
- `name` is required and must be unique across the loaded set.
- `description` is required (it's what the lead agent sees).
- `tools`, `skills`, `disallowed_tools` if present must be lists of
  non-empty strings.
- `max_turns` and `timeout_seconds` if present must be positive ints.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

from .spec import SubagentSpec

logger = logging.getLogger(__name__)


# Recognised file extensions. Order matters for auto-detection.
_YAML_EXTS = (".yaml", ".yml")
_TOML_EXTS = (".toml",)
_JSON_EXTS = (".json",)
_KNOWN_EXTS = _YAML_EXTS + _TOML_EXTS + _JSON_EXTS

# A conventional name for a single config file inside a directory.
_DEFAULT_BASENAMES = ("madcop-subagents.yaml", "madcop-subagents.yml",
                       "madcop-subagents.toml", "madcop-subagents.json")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def load_subagent_specs(source: str | Path) -> list[SubagentSpec]:
    """Load sub-agent specs from a file or directory.

    Args:
        source: Path to a YAML/TOML/JSON file, or to a directory
            containing such files (or a `madcop-subagents.*` single file).

    Returns:
        A list of `SubagentSpec` objects, deduplicated by name (later
        definitions win on conflict — useful for layered configs).
    """
    p = Path(source)
    if not p.exists():
        raise FileNotFoundError(f"subagent config path not found: {p}")

    if p.is_dir():
        return _load_from_directory(p)
    return _load_from_file(p)


# --------------------------------------------------------------------------- #
# File loading
# --------------------------------------------------------------------------- #


def _load_from_directory(directory: Path) -> list[SubagentSpec]:
    """Try a single config file first; fall back to scanning the dir."""
    for base in _DEFAULT_BASENAMES:
        candidate = directory / base
        if candidate.exists():
            logger.info("loading subagents from %s", candidate)
            return _parse_one(candidate)

    # Otherwise scan for known extensions.
    paths = sorted(
        path for ext in _KNOWN_EXTS for path in directory.glob(f"*{ext}")
    )
    if not paths:
        raise FileNotFoundError(
            f"no subagent config files found in {directory} "
            f"(looked for {'/'.join(_KNOWN_EXTS)})"
        )
    logger.info("loading %d subagent files from %s", len(paths), directory)
    return _parse_many(paths)


def _load_from_file(path: Path) -> list[SubagentSpec]:
    logger.info("loading subagent file: %s", path)
    return _parse_one(path)


def _parse_many(paths: Iterable[Path]) -> list[SubagentSpec]:
    """Parse multiple files and dedup by name (later definitions win)."""
    by_name: dict[str, SubagentSpec] = {}
    for path in paths:
        for spec in _parse_one(path):
            if spec.name in by_name:
                logger.warning(
                    "subagent %r redefined (later wins) — file=%s",
                    spec.name, path,
                )
            by_name[spec.name] = spec
    return list(by_name.values())


def _parse_one(path: Path) -> list[SubagentSpec]:
    ext = path.suffix.lower()
    if ext in _YAML_EXTS:
        raw = _read_yaml(path)
    elif ext in _TOML_EXTS:
        raw = _read_toml(path)
    elif ext in _JSON_EXTS:
        raw = _read_json(path)
    else:
        raise ValueError(
            f"unsupported subagent config extension: {ext!r} "
            f"(expected one of {'/'.join(_KNOWN_EXTS)})"
        )

    # Allow four top-level shapes:
    # 1. bare list                       -> [spec, spec, ...]
    # 2. {"subagents": [...]} wrapper    -> [spec, spec, ...]
    # 3. bare dict with 'name' key       -> [single spec]
    # 4. bare dict (other keys)          -> treat as single spec too
    if isinstance(raw, dict) and "subagents" in raw:
        items = raw["subagents"]
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = [raw]
    else:
        raise ValueError(
            f"{path}: expected a list of subagent specs, a dict with a "
            f"'subagents' key, or a single spec dict (got {type(raw).__name__})"
        )

    specs = [validate_and_build(item, source=str(path)) for item in items]

    # Dedup by name even within a single file: later wins. This makes
    # the loader's behavior consistent across "one file with two dups"
    # vs "two files with the same name".
    by_name: dict[str, SubagentSpec] = {}
    for spec in specs:
        if spec.name in by_name:
            logger.warning(
                "subagent %r appears more than once in %s (later wins)",
                spec.name, path,
            )
        by_name[spec.name] = spec
    return list(by_name.values())


# --------------------------------------------------------------------------- #
# Format readers
# --------------------------------------------------------------------------- #


def _read_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as e:
        raise ImportError(
            f"PyYAML is required to load {path.name} — install it with "
            f"`pip install pyyaml`"
        ) from e
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_toml(path: Path) -> Any:
    if sys.version_info >= (3, 11):
        import tomllib  # type: ignore[import-not-found]
        with path.open("rb") as f:
            return tomllib.load(f)
    # Python 3.10 fallback
    try:
        import tomli  # type: ignore[import-untyped]
    except ImportError as e:
        raise ImportError(
            f"tomli is required on Python 3.10 to load {path.name} — "
            f"install it with `pip install tomli`"
        ) from e
    with path.open("rb") as f:
        return tomli.load(f)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Validation + spec building
# --------------------------------------------------------------------------- #


def validate_and_build(item: Any, *, source: str = "<unknown>") -> SubagentSpec:
    """Validate one raw dict and turn it into a SubagentSpec."""
    if not isinstance(item, dict):
        raise ValueError(f"{source}: each subagent must be a dict, got {type(item).__name__}")

    name = item.get("name")
    if not name or not isinstance(name, str):
        raise ValueError(f"{source}: subagent missing or invalid 'name' (got {name!r})")

    description = item.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"{source}: subagent {name!r}: 'description' must be a string")

    system_prompt = item.get("system_prompt", "")
    if not isinstance(system_prompt, str):
        raise ValueError(f"{source}: subagent {name!r}: 'system_prompt' must be a string")

    tools = _validate_string_list(item.get("tools"), "tools", name, source, allow_none=True)
    skills = _validate_string_list(item.get("skills"), "skills", name, source, allow_none=True)
    disallowed = _validate_string_list(
        item.get("disallowed_tools"), "disallowed_tools", name, source, allow_none=True,
    ) or ("task",)  # safety: task is ALWAYS disallowed, no matter what user says

    model = item.get("model", "inherit")
    if not isinstance(model, str):
        raise ValueError(f"{source}: subagent {name!r}: 'model' must be a string")

    max_turns = _validate_positive_int(item.get("max_turns", 50), "max_turns", name, source)
    timeout = _validate_positive_int(item.get("timeout_seconds", 300), "timeout_seconds", name, source)

    return SubagentSpec(
        name=name,
        description=description,
        system_prompt=system_prompt,
        tools=tuple(tools) if tools is not None else None,
        skills=tuple(skills) if skills is not None else None,
        disallowed_tools=tuple(disallowed),
        model=model,
        max_turns=max_turns,
        timeout_seconds=timeout,
    )


def _validate_string_list(
    value: Any,
    field: str,
    name: str,
    source: str,
    *,
    allow_none: bool,
) -> list[str] | None:
    if value is None:
        return None if allow_none else []
    if not isinstance(value, list):
        raise ValueError(f"{source}: subagent {name!r}: '{field}' must be a list, got {type(value).__name__}")
    out: list[str] = []
    for i, v in enumerate(value):
        if not isinstance(v, str) or not v:
            raise ValueError(f"{source}: subagent {name!r}: '{field}[{i}]' must be a non-empty string")
        out.append(v)
    return out


def _validate_positive_int(
    value: Any,
    field: str,
    name: str,
    source: str,
) -> int:
    if isinstance(value, bool):  # bool is a subclass of int — reject explicitly
        raise ValueError(f"{source}: subagent {name!r}: '{field}' must be an int, got bool")
    if not isinstance(value, int):
        raise ValueError(f"{source}: subagent {name!r}: '{field}' must be an int, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{source}: subagent {name!r}: '{field}' must be > 0, got {value}")
    return value


__all__ = ["load_subagent_specs", "validate_and_build"]
