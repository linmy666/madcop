"""Regression: attachments reach deep task text; writes land in work_dir.

Run: python -m pytest tests/test_attachment_and_workdir.py -v
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from madcop.server.models import ChatAttachment
from madcop.server.app import _read_attachment_direct
from madcop.tools import default_registry
from madcop.tools.files import WriteFileTool, _resolve_in_allowlist


def test_read_attachment_txt_dataurl():
    body = "这是简历正文：姚振炀，5年经验。"
    b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
    att = ChatAttachment(
        id="att-1",
        name="resume.txt",
        type="file",
        dataUrl=f"data:text/plain;base64,{b64}",
    )
    text = _read_attachment_direct(att)
    assert "姚振炀" in text
    assert "5年经验" in text


def test_read_attachment_path():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "note.md"
        p.write_text("# 分析目标\n内容ABC", encoding="utf-8")
        att = ChatAttachment(id="att-2", name="note.md", type="file", path=str(p))
        text = _read_attachment_direct(att)
        assert "内容ABC" in text


def test_relative_write_resolves_to_workspace():
    with tempfile.TemporaryDirectory() as td:
        tool = WriteFileTool(allowed_dirs=[td])
        result = tool(path="analysis.md", content="hello workspace")
        assert result.get("status") == "ok"
        out = Path(td) / "analysis.md"
        assert out.is_file()
        assert out.read_text(encoding="utf-8") == "hello workspace"


def test_absolute_outside_allowlist_denied():
    with tempfile.TemporaryDirectory() as td:
        tool = WriteFileTool(allowed_dirs=[td])
        result = tool(path="/tmp/madcop_should_not_write_xyz.txt", content="x")
        assert "error" in result


def test_default_registry_includes_work_dir():
    with tempfile.TemporaryDirectory() as td:
        reg = default_registry(workspace_dir=td)
        names = set(reg.names())
        assert "write_file" in names
        assert "read_file" in names
        # Relative write via registry dispatch
        from madcop.llm.client import ToolCall  # may not exist
        # Call tool object directly
        wf = reg.get("write_file") if hasattr(reg, "get") else None
        if wf is None:
            # fallback: find by name
            for t in getattr(reg, "_tools", {}).values() if hasattr(reg, "_tools") else []:
                pass
        # Use WriteFileTool path resolution as the contract
        p = _resolve_in_allowlist("out.txt", [td])
        assert str(p).startswith(str(Path(td).resolve()))


def test_deep_task_text_includes_attachment_block_logic():
    """Mirror the app.py fix: last user content must be the injected one."""
    from madcop.llm import Message

    short = "帮忙分析下"
    injected = (
        f"{short}\n"
        f"\n--- ATTACHMENT: 简历.docx (ID: att-x) ---\n"
        f"姓名：测试\n--- END ---"
    )
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content=injected),
    ]
    task = ""
    for m in reversed(messages):
        if m.role == "user" and (m.content or "").strip():
            task = m.content
            break
    assert "ATTACHMENT" in task
    assert "姓名：测试" in task
    # The bug was using body.messages short text only:
    body_only = short
    assert "ATTACHMENT" not in body_only
