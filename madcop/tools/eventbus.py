"""v1.9.0 — Event bus + webhook delivery.

A pub/sub event bus for madcop. Components emit events; other
components (subscribers) react. Subscribers can be:
  - Sync callbacks (functions called in the same thread)
  - Async callbacks (dispatched to a thread pool)
  - Webhook URLs (delivered via HTTP POST)

This is the v1.9.0 "event bus" from the gap analysis vs
DeerFlow/OpenClaw. It enables:
  - Hooking up Slack/Discord/email to madcop events
  - External dashboards tracking runs in real time
  - Multi-agent event-driven coordination

Design (Qian control theory):
  - 可控性: subscribers can be added/removed at runtime
  - 稳定性: subscriber errors don't propagate; events are logged
  - 层次化: emitter → bus → [sync subscribers, async pool, webhooks]
  - 早纠偏: webhooks have a timeout + retry policy
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)

DEFAULT_WEBHOOK_TIMEOUT = 10  # seconds
DEFAULT_MAX_WORKERS = 4


# --------------------------------------------------------------------------- #
# Event
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Event:
    """An event on the bus."""
    type: str                       # e.g. "plan_started", "step_failed", "lesson_written"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: str = "madcop"          # component that emitted


# --------------------------------------------------------------------------- #
# Webhook subscription
# --------------------------------------------------------------------------- #


@dataclass
class WebhookSub:
    """A webhook subscription — URL + event filter."""
    url: str
    event_types: set[str] | None = None  # None = all events
    secret: str | None = None            # for HMAC signing (future)
    timeout: float = DEFAULT_WEBHOOK_TIMEOUT
    max_retries: int = 2

    def matches(self, event: Event) -> bool:
        if self.event_types is None:
            return True
        return event.type in self.event_types


# --------------------------------------------------------------------------- #
# EventBus
# --------------------------------------------------------------------------- #


EventCallback = Callable[[Event], None]


class EventBus:
    """Pub/sub event bus with sync, async, and webhook delivery.

    Thread-safe. Subscribers can be added/removed at runtime.
    """
    def __init__(self, *, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
        self._sync_subs: list[EventCallback] = []
        self._async_subs: list[EventCallback] = []
        self._webhooks: list[WebhookSub] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="madcop-eventbus",
        )
        self._history: list[Event] = []
        self._history_max = 1000

    # ---- subscribe / unsubscribe ----

    def subscribe(self, callback: EventCallback, *, async_dispatch: bool = False) -> None:
        """Register a callback for all events.

        If ``async_dispatch`` is True, the callback runs in the
        thread pool. If False, it runs synchronously in the
        emitter's thread.
        """
        with self._lock:
            if async_dispatch:
                self._async_subs.append(callback)
            else:
                self._sync_subs.append(callback)

    def unsubscribe(self, callback: EventCallback) -> bool:
        with self._lock:
            try:
                self._sync_subs.remove(callback)
                return True
            except ValueError:
                pass
            try:
                self._async_subs.remove(callback)
                return True
            except ValueError:
                return False

    def add_webhook(self, sub: WebhookSub) -> None:
        with self._lock:
            self._webhooks.append(sub)

    def remove_webhook(self, url: str) -> bool:
        with self._lock:
            new_list = [w for w in self._webhooks if w.url != url]
            if len(new_list) < len(self._webhooks):
                self._webhooks = new_list
                return True
            return False

    # ---- emit ----

    def emit(self, event_type: str, data: dict | None = None, *, source: str = "madcop") -> Event:
        """Emit an event. Returns the event object."""
        event = Event(type=event_type, data=data or {}, source=source)
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max:]
            sync_subs = list(self._sync_subs)
            async_subs = list(self._async_subs)
            webhooks = [w for w in self._webhooks if w.matches(event)]

        # Sync subscribers: run in emit thread
        for cb in sync_subs:
            try:
                cb(event)
            except Exception as e:
                logger.warning("EventBus sync subscriber failed: %s", e)

        # Async subscribers: dispatch to thread pool
        for cb in async_subs:
            try:
                self._executor.submit(self._safe_invoke, cb, event)
            except Exception as e:
                logger.warning("EventBus async dispatch failed: %s", e)

        # Webhooks: deliver via HTTP POST (also async)
        for wh in webhooks:
            try:
                self._executor.submit(self._deliver_webhook, wh, event)
            except Exception as e:
                logger.warning("EventBus webhook dispatch failed: %s", e)

        return event

    # ---- introspection ----

    @property
    def history(self) -> list[Event]:
        with self._lock:
            return list(self._history)

    def history_of(self, event_type: str) -> list[Event]:
        return [e for e in self.history if e.type == event_type]

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    # ---- internals ----

    @staticmethod
    def _safe_invoke(cb: EventCallback, event: Event) -> None:
        try:
            cb(event)
        except Exception as e:
            logger.warning("EventBus async subscriber failed: %s", e)

    def _deliver_webhook(self, sub: WebhookSub, event: Event) -> None:
        """POST event JSON to webhook URL. Retries on failure."""
        payload = {
            "type": event.type,
            "data": event.data,
            "timestamp": event.timestamp,
            "source": event.source,
        }
        body = json.dumps(payload).encode("utf-8")
        last_err = None

        for attempt in range(sub.max_retries + 1):
            try:
                req = urllib.request.Request(
                    sub.url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=sub.timeout) as resp:
                    if resp.status < 400:
                        return  # success
                    last_err = f"HTTP {resp.status}"
            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                last_err = str(e)
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"

            if attempt < sub.max_retries:
                time.sleep(0.5 * (attempt + 1))  # linear backoff

        logger.warning(
            "EventBus: webhook delivery to %s failed after %d attempts: %s",
            sub.url, sub.max_retries + 1, last_err,
        )


# --------------------------------------------------------------------------- #
# Global default bus
# --------------------------------------------------------------------------- #


_default_bus: EventBus | None = None
_default_bus_lock = threading.Lock()


def get_default_bus() -> EventBus:
    """Return the process-wide default EventBus (lazy-created)."""
    global _default_bus
    with _default_bus_lock:
        if _default_bus is None:
            _default_bus = EventBus()
        return _default_bus


def emit(event_type: str, data: dict | None = None, *, source: str = "madcop") -> Event:
    """Convenience: emit on the default bus."""
    return get_default_bus().emit(event_type, data, source=source)


__all__ = [
    "Event",
    "EventBus",
    "WebhookSub",
    "EventCallback",
    "get_default_bus",
    "emit",
]
