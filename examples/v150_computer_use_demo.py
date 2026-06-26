"""v1.5.0 — Computer Use demo: screenshot + permission system.

This demo shows the ComputerUseTool + PermissionManager in action.

  Phase 1: Take a screenshot (READ level — always allowed).
  Phase 2: Try to click (NAVIGATE — needs permission grant).
  Phase 3: Try to type (INPUT — needs permission grant).
  Phase 4: Try a destructive action (denied by default).
  Phase 5: Show the action log.

No real mouse/keyboard input is injected — we use dry_run=True.
But the screenshot IS real (if running on macOS).

Run:
  python examples/v150_computer_use_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madcop.tools import (
    ActionLevel,
    ComputerUseTool,
    Permission,
    PermissionManager,
    ToolRegistry,
)


def main() -> int:
    print("=" * 72)
    print("  madcop v1.5.0 — Computer Use + Permission System Demo")
    print("=" * 72)
    print()

    # Build permission manager with a scripted prompt
    decisions = iter([])  # no prompts needed — we grant explicitly

    import tempfile
    perms = PermissionManager(
        store_path=Path(tempfile.mkdtemp()) / "perms.json",
    )

    # Build tool in dry-run mode (safe for demo)
    tool = ComputerUseTool(
        perms=perms,
        dry_run=True,
        screenshot_dir=Path(tempfile.mkdtemp()),
    )

    # Register in a ToolRegistry (what the agent would see)
    registry = ToolRegistry()
    registry.register(tool)

    print(f"Registered tools: {registry.names()}")
    print()

    # Show the OpenAI-compatible schema
    import json
    schema = tool.to_openai_schema()
    print("OpenAI tool schema:")
    print(json.dumps(schema, indent=2)[:500])
    print("  ...\n")

    # =========================================================================
    # Phase 1: Screenshot (READ — always allowed)
    # =========================================================================
    print("─" * 72)
    print("  Phase 1: SCREENSHOT (READ level)")
    print("─" * 72)
    result = tool(action="screenshot")
    print(f"  status: {result['status']}")
    if result.get("screenshot_path"):
        print(f"  screenshot: {result['screenshot_path']}")
        print(f"  screen size: {result.get('screen_size', '?')}")
    print()

    # =========================================================================
    # Phase 2: Click (NAVIGATE — needs session grant)
    # =========================================================================
    print("─" * 72)
    print("  Phase 2: CLICK (NAVIGATE level)")
    print("─" * 72)

    # First try without permission
    print("  Attempt 1: no permission granted yet")
    result = tool(action="click", x=100, y=100)
    print(f"  → status: {result['status']}")
    if result["status"] == "dry_run":
        print(f"  → {result['message']}")
    print()

    # Grant session-level permission
    print("  Granting SESSION permission for 'click'...")
    perms.grant("click", Permission.SESSION)
    print(f"  Permission check: {perms.check('click')}")
    print()

    result = tool(action="click", x=200, y=200, button="left")
    print(f"  Attempt 2: click(200, 200)")
    print(f"  → status: {result['status']}")
    print(f"  → {result.get('message', '')}")
    print()

    # =========================================================================
    # Phase 3: Type (INPUT level)
    # =========================================================================
    print("─" * 72)
    print("  Phase 3: TYPE (INPUT level)")
    print("─" * 72)

    perms.grant("type", Permission.SESSION)
    result = tool(action="type", text="Hello from madcop!")
    print(f"  type('Hello from madcop!')")
    print(f"  → status: {result['status']}")
    print(f"  → {result.get('message', '')}")
    print()

    # Key press
    perms.grant("hotkey", Permission.SESSION)
    perms.grant("key_enter", Permission.SESSION)
    result = tool(action="key", key="enter")
    print(f"  key('enter')")
    print(f"  → status: {result['status']}")
    print(f"  → {result.get('message', '')}")
    print()

    # =========================================================================
    # Phase 4: Destructive (denied by default)
    # =========================================================================
    print("─" * 72)
    print("  Phase 4: DESTRUCTIVE action (default DENY)")
    print("─" * 72)
    # kill_app maps to DESTRUCTIVE — default is DENY
    result = tool(action="kill_app")
    print(f"  kill_app()")
    print(f"  → status: {result['status']}")
    print(f"  → {result.get('message', '')}")
    print()

    # =========================================================================
    # Phase 5: Action log
    # =========================================================================
    print("─" * 72)
    print("  Phase 5: Action log")
    print("─" * 72)
    log = tool.action_log
    print(f"  {len(log)} action(s) recorded:\n")
    print(f"  {'timestamp':22s} {'action':15s} {'level':12s} {'permission':10s} result")
    print(f"  {'-'*22} {'-'*15} {'-'*12} {'-'*10} {'-'*20}")
    for entry in log:
        print(f"  {entry.timestamp:22s} {entry.action:15s} {entry.level:12s} "
              f"{entry.permission:10s} {entry.result}")
    print()

    # =========================================================================
    # Summary
    # =========================================================================
    print("=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    print(f"  Actions taken:     {len(log)}")
    print(f"  READ allowed:      {sum(1 for e in log if e.level == 'READ')}")
    print(f"  NAVIGATE allowed:  {sum(1 for e in log if e.level == 'NAVIGATE')}")
    print(f"  INPUT allowed:     {sum(1 for e in log if e.level == 'INPUT')}")
    print(f"  DESTRUCTIVE denied:{sum(1 for e in log if e.level == 'DESTRUCTIVE')}")
    print()
    print("  Permission levels:")
    print("    READ        → always allowed (screenshots)")
    print("    NAVIGATE    → ask once (clicks, scrolling)")
    print("    INPUT       → ask once (typing, hotkeys)")
    print("    DESTRUCTIVE → denied by default (kill, close)")
    print()
    print("  Grant scopes: once / session / always (persisted)")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
