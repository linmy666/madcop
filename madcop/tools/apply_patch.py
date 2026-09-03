"""apply_patch — multi-hunk file editing (codex apply-patch crate port).

One tool call can create / update / move / delete MANY files, with
several hunks per file — the shape models are best at producing after
reading a file, and a big reliability win over N round-trips of
edit_file.

Patch format (codex-compatible, simplified hunks):

    *** Begin Patch
    *** Add File: relative/or/abs/path.py
    +line one
    +line two
    *** Update File: src/app.py
    *** Move to: src/app_renamed.py
    @@ optional context line (ignored, position hint only)
     unchanged context
    -removed line
    +added line
    *** Update File: other.txt
    @@ tail anchor
     last context
    -old ending
    +new ending
    *** End of File
    *** End Patch

Semantics ported from the crate:
  - hunk context lines locate the change via the 4-tier fuzzy
    seek_sequence (exact → rstrip → trim → Unicode punctuation);
  - `*** End of File` anchors the PREVIOUS Update hunk at the tail
    (eof-first search, forward fallback);
  - chunks (context + contiguous -/+ runs) apply left-to-right with a
    forward-moving cursor, so one hunk can hold many edits;
  - every touched file gets its pre-image registered as a revertible
    effect under the caller's effect_key (paper §3.1).

Safety: paths resolve through the same allowlist as write_file.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Sequence

from .files import _seek_sequence

logger = logging.getLogger(__name__)

_BEGIN = "*** Begin Patch"
_END = "*** End Patch"
_EOF_MARKER = "*** End of File"

_HEAD_RE = re.compile(r"^\*\*\* (Add File|Update File|Delete File):\s*(.+?)\s*$")
_MOVE_RE = re.compile(r"^\*\*\* Move to:\s*(.+?)\s*$")
_ACTION_NAMES = {"Add File": "add", "Update File": "update",
                 "Delete File": "delete"}


def parse_patch(patch: str) -> list[dict]:
    """Parse a patch body → list of file ops.

    Each op: {"action": "add"|"update"|"delete", "path": str,
    "move_to": str|None, "chunks": [{"pre": [...], "removed": [...],
    "added": [...], "eof": bool}], "lines": [...]}  (lines only for add).
    """
    if not patch or not patch.strip():
        raise ValueError("补丁为空")
    text = patch.replace("\r\n", "\n")
    if _BEGIN not in text:
        raise ValueError("缺少 *** Begin Patch 起始标记")
    body = text.split(_BEGIN, 1)[1]
    if _END in body:
        body = body.split(_END, 1)[0]

    ops: list[dict] = []
    cur: dict | None = None
    pending_eof_target: dict | None = None

    def _new_chunk():
        return {"pre": [], "removed": [], "added": [], "eof": False}

    for raw in body.split("\n"):
        line = raw.rstrip("\n")
        if not line.strip() and (cur is None or cur["action"] != "add"):
            continue
        head = _HEAD_RE.match(line)
        if head:
            cur = {"action": _ACTION_NAMES[head.group(1)],
                   "path": head.group(2).strip(), "move_to": None,
                   "chunks": [_new_chunk()], "lines": []}
            ops.append(cur)
            continue
        if cur is None:
            continue  # stray text before the first header
        move = _MOVE_RE.match(line)
        if move:
            cur["move_to"] = move.group(1).strip()
            continue
        if line.strip() == _EOF_MARKER:
            # Anchors the most recent update chunk at end-of-file.
            if cur and cur["action"] == "update" and cur["chunks"]:
                cur["chunks"][-1]["eof"] = True
            continue
        if line.startswith("@@"):
            # Position hint only — start a fresh chunk so the context
            # after @@ anchors the next change.
            cur["chunks"].append(_new_chunk())
            continue
        if line.startswith("***") and line.strip() != _BEGIN:
            raise ValueError(f"无法识别的补丁指令行: {line.strip()[:60]}")
        if cur["action"] == "add":
            if line.startswith("+"):
                cur["lines"].append(line[1:])
            elif line.strip() == "":
                cur["lines"].append("")
            else:
                raise ValueError(f"Add File 段的行必须以 + 开头: {line[:40]}")
            continue
        # update/delete hunks
        op, rest = (line[0], line[1:]) if line[:1] in (" ", "-", "+") \
            else (" ", line)
        chunk = cur["chunks"][-1]
        if op == " ":
            if chunk["removed"] or chunk["added"]:
                # context after a change run → new chunk (its pre-anchor)
                cur["chunks"].append(_new_chunk())
                chunk = cur["chunks"][-1]
            chunk["pre"].append(rest)
        elif op == "-":
            chunk["removed"].append(rest)
        else:
            chunk["added"].append(rest)

    # Drop empty navigation chunks (from @@ markers / add ops) — they
    # carry no anchor and no change.
    for op in ops:
        real = [c for c in op["chunks"]
                if c["pre"] or c["removed"] or c["added"]]
        if real:
            op["chunks"] = real
    return ops


def _apply_update(lines: list[str], chunks: list[dict],
                  display_path: str) -> list[str]:
    """Apply update chunks with a forward cursor (codex chunk walk)."""
    cursor = 0
    for chunk in chunks:
        pre, removed, added = chunk["pre"], chunk["removed"], chunk["added"]
        if not removed and not added:
            continue  # pure navigation chunk
        # Locate: pre-context anchors when present, else the removed run.
        anchor = pre if pre else removed
        idx, tier = _seek_sequence(lines, anchor, start=cursor,
                                   eof=chunk["eof"])
        if idx is None:
            raise ValueError(
                f"{display_path}: 补丁上下文定位失败（第 {cursor} 行之后）。"
                "请 read_file 后按文件原文重写补丁。")
        base = idx + (len(anchor) if pre else 0)
        # Verify the removed run actually sits there (fuzzy = rstrip).
        if removed:
            window = lines[base:base + len(removed)]
            ok = len(window) == len(removed) and all(
                window[j].rstrip() == removed[j].rstrip()
                for j in range(len(removed)))
            if not ok:
                raise ValueError(
                    f"{display_path}: 待删除内容与文件不符（位置 {base}）。"
                    "请以 read_file 的原文为准。")
        lines = lines[:base] + added + lines[base + len(removed):]
        cursor = base + len(added)
    return lines


class ApplyPatchTool:
    """Apply a multi-file patch. danger=mutating; per-file inverses are
    captured by the executor's effect layer."""

    name = "apply_patch"
    description = (
        "Apply a multi-file patch in ONE call (codex apply_patch format). "
        "Supports *** Add File / Update File / Delete File / Move to, "
        "multiple hunks per file with context anchors, and "
        "*** End of File tail anchors. Prefer this over edit_file when "
        "changing several places or several files at once."
    )

    def __init__(self, allowed_dirs: Sequence[str | Path] | None = None) -> None:
        self._allowed_dirs = list(allowed_dirs or [os.getcwd()])

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": (
                        "The patch text, starting with *** Begin Patch "
                        "and ending with *** End Patch."
                    ),
                },
            },
            "required": ["patch"],
        }

    def _resolve(self, path_str: str) -> Path:
        from .files import _resolve_in_allowlist
        return _resolve_in_allowlist(path_str, self._allowed_dirs)

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        patch = kwargs.get("patch", "")
        try:
            ops = parse_patch(patch)
        except ValueError as e:
            return {"error": f"补丁解析失败: {e}"}
        if not ops:
            return {"error": "补丁不含任何文件操作"}

        results: list[dict] = []
        try:
            for op in ops:
                results.append(self._apply_op(op))
        except (ValueError, OSError, PermissionError) as e:
            return {"error": f"apply_patch 失败: {e}",
                    "applied": [r.get("path") for r in results]}
        return {
            "status": "ok",
            "files_changed": len(results),
            "results": results,
        }

    def _apply_op(self, op: dict) -> dict:
        action = op["action"]
        p = self._resolve(op["path"])
        if action == "add":
            if p.exists():
                raise ValueError(f"{p}: 文件已存在（Add File 只能建新文件，"
                                 "改用 Update File）")
            p.parent.mkdir(parents=True, exist_ok=True)
            content = "\n".join(op["lines"])
            if content and not content.endswith("\n"):
                content += "\n"
            p.write_text(content, encoding="utf-8")
            logger.info("apply_patch: added %s", p)
            return {"path": str(p), "action": "add"}

        if action == "delete":
            if not p.exists():
                raise ValueError(f"{p}: 文件不存在（Delete File）")
            p.unlink()
            logger.info("apply_patch: deleted %s", p)
            return {"path": str(p), "action": "delete"}

        # update (+ optional move)
        if not p.exists():
            raise ValueError(f"{p}: 文件不存在（Update File）")
        content = p.read_text(encoding="utf-8", errors="replace")
        eol = "\r\n" if "\r\n" in content else "\n"
        lines = content.split(eol)
        if lines and lines[-1] == "":
            lines = lines[:-1]  # trailing newline → join adds it back
        lines = _apply_update(lines, op["chunks"], str(p))
        new_content = eol.join(lines) + (eol if content.endswith(eol) else "")

        target = self._resolve(op["move_to"]) if op.get("move_to") else p
        if op.get("move_to") and target != p:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
        if target != p:
            p.unlink()
        logger.info("apply_patch: updated %s%s", p,
                    f" → {target}" if target != p else "")
        return {"path": str(target), "action": "update",
                **({"moved_from": str(p)} if target != p else {})}

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


__all__ = ["ApplyPatchTool", "parse_patch"]
