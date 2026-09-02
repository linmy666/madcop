"""
Revertible effects — DeepSeek-Harness / Cordis paper (arXiv:2608.25512 §3.1)
adapted to MadCop's tool pipeline.

Core contract (Definition 8, simplified for an imperative host):

    effect application → (new_state, inverse)

Every *mutating tool call* returns, alongside its observable result, an
inverse callable that restores the pre-call state at the state where the
effect was applied (paper: the witness `g(δ) = γ` — the inverse only has
to revert the effect at THAT state, not at every state). The runtime
(here: EffectStore) holds inverses keyed by an externally meaningful key
(the tool_use_id) so a caller can:

    - undo one effect            → revert(key)
    - undo a sequence            → revert(k1, k2, ...) (reverse order)
    - declare non-revertibility  → mark(key) (e.g. bash side effects)

This turns the MEA loop's "soft revert" from an accounting fiction into
a real mechanism: an audit-blocked step applies the inverses of every
tool call it made and the workspace is restored before the retry.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class RecordedEffect:
    """One tracked effect: its key, a human label, and the inverse."""

    key: str
    label: str
    reversible: bool
    inverse: Callable[[], None] | None
    # Staged pre-image temp file backing the inverse (unlink on cleanup —
    # otherwise every write_file leaks a snapshot copy on disk).
    temp_path: str | None = None
    created_at: float = field(default_factory=time.time)


class EffectStore:
    """Thread-safe registry of inverses, keyed by tool_use_id.

    A key may accumulate several inverses (one per tool call that shared
    the key, e.g. an MEA step). Reverting a key applies its inverses in
    REVERSE registration order — the twisted composite of Definition 9.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._effects: dict[str, list[RecordedEffect]] = {}

    def register(
        self, key: str, label: str, inverse: Callable[[], None] | None,
        reversible: bool = True, temp_path: str | None = None,
    ) -> None:
        with self._lock:
            self._effects.setdefault(key, []).append(
                RecordedEffect(key=key, label=label, reversible=reversible,
                               inverse=inverse, temp_path=temp_path)
            )

    def mark_irreversible(self, key: str, label: str) -> None:
        """Record that `key` performed effects that cannot be undone
        (e.g. bash). Reverting such a key reports partial success."""
        self.register(key, label, None, reversible=False)

    def revert(self, key: str) -> dict:
        """Apply every inverse recorded under `key`, newest first.

        Returns a report dict; never raises (an inverse failure is
        logged and included in the report — a partially failed revert
        must still attempt the remaining inverses)."""
        with self._lock:
            effects = self._effects.pop(key, [])
        applied = failed = skipped = 0
        for eff in reversed(effects):
            if not eff.reversible or eff.inverse is None:
                skipped += 1
                continue
            try:
                eff.inverse()
                applied += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                logger.warning("[effects] inverse failed for %s (%s): %s",
                               key, eff.label, e)
        report = {"key": key, "applied": applied, "failed": failed,
                  "skipped": skipped, "total": len(effects)}
        logger.info("[effects] revert %s", report)
        return report

    def revert_prefix(self, prefix: str) -> dict:
        """Revert EVERY key under `prefix` (each key's own inverses in
        reverse order, keys themselves in registration order). Used by
        SessionRealm.revert_all — a derived realm's whole effect
        namespace unwinds in one call. Returns an aggregate report."""
        with self._lock:
            keys = [k for k in self._effects if k.startswith(prefix)]
        report = {"prefix": prefix, "keys": 0, "applied": 0,
                  "failed": 0, "skipped": 0}
        for k in keys:
            rep = self.revert(k)
            report["keys"] += 1
            report["applied"] += rep["applied"]
            report["failed"] += rep["failed"]
            report["skipped"] += rep["skipped"]
        return report

    def clear_prefix(self, prefix: str) -> int:
        """Drop every key starting with `prefix` and unlink the staged
        snapshot temps backing them. Called when a turn finishes and its
        output was verified/accepted — the inverses are no longer needed,
        and keeping them (plus each 25KB+ staged pre-image) leaks memory
        and disk on a long-running server. Returns the number of keys."""
        with self._lock:
            keys = [k for k in self._effects if k.startswith(prefix)]
            temps: list[str] = []
            for k in keys:
                for eff in self._effects.pop(k):
                    if eff.temp_path:
                        temps.append(eff.temp_path)
        for t in temps:
            try:
                os.unlink(t)
            except OSError:
                pass
        return len(keys)

    def peek(self, key: str) -> list[dict]:
        with self._lock:
            effects = list(self._effects.get(key, []))
        return [{"label": e.label, "reversible": e.reversible} for e in effects]

    def clear(self, key: str) -> None:
        with self._lock:
            self._effects.pop(key, None)


