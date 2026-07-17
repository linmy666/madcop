"""Vendor-aware retry for LLM calls."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRY_NEEDLES = (
    "429",
    "rate limit",
    "rate_limit",
    "timeout",
    "timed out",
    "503",
    "502",
    "overloaded",
    "temporarily unavailable",
    "connection reset",
    "connection aborted",
    "server error",
)


def is_retryable_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        return True
    return any(n in msg for n in _RETRY_NEEDLES)


def with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_s: float = 0.8,
    max_delay_s: float = 12.0,
    label: str = "llm",
) -> T:
    """Run ``fn`` with exponential backoff + jitter on retryable errors."""
    last: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt >= max_attempts or not is_retryable_error(e):
                raise
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay *= 0.5 + random.random()
            logger.warning(
                "%s attempt %s/%s failed (%s); retry in %.1fs",
                label, attempt, max_attempts, e, delay,
            )
            time.sleep(delay)
    assert last is not None
    raise last
