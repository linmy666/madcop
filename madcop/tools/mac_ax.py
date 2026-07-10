"""macOS Accessibility API bridge — element discovery without visual models.

Uses macOS's built-in Accessibility API via osascript (JXA).
No pyobjc, no ctypes, no fragile bindings — just Apple's own
JavaScript for Automation runtime, which every macOS has.

Architecture:
  mac_ax.list_apps()      → osascript → ["Chrome", "Terminal", ...]
  mac_ax.focus("Chrome")  → osascript → bring to front
  mac_ax.find("搜索框")   → osascript → AX tree search
  mac_ax.click(x, y)      → osascript → mouse click

Requires:
  - macOS
  - Accessibility permission in System Settings → Privacy → Accessibility
    (the very first action when permission is missing pops a dialog)
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

# ── JXA scripts (embedded as strings) ─────────────────────────────


def _jxa(script: str, timeout: float = 15) -> str:
    """Run a JXA script via osascript and return stdout."""
    # Write to a temp file to avoid shell escaping issues with complex scripts
    fd, path = tempfile.mkstemp(suffix=".js", prefix="mac_ax_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("ObjC.import('Cocoa');\n")
            f.write(script)
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", path],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "assistive access" in stderr.lower() or "-25211" in stderr:
                return '{"_error": "ACCESS_DENIED", "_message": "Accessibility permission required. Open System Settings → Privacy & Security → Accessibility → add your terminal app."}'
            return f'{{"_error": "JXA_ERROR", "_message": {stderr!r}}}'
        return result.stdout.strip() or "{}"
    except subprocess.TimeoutExpired:
        return '{"_error": "TIMEOUT"}'
    except Exception as e:
        return f'{{"_error": "EXCEPTION", "_message": {str(e)!r}}}'
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def _jxa_json(script: str, timeout: float = 15) -> Any:
    """Run JXA and parse the result as JSON."""
    out = _jxa(script, timeout=timeout)
    import json
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"_error": "PARSE_FAILED", "_raw": out[:500]}


# ── Public API ────────────────────────────────────────────────────


def check_permission() -> dict[str, Any]:
    """Check if Accessibility permission is granted."""
    result = _jxa_json(
        """
        var se = Application("System Events");
        var front = se.processes.whose({frontmost: true})[0];
        if (front) {
            JSON.stringify({granted: true, frontmost: front.name()});
        } else {
            JSON.stringify({granted: true, frontmost: "none"});
        }
        """
    )
    if result.get("_error") == "ACCESS_DENIED":
        return {"granted": False, "error": result["_message"]}
    return result


def list_apps() -> list[dict[str, Any]]:
    """List all running GUI applications with their properties."""
    result = _jxa_json(
        """
        var se = Application("System Events");
        var procs = se.processes();
        var apps = [];
        for (var i = 0; i < procs.length; i++) {
            var p = procs[i];
            try {
                apps.push({
                    name: p.name(),
                    pid: p.unixId(),
                    frontmost: p.frontmost(),
                    visible: p.visible(),
                });
            } catch(e) {}
        }
        JSON.stringify(apps);
        """
    )
    if isinstance(result, list):
        return result
    return []


def list_windows() -> list[dict[str, Any]]:
    """List all visible windows."""
    result = _jxa_json(
        """
        var se = Application("System Events");
        var procs = se.processes();
        var wins = [];
        for (var i = 0; i < procs.length; i++) {
            try {
                var proc = procs[i];
                var windows = proc.windows();
                for (var j = 0; j < windows.length; j++) {
                    var w = windows[j];
                    try {
                        var pos = w.position();
                        var size = w.size();
                        wins.push({
                            owner: proc.name(),
                            title: w.title(),
                            pid: proc.unixId(),
                            x: pos[0],
                            y: pos[1],
                            width: size[0],
                            height: size[1],
                            minimized: w.minimized(),
                        });
                    } catch(e2) {}
                }
            } catch(e) {}
        }
        JSON.stringify(wins);
        """
    )
    if isinstance(result, list):
        return result
    return []


def focus_app(name_or_pid: str | int) -> dict[str, Any]:
    """Bring an app to the foreground."""
    result = _jxa_json(
        f"""
        var se = Application("System Events");
        var target = "{name_or_pid}";
        var procs = se.processes();
        for (var i = 0; i < procs.length; i++) {{
            if (procs[i].name() === target || String(procs[i].unixId()) === target) {{
                procs[i].frontmost = true;
                JSON.stringify({{success: true, name: procs[i].name(), pid: procs[i].unixId()}});
                return;
            }}
        }}
        JSON.stringify({{success: false, error: "not found"}});
        """
    )
    return result


def launch_app(name: str) -> dict[str, Any]:
    """Launch an application by name."""
    result = _jxa_json(
        f"""
        var app = Application("{name}");
        app.activate();
        JSON.stringify({{launched: true, name: "{name}"}});
        """
    )
    return result


def click(x: int, y: int) -> dict[str, Any]:
    """Click at screen coordinates using System Events."""
    result = _jxa_json(
        f"""
        var se = Application("System Events");
        se.clickAt({{x: {x}, y: {y}}});
        JSON.stringify({{x: {x}, y: {y}, clicked: true}});
        """
    )
    return result


def type_text(text: str) -> dict[str, Any]:
    """Type text using System Events."""
    # Escape for JXA string
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    result = _jxa_json(
        f"""
        var se = Application("System Events");
        se.keyStrokes("{escaped}");
        JSON.stringify({{typed: true, length: {len(text)}}});
        """
    )
    return result


def press_key(key: str) -> dict[str, Any]:
    """Press a key."""
    result = _jxa_json(
        f"""
        var se = Application("System Events");
        se.keyCode({_key_to_code(key)});
        JSON.stringify({{key: "{key}", pressed: true}});
        """
    )
    return result


def find_element(
    label: str | None = None,
    role: str | None = None,
    frontmost_only: bool = True,
) -> list[dict[str, Any]]:
    """Search for UI elements by label or role in the frontmost app."""
    if not label and not role:
        return []

    role_filter = ""
    if role:
        role_filter = f"el.role() === '{role}'"
    label_filter = ""
    if label:
        escaped_label = label.replace("'", "\\'")
        label_filter = f"el.title() && el.title().toLowerCase().includes('{escaped_label.lower()}')"

    filters = []
    if role_filter:
        filters.append(role_filter)
    if label_filter:
        filters.append(label_filter)
    condition = " && ".join(filters) if filters else "true"

    script = f"""
    var se = Application("System Events");
    var frontApp = se.processes.whose({{frontmost: true}})[0];
    if (!frontApp) {{ JSON.stringify([]); }}
    var results = [];
    var windows = frontApp.windows();
    for (var w = 0; w < windows.length; w++) {{
        try {{
            var elems = windows[w].uiElements();
            for (var e = 0; e < elems.length; e++) {{
                try {{
                    var el = elems[e];
                    if ({condition}) {{
                        try {{
                            var pos = el.position();
                            var size = el.size();
                            results.push({{
                                role: el.role(),
                                label: el.title() || el.description() || "",
                                x: pos[0], y: pos[1],
                                width: size[0], height: size[1],
                                enabled: el.enabled(),
                            }});
                        }} catch(e2) {{}}
                    }}
                    // Recurse into children
                    var kids = el.uiElements();
                    for (var k = 0; k < kids.length; k++) {{
                        try {{
                            var kid = kids[k];
                            if ({condition}) {{
                                var pos = kid.position();
                                var size = kid.size();
                                results.push({{
                                    role: kid.role(),
                                    label: kid.title() || kid.description() || "",
                                    x: pos[0], y: pos[1],
                                    width: size[0], height: size[1],
                                    enabled: kid.enabled(),
                                }});
                            }}
                        }} catch(e3) {{}}
                    }}
                }} catch(e4) {{}}
            }}
        }} catch(e5) {{}}
    }}
    JSON.stringify(results);
    """
    result = _jxa_json(script)
    if isinstance(result, list):
        return result
    return []


def _key_to_code(key: str) -> str:
    """Convert a human-readable key name to macOS key code."""
    mapping = {
        "enter": "36", "return": "36",
        "tab": "48", "space": "49",
        "delete": "51", "backspace": "51",
        "escape": "53", "esc": "53",
        "up": "126", "down": "125", "left": "123", "right": "124",
        "f1": "122", "f2": "120", "f3": "99", "f4": "118",
        "f5": "96", "f6": "97", "f7": "98", "f8": "100",
        "home": "115", "end": "119", "pageup": "116", "pagedown": "121",
        "cmd": "55", "command": "55",
        "shift": "56", "option": "58", "alt": "58", "ctrl": "59",
    }
    key_lower = key.lower().strip()
    if key_lower in mapping:
        return mapping[key_lower]
    # Try to use the key as a character
    if len(key) == 1:
        return str(ord(key))
    return "0"