"""Session history injection for deep/standard agent modes."""

from __future__ import annotations

from types import SimpleNamespace

from madcop.agent_network.session_context import (
    build_session_context,
    wrap_task_with_history,
)


def _m(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


def test_build_session_context_drops_current_user_turn():
    msgs = [
        _m("user", "帮我分析一下这份简历"),
        _m("assistant", "简历总体不错，建议改摘要"),
        _m("user", "?"),
    ]
    ctx = build_session_context(msgs)
    assert "帮我分析一下这份简历" in ctx
    assert "简历总体不错" in ctx
    # current "?" must not appear in *prior* context
    assert "?" not in ctx or "帮我分析" in ctx
    # last user line alone should not be the whole context
    assert not ctx.strip().endswith("?")


def test_build_session_context_empty_when_only_current():
    assert build_session_context([_m("user", "hello")]) == ""


def test_wrap_task_embeds_history_and_forbids_amnesia():
    wrapped = wrap_task_with_history("你自己看下上下文", "[用户]\n上文任务A")
    assert "本会话对话历史" in wrapped
    assert "上文任务A" in wrapped
    assert "当前用户请求" in wrapped
    assert "你自己看下上下文" in wrapped
    assert "禁止声称" in wrapped


def test_wrap_without_history_is_passthrough():
    assert wrap_task_with_history("only task", "") == "only task"
