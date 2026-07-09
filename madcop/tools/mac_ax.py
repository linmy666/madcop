"""macOS Accessibility API bridge — element discovery without visual models.

Uses macOS's built-in Accessibility API (AXAPI) to read the UI element
tree of any running application. No screenshots, no ML, no Playwright.

The key insight: macOS already knows every button, text field, menu item,
and window on screen — it's how VoiceOver, Siri, and automation tools
work. We just ask the system.

Architecture:
  mac_ax.discover()     → list all running applications
  mac_ax.focus(pid)     → bring an app to front
  mac_ax.find(pid, label, role) → recursively search the AX tree
  mac_ax.attrs(element) → dump all attributes of an element
  mac_ax.hierarchy(pid) → print the full AX tree for debugging

Dependencies:
  - pyobjc (installed with MadCop) — bridges Python to macOS's
    Objective-C runtime
  - ApplicationServices.framework — the AXAPI itself

Safety:
  - READ-ONLY: does not inject input itself (use pyautogui for that)
  - Permission: the user must grant Accessibility permission in
    System Settings → Privacy & Security → Accessibility
    (MadCop's Privacy permission request handles this)
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — pyobjc is available but we don't want import-time failures
# ---------------------------------------------------------------------------
_Quartz = None
_NSWorkspace = None
_NSRunningApplication = None


def _ensure_imports() -> None:
    global _Quartz, _NSWorkspace, _NSRunningApplication
    if _Quartz is not None:
        return
    try:
        import Quartz
        from AppKit import NSWorkspace
        from AppKit import NSRunningApplication

        _Quartz = Quartz
        _NSWorkspace = NSWorkspace
        _NSRunningApplication = NSRunningApplication
    except ImportError as e:
        raise ImportError(
            "pyobjc is required for macOS AXAPI. "
            "Install: pip install pyobjc-framework-Quartz pyobjc-framework-AppKit"
        ) from e


# ---------------------------------------------------------------------------
# AXAPI wrappers — thin wrappers over C APIs
# ---------------------------------------------------------------------------

def _ax_element_for_pid(pid: int) -> Any | None:
    """Get the root AXUIElement for a process."""
    _ensure_imports()
    app = _Quartz.AXUIElementCreateApplication(pid)
    if app is None:
        return None
    return app


def _ax_attribute(element: Any, attr: str) -> Any | None:
    """Get a single AX attribute. Returns None on error/missing."""
    _ensure_imports()
    err, value = _Quartz.AXUIElementCopyAttributeValue(element, attr, None)
    if err != 0:
        return None
    return value


def _ax_attributes(element: Any) -> list[str]:
    """List all attribute names for an element."""
    _ensure_imports()
    err, attrs = _Quartz.AXUIElementCopyAttributeNames(element, None)
    if err != 0:
        return []
    return list(attrs)


def _ax_children(element: Any) -> list[Any]:
    """Get all children of an AX element."""
    raw = _ax_attribute(element, "AXChildren")
    if not raw:
        return []
    return list(raw)


def _ax_role(element: Any) -> str:
    """Get the role of an AX element (e.g. AXButton, AXTextField)."""
    val = _ax_attribute(element, "AXRole")
    return val if val else ""


def _ax_label(element: Any) -> str:
    """Get the human-readable label / title of an element."""
    for attr in ("AXTitle", "AXDescription", "AXLabel", "AXValue"):
        val = _ax_attribute(element, attr)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _ax_focused(element: Any) -> bool:
    """Check if an element has keyboard focus."""
    val = _ax_attribute(element, "AXFocused")
    return bool(val)


def _ax_position(element: Any) -> tuple[float, float, float, float] | None:
    """Get (x, y, width, height) of an element in screen coordinates."""
    pos = _ax_attribute(element, "AXPosition")
    size = _ax_attribute(element, "AXSize")
    if pos and size:
        return (pos.x, pos.y, size.width, size.height)
    return None


def _ax_enabled(element: Any) -> bool:
    val = _ax_attribute(element, "AXEnabled")
    return val if val is not None else True


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def list_apps() -> list[dict[str, Any]]:
    """List all running GUI applications with their PID, name, bundle ID."""
    _ensure_imports()
    workspace = _NSWorkspace.sharedWorkspace()
    apps = workspace.runningApplications()
    result = []
    for app in apps:
        if not app.activationPolicy() or app.activationPolicy() == 0:
            continue  # skip background processes
        result.append({
            "pid": app.processIdentifier(),
            "name": app.localizedName() or "",
            "bundleId": app.bundleIdentifier() or "",
            "frontmost": app.isActive(),
        })
    return result


def focus_app(pid: int) -> bool:
    """Bring an app to the foreground."""
    _ensure_imports()
    workspace = _NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        if app.processIdentifier() == pid:
            app.activateWithOptions(0)
            return True
    return False


def find_element(
    pid: int,
    label: str | None = None,
    role: str | None = None,
    max_depth: int = 20,
    timeout: float = 5.0,
) -> list[dict[str, Any]]:
    """Recursively search the AX tree of an app for matching elements.

    Args:
        pid: Process ID of the target application.
        label: Substring to match against element title/label/description.
        role: Exact AX role to match (e.g. "AXButton", "AXTextField").
        max_depth: Maximum recursion depth.
        timeout: Max seconds to search.

    Returns:
        List of matching elements with their attributes.
    """
    root = _ax_element_for_pid(pid)
    if root is None:
        return []

    results: list[dict[str, Any]] = []
    _visited = set()
    deadline = time.monotonic() + timeout

    def _search(element: Any, depth: int) -> None:
        if time.monotonic() > deadline or depth > max_depth:
            return
        # Avoid cycles
        elem_id = id(element)
        if elem_id in _visited:
            return
        _visited.add(elem_id)

        el_role = _ax_role(element)
        el_label = _ax_label(element)

        # Check if this element matches
        if role and el_role != role:
            pass  # role doesn't match — keep searching children
        elif label and label.lower() not in el_label.lower():
            pass  # label doesn't match — keep searching
        else:
            # Matched!
            pos = _ax_position(element)
            entry = {
                "role": el_role,
                "label": el_label,
                "enabled": _ax_enabled(element),
                "focused": _ax_focused(element),
            }
            if pos:
                entry["x"] = round(pos[0])
                entry["y"] = round(pos[1])
                entry["width"] = round(pos[2])
                entry["height"] = round(pos[3])
            results.append(entry)

        # Recurse into children
        for child in _ax_children(element):
            _search(child, depth + 1)

    _search(root, 0)
    return results


def dump_tree(pid: int, max_depth: int = 5) -> list[str]:
    """Print the AX tree of an app for debugging. Returns formatted lines."""
    root = _ax_element_for_pid(pid)
    lines: list[str] = []

    def _walk(element: Any, depth: int) -> None:
        if depth > max_depth:
            return
        role = _ax_role(element)
        label = _ax_label(element)
        pos = _ax_position(element)
        indent = "  " * depth
        line = f"{indent}{role}"
        if label:
            line += f" \"{label}\""
        if pos:
            line += f" [{pos[0]:.0f},{pos[1]:.0f} {pos[2]:.0f}x{pos[3]:.0f}]"
        lines.append(line)
        for child in _ax_children(element):
            _walk(child, depth + 1)

    _walk(root, 0)
    return lines


def element_attrs(pid: int, depth: int = 0) -> dict[str, Any]:
    """Dump all attributes of the root element (for debugging)."""
    root = _ax_element_for_pid(pid)
    if root is None:
        return {"error": "no element"}
    attrs = _ax_attributes(root)
    result: dict[str, Any] = {}
    for attr in sorted(attrs):
        val = _ax_attribute(root, attr)
        if val is not None:
            # Stringify non-primitive values
            if hasattr(val, "description"):
                val = val.description()
            elif hasattr(val, "__len__") and not isinstance(val, (str, bytes)):
                try:
                    val = len(val)
                except Exception:
                    val = str(val)[:100]
            result[attr] = str(val)[:200]
    return result