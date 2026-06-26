"""v1.8.0 — Channel abstraction for madcop.

A Channel is a bidirectional interface between madcop and an external
messaging platform (Telegram, Discord, etc.). It:
  - Receives user messages and dispatches them to the agent
  - Sends agent responses back to the user

Common interface:
  channel.send_message(user_id, text) → bool
  channel.start() / channel.stop() — background polling loop
  channel.on_message(callback) — register message handler
"""
from __future__ import annotations

from .base import ChannelBase, IncomingMessage, MessageHandler
from .telegram import TelegramChannel
from .discord import DiscordChannel

__all__ = [
    "ChannelBase",
    "IncomingMessage",
    "MessageHandler",
    "TelegramChannel",
    "DiscordChannel",
]
