#!/bin/bash
# MadCop Agent (dev) — one-click launcher.
# Always rebuilds + reloads the latest source (frontend, python, electron)
# so you can edit a file and re-run this script without manually
# opening a terminal.
set -e
cd "$(dirname "$0")"
# Forward to the canonical npm script
exec npm --prefix "$(pwd)/desktop" run dev:electron
