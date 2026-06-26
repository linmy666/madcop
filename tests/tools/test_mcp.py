"""v1.2.0 — Tests for the MCP stdio client.

Strategy: spawn a tiny Python script as a fake MCP server, then
test against it. This is more realistic than mocking subprocess.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest

from madcop.tools import MCPClient, MCPClientManager, MCPError, MCPTimeoutError


# ---------------------------------------------------------------------------
# Fake MCP server (a Python script that speaks the protocol on stdio)
# ---------------------------------------------------------------------------


FAKE_MCP_SCRIPT = textwrap.dedent('''\
    #!/usr/bin/env python3
    """A minimal MCP server that exposes two tools: add, echo."""
    import json
    import sys

    def read_message():
        line = sys.stdin.readline()
        if not line:
            return None
        return json.loads(line)

    def write_message(msg):
        sys.stdout.write(json.dumps(msg) + "\\n")
        sys.stdout.flush()

    initialized = False
    while True:
        msg = read_message()
        if msg is None:
            break
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-25",
                    "serverInfo": {"name": "fake-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            })
        elif method == "notifications/initialized":
            initialized = True
            # No response for notifications
        elif method == "tools/list":
            if not initialized:
                write_message({"jsonrpc": "2.0", "id": msg_id,
                                "error": {"code": -32002, "message": "not initialized"}})
                continue
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "add",
                            "description": "Add two numbers",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "a": {"type": "number"},
                                    "b": {"type": "number"},
                                },
                                "required": ["a", "b"],
                            },
                        },
                        {
                            "name": "echo",
                            "description": "Echoes a string back",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                            },
                        },
                    ]
                },
            })
        elif method == "tools/call":
            name = msg["params"]["name"]
            args = msg["params"].get("arguments", {})
            if name == "add":
                result = args.get("a", 0) + args.get("b", 0)
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": [{"type": "text", "text": str(result)}]},
                })
            elif name == "echo":
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": [{"type": "text", "text": args.get("text", "")}]},
                })
            elif name == "slow":
                import time
                time.sleep(10)
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": []},
                })
            else:
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"unknown tool: {name}"},
                })
        else:
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
            })
''')


@pytest.fixture
def fake_mcp_server(tmp_path: Path) -> str:
    """Write the fake MCP server to a temp file and return its path."""
    p = tmp_path / "fake_mcp_server.py"
    p.write_text(FAKE_MCP_SCRIPT)
    p.chmod(0o755)
    return str(p)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_mcp_client_connect_and_close(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    client.connect()
    assert client._initialized
    client.close()
    assert client._proc is None


def test_mcp_client_context_manager(fake_mcp_server: str):
    with MCPClient([sys.executable, fake_mcp_server]) as client:
        assert client._initialized
    assert client._proc is None


def test_mcp_client_idempotent_connect(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    client.connect()
    client.connect()  # second call is a no-op
    assert client._initialized
    client.close()


def test_mcp_client_fails_to_start_on_bad_command():
    client = MCPClient(["definitely_not_a_real_command_xyz123"])
    with pytest.raises(MCPError, match="failed to start"):
        client.connect()


# ---------------------------------------------------------------------------
# Handshake
# ---------------------------------------------------------------------------


def test_mcp_handshake_records_server_info(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    client.connect()
    assert client._server_info.get("serverInfo", {}).get("name") == "fake-mcp"
    assert client._server_info.get("protocolVersion") == "2024-11-25"
    client.close()


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------


def test_mcp_list_tools_returns_tool_objects(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    with client:
        tools = client.list_tools()
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"add", "echo"}


def test_mcp_list_tools_schemas_have_required_fields(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    with client:
        tools = {t.name: t for t in client.list_tools()}
    add = tools["add"]
    assert "a" in add.parameters_schema["required"]
    assert "b" in add.parameters_schema["required"]
    assert add.parameters_schema["properties"]["a"]["type"] == "number"


def test_mcp_list_tools_can_be_registered_in_registry(fake_mcp_server: str):
    from madcop.tools import ToolRegistry
    client = MCPClient([sys.executable, fake_mcp_server])
    with client:
        tools = client.list_tools()
    registry = ToolRegistry()
    for t in tools:
        registry.register(t)
    assert "add" in registry
    assert "echo" in registry


# ---------------------------------------------------------------------------
# tools/call
# ---------------------------------------------------------------------------


def test_mcp_call_tool_add(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    with client:
        result = client.call_tool("add", {"a": 3, "b": 4})
    # Result format: {"content": [{"type": "text", "text": "7"}]}
    assert result["content"][0]["text"] == "7"


def test_mcp_call_tool_echo(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    with client:
        result = client.call_tool("echo", {"text": "hello"})
    assert result["content"][0]["text"] == "hello"


def test_mcp_call_unknown_tool_raises(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server])
    with client:
        with pytest.raises(MCPError, match="unknown tool"):
            client.call_tool("nope", {})


def test_mcp_wrapped_tool_can_be_called_directly(fake_mcp_server: str):
    """The FunctionTool wrapper should call the MCP server when invoked."""
    from madcop.llm import ToolCall
    client = MCPClient([sys.executable, fake_mcp_server])
    with client:
        tools = {t.name: t for t in client.list_tools()}
        result = tools["add"](a=10, b=20)
    assert result["content"][0]["text"] == "30"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_mcp_call_times_out_on_slow_server(fake_mcp_server: str):
    client = MCPClient([sys.executable, fake_mcp_server], timeout_s=0.5)
    with client:
        with pytest.raises(MCPTimeoutError):
            client.call_tool("slow", {})


# ---------------------------------------------------------------------------
# MCPClientManager
# ---------------------------------------------------------------------------


def test_mcp_client_manager_aggregates_tools(fake_mcp_server: str):
    mgr = MCPClientManager()
    mgr.add("fake1", [sys.executable, fake_mcp_server])
    mgr.add("fake2", [sys.executable, fake_mcp_server])
    mgr.connect_all()
    try:
        tools = mgr.all_tools()
        # 2 tools from each server = 4 total
        assert len(tools) == 4
    finally:
        mgr.close_all()


def test_mcp_client_manager_close_all_is_idempotent(fake_mcp_server: str):
    mgr = MCPClientManager()
    mgr.add("fake", [sys.executable, fake_mcp_server])
    mgr.connect_all()
    mgr.close_all()
    mgr.close_all()  # second call should not raise
