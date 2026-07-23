"""
v3.9.2 — Tool input Pydantic schemas for safety guardrails.

Each tool has a Pydantic model that:
1. Validates the input structure (type checks, required fields)
2. Enforces a max content length to prevent the "write_file too long"
   loop the user saw with the plant vs zombies request
3. Tags "dangerous" tools (rm, run shell with sudo, etc.) for HITL

The schemas are applied by ReActEngine before each tool call.
If validation fails, the error message is returned as Observation
so the model can self-correct (closed-loop repair).
"""
from __future__ import annotations

import re
from typing import Any, Optional, Literal

try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:  # pragma: no cover
    # pydantic not available — fall back to plain classes that mimic
    # the .model_dump() / .validation_error API enough for our usage.
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def model_dump(self):
            return self.__dict__
    def Field(*_args, **_kwargs):  # type: ignore
        return None
    def field_validator(*_args, **_kwargs):  # type: ignore
        return lambda f: f


# --------------------------------------------------------------------------- #
# Content size limits
# --------------------------------------------------------------------------- #
# write_file's content can be long (HTML pages, JSON config) but
# the "plant vs zombies" test showed that 1059 reasoning events
# burned through tokens because the model kept retrying with full
# content. Cap at 32K chars; if more, the tool returns a clear
# error and the model should split into multiple smaller writes.
MAX_CONTENT_CHARS = 32_000
MAX_FILE_PATH_CHARS = 1024
MAX_QUERY_CHARS = 2000
MAX_URL_CHARS = 2048


# --------------------------------------------------------------------------- #
# Danger levels (used for HITL)
# --------------------------------------------------------------------------- #
# - "safe":     no confirmation needed
# - "mutating": needs HITL before executing
# - "destructive": always needs HITL
DANGER_LEVELS: dict[str, str] = {
    # Safe / read-only
    "get_current_time": "safe",
    "get_current_model": "safe",
    "get_weather": "safe",
    "read_file": "safe",
    "web_search": "safe",
    "web_fetch": "safe",
    "query_rag": "safe",
    "recall_memory": "safe",
    "ask_user": "safe",
    "echo": "safe",
    # Mutating but reversible
    "write_file": "mutating",
    "write_xlsx": "mutating",
    "edit_file": "mutating",
    "read_file": "safe",
    "remember": "mutating",
    # Destructive / shell
    "bash": "destructive",
    "run_command": "destructive",
}


# --------------------------------------------------------------------------- #
# Per-tool Pydantic schemas
# --------------------------------------------------------------------------- #
class WriteFileInput(BaseModel):
    path: str = Field(..., min_length=1, max_length=MAX_FILE_PATH_CHARS)
    content: str = Field(..., max_length=MAX_CONTENT_CHARS)
    encoding: Optional[str] = None

    @field_validator("path")
    @classmethod
    def _path_safe(cls, v: str) -> str:
        # Block obvious dangerous paths
        if v.startswith("/etc/") or v.startswith("/System/") or "/.ssh/" in v:
            raise ValueError(
                f"refusing to write to sensitive system path: {v!r}. "
                "Ask the user to confirm before writing here."
            )
        return v


class EditFileInput(BaseModel):
    path: str = Field(..., min_length=1, max_length=MAX_FILE_PATH_CHARS)
    old_string: str = Field(..., max_length=MAX_CONTENT_CHARS)
    new_string: str = Field(..., max_length=MAX_CONTENT_CHARS)


class ReadFileInput(BaseModel):
    path: str = Field(..., min_length=1, max_length=MAX_FILE_PATH_CHARS)


