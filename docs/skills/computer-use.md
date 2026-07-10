---
name: computer-use
description: macOS Computer Use — let the agent see and control the screen via AXAPI
triggers:
  - "帮我操作电脑"
  - "帮我截图"
  - "帮我打开XX应用"
  - "帮我在XX里找到XX"
  - "帮我点击XX"
  - "control my screen"
  - "computer use"
  - "take a screenshot"
created_at: "2026-07-06"
updated_at: "2026-07-06"
source: manual
version: "1.0"
tags:
  - macos
  - accessibility
  - axapi
  - automation
---

# macOS Computer Use

## When to use

Use this skill when the user asks you to:
- **Screenshot** — capture what's on screen
- **Click** — click at a specific position
- **Type** — type text into a focused field
- **Press a key** — simulate keyboard input
- **Launch an app** — open an application
- **Focus an app** — bring an app to the foreground
- **Find an element** — search the accessibility tree for a button/field/label
- **List apps** — show what applications are running
- **Check permissions** — verify AXAPI/screen recording access

## Tools available

MadCop exposes a `computer_use` tool in the tool registry, and a standalone `macos-axapi` MCP server that can be connected independently.

### Via MadCop tool registry (preferred)

```json
{
  "name": "computer_use",
  "action": "screenshot | click | type | key | scroll | find_element | list_apps | focus_app | launch_app | list_windows | check_permission"
}
```

### Via MCP server (external clients)

Run: `python3 -m madcop.tools.mac_ax_mcp_server`

## Common workflows

### 1. Screenshot → analyze
```
action: screenshot
```
→ Returns image path. Feed it to a vision model.

### 2. Find → click
```
action: find_element
label: "搜索"
role: AXButton
```
→ Returns element coords. Then:
```
action: click
x: <coord.x>
y: <coord.y>
```

### 3. Launch → type → press Enter
```
action: launch_app
name: "Calculator"
```
→ Then type and press enter:
```
action: type
text: "42*15"
action: key
key: "enter"
```

### 4. Check environment
```
action: check_permission
```
→ Returns: `{"granted": true/false, "frontmost": "AppName"}
```
action: list_apps
```
→ Returns all running GUI apps with PIDs

## Required permissions

For the tool to work, the user must grant:
1. **Accessibility** — System Settings → Privacy & Security → Accessibility → add Terminal/Electron
2. **Screen Recording** — System Settings → Privacy & Security → Screen Recording → add Terminal/Electron
   (required for window listing and element discovery)

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `ACCESS_DENIED` | Missing Accessibility permission | Add the app to System Settings → Privacy → Accessibility |
| `window list empty` | Missing Screen Recording permission | Add the app to System Settings → Privacy → Screen Recording |
| `osascript not found` | macOS only feature | Only available on macOS |
| `TIMEOUT` | AXAPI call hung | Try again, or kill stuck osascript process |
| clicked but no effect | Element off-screen / overlay | Use `find_element` first to get valid coords |

## Notes

- All AXAPI calls are synchronous (blocking).
- The tool uses `osascript -l JavaScript` under the hood — no pyobjc, no ctypes.
- Coordinates are screen-space pixels (not retina points — macOS handles the scaling).
- `find_element` only searches one level deep + direct children; for deep trees, use the MCP server's interactive dump.