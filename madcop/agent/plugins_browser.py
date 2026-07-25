"""
v4.0 — Phase 4: One-line plugin registration for browser-use / computer-use.

This module is the canonical example for the plan\'s "新能力一行注册"
requirement. The PluginRegistry already exists in
``madcop.agent.tool_executor``; this file shows the **only** code
needed to add a new external capability (browser automation,
computer/screen control) without touching the engine or the chat
route.

Three sample plugins ship here:

* ``browser_navigate`` — load a URL in a headless browser and return
  the page title + first ~500 chars of body text. The handler is a
  stub (returns the URL + a marker) so the unit test does not need a
  real browser binary; in production swap the body for a Playwright
  call.
* ``browser_screenshot`` — take a screenshot of the current page and
  return the path (stub: returns a deterministic temp path).
* ``computer_screenshot`` — capture the user\'s screen and return the
  path. Stub: returns a deterministic temp path.

All three are registered via ``register_browser_plugins(registry)``
which the application calls once at startup, so the engine sees them
in ``PluginRegistry.get_all_schemas()`` and the LLM gets the JSON
schema. Adding another tool is one new handler + one more
``registry.register(...)`` line.

To actually wire it into the running app, edit
``build_default_registry`` in ``madcop/agent/tool_executor.py`` and
add::

    from .plugins_browser import register_browser_plugins
    register_browser_plugins(reg)

or pass the registry to a custom builder.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from madcop.agent.tool_executor import PluginRegistry, ToolPlugin
from madcop.tools.safety import danger_level

logger = logging.getLogger(__name__)


# ─── Plugin handlers (stubs; replace with real implementations) ─────────────


def _browser_navigate_stub(url: str = "", **_kwargs: Any) -> str:
    """Headless-browser navigation stub.

    Real implementation should:
      1. Open ``url`` in Playwright (sync or async).
      2. Wait for ``domcontentloaded``.
      3. Return ``title`` + first ``<body>`` text up to 500 chars.
    """
    if not url:
        return "[browser_navigate] missing url"
    return (
        f"[browser_navigate] navigated to {url} "
        "(stub: install playwright + replace this handler)"
    )


def _browser_screenshot_stub(path: str = "", **_kwargs: Any) -> str:
    """Browser screenshot stub. Returns a deterministic path."""
    out = path or os.path.join(tempfile.gettempdir(), "madcop_browser.png")
    return f"[browser_screenshot] saved to {out} (stub)"


def _computer_screenshot_stub(path: str = "", **_kwargs: Any) -> str:
    """Computer/screen capture stub. Returns a deterministic path."""
    out = path or os.path.join(tempfile.gettempdir(), "madcop_screen.png")
    return f"[computer_screenshot] saved to {out} (stub)"


# ─── Schemas (OpenAI function-calling format) ───────────────────────────────


_BROWSER_NAVIGATE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "browser_navigate",
        "description": (
            "Open a URL in a headless browser and return the page title "
            "+ the first 500 chars of the rendered body text. Use this "
            "when you need to read content that requires JavaScript "
            "rendering or that web_fetch can\'t reach (login-walled, "
            "dynamic, anti-bot)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Absolute URL to open (http or https).",
                },
                "wait_for": {
                    "type": "string",
                    "description": (
                        "Optional CSS selector. If set, wait until the "
                        "selector appears in the DOM before returning."
                    ),
                },
            },
            "required": ["url"],
        },
    },
}

_BROWSER_SCREENSHOT_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "browser_screenshot",
        "description": (
            "Take a screenshot of the current browser page and save it "
            "to disk. Returns the saved path. Use this to capture "
            "visual state for the user or for later inspection."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Output path. Defaults to $TMP/madcop_browser.png.",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "If true, capture the full scrollable page, not just the viewport.",
                },
            },
        },
    },
}

_COMPUTER_SCREENSHOT_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "computer_screenshot",
        "description": (
            "Capture the user\'s screen and save it as a PNG. Use this "
            "for computer-use workflows where the model needs to see "
            "what is on screen (desktop apps, OS dialogs)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Output path. Defaults to $TMP/madcop_screen.png.",
                },
            },
        },
    },
}


# ─── Registration ───────────────────────────────────────────────────────────


def register_browser_plugins(registry: PluginRegistry) -> int:
    """Register browser_navigate + browser_screenshot + computer_screenshot.

    Returns the number of plugins added. This is the **only** code
    needed to wire external capabilities into the v4 agent; the
    engine sees them automatically via
    ``registry.get_all_schemas()`` and the LLM gets the JSON schemas
    in its system prompt.
    """
    plugins = [
        ToolPlugin(
            name="browser_navigate",
            handler=_browser_navigate_stub,
            schema=_BROWSER_NAVIGATE_SCHEMA,
            danger=danger_level("browser_navigate"),
            timeout_s=30,
        ),
        ToolPlugin(
            name="browser_screenshot",
            handler=_browser_screenshot_stub,
            schema=_BROWSER_SCREENSHOT_SCHEMA,
            danger=danger_level("browser_screenshot"),
            timeout_s=15,
        ),
        ToolPlugin(
            name="computer_screenshot",
            handler=_computer_screenshot_stub,
            schema=_COMPUTER_SCREENSHOT_SCHEMA,
            danger=danger_level("computer_screenshot"),
            timeout_s=15,
        ),
    ]
    for p in plugins:
        registry.register(p)
        logger.debug("registered browser plugin: %s", p.name)
    return len(plugins)


__all__ = ["register_browser_plugins"]