"""
Reactive coeffects — DeepSeek-Harness paper (arXiv:2608.25512 §3.2)
adapted to MadCop's tool registry.

A tool declares the context KEYS it requires (its coeffect
specification, Definition 21):

    web_search.requires = {"net"}
    bash.requires       = {"shell"}
    write_file.requires = {"fs.write"}          (workspace binding)
    <mcp tool>.requires = {"mcp:<server>"}

A binding provision (Definition 20 set) writes a key into the shared
table and returns a dispose function — provision/withdrawal are two
sides of one revertible effect. Every transition is classified against
each tool's specification (Definition 22):

    activating   — was unsatisfied, now satisfied  → tool becomes callable
    deactivating — was satisfied, now unsatisfied  → tool is gated
    neutral      — satisfaction unchanged

Gating is CENTRAL: a tool whose specification is unsatisfied never
reaches the executor (the engine sees "[coeffect] ..."), replacing the
per-call allowlist/HITL ad-hoc checks scattered through engines.

Built-in bindings
-----------------
    approval.dir:<abs>   session-scoped HITL approval for a directory
                         (provided by the chat route on scope="session";
                         withdrawable to re-gate future calls)
    mcp:<server>         provided while MCP server <server> is connected
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class CoeffectStore:
    """Shared dependency table + reactive notification.

    `notify` callbacks fire on every provision/withdrawal with the
    changed key and the transition class — the tool registry uses this
    to flip tool availability (Algorithm 3, reactive notification)."""

    bindings: dict[str, object] = field(default_factory=dict)
    listeners: list[Callable[[str, str], None]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ── effect: provide (carries its inverse, paper §3.1) ──────────
    def provide(self, key: str, value: object = True) -> Callable[[], None]:
        """Bind `key` → `value`. Returns the dispose (inverse) function:
        calling it withdraws the binding and notifies. Provision is an
        effect on the shared table, so it is revertible by construction."""
        with self._lock:
            existed = key in self.bindings
            self.bindings[key] = value
        if not existed:
            self._notify(key, "activating")
        else:
            self._notify(key, "neutral")

        def _dispose() -> None:
            self.withdraw(key)

        return _dispose

    def withdraw(self, key: str) -> bool:
        """Remove a binding (the inverse of provide). Returns True if a
        binding was removed. Deactivation is notified one step BEFORE
        dependents re-read the table (paper: withdrawal visibility)."""
        with self._lock:
            existed = key in self.bindings
            self.bindings.pop(key, None)
        if existed:
            self._notify(key, "deactivating")
        return existed

    def get(self, key: str, default: object = None) -> object:
        with self._lock:
            return self.bindings.get(key, default)

    def has(self, *keys: str) -> bool:
        with self._lock:
            return all(k in self.bindings for k in keys)

    def on_change(self, cb: Callable[[str, str], None]) -> None:
        with self._lock:
            self.listeners.append(cb)

    def _notify(self, key: str, transition: str) -> None:
        for cb in list(self.listeners):
            try:
                cb(key, transition)
            except Exception as e:  # noqa: BLE001
                logger.warning("[coeffects] listener failed on %s: %s", key, e)

    # ── isolation (Definition 24-25): derived child realms ─────────
    def derive(self, overrides: dict[str, object]) -> "CoeffectStore":
        """A derived store: same table, overridden keys. Realization is
        'derived' (paper §3.2.3) — the parent is untouched, recovery is
        discarding the child, so NO inverse is needed. Used for MEA
        executor contexts (isolated approvals/memory per subagent)."""
        child = CoeffectStore()
        with self._lock:
            child.bindings.update(self.bindings)
        child.bindings.update(overrides)
        return child


# Session-scoped store. Approvals and MCP bindings are per-conversation;
# the chat route provides/withdraws keys for the active session id.
_STORES: dict[str, CoeffectStore] = {}
_GLOBAL = CoeffectStore()
_REG_LOCK = threading.Lock()


def coeffects_for(session_id: str) -> CoeffectStore:
    """Return (creating if needed) the coeffect store for a session.
    Falls back to the global store for empty session ids (CLI/tests)."""
    if not session_id:
        return _GLOBAL
    with _REG_LOCK:
        s = _STORES.get(session_id)
        if s is None:
            s = CoeffectStore()
            _STORES[session_id] = s
        return s


def drop_session(session_id: str) -> None:
    """Withdraw every binding when a session is deleted (inverse of the
    session's accumulated provisions)."""
    with _REG_LOCK:
        _STORES.pop(session_id, None)


__all__ = [
    "CoeffectStore", "coeffects_for", "drop_session",
]
