"""WS limits, MCP import, provider capabilities."""
from __future__ import annotations

from fastapi.testclient import TestClient

from madcop.server.app import create_app


def test_provider_capabilities_endpoint():
    client = TestClient(create_app())
    r = client.get("/api/providers/capabilities")
    assert r.status_code == 200
    data = r.json()
    assert "capabilities" in data
    caps = data["capabilities"]
    assert "supports_tools" in caps
    assert "context_window" in caps


def test_mcp_import_claude_desktop_shape(tmp_path, monkeypatch):
    import madcop.server.madcop_compat as compat
    mcp_file = tmp_path / "mcp.json"
    monkeypatch.setattr(compat, "_MCP_FILE", mcp_file)
    # reset load/save to use temp
    def _load():
        if not mcp_file.exists():
            return []
        import json
        return json.loads(mcp_file.read_text())
    def _save(servers):
        import json
        mcp_file.write_text(json.dumps(servers))
    monkeypatch.setattr(compat, "_load_mcp_servers", _load)
    monkeypatch.setattr(compat, "_save_mcp_servers", _save)

    client = TestClient(create_app())
    payload = {
        "config": {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                }
            }
        },
        "scope": "user",
    }
    r = client.post("/api/mcp/import", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "filesystem" in data.get("imported", [])

    # second import skips
    r2 = client.post("/api/mcp/import", json=payload)
    assert r2.json().get("skipped") == ["filesystem"]


def test_ws_rejects_oversized_user_message():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/test-ws-limits") as ws:
        hello = ws.receive_json()
        assert hello.get("type") == "connected"
        huge = "x" * 600_000
        ws.send_json({"type": "user_message", "content": huge})
        msg = ws.receive_json()
        assert msg.get("type") == "error"
        assert "too large" in (msg.get("error") or "")
