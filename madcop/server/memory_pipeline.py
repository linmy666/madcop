"""Async memory extraction with debounce (Gap 7).

DeerFlow's pattern: when a chat completes, the response is streamed
back to the user immediately and memory extraction runs in a
background thread. We add a debounce so rapid-fire duplicate messages
(e.g. a user clicking send twice) don't re-extract the same fact.

Public surface:
    from madcop.server.memory_pipeline import schedule_extraction
    schedule_extraction(messages)  # fire-and-forget
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Iterable

from ..llm import Message


_DEBOUNCE_SECONDS = 30.0
_MAX_BACKLOG = 32

# Module-level state
_lock = threading.Lock()
_last_seen: dict[str, float] = {}  # content_hash -> timestamp
_extracted_hashes: set[str] = set()
_extraction_count = 0  # monotonic counter for tests
_worker_started = False


def _content_hash(messages: Iterable[Message]) -> str:
    """Hash the joined user-message contents. Used for dedup."""
    parts: list[str] = []
    for m in messages:
        if m.role == "user" and m.content:
            parts.append(m.content)
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _do_extract(messages: list[Message]) -> int:
    """Run the actual extraction. Returns number of facts stored."""
    # Late import: app.py has the real function and would create a
    # circular import at module load.
    from .app import _store_extracted_facts
    return _store_extracted_facts(messages)


def _worker(messages: list[Message], hash_key: str) -> None:
    """Background worker: waits, dedup-checks, then extracts."""
    global _extraction_count
    time.sleep(debounce_seconds() / 2)
    with _lock:
        if hash_key in _extracted_hashes:
            return  # already extracted by a prior worker
    try:
        n = _do_extract(messages)
        with _lock:
            _extraction_count += 1
            if n > 0:
                _extracted_hashes.add(hash_key)
    except Exception:
        pass


def schedule_extraction(messages: list[Message]) -> bool:
    """Fire-and-forget: schedule a debounced extraction in a background thread.

    Returns True if a job was scheduled, False if it was deduped
    (already-pending or already-extracted).
    """
    global _worker_started
    if not messages:
        return False
    hash_key = _content_hash(messages)
    with _lock:
        if hash_key in _extracted_hashes:
            return False  # already done
        last_ts = _last_seen.get(hash_key, 0)
        # If a similar message was seen very recently, skip
        if time.time() - last_ts < 1.0:
            return False
        # Reserve the slot now (so concurrent calls dedup against it)
        if len(_last_seen) > _MAX_BACKLOG:
            # Drop oldest entries to keep the map bounded
            sorted_keys = sorted(_last_seen.items(), key=lambda kv: kv[1])
            for k, _ in sorted_keys[:_MAX_BACKLOG // 4]:
                _last_seen.pop(k, None)
        _last_seen[hash_key] = time.time()
    t = threading.Thread(
        target=_worker, args=(list(messages), hash_key), daemon=True
    )
    t.start()
    return True


# Test helpers ---------------------------------------------------------- #

def reset_for_tests() -> None:
    """Clear all dedup state. Used by tests to start clean."""
    global _extraction_count
    with _lock:
        _last_seen.clear()
        _extracted_hashes.clear()
        _extraction_count = 0


def extraction_count() -> int:
    """Total number of extractions that have actually run."""
    with _lock:
        return _extraction_count


def debounce_seconds() -> float:
    return _DEBOUNCE_SECONDS
