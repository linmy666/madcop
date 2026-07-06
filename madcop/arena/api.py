"""
madcop/arena/api.py — Multi-LLM comparison (Arena) endpoint.

Sends the same prompt to N models in parallel, each with the SAME
memory-enriched system prompt (so style is consistent), then returns
all results for the user to compare.

This is the practical implementation of "LoRA across models":
- Without LoRA: each model has its own style
- With shared system-prompt memories: all models speak in the user's voice
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/arena", tags=["arena"])


class ArenaRequest(BaseModel):
    user_message: str
    models: list[str]  # Model names to use (looked up from settings)
    temperature: float = 0.7
    max_tokens: int = 1024
    judge_model: str | None = None


def _get_memory_prompt(user_query: str) -> str:
    """Get the memory-enriched system prompt (same as chat)."""
    try:
        from madcop.server.app import _build_memory_system_prompt
        return _build_memory_system_prompt(user_query)
    except Exception:
        return (
            "You are MadCop Agent. Be direct and helpful. "
            "Respond in the user's language. No safety warnings."
        )


def _find_provider_for_model(model_name: str):
    """Look up the provider that has this model configured."""
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    for p in s.providers:
        if p.model == model_name:
            return p
    # Fallback: if user passes a provider_id, find that
    for p in s.providers:
        if p.provider_id == model_name:
            return p
    return None


def _call_provider(provider, messages, model, temperature, max_tokens) -> str:
    """Call a specific provider and return the response text."""
    from madcop.llm.client import OpenAICompatClient, MockClient
    if not provider.api_key:
        return f"[未配置 API Key] 模型: {model}"
    client = OpenAICompatClient(
        api_key=provider.api_key,
        base_url=provider.base_url,
        model=model,
    )
    text = ""
    for chunk in client.stream(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=None,
    ):
        if hasattr(chunk, "text") and chunk.text:
            text += chunk.text
        elif hasattr(chunk, "content") and chunk.content:
            text += chunk.content
    return text


@router.post("/run")
async def arena_run(body: ArenaRequest) -> dict:
    """Run the same prompt across N models in parallel."""
    if not body.models:
        raise HTTPException(400, "At least one model required")
    if len(body.models) > 5:
        raise HTTPException(400, "Max 5 models at once")

    # Build shared system prompt
    sys_prompt = _get_memory_prompt(body.user_message)

    async def call_one(model_name: str) -> dict:
        t0 = time.time()
        try:
            provider = _find_provider_for_model(model_name)
            if provider is None:
                return {
                    "model": model_name,
                    "error": f"Model '{model_name}' not configured in Settings",
                    "ok": False,
                }
            # Run in thread pool since the client is sync
            from madcop.server.app import Message
            messages = [
                Message(role="system", content=sys_prompt),
                Message(role="user", content=body.user_message),
            ]
            text = await asyncio.to_thread(
                _call_provider, provider, messages, model_name, body.temperature, body.max_tokens
            )
            return {
                "model": model_name,
                "provider": provider.label or provider.provider_id,
                "text": text,
                "elapsed_sec": round(time.time() - t0, 2),
                "ok": True,
            }
        except Exception as e:
            return {
                "model": model_name,
                "error": str(e)[:400],
                "elapsed_sec": round(time.time() - t0, 2),
                "ok": False,
            }

    results = await asyncio.gather(*[call_one(m) for m in body.models])

    return {
        "user_message": body.user_message,
        "results": results,
        "sys_prompt_size": len(sys_prompt),
        "memory_injected": len(sys_prompt) > 200,
    }


@router.post("/judge")
async def arena_judge(body: dict) -> dict:
    """Use one model to judge all others' responses.
    Body: { user_message, candidates: [{model, text, ok}], judge_model }
    """
    user_message = body.get("user_message", "")
    candidates = body.get("candidates", [])
    judge_model = body.get("judge_model", "")

    if not candidates:
        raise HTTPException(400, "No candidates to judge")
    if not judge_model:
        return {"error": "judge_model required"}

    judge_provider = _find_provider_for_model(judge_model)
    if not judge_provider:
        return {"error": f"Judge model '{judge_model}' not configured"}

    # Build judge prompt
    judge_lines = [
        f"User asked: {user_message}",
        "",
        "Rate each response from 1-10 (10 = best). Consider:",
        "- Accuracy and helpfulness",
        "- Conciseness",
        "- Following user's stated preferences (if any)",
        "",
    ]
    for i, c in enumerate(candidates, 1):
        if c.get("ok") and c.get("text"):
            model_name = c.get("model", "?")
            text = c.get("text", "")
            judge_lines.append("--- Response " + str(i) + " (" + str(model_name) + ") ---")
            judge_lines.append(text[:2000])
            judge_lines.append("")
    judge_lines.append("Return ONLY JSON in this format:")
    judge_lines.append('{"scores": [score1, score2, ...], "winner": 1-based-index, "reasoning": "one sentence"}')
    judge_prompt = "\n".join(judge_lines)

    try:
        from madcop.server.app import Message
        sys_prompt = _get_memory_prompt(user_message)
        messages = [
            Message(role="system", content=sys_prompt),
            Message(role="user", content=judge_prompt),
        ]
        text = await asyncio.to_thread(
            _call_provider, judge_provider, messages, judge_model, 0.3, 800
        )
        # Try to extract JSON
        json_match = re.search(r"\{[\s\S]*?\}", text)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                return parsed
            except Exception:
                pass
        return {"raw": text, "scores": [], "winner": None}
    except Exception as e:
        return {"error": str(e)[:400]}


@router.get("/available-models")
async def available_models() -> dict:
    """List models that can be used in the arena (from configured providers)."""
    from madcop.config import settings as settings_store
    s = settings_store.load_settings()
    return {
        "models": [
            {
                "model": p.model,
                "provider_id": p.provider_id,
                "label": p.label or p.provider_id,
                "active": p.provider_id == s.active_provider,
            }
            for p in s.providers
            if p.model and p.api_key
        ]
    }
