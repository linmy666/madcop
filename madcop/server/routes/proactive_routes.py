"""Sprint 5 — Proactive Observer backend.

A single lightweight endpoint that the Electron coordinator calls to
ask: "given this file change / terminal output, is it worth nudging the
user, and if so, what should I say?" It makes one small LLM call and
returns a structured verdict.

The route is self-contained (does not import app.py, which has a
pre-existing import-time error) so it can be unit-tested in isolation
with a fake client injected via the app state.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/proactive", tags=["proactive"])


class ProactiveCheck(BaseModel):
    """Inbound payload from the Electron proactive coordinator."""
    source: str = Field(..., description="'file' or 'terminal'")
    content: str = Field(..., description="The changed file diff/summary, or terminal scrollback tail")
    workspace: str = ""


# ── Prompt ───────────────────────────────────────────────────────────────────

_PROACTIVE_PROMPT = """\
你是一个安静的编程助手助手（不是给用户直接回复，而是判断是否需要提醒用户）。
下面是用户工作区里的一段活动（来源：{source}）。请判断它是否值得打断用户。

来源：{source}
工作区：{workspace}

活动内容（最多 {max_chars} 字符）：
\"\"\"{content}\"\"\"

判断标准（值得提醒 = True）：
- 明显的错误：报错、异常堆栈、测试失败、编译失败、linter 报红。
- 可能的问题：疑似配置错误、密钥泄漏、删除了大量文件、疑似死循环。
不值得提醒（False）：正常的文件保存、普通日志输出、成功的命令、无关紧要的改动。

只返回一个 JSON 对象，不要任何额外文字：
{{"worth": true/false, "summary": "一句话概括发生了什么(≤30字)", "suggestion": "若值得提醒，给一句≤40字的建议；否则空字符串"}}
"""


def _build_proactive_prompt(source: str, content: str, workspace: str) -> str:
    max_chars = 1500
    trimmed = content[:max_chars]
    return _PROACTIVE_PROMPT.format(
        source=source, workspace=workspace or "(未指定)",
        content=trimmed, max_chars=max_chars,
    )


def _parse_verdict(raw: str) -> dict[str, Any]:
    """Best-effort parse of the LLM JSON verdict."""
    if not raw:
        return {"worth": False, "summary": "", "suggestion": ""}
    cleaned = raw.strip()
    # Strip markdown fences if present.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    # Extract the first {...} block.
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        cleaned = m.group(0)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return {
                "worth": bool(data.get("worth")),
                "summary": str(data.get("summary", ""))[:120],
                "suggestion": str(data.get("suggestion", ""))[:160],
            }
    except json.JSONDecodeError:
        pass
    return {"worth": False, "summary": "", "suggestion": ""}


def _get_client(request: Request) -> Any:
    """Resolve an LLM client. Priority:
    1. ``app.state.proactive_client`` — injected by tests / callers.
    2. Built from the active provider settings.
    3. None if nothing is configured (caller then skips the LLM call).
    """
    injected = getattr(request.app.state, "proactive_client", None)
    if injected is not None:
        return injected
    try:
        from madcop.config.settings import get_active_client_config, load_settings
        from madcop.llm.factory import build_client_from_config
        settings = load_settings()
        cfg = get_active_client_config(settings)
        if not cfg:
            return None
        return build_client_from_config(cfg, timeout=30.0)
    except Exception:
        return None


@router.post("/check")
def proactive_check(payload: ProactiveCheck, request: Request) -> dict[str, Any]:
    """Decide whether a workspace event is worth a proactive nudge.

    Returns ``{worth, summary, suggestion}``. When no LLM is configured
    we conservatively return ``worth=false`` rather than erroring, so the
    observer silently no-ops instead of spamming the user.
    """
    client = _get_client(request)
    if client is None:
        return {"worth": False, "summary": "", "suggestion": "", "reason": "no_llm"}

    prompt = _build_proactive_prompt(payload.source, payload.content, payload.workspace)
    raw = ""
    try:
        from madcop.llm.client import Message
        messages = [Message(role="user", content=prompt)]
        if hasattr(client, "chat"):
            resp = client.chat(messages, temperature=0.1, max_tokens=160)
            raw = getattr(resp, "content", "") or str(resp)
        elif hasattr(client, "stream"):
            parts: list[str] = []
            for chunk in client.stream(messages, temperature=0.1, max_tokens=160):
                t = getattr(chunk, "text", "") or ""
                if t:
                    parts.append(t)
                if getattr(chunk, "finish_reason", None):
                    break
            raw = "".join(parts)
    except Exception as e:  # noqa: BLE001 — degrade, don't crash the observer
        return {"worth": False, "summary": "", "suggestion": "",
                "reason": f"llm_error: {type(e).__name__}"}

    verdict = _parse_verdict(raw)
    # P2-6 — always return a stable `reason` so the frontend can tell
    # "the LLM judged this" apart from "no LLM configured" / "LLM errored".
    verdict["reason"] = "judged"
    return verdict


__all__ = ["router", "ProactiveCheck", "_build_proactive_prompt", "_parse_verdict"]
