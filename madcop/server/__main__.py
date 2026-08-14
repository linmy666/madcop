"""Entry point: python3 -m madcop.server"""
import os
import socket
import uvicorn

# Auto-detect visitproject if it exists at the default location.
# This makes web_search work out-of-the-box when visitproject is
# installed locally, without requiring manual env var setup.
_vp_default = os.path.expanduser("~/ZCodeProject/visitproject/dist/index.js")
if os.path.exists(_vp_default) and not os.environ.get("VISITPROJECT_BIN"):
    os.environ["VISITPROJECT_BIN"] = _vp_default

# BUG-FIX: only set SEARXNG_URL if SearXNG is actually listening on
# localhost:8080. Previously this was set unconditionally, so every
# web_search call wasted 10s on a connection-refused timeout before
# falling through to Bing. A 200ms port probe is far cheaper than the
# 10s HTTP timeout.
def _port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

if not os.environ.get("VISITPROJECT_SEARXNG_URL") and _port_open("localhost", 8080):
    os.environ["VISITPROJECT_SEARXNG_URL"] = "http://localhost:8080"
os.environ.setdefault("VISITPROJECT_DEPTH", "quick")

if __name__ == "__main__":
    uvicorn.run(
        "madcop.server.app:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_level="info",
    )
