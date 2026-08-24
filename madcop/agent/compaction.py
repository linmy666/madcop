"""Token-driven context compaction (pi-mono design, compaction.ts port).

Replaces MadCop's old truncation ("keep head-2 + tail-12, chop middle
to 200 chars per message") which destroyed long-session context
quality. The pi design:

- Trigger:  context_tokens > context_window - RESERVE_TOKENS
- Summary:  structured checkpoint prompt (Goal / Constraints /
            Progress / Key Decisions / Next Steps / Critical Context)
            — with an INCREMENTAL variant for repeat compactions.
- Cut:      keep the most recent KEEP_RECENT_TOKENS, cut ONLY at a
            user-message boundary (never orphans an assistant turn).
- Overflow: a provider context-length error force-compacts and the
            caller retries once.
- The summary request runs on its own (tool-less, low-temp) call so
  it doesn't pollute the main conversation trajectory.

Usage (chat_v4):
    from madcop.agent.compaction import should_compact, compact_messages
    if should_compact(messages, last_usage):
        messages, record = compact_messages(messages, client, model)
        session_log.append(system_event("compaction", record["summary"],
                                        **{"keep_tail_n": record["keep_tail_n"], ...}))
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Defaults (overridable via env for testing / small-window providers).
DEFAULT_CONTEXT_WINDOW = int(os.environ.get("MADCOP_CONTEXT_WINDOW", "128000"))
RESERVE_TOKENS = int(os.environ.get("MADCOP_COMPACTION_RESERVE", "16384"))
KEEP_RECENT_TOKENS = int(os.environ.get("MADCOP_COMPACTION_KEEP_RECENT", "20000"))

_OVERFLOW_MARKERS = (
    "context length", "context_length", "maximum context",
    "too many tokens", "prompt is too long", "exceeds the model",
    "input length and `max_tokens` exceed",
)


def estimate_tokens(text: str) -> int:
    """chars/4 heuristic — pi's estimateTokens. Good enough to decide
    WHEN to compact; provider usage (when available) is the precise
    number and wins over this estimate."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def is_overflow_error(exc: Exception) -> bool:
    """Does this provider error mean the context window is full?"""
    msg = str(exc).lower()
    return any(marker in msg for marker in _OVERFLOW_MARKERS)


def messages_tokens(messages: Iterable[dict[str, str]]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in messages)


def context_tokens(messages: Iterable[dict[str, str]],
                   last_usage: dict[str, int] | None) -> int:
    """Best live estimate: provider usage (P1-5) when fresh, else the
    chars/4 estimate over the whole assembled context."""
    est = messages_tokens(messages)
    if last_usage and last_usage.get("prompt_tokens"):
        # prompt_tokens already includes the system prompt + history —
        # take whichever signal is larger (usage lags by one call).
        return max(est, int(last_usage["prompt_tokens"]))
    return est


def should_compact(messages: list[dict[str, str]],
                   last_usage: dict[str, int] | None,
                   context_window: int = DEFAULT_CONTEXT_WINDOW) -> bool:
    return context_tokens(messages, last_usage) > context_window - RESERVE_TOKENS


def select_cut_point(messages: list[dict[str, str]],
                     keep_recent_tokens: int = KEEP_RECENT_TOKENS) -> int:
    """Index where history splits head/tail.

    Walks from the tail accumulating tokens; the cut snaps FORWARD to
    the nearest user-message boundary so an assistant turn + its
    observation never split. Returns len(messages) (no compaction)
    when the whole history fits in the keep-recent budget; returns 0
    in the degenerate case where even one message blows the budget
    (compact everything — callers bump 0 to 1 to keep a non-empty head).
    """
    acc = 0
    exceeded = False
    cut = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        acc += estimate_tokens(messages[i].get("content", ""))
        if acc > keep_recent_tokens:
            exceeded = True
            break
        cut = i
    if not exceeded:
        return len(messages)
    # snap forward to a user boundary (tail starts at a user turn)
    while cut < len(messages) and messages[cut].get("role") != "user":
        cut += 1
    if cut >= len(messages):
        return 0  # tail would be empty — compact from the very start
    return cut


