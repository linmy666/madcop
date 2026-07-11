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

    def _read_attachment(self, att: dict[str, Any]) -> dict[str, Any]:
        """Decode an inline attachment (from chat composer) and return its
        content as a string. Supports text files (utf-8) and a metadata
        header for binary files like images/PDFs."""
        name = att.get("name", "attachment")
        mime = att.get("mimeType", "")
        data = att.get("data", "")
        if not data:
            return {"error": f"no data for attachment {name}"}
        # data may be a data URL (data:<mime>;base64,<...>) — keep the
        # metadata but truncate the body for very large files.
        if data.startswith("data:") and "," in data:
            header, body = data.split(",", 1)
            # If it's a text-y mime, try to decode and return text.
            if mime.startswith("text/") or mime in ("application/json", "application/xml"):
                import base64 as _b64
                try:
                    return {"path": att.get("id") or name,
                            "content": _b64.b64decode(body).decode("utf-8", errors="replace")}
                except Exception as e:
                    return {"error": f"failed to decode {name}: {e}"}
            # PDF: extract real text using pypdf
            if mime == "application/pdf" or name.lower().endswith(".pdf"):
                try:
                    import base64 as _b64
                    import io as _io
                    from pypdf import PdfReader as _PdfReader
                    raw_bytes = _b64.b64decode(body)
                    reader = _PdfReader(_io.BytesIO(raw_bytes))
                    pages_text = []
                    for i, page in enumerate(reader.pages):
                        try:
                            t = page.extract_text() or ""
                        except Exception:
                            t = ""
                        pages_text.append(f"--- Page {i + 1} ---\n{t}")
                    text = "\n\n".join(pages_text).strip()
                    if text:
                        # Truncate very large PDFs to keep response manageable
                        max_chars = 30_000
                        if len(text) > max_chars:
                            text = text[:max_chars] + f"\n\n[truncated at {max_chars} chars of {len(text)} total]"
                        return {
                            "path": att.get("id") or name,
                            "content": text,
                        }
                    return {
                        "error": f"could not extract text from PDF: {name} (scanned/image-only PDF?)"
                    }
                except Exception as e:
                    return {"error": f"failed to parse PDF {name}: {e}"}
            # Binary: return metadata; LLM can decide what to do.
            # Excel xlsx — extract as text via openpyxl
            if name.lower().endswith(".xlsx") or name.lower().endswith(".xls") or mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                import base64 as _b64
                raw_bytes = _b64.b64decode(body)
                try:
                    import io as _io, openpyxl as _xl
                    wb = _xl.load_workbook(_io.BytesIO(raw_bytes), data_only=True, read_only=True)
                    parts = []
                    for sheet_name in wb.sheetnames:
                        ws = wb[sheet_name]
                        rows = list(ws.iter_rows(values_only=True))
                        if not rows: continue
                        parts.append(f"## Sheet: {sheet_name} ({len(rows)} rows, {len(rows[0])} cols)")
                        header = " | ".join(str(c or "") for c in rows[0])
                        sep = " | ".join("---" for _ in rows[0])
                        body_rows = []
                        for row in rows[1:201]:
                            body_rows.append(" | ".join(str(c or "") for c in row))
                        parts.append(f"| {header} |\n| {sep} |\n" + "\n".join(f"| {r} |" for r in body_rows))
                        if len(rows) > 201:
                            parts.append(f"... ({len(rows) - 201} more rows)")
                    wb.close()
                    content = "\n\n".join(parts)
                    return {"path": att.get("id") or name, "content": content[:60_000] or "[empty xlsx]"}
                except Exception as _xe:
                    return {"path": att.get("id") or name, "content": f"[xlsx parse error: {_xe}]"}
            return {
                "path": att.get("id") or name,
                "content": f"[binary file: {name}, type: {mime}, size: {len(body)} base64 chars — describe what you see or do not try to render]",
            }
        # Raw text fallback.
        return {"path": att.get("id") or name, "content": data}

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        path_str = kwargs.get("path", "")
        if not path_str:
            return {"error": "missing 'path'"}

        # Virtual path scheme for inline attachments sent from the chat
        # composer. We can't use the real disk path because the user's
        # file API may not have a path in Electron. Instead we look up
        # the attachment in a module-level registry keyed by id.
        if path_str.startswith("attachment://"):
            from . import inline_attachments
            att_id = path_str[len("attachment://"):]
            att = inline_attachments.get(att_id)
            if not att:
                return {"error": f"attachment not found: {att_id}"}
            return self._read_attachment(att)

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

        # Detect PDF by extension and use pypdf to extract text instead of
        # reading raw binary bytes as UTF-8 (which produces garbage).
        if str(p).lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader as _PdfReader
                reader = _PdfReader(str(p))
                pages_text = []
                for i, page in enumerate(reader.pages):
                    try:
                        t = page.extract_text() or ""
                    except Exception:
                        t = ""
                    pages_text.append(f"--- Page {i + 1} ---\n{t}")
                text = "\n\n".join(pages_text).strip()
                if text:
                    max_chars = 60_000
                    if len(text) > max_chars:
                        text = text[:max_chars] + f"\n\n[truncated at {max_chars} chars of {len(text)} total]"
                    return {"path": str(p), "content": text}
                return {"error": f"could not extract text from PDF: {p.name} (scanned/image-only PDF?)"}
            except Exception as e:
                return {"error": f"failed to parse PDF {p.name}: {e}"}

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