# Process-wide store. Tools live in one backend process; session
# scoping rides on the key namespace ("sess:<id>:<tool_use_id>").
STORE = EffectStore()


# ─── File snapshot inverses ──────────────────────────────────────────────────
#
# The inverse is captured at the APPLICATION POINT (before the write),
# per Definition 8's input-side change: it reverts the one state it was
# taken at. Captured bytes are staged in a temp file so the inverse is
# O(bytes) at write time and immune to later mutation of the target.


def make_file_restore_inverse(path_str: str) -> Callable[[], None] | None:
    """Snapshot `path_str` (or its absence) and return an inverse that
    restores exactly that state. None if the path cannot be snapshotted
    (unreadable parent etc.) — caller then registers non-reversible."""
    p = Path(path_str).expanduser()
    try:
        if p.exists():
            fd, tmp = tempfile.mkstemp(prefix="madcop-inv-")
            with os.fdopen(fd, "wb") as f:
                with open(p, "rb") as src:
                    shutil.copyfileobj(src, f)
            st = p.stat()

            def _restore_existing() -> None:
                shutil.copyfile(tmp, p)
                try:
                    os.chmod(p, st.st_mode)
                    os.utime(p, (st.st_atime, st.st_mtime))
                except OSError:
                    pass
                finally:
                    os.unlink(tmp)

            _restore_existing.snapshot_tmp = tmp  # cleared via clear_prefix
            return _restore_existing
        # File does not exist yet → inverse deletes it.
        def _restore_absent() -> None:
            if p.exists():
                p.unlink()

        return _restore_absent
    except Exception as e:  # noqa: BLE001
        logger.warning("[effects] snapshot failed for %s: %s", path_str, e)
        return None


MUTATING_FILE_TOOLS = {
    "write_file", "edit_file", "write_xlsx", "write_pptx",
}


def capture_file_inverse(
    tool_name: str, args: dict, effect_key: str, label: str = "",
) -> dict:
    """Snapshot pre-state for a mutating file tool and register the
    inverse under `effect_key`. Returns the EffectStore report entry.

    bash / run_command are recorded as IRREVERSIBLE: their side effects
    (network, subprocesses) have no faithful inverse — the paper allows
    unwitnessed effects; the store simply reports them as skipped on
    revert so callers can surface partial success honestly.
    """
    from madcop.tools.safety import danger_level

    if tool_name == "bash" or tool_name == "run_command":
        STORE.mark_irreversible(effect_key, label or tool_name)
        return {"key": effect_key, "reversible": False}
    if tool_name not in MUTATING_FILE_TOOLS:
        return {"key": effect_key, "reversible": False, "noop": True}
    raw_path = str(args.get("path") or args.get("file_path") or "")
    if not raw_path:
        STORE.mark_irreversible(effect_key, label or tool_name)
        return {"key": effect_key, "reversible": False, "reason": "no path"}
    p = Path(raw_path).expanduser()
    inverse = make_file_restore_inverse(str(p))
    if inverse is None:
        STORE.mark_irreversible(effect_key, label or tool_name)
        return {"key": effect_key, "reversible": False, "reason": "snapshot failed"}
    STORE.register(effect_key, label or f"{tool_name}:{p.name}", inverse,
                   temp_path=getattr(inverse, "snapshot_tmp", None))
    return {"key": effect_key, "reversible": True}


__all__ = [
    "EffectStore", "STORE", "RecordedEffect",
    "make_file_restore_inverse", "capture_file_inverse",
    "MUTATING_FILE_TOOLS",
]