CHECKPOINT_PROMPT = """你是会话压缩器。把下面的对话历史压缩成结构化检查点，供后续对话继续使用。
保留所有具体信息：文件路径、报错原文、命令、数字、已做的决定。不要泛化。

输出格式（严格遵守）：
## 目标
（用户最初的请求/当前任务）
## 约束
（技术栈、路径限制、用户偏好等）
## 进展
### 已完成
### 进行中
### 受阻
## 关键决策
（已确定的技术选择及原因）
## 下一步
## 关键上下文
（必须延续的事实：路径、文件名、函数名、错误信息）

对话历史：
{history}"""

CHECKPOINT_UPDATE_PROMPT = """你是会话压缩器。已有旧检查点和新增对话，输出合并后的新检查点。
保留旧检查点中仍然有效的信息，合并新增进展，移除已被取代的内容。
格式与旧检查点相同（目标/约束/进展/关键决策/下一步/关键上下文）。

旧检查点：
{prev_summary}

新增对话：
{history}"""


def _render_history(messages: list[dict[str, str]], limit_chars: int = 24000) -> str:
    """Compact textual rendering of the head messages for the summarizer
    (bounded so the summary call itself can't overflow)."""
    parts: list[str] = []
    total = 0
    for m in messages:
        line = f"[{m.get('role', 'user')}] {m.get('content', '')}"
        if total + len(line) > limit_chars:
            remain = limit_chars - total
            if remain > 200:
                parts.append(line[:remain] + "…(截断)")
            break
        parts.append(line)
        total += len(line)
    return "\n".join(parts)


def compact_messages(
    messages: list[dict[str, str]],
    client: Any,
    model: str | None = None,
    prev_summary: str = "",
    keep_recent_tokens: int = KEEP_RECENT_TOKENS,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Compact a message list → (new_messages, record).

    new_messages = [summary as user message] + tail. record describes
    what happened (for the session log's compaction event). On summary
    failure, falls back to keeping [prev_summary or brief note] + tail
    — never raises into the chat path.
    """
    cut = select_cut_point(messages, keep_recent_tokens)
    if cut == 0:
        cut = min(1, len(messages))
    head, tail = messages[:cut], messages[cut:]
    if not head:
        return messages, {"compacted": False, "keep_tail_n": len(messages)}

    history_text = _render_history(head)
    prompt = (
        CHECKPOINT_UPDATE_PROMPT.format(prev_summary=prev_summary, history=history_text)
        if prev_summary else
        CHECKPOINT_PROMPT.format(history=history_text)
    )
    summary = ""
    try:
        from madcop.llm.client import Message
        resp = client.chat(
            [Message(role="user", content=prompt)],
            model=model, temperature=0.3, max_tokens=2000,
        )
        summary = (getattr(resp, "content", "") or "").strip()
    except Exception as e:
        logger.warning("compaction summary failed, keeping note: %s", e)

    if not summary:
        if prev_summary:
            summary = prev_summary
        else:
            summary = (
                "--- 早期对话已压缩（摘要生成失败，仅保留要点）---\n"
                + _render_history(head, limit_chars=1500)
            )

    new_messages = [
        {"role": "user",
         "content": f"<summary>以下是本会话早期内容的压缩检查点：\n\n{summary}\n</summary>"},
        *tail,
    ]
    record = {
        "compacted": True,
        "summary": summary,
        "keep_tail_n": len(tail),
        "head_turns": cut,
        "used_prev_summary": bool(prev_summary),
    }
    return new_messages, record


__all__ = [
    "DEFAULT_CONTEXT_WINDOW", "RESERVE_TOKENS", "KEEP_RECENT_TOKENS",
    "estimate_tokens", "is_overflow_error", "messages_tokens",
    "context_tokens", "should_compact", "select_cut_point",
    "compact_messages",
]
