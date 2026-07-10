#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# MadCop — one-command start script
# Builds Vue 3 frontend, starts Python backend, launches Electron
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DESKTOP="$ROOT/desktop"
MADCOP="$ROOT/madcop"

cd "$ROOT"

echo "╔══════════════════════════════════════════╗"
echo "║   MadCop v0.9 — macOS Native Agent      ║"
echo "╚══════════════════════════════════════════╝"

# ── 1. Check python3 ──
echo ""
echo "▸ Checking Python..."
PYTHON=""
for candidate in python3.12 python3.11 python3.13 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "✗ python3 not found in PATH"
    echo "  Install via: brew install python@3.12"
    exit 1
fi
echo "  Python: $($PYTHON --version 2>&1)"

# ── 2. Activate/create venv ──
VENV="$HOME/.madcop/memory/.venv"
if [ -f "$VENV/bin/python3" ]; then
    source "$VENV/bin/activate"
    echo "  Venv: $VENV (active)"
else
    echo "  No venv found — creating one..."
    $PYTHON -m venv "$VENV"
    source "$VENV/bin/activate"
    echo "  Venv: $VENV (created)"
fi

# ── 3. Install deps ──
echo ""
echo "▸ Installing Python dependencies..."
pip install -q --upgrade pip 2>/dev/null || true
pip install -q -e "$ROOT" 2>/dev/null || pip install -q fastapi uvicorn 2>/dev/null || true
echo "  Done"

# ── 4. Build Vue 3 frontend ──
echo ""
echo "▸ Building Vue 3 frontend..."
cd "$DESKTOP"
if [ ! -d "node_modules" ]; then
    npm install --silent 2>/dev/null
fi
npx vite build --config vite.vue.config.ts 2>&1 | tail -3
echo "  ✓ dist-vue/index.html ready"
cd "$ROOT"

# ── 5. Start backend ──
echo ""
echo "▸ Starting backend (port 8765)..."
# Kill any existing process on port 8765
lsof -ti:8765 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 0.3

uvicorn madcop.server.app:app --host 127.0.0.1 --port 8765 --reload &
BACKEND_PID=$!
echo "  PID: $BACKEND_PID"

# Wait for backend to be ready
for i in $(seq 1 20); do
    if curl -s http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
        echo "  ✓ Backend healthy"
        break
    fi
    sleep 0.5
done

# ── 6. Launch Electron ──
echo ""
echo "▸ Launching Electron..."
cd "$DESKTOP"
npm run dev &
ELECTRON_PID=$!
echo "  PID: $ELECTRON_PID"
cd "$ROOT"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   MadCop is running!                     ║"
echo "║                                          ║"
echo "║   Backend:  http://127.0.0.1:8765        ║"
echo "║   Debug:    chrome://inspect → 9223      ║"
echo "║                                          ║"
echo "║   Stop:     kill $BACKEND_PID $ELECTRON_PID  ║"
echo "╚══════════════════════════════════════════╝"
