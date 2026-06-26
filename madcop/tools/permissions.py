"""v1.5.0 — Action-level permission system for computer use.

Every computer-use action (screenshot, click, type, etc.) has a
*danger level*. The permission manager gates execution based on
the level + the user's stored preferences.

Levels (from least to most dangerous):
  READ        — screenshot, get clipboard, get window list
  NAVIGATE    — click, scroll, arrow keys, tab
  INPUT       — type text, paste, function keys
  DESTRUCTIVE — close window, cmd+Q, delete, empty trash

Policies (how the user authorises an action):
  DENY        — refuse (don't execute)
  ONCE        — allow this one time (ask again next time)
  SESSION     — allow for the rest of this process
  ALWAYS      — allow forever (persisted to ~/.madcop/permissions.json)

Default behaviour when no policy is set:
  READ        → ALLOW (no prompt)
  NAVIGATE    → ASK  (prompt user)
  INPUT       → ASK  (prompt user)
  DESTRUCTIVE → DENY (must be explicitly granted)

Design (Qian control theory):
  - 可控性: every action is interceptable; DENY is always available
  - 稳定性: persisting ALWAYS means the user doesn't re-approve every run
  - 早纠偏: READ is free; catching visual state early prevents wrong actions
  - 层次化: levels are monotonic — if you approve NAVIGATE,
    READ is implied
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Action levels (monotonic ordering)
# --------------------------------------------------------------------------- #

class ActionLevel(IntEnum):
    """Danger level of a computer-use action.

    Higher = more dangerous. Ordering is monotonic: approving level N
    implies approving all levels < N.
    """
    READ = 0
    NAVIGATE = 1
    INPUT = 2
    DESTRUCTIVE = 3

    @classmethod
    def from_str(cls, s: str) -> "ActionLevel":
        s = s.upper().strip()
        try:
            return cls[s]
        except KeyError:
            raise ValueError(f"unknown action level: {s!r}")


# Map action names → levels. This is the single source of truth.
ACTION_LEVELS: dict[str, ActionLevel] = {
    # READ
    "screenshot": ActionLevel.READ,
    "get_clipboard": ActionLevel.READ,
    "get_window_list": ActionLevel.READ,
    "get_screen_size": ActionLevel.READ,
    # NAVIGATE
    "click": ActionLevel.NAVIGATE,
    "right_click": ActionLevel.NAVIGATE,
    "double_click": ActionLevel.NAVIGATE,
    "scroll": ActionLevel.NAVIGATE,
    "move": ActionLevel.NAVIGATE,
    "key_arrow": ActionLevel.NAVIGATE,       # arrows, tab, escape
    # INPUT
    "type": ActionLevel.INPUT,
    "paste": ActionLevel.INPUT,
    "hotkey": ActionLevel.INPUT,             # cmd+c, cmd+v, etc.
    "key_enter": ActionLevel.INPUT,
    "key_function": ActionLevel.INPUT,       # F1-F12
    # DESTRUCTIVE
    "close_window": ActionLevel.DESTRUCTIVE,
    "kill_app": ActionLevel.DESTRUCTIVE,
    "key_cmd_q": ActionLevel.DESTRUCTIVE,
    "delete": ActionLevel.DESTRUCTIVE,
}


def level_for_action(action: str) -> ActionLevel:
    """Look up the danger level for an action name."""
    return ACTION_LEVELS.get(action, ActionLevel.DESTRUCTIVE)


def level_for_computer_action(action: str, **kwargs: Any) -> ActionLevel:
    """Look up the danger level for a ComputerUseTool action.

    The tool exposes 5 generic actions (screenshot/click/type/key/scroll).
    This function maps them to ActionLevel, using kwargs for finer
    discrimination (e.g. key='cmd+q' → DESTRUCTIVE, key='enter' → INPUT).
    """
    # Direct mapping for non-key actions
    direct = {
        "screenshot": ActionLevel.READ,
        "click": ActionLevel.NAVIGATE,
        "scroll": ActionLevel.NAVIGATE,
        "type": ActionLevel.INPUT,
    }
    if action in direct:
        return direct[action]

    # 'key' action: discriminate by the key value
    if action == "key":
        key_val = (kwargs.get("key") or "").lower().strip()
        # Destructive keys
        destructive_keys = {"cmd+q", "cmd+w", "alt+f4", "ctrl+alt+del"}
        if key_val in destructive_keys:
            return ActionLevel.DESTRUCTIVE
        # Navigation keys (arrows, tab, escape, space, home/end/pgup/pgdn)
        nav_keys = {"up", "down", "left", "right", "tab", "escape",
                    "space", "home", "end", "pageup", "pagedown",
                    "pgup", "pgdn"}
        if key_val in nav_keys:
            return ActionLevel.NAVIGATE
        # Everything else (enter, f-keys, hotkeys) is INPUT
        return ActionLevel.INPUT

    # 'kill_app' and other explicitly destructive actions
    return ACTION_LEVELS.get(action, ActionLevel.DESTRUCTIVE)


# --------------------------------------------------------------------------- #
# Permission policies
# --------------------------------------------------------------------------- #

class Permission(str):
    """A permission decision."""
    DENY = "deny"
    ONCE = "once"
    SESSION = "session"
    ALWAYS = "always"

    ALL = (DENY, ONCE, SESSION, ALWAYS)
    ALLOWED = (ONCE, SESSION, ALWAYS)  # values that mean "yes"

    @classmethod
    def is_allowed(cls, value: str) -> bool:
        return value in cls.ALLOWED


# Default policy per level (when nothing is stored)
DEFAULT_POLICY: dict[ActionLevel, str] = {
    ActionLevel.READ: Permission.ALWAYS,       # screenshots are free
    ActionLevel.NAVIGATE: Permission.ONCE,     # ask each time by default
    ActionLevel.INPUT: Permission.ONCE,        # ask each time by default
    ActionLevel.DESTRUCTIVE: Permission.DENY,  # must explicitly grant
}


# --------------------------------------------------------------------------- #
# Permission manager
# --------------------------------------------------------------------------- #

@dataclass
class PermissionEntry:
    """A stored permission rule."""
    action: str              # e.g. "click" or "*" (wildcard)
    level: str               # ActionLevel name or "*"
    permission: str          # deny | once | session | always

    def matches(self, action: str, level: ActionLevel) -> bool:
        if self.action != "*" and self.action != action:
            return False
        if self.level != "*" and self.level != level.name:
            return False
        return True


class PermissionManager:
    """Manages computer-use permissions with three tiers:

    1. Session-level (in-memory dict, cleared on process exit)
    2. Always (persisted to JSON file, survives restarts)
    3. Defaults (hardcoded per ActionLevel)

    Lookup order: session → always → default.

    When an action is checked:
    - If a matching rule grants ALWAYS or SESSION → allow
    - If a matching rule is ONCE → allow (and consume → don't persist)
    - If DENY or no match → consult default_policy[level]
    """

    def __init__(
        self,
        store_path: str | Path | None = None,
        *,
        prompt_fn: Callable[[str, str], str] | None = None,
        defaults: dict[ActionLevel, str] | None = None,
    ) -> None:
        self._store_path = Path(store_path) if store_path else None
        self._session: dict[str, str] = {}  # key → permission
        self._always: list[PermissionEntry] = []
        self._prompt_fn = prompt_fn or self._default_prompt
        self._defaults = defaults or dict(DEFAULT_POLICY)
        self._load_always()

    # ---- core check ----

    def check(self, action: str, context: str = "") -> str:
        """Check if an action is allowed.

        Returns one of: deny, once, session, always.
        Does NOT auto-prompt — call ``request()`` for that.
        """
        level = level_for_action(action)

        # 1. Session-level grant (highest priority)
        session_perm = self._session.get(self._key(action, level))
        if session_perm:
            return session_perm

        # 2. Always-level grant (persisted)
        for entry in self._always:
            if entry.matches(action, level):
                if Permission.is_allowed(entry.permission):
                    return entry.permission

        # 3. Default
        return self._defaults.get(level, Permission.DENY)

    def is_allowed(self, action: str, context: str = "") -> bool:
        """Convenience: True if check() returns an allowed value."""
        return Permission.is_allowed(self.check(action, context))

    def request(self, action: str, context: str = "") -> str:
        """Check + prompt if needed.

        If the action is already allowed (session/always), return immediately.
        If not, call ``prompt_fn`` to ask the user.
        Store the result.
        """
        level = level_for_action(action)
        current = self.check(action)

        # SESSION and ALWAYS are persistent grants — no prompt needed.
        # ONCE is a transient "default" that means "ask me" — prompt.
        # DENY means denied — prompt (user might override).
        if current in (Permission.SESSION, Permission.ALWAYS):
            return current

        # Need to prompt (ONCE default, DENY default, or no match)
        decision = self._prompt_fn(action, context)
        decision = decision.lower().strip()

        if decision not in Permission.ALL:
            decision = Permission.DENY

        self._store_decision(action, level, decision)
        return decision

    # ---- explicit grant / revoke ----

    def grant(self, action: str, permission: str = Permission.SESSION) -> None:
        """Explicitly grant permission for an action."""
        level = level_for_action(action)
        self._store_decision(action, level, permission)

    def revoke(self, action: str) -> None:
        """Revoke all permissions for an action."""
        level = level_for_action(action)
        key = self._key(action, level)
        self._session.pop(key, None)
        self._always = [
            e for e in self._always
            if not e.matches(action, level)
        ]
        self._save_always()

    def reset(self) -> None:
        """Clear all session + always permissions."""
        self._session.clear()
        self._always.clear()
        self._save_always()

    # ---- internals ----

    @staticmethod
    def _key(action: str, level: ActionLevel) -> str:
        return f"{level.name}:{action}"

    def _store_decision(
        self, action: str, level: ActionLevel, permission: str,
    ) -> None:
        if permission == Permission.ONCE:
            # Don't persist — just return the decision
            return
        if permission == Permission.SESSION:
            key = self._key(action, level)
            self._session[key] = permission
        elif permission == Permission.ALWAYS:
            entry = PermissionEntry(
                action=action, level=level.name, permission=permission,
            )
            # Remove conflicting entries
            self._always = [
                e for e in self._always
                if not (e.matches(action, level))
            ]
            self._always.append(entry)
            self._save_always()

    def _load_always(self) -> None:
        if self._store_path is None or not self._store_path.exists():
            return
        try:
            data = json.loads(self._store_path.read_text())
            for item in data.get("always", []):
                self._always.append(PermissionEntry(
                    action=item["action"],
                    level=item["level"],
                    permission=item["permission"],
                ))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to load permissions from %s: %s",
                           self._store_path, e)

    def _save_always(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "always": [
                {"action": e.action, "level": e.level, "permission": e.permission}
                for e in self._always
            ]
        }
        self._store_path.write_text(json.dumps(data, indent=2))

    @staticmethod
    def _default_prompt(action: str, context: str) -> str:
        """Default prompt function — asks via stdin/stdout."""
        level = level_for_action(action)
        msg = f"\n  [PERMISSION] {level.name} action: {action}"
        if context:
            msg += f"\n  context: {context}"
        msg += f"\n  Allow? (once/session/always/no): "
        try:
            answer = input(msg).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return Permission.DENY
        if answer in ("o", "once", "y", "yes", ""):
            return Permission.ONCE
        if answer in ("s", "session"):
            return Permission.SESSION
        if answer in ("a", "always"):
            return Permission.ALWAYS
        return Permission.DENY

    # ---- introspection ----

    def summary(self) -> dict[str, Any]:
        """Return a summary of current permissions (for debugging/display)."""
        return {
            "session_rules": dict(self._session),
            "always_rules": [
                {"action": e.action, "level": e.level, "permission": e.permission}
                for e in self._always
            ],
            "defaults": {
                level.name: perm for level, perm in self._defaults.items()
            },
        }


__all__ = [
    "ActionLevel",
    "ACTION_LEVELS",
    "level_for_action",
    "level_for_computer_action",
    "Permission",
    "DEFAULT_POLICY",
    "PermissionEntry",
    "PermissionManager",
]
