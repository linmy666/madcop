#!/usr/bin/env python3
"""macOS AXAPI MCP Server — expose UI element control via Model Context Protocol.

Run as a standalone MCP server (stdio transport):
    python3 -m madcop.tools.mac_ax_mcp_server

Connect from any MCP client:
    # Claude Desktop config.json
    {
      "mcpServers": {
        "macos-axapi": {
          "command": "python3",
          "args": ["-m", "madcop.tools.mac_ax_mcp_server"]
        }
      }
    }

What this gives you:
  - check_permission     – verify AXAPI accessibility is granted
  - check_screen_recording – verify screen recording permission
  - list_apps            – enumerate running GUI applications
  - list_windows         – enumerate all visible windows
  - focus_app            – bring an app to the foreground (by name or PID)
  - launch_app           – launch an application by name
  - find_element         – search AX tree for UI elements by label/role
  - click                – send a mouse click at (x, y)
  - type_text            – type a string via AXAPI keystrokes
  - press_key            – press a named key (enter, tab, escape, …)

Requires:
  - macOS
  - Accessibility permission (System Settings → Privacy → Accessibility)
  - Screen Recording for window/element discovery (same place → Screen Recording)
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from typing import Any

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger("mac_ax_mcp")

# ─────────────────────────────────────────────────────────
# MCP Protocol constants
# ─────────────────────────────────────────────────────────
MCP_PROTOCOL_VERSION = "2024-11-25"
SERVER_NAME = "macos-axapi"
SERVER_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────
# Tool definitions (MCP format)
# ─────────────────────────────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "check_permission",
        "description": "Check if macOS Accessibility permission is granted for this process",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "check_screen_recording",
        "description": "Check if Screen Recording permission is granted by probing window enumeration",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_apps",
        "description": "List all currently running GUI applications with name, PID, visibility",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_windows",
        "description": "List all visible windows across all apps with title, position, size",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "focus_app",
        "description": "Bring an application to the foreground by name (exact match) or PID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_or_pid": {
                    "type": "string",
                    "description": "Application name (e.g. 'Safari') or PID as string (e.g. '12345')",
                },
            },
            "required": ["name_or_pid"],
        },
    },
    {
        "name": "launch_app",
        "description": "Launch an application by name (e.g. 'Calculator', 'Safari')",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Application name to launch (e.g. 'Calculator')",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "find_element",
        "description": "Search the accessibility tree of the frontmost app for UI elements matching a label or role",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Substring to match against element titles/descriptions (case-insensitive)",
                },
                "role": {
                    "type": "string",
                    "description": "AX role to filter by (e.g. AXButton, AXTextField, AXStaticText)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "click",
        "description": "Send a mouse click at screen coordinates (x, y)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate (pixels from left)"},
                "y": {"type": "integer", "description": "Y coordinate (pixels from top)"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "type_text",
        "description": "Type a string of text using AXAPI keystrokes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "press_key",
        "description": "Press a keyboard key by name. Supports: enter, tab, escape, space, up, down, left, right, delete, f1-f12, cmd, shift, option, ctrl, and single characters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name (e.g. 'enter', 'escape', 'tab', 'cmd')"},
            },
            "required": ["key"],
        },
    },
]

# ─────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────


def _exec(action: str, args: dict[str, Any]) -> Any:
    """Route tool calls to mac_ax functions."""
    from .mac_ax import (
        check_permission,
        check_screen_recording,
        click,
        find_element,
        focus_app,
        launch_app,
        list_apps,
        list_windows,
        press_key,
        type_text,
    )

    _DISPATCH = {
        "check_permission":         lambda: check_permission(),
        "check_screen_recording":   lambda: check_screen_recording(),
        "list_apps":                lambda: {"apps": list_apps(), "count": len(list_apps())},
        "list_windows":             lambda: {"windows": list_windows(), "count": len(list_windows())},
        "focus_app":                lambda: focus_app(args.get("name_or_pid", "")),
        "launch_app":               lambda: launch_app(args.get("name", "")),
        "find_element":             lambda: {"matches": find_element(label=args.get("label"), role=args.get("role")), "count": len(find_element(label=args.get("label"), role=args.get("role")))},
        "click":                    lambda: click(int(args.get("x", 0)), int(args.get("y", 0))),
        "type_text":                lambda: type_text(args.get("text", "")),
        "press_key":                lambda: press_key(args.get("key", "")),
    }

    fn = _DISPATCH.get(action)
    if fn is None:
        raise ValueError(f"Unknown action: {action}")
    return fn()


# ─────────────────────────────────────────────────────────
# MCP Server loop
# ─────────────────────────────────────────────────────────


def _read_request() -> dict[str, Any] | None:
    """Read one JSON-RPC request from stdin (line-delimited)."""
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return _read_request()
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning("malformed JSON: %s", e)
        return _read_request()


def _send_response(msg: dict[str, Any]) -> None:
    """Write a JSON-RPC response to stdout."""
    line = json.dumps(msg, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _send_error(id_val: int | str | None, code: int, message: str, data: Any = None) -> None:
    _send_response({
        "jsonrpc": "2.0",
        "id": id_val,
        "error": {"code": code, "message": message, "data": data},
    })


def run() -> None:
    """Main MCP server loop. Reads from stdin, writes to stdout."""
    # Suppress logging to stdout (stdout is the MCP transport)
    logging.getLogger().handlers.clear()
    logging.getLogger().addHandler(logging.StreamHandler(sys.stderr))

    logger.info("mac_ax MCP server starting...")
    logger.info("Waiting for requests on stdin...")

    while True:
        req = _read_request()
        if req is None:
            logger.info("stdin closed, exiting")
            break

        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params", {}) or {}

        # Handle initialize (no id required per spec)
        if method == "initialize":
            _send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            })
            continue

        # Handle initialized notification (no response expected)
        if method == "notifications/initialized":
            continue

        # Handle tools/list
        if method == "tools/list":
            _send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS},
            })
            continue

        # Handle tools/call
        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}
            try:
                result = _exec(tool_name, tool_args)
                # Result must be list of content blocks
                content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]
                _send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": content},
                })
            except Exception as e:
                tb = traceback.format_exc()
                logger.error("Tool call failed: %s\n%s", e, tb)
                _send_error(req_id, -32603, str(e), {"traceback": tb})
            continue

        # Unknown method — return MethodNotFound
        _send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    run()