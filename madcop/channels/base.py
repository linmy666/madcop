"""v1.8.0 — Channel base class for madcop.

A Channel is a bidirectional interface between madcop and an external
messaging platform (Telegram, Discord, etc.). It:
  - Receives user messages and dispatches them to the agent
  - Sends agent responses back to the user

Common interface:
  channel.send_message(user_id, text) → bool
  channel.start() / channel.stop() — background polling loop
  channel.on_message(callback) — register message handler

Design (Qian control theory):
  - 可控性: each channel has start/stop; daemon thread lifecycle
  - 稳定性: rate-limiting + error isolation (one bad message
    doesn't kill the polling loop)
  - 层次化: ChannelBase → TelegramChannel / DiscordChannel
"""
from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# IncomingMessage
# --------------------------------------------------------------------------- #


@dataclass
class IncomingMessage:
    """A message received from a channel."""
    user_id: str           # platform-specific user ID
    user_name: str         # display name (or "@anonymous")
    text: str              # the message content
    raw: dict[str, Any] = field(default_factory=dict)


# Message handler callback
MessageHandler = Callable[["ChannelBase", IncomingMessage], None]


# --------------------------------------------------------------------------- #
# ChannelBase
# --------------------------------------------------------------------------- #


class ChannelBase(ABC):
    """Base class for messaging channels.

    Subclasses must implement ``_poll()`` and ``_send_impl()``.
    The base class manages:
      - Background thread lifecycle (start/stop)
      - Message handler registration
      - Rate limiting
      - Error isolation (one exception doesn't kill the loop)
    """

    name: str = "base"

    def __init__(
        self,
        rate_limit_seconds: float = 1.0,
        *,
        on_message: MessageHandler | None = None,
    ) -> None:
        self._rate_limit = rate_limit_seconds
        self._handler = on_message
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_send_ts: dict[str, float] = {}

    # ---- public API ----

    def on_message(self, handler: MessageHandler) -> None:
        """Register a callback for incoming messages."""
        self._handler = handler

    def send_message(self, user_id: str, text: str) -> bool:
        """Send a message to a user. Returns True on success.

        Enforces rate limiting per user.
        """
        last = self._last_send_ts.get(user_id, 0.0)
        if time.time() - last < self._rate_limit:
            time.sleep(self._rate_limit)
        try:
            self._send_impl(user_id, text)
            self._last_send_ts[user_id] = time.time()
            return True
        except Exception as e:
            logger.warning("%s: send failed to %s: %s", self.name, user_id, e)
            return False

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True,
            name=f"madcop-channel-{self.name}",
        )
        self._thread.start()
        logger.info("%s: channel started", self.name)

    def stop(self) -> None:
        """Stop the background thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("%s: channel stopped", self.name)

    # ---- abstract interface ----

    @abstractmethod
    def _poll(self) -> list[IncomingMessage]:
        """Fetch new messages from the platform. Returns empty if none."""
        ...

    @abstractmethod
    def _send_impl(self, user_id: str, text: str) -> None:
        """Platform-specific send. Subclasses implement this."""
        ...

    # ---- internals ----

    def _run_loop(self) -> None:
        """Main loop: poll → dispatch → sleep → repeat."""
        while not self._stop_event.is_set():
            try:
                messages = self._poll()
                for msg in messages:
                    self._dispatch(msg)
            except Exception as e:
                logger.warning("%s: poll error: %s", self.name, e)
            self._stop_event.wait(1.0)

    def _dispatch(self, msg: IncomingMessage) -> None:
        """Run the registered handler. Errors don't kill the loop."""
        if self._handler is None:
            logger.debug("%s: no handler for message from %s", self.name, msg.user_id)
            return
        try:
            self._handler(self, msg)
        except Exception as e:
            logger.warning(
                "%s: handler failed for message from %s: %s",
                self.name, msg.user_id, e,
            )


__all__ = ["ChannelBase", "IncomingMessage", "MessageHandler"]
