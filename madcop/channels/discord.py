"""v1.8.0 — Discord channel.

Uses Discord's REST API to send messages and the Gateway
WebSocket API to receive them. To keep the dep footprint small
(``httpx`` only — no ``discord.py``), the channel:

  - Sends via ``POST /channels/{id}/messages``
  - Receives by polling the gateway WebSocket once per poll cycle.

For v1.8 we implement **send-only** with a simple webhook
integration as the receive side, since the full WebSocket
handshake requires an asyncio loop and library code. A user
who wants full receive can plug in a custom Channel subclass.

Setup:
  1. Create a Discord bot at discord.com/developers.
  2. Set ``MADCOP_DISCORD_BOT_TOKEN=***`` env var (for send).
  3. For receive: register a webhook at channel creation.

Webhooks:
  For receive-only integration, point a Discord webhook at
  ``POST http://localhost:PORT/discord/webhook`` and we
  ingest the messages.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import ChannelBase, IncomingMessage

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
_MAX_MSG_LEN = 2000  # Discord limit


class DiscordChannel(ChannelBase):
    """Discord channel using webhooks (receive) + bot API (send).

    For v1.8, the receive path uses an embedded HTTP server bound
    to a local port. The user configures a Discord webhook that
    POSTs to this server. The send path uses the bot token.

    Args:
        bot_token: Discord bot token. Falls back to
            ``MADCOP_DISCORD_BOT_TOKEN`` env var.
        webhook_port: Local port for the webhook receiver. Default 8765.
        allowed_channel_ids: Optional set of channel IDs to accept.
    """

    name = "discord"

    def __init__(
        self,
        bot_token: str | None = None,
        *,
        webhook_port: int = 8765,
        allowed_channel_ids: set[str] | None = None,
        rate_limit_seconds: float = 1.0,
        on_message=None,
    ) -> None:
        super().__init__(rate_limit_seconds, on_message=on_message)
        self._bot_token = bot_token or os.environ.get("MADCOP_DISCORD_BOT_TOKEN")
        self._webhook_port = webhook_port
        self._allowed_channel_ids = allowed_channel_ids
        # Inbound messages from the webhook server
        self._inbox: list[IncomingMessage] = []
        self._server: Any = None  # http.server.HTTPServer, lazy
        self._server_thread: Any = None

    # ---- receive side: webhook ----

    def handle_webhook_post(self, payload: dict[str, Any]) -> None:
        """Call this from your HTTP server when Discord POSTs a webhook.

        Exposed for testability and for the user to wire into their
        own server. We also start a minimal built-in server when
        ``start()`` is called.
        """
        text = payload.get("content", "").strip()
        if not text:
            return
        user_id = payload.get("user_id") or payload.get("author_id") or "unknown"
        user_name = payload.get("username", "discord-user")
        channel_id = payload.get("channel_id", "")
        if (
            self._allowed_channel_ids is not None
            and channel_id not in self._allowed_channel_ids
        ):
            return
        self._inbox.append(IncomingMessage(
            user_id=str(user_id),
            user_name=user_name,
            text=text,
            raw=payload,
        ))

    def _poll(self) -> list[IncomingMessage]:
        """Drain the inbox."""
        if not self._inbox:
            return []
        out, self._inbox = self._inbox, []
        return out

    # ---- send side: bot API ----

    def _send_impl(self, user_id: str, text: str) -> None:
        """Send a message via Discord's bot API.

        ``user_id`` is a channel ID (Discord DMs need extra setup).
        """
        if not self._bot_token:
            raise RuntimeError(
                "Discord bot_token required to send. "
                "Set MADCOP_DISCORD_BOT_TOKEN or pass token=."
            )
        if len(text) > _MAX_MSG_LEN - 5:
            text = text[:_MAX_MSG_LEN - 5] + "..."

        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{DISCORD_API}/channels/{user_id}/messages",
                headers={
                    "Authorization": f"Bot {self._bot_token}",
                    "Content-Type": "application/json",
                },
                json={"content": text},
            )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Discord sendMessage HTTP {resp.status_code}: {resp.text[:200]}"
            )

    # ---- built-in webhook server ----

    def start(self) -> None:
        """Start the polling thread and the local webhook server."""
        super().start()
        self._start_webhook_server()

    def _start_webhook_server(self) -> None:
        """Start a minimal HTTP server on the configured port."""
        try:
            from http.server import BaseHTTPRequestHandler, HTTPServer
        except ImportError:
            logger.warning("http.server not available; webhook disabled")
            return

        channel = self  # closure

        class WebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                import json as _json
                try:
                    payload = _json.loads(body) if body else {}
                except Exception:
                    payload = {}
                channel.handle_webhook_post(payload)
                self.send_response(204)
                self.end_headers()

            def log_message(self, format, *args):  # silence stderr noise
                pass

        try:
            self._server = HTTPServer(("127.0.0.1", self._webhook_port), WebhookHandler)
        except OSError as e:
            logger.warning("Discord webhook server failed to bind port %d: %s",
                           self._webhook_port, e)
            self._server = None
            return

        import threading
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="madcop-discord-webhook",
        )
        self._server_thread.start()
        logger.info("Discord: webhook server listening on 127.0.0.1:%d",
                    self._webhook_port)

    def stop(self) -> None:
        """Stop the polling thread and the webhook server."""
        super().stop()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._server_thread = None


__all__ = ["DiscordChannel", "DISCORD_API"]
