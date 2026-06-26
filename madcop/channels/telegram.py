"""v1.8.0 — Telegram channel.

Uses Telegram's Bot API with long-polling (``getUpdates``) to
receive messages. Sends via ``sendMessage``. No third-party
Telegram library — just ``httpx``.

Setup:
  1. Create a bot via @BotFather on Telegram, get the token.
  2. Set ``MADCOP_TELEGRAM_BOT_TOKEN=...`` env var (or pass token=).
  3. Start the channel: ``TelegramChannel(token).start()``.

Long polling timeout: 25 seconds (Telegram's recommended max).
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import ChannelBase, IncomingMessage

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
_LONG_POLL_TIMEOUT = 25  # seconds
_ALLOWED_UPDATES = 30   # timeout for httpx in long poll


class TelegramChannel(ChannelBase):
    """Telegram bot integration via long polling.

    Args:
        token: Bot token from @BotFather. Falls back to
            ``MADCOP_TELEGRAM_BOT_TOKEN`` env var.
        allowed_user_ids: Optional set of user IDs to accept. If None,
            accepts all users.
    """

    name = "telegram"

    def __init__(
        self,
        token: str | None = None,
        *,
        allowed_user_ids: set[int] | None = None,
        rate_limit_seconds: float = 1.0,
        on_message=None,
    ) -> None:
        super().__init__(rate_limit_seconds, on_message=on_message)
        self._token = token or os.environ.get("MADCOP_TELEGRAM_BOT_TOKEN")
        if not self._token:
            raise ValueError(
                "Telegram token required. Pass token= or set "
                "MADCOP_TELEGRAM_BOT_TOKEN env var."
            )
        self._allowed_user_ids = allowed_user_ids
        self._offset: int | None = None  # for getUpdates long polling
        self._client = httpx.Client(timeout=_LONG_POLL_TIMEOUT + 5)

    # ---- ChannelBase interface ----

    def _poll(self) -> list[IncomingMessage]:
        """Long-poll for new updates via getUpdates."""
        params: dict[str, Any] = {
            "timeout": _LONG_POLL_TIMEOUT,
            "allowed_updates": ["message"],
        }
        if self._offset is not None:
            params["offset"] = self._offset

        try:
            resp = self._client.get(
                f"{TELEGRAM_API}/bot{self._token}/getUpdates",
                params=params,
            )
        except httpx.TimeoutException:
            # Normal for long-polling — no new updates
            return []
        except Exception as e:
            logger.warning("Telegram getUpdates failed: %s", e)
            return []

        if resp.status_code != 200:
            logger.warning("Telegram getUpdates HTTP %d: %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()
        if not data.get("ok"):
            logger.warning("Telegram returned not-ok: %s", data)
            return []

        results = data.get("result", [])
        messages = []
        for update in results:
            update_id = update.get("update_id")
            if update_id is not None:
                # Mark as acknowledged
                self._offset = update_id + 1

            msg_data = update.get("message")
            if not msg_data:
                continue
            text = msg_data.get("text", "").strip()
            if not text:
                continue

            from_user = msg_data.get("from", {})
            user_id = str(from_user.get("id", ""))
            user_name = from_user.get("username") or from_user.get("first_name", "anonymous")

            # Allowlist check
            if self._allowed_user_ids is not None:
                if int(user_id) not in self._allowed_user_ids:
                    logger.info("Telegram: ignoring message from non-allowed user %s", user_id)
                    continue

            messages.append(IncomingMessage(
                user_id=user_id,
                user_name=user_name,
                text=text,
                raw=update,
            ))

        return messages

    def _send_impl(self, user_id: str, text: str) -> None:
        """Send a message via sendMessage."""
        # Telegram message limit: 4096 chars
        if len(text) > 4000:
            text = text[:3997] + "..."

        resp = self._client.post(
            f"{TELEGRAM_API}/bot{self._token}/sendMessage",
            json={
                "chat_id": int(user_id),
                "text": text,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Telegram sendMessage HTTP {resp.status_code}: {resp.text[:200]}"
            )

    def send_message(self, user_id: str, text: str) -> bool:
        """Override to also support chat_id strings starting with @."""
        if user_id.startswith("@"):
            # Username — would need getChat to resolve; skip
            logger.warning("Telegram: send to @username not supported yet")
            return False
        return super().send_message(user_id, text)


__all__ = ["TelegramChannel", "TELEGRAM_API"]
