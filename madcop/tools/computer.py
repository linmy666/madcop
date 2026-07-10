"""v1.5.0 — ComputerUseTool: let the agent see and control the screen.

This module implements a single `ComputerUseTool` that exposes 5
actions the agent can call:

  screenshot   — capture the screen, return as file path
  click        — move mouse to (x, y) and click
  type         — type a string of text
  key          — press a key (enter, tab, escape, etc.)
  scroll       — scroll up/down by N clicks

Every action passes through the PermissionManager, which gates
based on danger level (READ / NAVIGATE / INPUT / DESTRUCTIVE).

Safety rails (Qian control theory — 可控性):
  - Screen bounds checking: clicks outside [0, width) × [0, height) are rejected
  - Allowed-apps whitelist: optionally restrict to specific apps
  - Dry-run mode: screenshot-only, no input injection
  - Action log: every action is recorded (for audit / debugging)

Dependencies:
  - pyautogui (pip install pyautogui) — mouse/keyboard control
  - screencapture (macOS built-in) — screenshots
  - On non-macOS: pyautogui handles screenshots too

Why pyautogui (not CGEventPost directly)?
  - Cross-platform: works on macOS + Linux + Windows
  - Well-tested, handles edge cases (retina scaling, multi-monitor)
  - Fail-safe: throws if mouse hits corner (pyautogui.FailSafeException)
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .permissions import ActionLevel, PermissionManager, Permission, level_for_action, level_for_computer_action
from .registry import Tool, ToolResult

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Action log entry
# --------------------------------------------------------------------------- #

@dataclass
class ActionLogEntry:
    """A record of one executed (or denied) computer-use action."""
    timestamp: str
    action: str
    level: str               # ActionLevel name
    permission: str          # deny/once/session/always
    args: dict[str, Any]
    result: str              # "ok" | "denied" | "error: ..."
    screenshot_before: str | None = None  # path to pre-action screenshot
    screenshot_after: str | None = None   # path to post-action screenshot


# --------------------------------------------------------------------------- #
# ComputerUseTool
# --------------------------------------------------------------------------- #

class ComputerUseTool(Tool):
    """A tool that lets the agent see and control the computer.

    The agent calls this tool with ``action="screenshot"`` etc.
    Each call goes through the permission manager before executing.

    Args:
        perms: A PermissionManager instance. If None, creates one
            with defaults (READ=always, others=once).
        dry_run: If True, only screenshots work; all input actions
            are logged but not executed. Useful for demos.
        allowed_apps: Optional set of app names (e.g. {"Calculator"}).
            If set, the tool checks the frontmost app before acting.
        screenshot_dir: Where to save screenshots. Default: temp dir.
    """

    name = "computer_use"
    description = (
        "Control the computer screen. Actions: screenshot, click, "
        "type, key, scroll. Each action requires permission."
    )

    def __init__(
        self,
        perms: PermissionManager | None = None,
        *,
        dry_run: bool = False,
        allowed_apps: set[str] | None = None,
        screenshot_dir: str | Path | None = None,
    ) -> None:
        self.perms = perms or PermissionManager()
        self.dry_run = dry_run
        self.allowed_apps = allowed_apps
        self.screenshot_dir = Path(screenshot_dir or tempfile.gettempdir())
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._action_log: list[ActionLogEntry] = []
        self._screen_size: tuple[int, int] | None = None

    # ---- Tool interface ----

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["screenshot", "click", "type", "key", "scroll",
                             "find_element", "list_apps", "focus_app", "dump_tree",
                             "launch_app", "list_windows", "check_permission"],
                    "description": "The computer-use action to perform.",
                },
                "x": {
                    "type": "integer",
                    "description": "X coordinate for click (0 = left edge).",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate for click (0 = top edge).",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for 'type' action).",
                },
                "key": {
                    "type": "string",
                    "description": (
                        "Key to press (for 'key' action). "
                        "Examples: enter, tab, escape, space, "
                        "up, down, left, right, "
                        "f1-f12, cmd+c, cmd+v, cmd+q."
                    ),
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll direction (for 'scroll' action).",
                },
                "clicks": {
                    "type": "integer",
                    "description": "Number of scroll clicks (default 3).",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button for click (default left).",
                },
                "pid": {
                    "type": "integer",
                    "description": "Process ID of the target app (for find_element/focus_app/dump_tree).",
                },
                "label": {
                    "type": "string",
                    "description": "Label/title substring to search for (for find_element).",
                },
                "role": {
                    "type": "string",
                    "description": "AX role to find (e.g. AXButton, AXTextField). Default: any.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max recursion depth for AX tree search (default 20).",
                },
                "name": {
                    "type": "string",
                    "description": "App name or bundle ID (for launch_app action).",
                },
            },
            "required": ["action"],
        }

    # ---- Main dispatch ----

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action", "")
        if not action:
            return {"error": "missing 'action' parameter"}

        level = level_for_computer_action(action, **{k: v for k, v in kwargs.items() if k != "action"})

        # Check permissions
        permission = self.perms.check(action)
        if not Permission.is_allowed(permission):
            self._log_action(action, level, permission, kwargs, "denied")
            return {
                "action": action,
                "status": "denied",
                "message": f"Permission denied for {level.name} action '{action}'. "
                           f"Use madcop's permission system to grant access.",
            }

        # Check dry-run
        if self.dry_run and level > ActionLevel.READ:
            self._log_action(action, level, permission, kwargs, "ok (dry-run)")
            return {
                "action": action,
                "status": "dry_run",
                "message": f"Action '{action}' not executed (dry-run mode).",
            }

        # Check allowed apps
        if self.allowed_apps is not None and level > ActionLevel.READ:
            frontmost = self._get_frontmost_app()
            if frontmost and frontmost not in self.allowed_apps:
                self._log_action(action, level, permission, kwargs,
                                 f"blocked (app={frontmost})")
                return {
                    "action": action,
                    "status": "blocked",
                    "message": f"Frontmost app '{frontmost}' not in allowed list.",
                }

        # Execute
        try:
            result = self._execute(action, kwargs)
            self._log_action(action, level, permission, kwargs, "ok")
            return result
        except Exception as e:
            self._log_action(action, level, permission, kwargs,
                             f"error: {type(e).__name__}: {e}")
            return {
                "action": action,
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            }

    # ---- Action implementations ----

    def _execute(self, action: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        if action == "screenshot":
            return self._screenshot()
        elif action == "click":
            return self._click(
                kwargs.get("x", 0), kwargs.get("y", 0),
                button=kwargs.get("button", "left"),
            )
        elif action == "type":
            return self._type_text(kwargs.get("text", ""))
        elif action == "key":
            return self._press_key(kwargs.get("key", ""))
        elif action == "scroll":
            return self._scroll(
                kwargs.get("direction", "down"),
                kwargs.get("clicks", 3),
            )
        elif action == "list_apps":
            return self._list_apps()
        elif action == "focus_app":
            return self._focus_app(kwargs.get("pid", 0))
        elif action == "find_element":
            return self._find_element(
                pid=kwargs.get("pid", 0),
                label=kwargs.get("label"),
                role=kwargs.get("role"),
                max_depth=kwargs.get("max_depth", 20),
            )
        elif action == "dump_tree":
            return self._dump_tree(
                pid=kwargs.get("pid", 0),
                max_depth=kwargs.get("max_depth", 5),
            )
        elif action == "launch_app":
            return self._launch_app(kwargs.get("name", ""))
        elif action == "list_windows":
            return self._list_windows()
        elif action == "check_permission":
            return self._check_permission()
        else:
            return {"error": f"unknown action: {action}"}

    def _screenshot(self) -> dict[str, Any]:
        """Capture the screen and save as PNG."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = self.screenshot_dir / f"madcop_screenshot_{ts}.png"

        if shutil.which("screencapture"):
            # macOS: use system screencapture (better retina handling)
            subprocess.run(
                ["screencapture", "-x", str(path)],
                check=True, capture_output=True, timeout=5,
            )
        else:
            # Fallback: pyautogui
            import pyautogui
            img = pyautogui.screenshot()
            img.save(str(path))

        w, h = self._get_screen_size()
        return {
            "action": "screenshot",
            "status": "ok",
            "screenshot_path": str(path),
            "screen_size": {"width": w, "height": h},
            "message": f"Screenshot saved to {path}",
        }

    def _click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        """Click at (x, y)."""
        w, h = self._get_screen_size()
        if not (0 <= x < w and 0 <= y < h):
            return {
                "action": "click",
                "status": "error",
                "error": f"Coordinates ({x}, {y}) out of bounds "
                         f"(screen: {w}x{h})",
            }

        import pyautogui
        pyautogui.click(x, y, button=button)
        return {
            "action": "click",
            "status": "ok",
            "x": x, "y": y,
            "button": button,
            "message": f"Clicked at ({x}, {y}) with {button} button.",
        }

    def _type_text(self, text: str) -> dict[str, Any]:
        """Type a string of text."""
        if not text:
            return {"action": "type", "status": "error", "error": "empty text"}
        import pyautogui
        pyautogui.typewrite(text, interval=0.02)
        return {
            "action": "type",
            "status": "ok",
            "text": text[:100],  # truncate for logging
            "message": f"Typed {len(text)} character(s).",
        }

    def _press_key(self, key: str) -> dict[str, Any]:
        """Press a key or key combination.

        Supports pyautogui key names: enter, tab, escape, space,
        up, down, left, right, f1-f12, and combos like 'ctrl+c',
        'cmd+v', 'alt+tab'.
        """
        if not key:
            return {"action": "key", "status": "error", "error": "empty key"}
        import pyautogui

        # Normalize: pyautogui uses '+' for combos
        if "+" in key:
            parts = [p.strip() for p in key.split("+")]
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(key)

        return {
            "action": "key",
            "status": "ok",
            "key": key,
            "message": f"Pressed: {key}",
        }

    def _scroll(self, direction: str, clicks: int = 3) -> dict[str, Any]:
        """Scroll up or down."""
        import pyautogui
        if direction == "up":
            pyautogui.scroll(clicks)
        else:
            pyautogui.scroll(-clicks)
        return {
            "action": "scroll",
            "status": "ok",
            "direction": direction,
            "clicks": clicks,
            "message": f"Scrolled {direction} {clicks} click(s).",
        }

    # ---- Helpers ----

    def _get_screen_size(self) -> tuple[int, int]:
        if self._screen_size is not None:
            return self._screen_size
        import pyautogui
        size = pyautogui.size()
        self._screen_size = (size.width, size.height)
        return self._screen_size

    def _get_frontmost_app(self) -> str | None:
        """Get the name of the frontmost application (macOS only)."""
        if not shutil.which("osascript"):
            return None
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=3,
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    def _log_action(
        self, action: str, level: ActionLevel, permission: str,
        kwargs: dict[str, Any], result: str,
    ) -> None:
        """Record an action in the action log."""
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        # Sanitize kwargs for logging (don't log full text content)
        safe_kwargs = {}
        for k, v in kwargs.items():
            if k == "text":
                safe_kwargs[k] = str(v)[:50] + "..." if len(str(v)) > 50 else str(v)
            elif k == "action":
                continue
            else:
                safe_kwargs[k] = v

        entry = ActionLogEntry(
            timestamp=ts,
            action=action,
            level=level.name,
            permission=permission,
            args=safe_kwargs,
            result=result,
        )
        self._action_log.append(entry)
        logger.info("ComputerUse: %s [%s] → %s", action, level.name, result)

    # ---- Introspection ----

    @property
    def action_log(self) -> list[ActionLogEntry]:
        return list(self._action_log)

    def clear_log(self) -> None:
        self._action_log.clear()

    # ---- macOS AXAPI actions ---- #

    def _list_apps(self) -> dict[str, Any]:
        """List all running GUI applications visible via AXAPI."""
        try:
            from .mac_ax import list_apps
            apps = list_apps()
            return {
                "action": "list_apps",
                "apps": apps,
                "count": len(apps),
            }
        except ImportError as e:
            return {"error": f"AXAPI not available: {e}"}
        except Exception as e:
            return {"error": f"AXAPI error: {e}"}

    def _focus_app(self, pid: int) -> dict[str, Any]:
        """Bring an app to the foreground by PID."""
        try:
            from .mac_ax import focus_app
            ok = focus_app(pid)
            return {
                "action": "focus_app",
                "pid": pid,
                "success": ok,
            }
        except ImportError as e:
            return {"error": f"AXAPI not available: {e}"}
        except Exception as e:
            return {"error": f"AXAPI error: {e}"}

    def _find_element(
        self,
        pid: int,
        label: str | None = None,
        role: str | None = None,
        max_depth: int = 20,
    ) -> dict[str, Any]:
        """Search the AX tree for matching UI elements."""
        try:
            from .mac_ax import find_element
            results = find_element(pid, label=label, role=role, max_depth=max_depth)
            return {
                "action": "find_element",
                "pid": pid,
                "label": label,
                "role": role,
                "matches": results,
                "count": len(results),
            }
        except ImportError as e:
            return {"error": f"AXAPI not available: {e}"}
        except Exception as e:
            return {"error": f"AXAPI error: {e}"}

    def _dump_tree(self, pid: int, max_depth: int = 5) -> dict[str, Any]:
        """Print the full AX tree of an app for debugging."""
        try:
            from .mac_ax import dump_tree
            lines = dump_tree(pid, max_depth=max_depth)
            return {
                "action": "dump_tree",
                "pid": pid,
                "tree": lines,
            }
        except ImportError as e:
            return {"error": f"AXAPI not available: {e}"}
        except Exception as e:
            return {"error": f"AXAPI error: {e}"}

    def _launch_app(self, name: str) -> dict[str, Any]:
        """Launch an application by name or bundle ID."""
        if not name:
            return {"error": "name required"}
        try:
            from .mac_ax import launch_app
            return launch_app(name)
        except ImportError as e:
            return {"error": f"AXAPI not available: {e}"}
        except Exception as e:
            return {"error": f"launch error: {e}"}

    def _list_windows(self) -> dict[str, Any]:
        """List all visible windows on screen."""
        try:
            from .mac_ax import list_windows
            windows = list_windows()
            return {
                "action": "list_windows",
                "windows": windows,
                "count": len(windows),
            }
        except ImportError as e:
            return {"error": f"AXAPI not available: {e}"}
        except Exception as e:
            return {"error": f"window list error: {e}"}

    def _check_permission(self) -> dict[str, Any]:
        """Check if AXAPI accessibility permission is granted."""
        try:
            from .mac_ax import check_permission
            return check_permission()
        except ImportError as e:
            return {"error": f"AXAPI not available: {e}"}
        except Exception as e:
            return {"error": f"permission check error: {e}"}


__all__ = [
    "ComputerUseTool",
    "ActionLogEntry",
]