class BashInput(BaseModel):
    command: str = Field(..., min_length=1, max_length=4096)

    @field_validator("command")
    @classmethod
    def _no_sudo(cls, v: str) -> str:
        # Block sudo / rm -rf patterns. Force HITL via danger level
        # anyway, but defense in depth.
        if re.search(r"\bsudo\b", v):
            raise ValueError(
                "sudo commands are blocked at the model layer. "
                "Ask the user to confirm."
            )
        if re.search(r"\brm\s+-rf?\b\s+/", v) or re.search(r"\brm\s+-rf?\b\s+~", v):
            raise ValueError(
                "destructive 'rm -rf' commands are blocked. "
                "Ask the user to confirm before deleting files."
            )
        return v


class WebSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS)


class WebFetchInput(BaseModel):
    url: str = Field(..., min_length=1, max_length=MAX_URL_CHARS)


class AskUserInput(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    options: list[str] = Field(default_factory=list)


# Map tool name -> (schema class, fields to extract from input dict)
TOOL_SCHEMAS: dict[str, tuple[type, list[str]]] = {
    "write_file":  (WriteFileInput, ["path", "content", "encoding"]),
    "write_xlsx":  (WriteFileInput, ["path", "content"]),
    "edit_file":   (EditFileInput,  ["path", "old_string", "new_string"]),
    "read_file":   (ReadFileInput,  ["path"]),
    "bash":        (BashInput,      ["command"]),
    "web_search":  (WebSearchInput, ["query"]),
    "web_fetch":   (WebFetchInput,  ["url"]),
    "ask_user":    (AskUserInput,   ["question", "options"]),
}


# --------------------------------------------------------------------------- #
# Validation entry point
# --------------------------------------------------------------------------- #
class ToolValidationError(Exception):
    """Raised when a tool input fails Pydantic validation."""

    def __init__(self, tool: str, errors: list[str]):
        self.tool = tool
        self.errors = errors
        # Human-readable error for the model to see as Observation.
        msg = f"工具 {tool!r} 输入校验失败:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        super().__init__(msg)


def validate_tool_input(tool: str, raw_input: Any) -> tuple[bool, str, Any]:
    """Validate a tool's input against its Pydantic schema.

    Returns (ok, error_message, validated_input).
    On error, error_message is non-empty and validated_input is None.
    On success, error_message is empty and validated_input is the
    Pydantic model (call .model_dump() to get a dict).
    """
    if tool not in TOOL_SCHEMAS:
        # Unknown tool — let it through; ReActEngine's normal
        # error path will catch "tool not found".
        return True, "", None
    schema_cls, fields = TOOL_SCHEMAS[tool]
    if raw_input is None:
        raw_input = {}
    if isinstance(raw_input, str):
        # Models sometimes emit the JSON as a string. Try to parse.
        import json
        try:
            raw_input = json.loads(raw_input)
        except Exception:
            raw_input = {}
    if not isinstance(raw_input, dict):
        return False, f"工具 {tool!r} 输入必须是 JSON 对象，收到 {type(raw_input).__name__}", None
    # Pick only the fields the schema knows about
    filtered = {k: v for k, v in raw_input.items() if k in fields}
    try:
        validated = schema_cls(**filtered)
    except Exception as e:
        # pydantic raises ValidationError; we just stringify
        errs = [str(e)]
        try:
            # Pydantic v2 — extract per-field errors
            if hasattr(e, "errors"):
                errs = [
                    f"{'.'.join(str(p) for p in err.get('loc', []))}: {err.get('msg', '')}"
                    for err in e.errors()
                ]
        except Exception:
            pass
        return False, "\n".join(errs), None
    return True, "", validated


def danger_level(tool: str) -> str:
    """Return the danger level for HITL gating: safe|mutating|destructive."""
    return DANGER_LEVELS.get(tool, "safe")


__all__ = [
    "WriteFileInput",
    "EditFileInput",
    "ReadFileInput",
    "BashInput",
    "WebSearchInput",
    "WebFetchInput",
    "AskUserInput",
    "TOOL_SCHEMAS",
    "DANGER_LEVELS",
    "ToolValidationError",
    "validate_tool_input",
    "danger_level",
    "MAX_CONTENT_CHARS",
]
