"""SessionRealm — the unified context paradigm (paper §3.3, practical form).

Before this module, a running turn touched FOUR separate per-session
stores, each derived/disposed by its own ad-hoc code path:

  - message history   (RunContext.messages + SessionLog)
  - revertible effects (EffectStore, namespaced "session:tool_use_id")
  - reactive coeffects (CoeffectStore per session id)
  - the steer queue    (steer_queue, keyed by session id)

The paper's context paradigm says these are ONE object: a context is
whatever its effects, coeffects and observations jointly determine
(Γ∞ = μΓ.Γ×(Γ→Γ)×Σ). Python can't express that type, but the practical
half is achievable: ONE facade owning all four, whose ``derive()`` forks
them COHERENTLY (a child realm gets its own effect namespace, a derived
coeffect table, and keeps draining the conversation's steer queue), and
whose ``dispose()`` tears them down in one call.

MEA uses ``realm.derive()`` for executor steps: a blocked audit disposes
the child realm (its effect namespace reverts in one sweep) without ever
touching the parent's state.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class SessionRealm:
    """Unified per-session context: effects + coeffects + steers + log."""

    __slots__ = ("session_id", "effects_prefix", "coeffects", "log",
                 "steer_session")

    def __init__(self, session_id: str, effects_prefix: str,
                 coeffects: Any, log: Any = None,
                 steer_session: str = ""):
        self.session_id = session_id or ""
        self.effects_prefix = effects_prefix or session_id or "sess"
        self.coeffects = coeffects
        self.log = log
        # Child realms keep draining the ROOT conversation's steer queue —
        # a steer steers the whole thread (Codex Op::Steer semantics),
        # not whichever subagent happens to sample next.
        self.steer_session = steer_session or self.session_id

    # ── construction ────────────────────────────────────────────────
    @classmethod
    def root(cls, session_id: str, log: Any = None) -> "SessionRealm":
        from .coeffects import coeffects_for
        sid = session_id or ""
        return cls(
            session_id=sid,
            effects_prefix=sid or "sess",
            coeffects=coeffects_for(sid),
            log=log,
            steer_session=sid,
        )

    # ── derivation (paper §3.2.3 + §3.3) ───────────────────────────
    def derive(self, child_id: str | None = None,
               coeffect_overrides: dict | None = None) -> "SessionRealm":
        """Fork every store coherently.

        - effects: child gets its OWN namespace, so reverting/disposing
          the child never reaches the parent's recorded inverses;
        - coeffects: child sees the parent's bindings + overrides
          (realization is 'derived' — discard the child to recover);
        - steers: child keeps draining the ROOT session's queue;
        - log: children write nothing to the parent's log directly.
        """
        child_id = child_id or f"{self.session_id}/{uuid.uuid4().hex[:6]}"
        try:
            child_coe = self.coeffects.derive(coeffect_overrides or {})
        except Exception:
            child_coe = self.coeffects
        return SessionRealm(
            session_id=child_id,
            effects_prefix=child_id.replace("/", ":"),
            coeffects=child_coe,
            log=None,
            steer_session=self.steer_session,
        )

    # ── effects namespace ───────────────────────────────────────────
    def effect_key(self, use_id: str) -> str:
        """The EffectStore key for one tool call in this realm."""
        return f"{self.effects_prefix}:{use_id}"

    def revert_all(self) -> dict:
        """Revert every effect recorded under this realm's namespace."""
        from .effects import STORE
        return STORE.revert_prefix(f"{self.effects_prefix}:")

    def dispose(self) -> dict:
        """Turn-scoped teardown: drop this namespace's effects (and the
        staged pre-images backing them). Coeffects are NOT dropped —
        session approvals must survive across turns; they die with
        ``drop_session`` when the conversation is deleted."""
        from .effects import STORE
        cleared = STORE.clear_prefix(f"{self.effects_prefix}:")
        return {"cleared_keys": cleared}

    # ── steers ──────────────────────────────────────────────────────
    def drain_steers(self) -> list[str]:
        try:
            from madcop.server.steer_queue import drain_steers
            return drain_steers(self.steer_session)
        except Exception as e:  # noqa: BLE001
            logger.debug("[realm] steer drain failed: %s", e)
            return []


def effect_key_for(ctx: Any, use_id: str) -> str:
    """Effect key for a tool call made under `ctx` — realm-aware.

    Engines without a realm (legacy paths, tests) keep the historical
    "session:use_id" shape so existing revert code keeps working."""
    realm = getattr(ctx, "realm", None)
    if realm is not None:
        return realm.effect_key(use_id)
    return f"{getattr(ctx, 'session_id', '') or 'sess'}:{use_id}"


__all__ = ["SessionRealm", "effect_key_for"]
