"""Tests for ReAct FINAL_ANSWER JSON unwrapping."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from madcop.agent_network.react_engine import normalize_final_answer


def test_unwrap_message_json():
    raw = '{"message": "✅ 完成\\n\\n## 标题\\n内容"}'
    out = normalize_final_answer(raw)
    assert out.startswith("✅ 完成")
    assert "\n" in out
    assert "## 标题" in out
    assert '{"message"' not in out


def test_plain_markdown_unchanged():
    md = "# 标题\n\n- a\n- b"
    assert normalize_final_answer(md) == md


def test_fence_stripped():
    raw = '```json\n{"answer": "hello\\nworld"}\n```'
    out = normalize_final_answer(raw)
    assert "hello" in out
    assert "world" in out
