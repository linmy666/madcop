"""Vendor-aware retry for LLM calls."""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass, field
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


# ─── P1-8: normalized stream-error classification ──────────────────────────
# Mirrors OpenAI Agents SDK retry.py: classify the failure, decide
# retryability, and keep REPLAY SAFETY separate from retry — a stream
# that already delivered chunks must never silently restart (the UI
# would show duplicated content).

@dataclass
class StreamErrorInfo:
    category: str            # network | timeout | rate_limit | server | auth | context_length | other
    retryable: bool          # category is worth retrying at all
    retry_after_s: float | None = None   # provider-advertised wait (429)
    message: str = ""


_RATE_RE = re.compile(r"retry[- ]after[=: ]\s*([0-9.]+)", re.IGNORECASE)


def classify_stream_error(exc: BaseException) -> StreamErrorInfo:
    """Normalize a streaming failure into a typed decision."""
    msg = str(exc)
    low = msg.lower()
    name = type(exc).__name__.lower()

    if "timeout" in low or "timed out" in low or "timeout" in name:
        return StreamErrorInfo("timeout", True, message=msg)
    if "429" in low or "rate limit" in low or "rate_limit" in low:
        m = _RATE_RE.search(msg)
        wait = float(m.group(1)) if m else None
        return StreamErrorInfo("rate_limit", True, retry_after_s=wait, message=msg)
    if any(n in low for n in ("401", "403", "invalid api key", "authentication")):
        return StreamErrorInfo("auth", False, message=msg)
    if any(n in low for n in (
        "context length", "context_length", "maximum context",
        "too many tokens", "prompt is too long",
    )):
        return StreamErrorInfo("context_length", False, message=msg)
    if any(n in low for n in (
        "502", "503", "504", "overloaded", "server error",
        "temporarily unavailable", "internal server error",
    )):
        return StreamErrorInfo("server", True, message=msg)
    if "connection" in low or "connection" in name:
        return StreamErrorInfo("network", True, message=msg)
    return StreamErrorInfo("other", False, message=msg)


def stream_with_retry(
    chunk_iter_factory: Callable[[], object],
    *,
    max_retries: int = 2,
    base_delay_s: float = 1.0,
    label: str = "llm-stream",
):
    """Iterate a provider stream with replay-safe retry.

    Retries ONLY when ZERO chunks were received (connection-level
    failure — nothing reached the engine/UI, so restarting is
    invisible). A failure after the first chunk propagates: the caller
    surfaces it as a resumable error instead of silently replaying
    half-delivered content.
    """
    last: Exception | None = None
    for attempt in range(max_retries + 1):
        received_any = False
        try:
            for chunk in chunk_iter_factory():
                received_any = True
                yield chunk
            return
        except Exception as e:
            info = classify_stream_error(e)
            if received_any or not info.retryable or attempt >= max_retries:
                raise
            delay = info.retry_after_s or (base_delay_s * (attempt + 1))
            delay *= 0.5 + random.random() * 0.5
            logger.warning(
                "%s attempt %s/%s failed (%s: %s); retry in %.1fs",
                label, attempt + 1, max_retries + 1, info.category, e, delay,
            )
            time.sleep(delay)
            last = e
    assert last is not None
    raise last


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
