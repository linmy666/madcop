"""Entry point: python3 -m madcop.server"""
import os
import uvicorn

# Auto-detect visitproject if it exists at the default location.
# This makes web_search work out-of-the-box when visitproject is
# installed locally, without requiring manual env var setup.
_vp_default = os.path.expanduser("~/ZCodeProject/visitproject/dist/index.js")
if os.path.exists(_vp_default) and not os.environ.get("VISITPROJECT_BIN"):
    os.environ["VISITPROJECT_BIN"] = _vp_default
if not os.environ.get("VISITPROJECT_SEARXNG_URL"):
    # Check if SearXNG is running locally
    os.environ.setdefault("VISITPROJECT_SEARXNG_URL", "http://localhost:8080")
os.environ.setdefault("VISITPROJECT_DEPTH", "quick")

if __name__ == "__main__":
    uvicorn.run(
        "madcop.server.app:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_level="info",
    )
