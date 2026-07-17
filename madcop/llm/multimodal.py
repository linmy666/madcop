"""Helpers to build multimodal Message content for different LLM families."""
from __future__ import annotations

from typing import Any

from madcop.llm.capabilities import image_content_block, text_content_block
from madcop.llm.client import Message


def user_message_with_images(
    text: str,
    images: list[dict[str, str]],
    *,
    api_format: str = "openai_chat",
) -> Message:
    """Build a user Message with optional images.

    Each image dict: ``{"data_url": "..."}`` or ``{"url": "...", "media_type": "..."}``.
    """
    if not images:
        return Message(role="user", content=text)
    blocks: list[dict[str, Any]] = [text_content_block(text, api_format)]
    for img in images:
        blocks.append(
            image_content_block(
                data_url=img.get("data_url") or img.get("dataUrl"),
                url=img.get("url"),
                media_type=img.get("media_type") or img.get("mediaType") or "image/png",
                api_format=api_format,
            )
        )
    return Message(role="user", content=blocks)
