#!/bin/bash
# MadCop Agent launcher — template for the desktop shortcut (.app wrapper).
#
# This is the source of truth for the shell script that lives inside
# ~/Desktop/MadCop Agent.app/Contents/MacOS/MadCopAgent. It:
#   1. Starts the FastAPI backend (python3 -m madcop.server) on 127.0.0.1:8765
#      if it isn't already listening.
#   2. Launches Electron against the built main.cjs.
#
# Two non-obvious gotchas this script handles:
#
#   GOTCHA 1 — GUI launch ignores shell PATH.
#     Double-clicking the .app runs under a minimal LaunchServices
#     environment that does NOT source ~/.zshrc / ~/.bash_profile, so a
#     bare `python3` resolves to the Xcode Command-Line-Tools python3
#     (which lacks fastapi/uvicorn and can't see the madcop package).
#     Fix: pin the framework Python by absolute path.
#
#   GOTCHA 2 — the .app is tagged "Open using Rosetta" on Apple Silicon.
#     Even on an arm64 Mac, `open` runs this whole script (and the
#     universal Python binary) under x86_64. The arm64 .so wheels
#     (pydantic_core, etc.) then fail to dlopen with
#       "mach-o file, but is an incompatible architecture".
#     Fix: unconditionally wrap the python call in `arch -arm64` so the
#     interpreter runs on the native slice regardless of the parent arch.
#
# Rebuild the desktop shortcut from this template:
#   install -m755 desktop/scripts/madcop-agent-launcher.sh \
#     "~/Desktop/MadCop Agent.app/Contents/MacOS/MadCopAgent"
# (adjust MADCOP_DIR / PYTHON_BIN below for your machine first).

MADCOP_DIR="/Users/linruihan/PycharmProjects/madcop"
ELECTRON_BIN="$MADCOP_DIR/desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
MAIN_CJS="$MADCOP_DIR/desktop/electron-dist/main.cjs"
LOG_DIR="$HOME/Library/Logs/MadCop Agent"
mkdir -p "$LOG_DIR"

# Pin the Python that actually has the deps. Override with MADCOP_PYTHON
# if your interpreter lives elsewhere.
PYTHON_BIN="${MADCOP_PYTHON:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3}"

# Start FastAPI if not already running.
if ! /usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
    if [ ! -x "$PYTHON_BIN" ]; then
        osascript -e "display notification \"找不到 Python: $PYTHON_BIN。请安装 Python 3.11+ 并运行 pip3 install fastapi uvicorn\" with title \"MadCop Agent\""
    else
        osascript -e 'display notification "Starting FastAPI backend on port 8765..." with title "MadCop Agent"'
        # Run from the repo root so the `madcop` package is importable.
        cd "$MADCOP_DIR" || exit 1
        # Force native arm64 — see GOTCHA 2 above.
        if command -v arch >/dev/null 2>&1 && arch -arm64 true 2>/dev/null; then
            nohup arch -arm64 "$PYTHON_BIN" -m madcop.server > "$LOG_DIR/backend.log" 2>&1 &
        else
            nohup "$PYTHON_BIN" -m madcop.server > "$LOG_DIR/backend.log" 2>&1 &
        fi
        BACKEND_PID=$!
        echo "Started FastAPI (PID $BACKEND_PID), waiting for boot..."
        # Wait up to 15s for the backend to come up.
        for i in $(seq 1 30); do
            if /usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
                break
            fi
            # Bail early if the backend died (import error, missing deps, etc.)
            if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
                osascript -e "display notification \"后端启动失败，请查看 $LOG_DIR/backend.log\" with title \"MadCop Agent\""
                break
            fi
            sleep 0.5
        done
    fi
fi

# Launch Electron (strip env vars that make Electron run as pure Node).
exec env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS "$ELECTRON_BIN" "$MAIN_CJS" --no-sandbox
