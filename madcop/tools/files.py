"""v1.6.0 — File read/write/edit tools.

Three tools the agent can call for file operations:

  read_file   — read a file, return content as text
  write_file  — write content to a file (overwrite)
  edit_file   — find-and-replace within a file

All three enforce a **working-directory allowlist** — the agent can
only touch files under an allowed root. This prevents the agent from
reading ``~/.ssh/id_rsa`` or writing to ``/etc/passwd``.

Design (Qian control theory):
  - 可控性: every read/write is scoped to allowed_dirs
  - 稳定性: size caps on read/write prevent memory exhaustion
  - 早纠偏: write_file refuses to create directories outside allowlist
  - 层次化: these tools compose with the sandbox (subprocess) layer
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Sequence

from .registry import Tool

logger = logging.getLogger(__name__)

_MAX_READ_BYTES = 500_000   # 500 KB read cap
_MAX_WRITE_BYTES = 500_000  # 500 KB write cap


def _resolve_in_allowlist(
    path: str | Path,
    allowed_dirs: Sequence[str | Path],
) -> Path:
    """Resolve ``path`` and verify it's inside one of ``allowed_dirs``.

    Raises ``PermissionError`` if outside.
    """
    p = Path(path).expanduser().resolve()
    for allowed in allowed_dirs:
        a = Path(allowed).expanduser().resolve()
        if p == a or a in p.parents:
            return p
    raise PermissionError(
        f"Path '{p}' is outside allowed directories: "
        f"{[str(Path(d).expanduser().resolve()) for d in allowed_dirs]}"
    )


# --------------------------------------------------------------------------- #
# ReadFileTool
# --------------------------------------------------------------------------- #


class ReadFileTool(Tool):
    """Read a text file and return its content."""

    name = "read_file"
    description = (
        "Read a text file and return its content. "
        "The path must be inside an allowed working directory."
    )

    def __init__(self, allowed_dirs: Sequence[str | Path] | None = None) -> None:
        self._allowed_dirs = list(allowed_dirs or [os.getcwd()])

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start from (1-indexed). Default 1.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines to read. Default 500.",
                },
            },
            "required": ["path"],
        }

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        path_str = kwargs.get("path", "")
        if not path_str:
            return {"error": "missing 'path'"}

        try:
            p = _resolve_in_allowlist(path_str, self._allowed_dirs)
        except PermissionError as e:
            return {"error": str(e)}

        if not p.exists():
            return {"error": f"file not found: {p}"}
        if not p.is_file():
            return {"error": f"not a file: {p}"}

        offset = max(1, int(kwargs.get("offset", 1)))
        limit = min(2000, max(1, int(kwargs.get("limit", 500))))

        try:
            content = p.read_text(
                encoding="utf-8", errors="replace",
            )[:_MAX_READ_BYTES]

            lines = content.split("\n")
            total_lines = len(lines)
            start = offset - 1
            end = start + limit
            selected = lines[start:end]

            result_text = "\n".join(selected)
            return {
                "path": str(p),
                "content": result_text,
                "lines": len(selected),
                "total_lines": total_lines,
                "offset": offset,
                "truncated": end < total_lines,
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------- #
# WriteFileTool
# --------------------------------------------------------------------------- #


class WriteFileTool(Tool):
    """Write text content to a file (creates or overwrites)."""

    name = "write_file"
    description = (
        "Write text content to a file. Creates parent directories. "
        "Overwrites existing content. Path must be in allowed dirs."
    )

    def __init__(self, allowed_dirs: Sequence[str | Path] | None = None) -> None:
        self._allowed_dirs = list(allowed_dirs or [os.getcwd()])

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The text content to write.",
                },
            },
            "required": ["path", "content"],
        }

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        path_str = kwargs.get("path", "")
        content = kwargs.get("content", "")

        if not path_str:
            return {"error": "missing 'path'"}
        if len(content) > _MAX_WRITE_BYTES:
            return {"error": f"content too large ({len(content)} > {_MAX_WRITE_BYTES} bytes)"}

        try:
            p = _resolve_in_allowlist(path_str, self._allowed_dirs)
        except PermissionError as e:
            return {"error": str(e)}

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            logger.info("write_file: wrote %d bytes to %s", len(content), p)
            return {
                "path": str(p),
                "bytes": len(content),
                "status": "ok",
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------- #
# EditFileTool
# --------------------------------------------------------------------------- #


class EditFileTool(Tool):
    """Find-and-replace within a file.

    Replaces the first occurrence of ``old_text`` with ``new_text``.
    If ``old_text`` is not found, returns an error.
    """

    name = "edit_file"
    description = (
        "Find and replace text within a file. Replaces first match. "
        "Use for targeted edits without rewriting the whole file."
    )

    def __init__(self, allowed_dirs: Sequence[str | Path] | None = None) -> None:
        self._allowed_dirs = list(allowed_dirs or [os.getcwd()])

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit.",
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find.",
                },
                "new_text": {
                    "type": "string",
                    "description": "The replacement text.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        path_str = kwargs.get("path", "")
        old_text = kwargs.get("old_text", "")
        new_text = kwargs.get("new_text", "")

        if not path_str:
            return {"error": "missing 'path'"}
        if not old_text:
            return {"error": "missing 'old_text'"}

        try:
            p = _resolve_in_allowlist(path_str, self._allowed_dirs)
        except PermissionError as e:
            return {"error": str(e)}

        if not p.exists():
            return {"error": f"file not found: {p}"}

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            if old_text not in content:
                return {"error": f"old_text not found in {p}"}

            new_content = content.replace(old_text, new_text, 1)
            p.write_text(new_content, encoding="utf-8")

            logger.info("edit_file: replaced %d chars in %s", len(old_text), p)
            return {
                "path": str(p),
                "status": "ok",
                "old_len": len(old_text),
                "new_len": len(new_text),
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}


__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
]
