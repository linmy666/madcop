"""Build conversation-history context for agent modes (standard / deep).

Deep multi-agent previously received only the *last* user line, so follow-ups
like「?」or「你看下上下文」claimed there was no session history. Standard mode
already injected prior turns into ReAct; this module centralises the same
logic for both paths.
"""

from __future__ import annotations

from typing import Any, Sequence


def build_session_context(
    messages: Sequence[Any],
    *,
    max_turns: int = 16,
    max_chars_per_turn: int = 12_000,
    max_total_chars: int = 80_000,
) -> str:
    """Return prior user/assistant turns as a single text block.

    The *current* user message (last user turn) is excluded so callers can
    pass it separately as the active task.
    """
    ua = [
        m
        for m in messages
        if getattr(m, "role", None) in ("user", "assistant")
        and (getattr(m, "content", None) or "").strip()
    ]
    if not ua:
        return ""
    # Drop last user turn — that is the current task.
    prior = ua[:-1] if getattr(ua[-1], "role", None) == "user" else ua
    if not prior:
        return ""

    parts: list[str] = []
    for m in prior[-max_turns:]:
        role = "用户" if m.role == "user" else "助手"
        c = (m.content or "").strip()
        if len(c) > max_chars_per_turn:
            c = c[:max_chars_per_turn] + "\n…(截断)"
        parts.append(f"[{role}]\n{c}")
    ctx = "\n\n---\n\n".join(parts)
    if len(ctx) > max_total_chars:
        ctx = ctx[-max_total_chars:]
    return ctx


def wrap_task_with_history(task: str, context: str) -> str:
    """Embed session history above the current user request for deep/DAG agents."""
    task = (task or "").strip()
    context = (context or "").strip()
    if not context:
        return task
    return (
        "【本会话对话历史】下列内容是本 session 中已有的用户/助手对话。"
        "你**可以且应当**使用这些上文来回答。"
        "禁止声称「无法访问之前的对话」「没有上下文」「看不到历史」。"
        "若用户问「上下文是什么 / 你能看到上文吗」，请根据下列历史如实摘要。\n\n"
        f"{context}\n\n"
        "---\n\n"
        f"【当前用户请求】\n{task}"
    )


__all__ = ["build_session_context", "wrap_task_with_history"]
