"""Entry point: python3 -m madcop.server"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "madcop.server.app:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_level="info",
    )
