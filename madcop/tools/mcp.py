"""v1.2.0 — MCP (Model Context Protocol) client, stdio transport only.

The Model Context Protocol is an emerging standard (Nov 2024, now
backed by Anthropic + the broader agent ecosystem) for connecting
LLM agents to external tools and data sources. Servers expose a
list of tools via JSON-RPC over stdio, HTTP/SSE, or Streamable HTTP.
We implement the stdio transport — the simplest and most common
for local tools.

This module is the CLIENT side (we connect to MCP servers). The
PROTOCOL is JSON-RPC 2.0 over a line-delimited JSON stream:

  client → server:  {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
  server → client:  {"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}}

We support the three methods we actually need:
1. `initialize`     — handshake (protocol version, capabilities)
2. `tools/list`     — get the server's tool list
3. `tools/call`     — invoke a tool by name

For higher-level integration:
- `MCPClient.list_tools()` returns Python `Tool` objects you can
  register in a `ToolRegistry`
- `MCPClient.call_tool(name, args)` invokes a tool

Qian invariants:
- **稳定性**: timeout on every read/write; process killed on close
- **可控性**: every JSON-RPC message is logged at DEBUG
- **早纠偏**: process crash → `MCPError` raised; caller decides

What this module does NOT do:
- HTTP/SSE transports (use `mcp` Python SDK if you need them)
- Server mode (this is CLIENT only)
- Authentication (stdio is local-only; no auth needed)
- Resource / Prompt methods (we only need tools)
"""
from __future__ import annotations

import json
import logging
import select
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import FunctionTool, Tool

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class MCPError(Exception):
    """Raised when an MCP server returns an error or the wire breaks."""
    def __init__(self, code: int | None, message: str, *, data: Any = None):
        super().__init__(f"MCP error {code}: {message}" if code is not None else f"MCP error: {message}")
        self.code = code
        self.message = message
        self.data = data


class MCPTimeoutError(MCPError):
    """Raised when an MCP call exceeds the timeout."""
    def __init__(self, timeout_s: float):
        super().__init__(None, f"MCP call timed out after {timeout_s}s")
        self.timeout_s = timeout_s


# --------------------------------------------------------------------------- #
# JSON-RPC message types
# --------------------------------------------------------------------------- #


@dataclass
class MCPResponse:
    """A parsed JSON-RPC response from the server."""
    id: int
    result: Any = None
    error: dict | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


# --------------------------------------------------------------------------- #
# MCPClient
# --------------------------------------------------------------------------- #


# Default MCP protocol version (as of 2024-11-25 spec)
MCP_PROTOCOL_VERSION = "2024-11-25"
CLIENT_NAME = "madcop"
CLIENT_VERSION = "1.2.0"


class MCPClient:
    """A client for an MCP server speaking JSON-RPC over stdio.

    Usage:
        client = MCPClient(command=["python", "my_mcp_server.py"])
        client.connect()
        try:
            tools = client.list_tools()
            for tool in tools:
                registry.register(tool)
        finally:
            client.close()
    """

    def __init__(
        self,
        command: list[str],
        *,
        timeout_s: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = list(command)
        self._timeout_s = timeout_s
        self._env = env
        self._proc: subprocess.Popen | None = None
        self._next_id = 0
        # Cache the handshake result so we don't re-init on every call
        self._initialized = False
        self._server_info: dict[str, Any] = {}

    # ----- lifecycle ----------------------------------------------------

    def connect(self) -> None:
        """Spawn the subprocess and perform the MCP handshake."""
        if self._proc is not None:
            return
        logger.info("[mcp] starting: %s", self._command)
        try:
            self._proc = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env,
                text=True,
                bufsize=1,             # line-buffered
            )
        except FileNotFoundError as e:
            raise MCPError(None, f"failed to start MCP server {self._command!r}: {e}") from e
        self._handshake()

    def close(self) -> None:
        """Kill the subprocess and clean up."""
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        except Exception as e:  # noqa: BLE001
            logger.warning("[mcp] close error: %s", e)
        finally:
            self._proc = None
            self._initialized = False

    def __enter__(self) -> "MCPClient":
        self.connect()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ----- low-level JSON-RPC ------------------------------------------

    def _send(self, method: str, params: dict | None = None) -> MCPResponse:
        """Send a JSON-RPC request and read the response."""
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise MCPError(None, "MCP client not connected (call connect() first)")
        msg_id = self._next_id
        self._next_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params
        line = json.dumps(request, ensure_ascii=False) + "\n"
        logger.debug("[mcp] → %s", line.strip())
        try:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        except BrokenPipeError as e:
            raise MCPError(None, f"MCP server closed the connection: {e}") from e

        # Read ONE response line. If multiple responses come (e.g.
        # server-side notifications interleaved), we ignore them
        # because the spec says notifications don't have an `id`.
        # We read by line and parse each one until we find a match.
        # Use select() so the timeout actually fires while the
        # subprocess is blocked.
        deadline = time.monotonic() + self._timeout_s
        while True:
            if time.monotonic() > deadline:
                raise MCPTimeoutError(self._timeout_s)
            # Check process liveness first
            if self._proc.poll() is not None:
                # Process exited — grab any stderr
                _, stderr = self._proc.communicate()
                raise MCPError(None, f"MCP server died (rc={self._proc.returncode}): {stderr}")
            # Wait up to 100ms for stdout to be readable
            ready, _, _ = select.select([self._proc.stdout], [], [], 0.1)
            if not ready:
                continue
            line = self._proc.stdout.readline()
            if not line:
                # EOF — process likely died
                if self._proc.poll() is not None:
                    _, stderr = self._proc.communicate()
                    raise MCPError(None, f"MCP server died (rc={self._proc.returncode}): {stderr}")
                time.sleep(0.01)
                continue
            line = line.strip()
            if not line:
                continue
            logger.debug("[mcp] ← %s", line)
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("[mcp] malformed JSON: %s", e)
                continue
            # Skip notifications (no `id` field)
            if "id" not in msg:
                logger.debug("[mcp] notification: %s", msg)
                continue
            if msg.get("id") != msg_id:
                logger.debug("[mcp] out-of-order response: %s", msg)
                continue
            break

        if "error" in msg:
            err = msg["error"] or {}
            raise MCPError(
                err.get("code"),
                err.get("message", "unknown error"),
                data=err.get("data"),
            )
        return MCPResponse(id=msg_id, result=msg.get("result"))

    # ----- handshake ----------------------------------------------------

    def _handshake(self) -> None:
        """Perform the MCP `initialize` handshake. Idempotent."""
        if self._initialized:
            return
        resp = self._send("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
        })
        self._server_info = resp.result or {}
        logger.info(
            "[mcp] handshake OK — server: %s v%s, protocol %s",
            self._server_info.get("serverInfo", {}).get("name", "?"),
            self._server_info.get("serverInfo", {}).get("version", "?"),
            self._server_info.get("protocolVersion", "?"),
        )
        # Send the `initialized` notification (no response expected)
        if self._proc and self._proc.stdin:
            note = json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }) + "\n"
            try:
                self._proc.stdin.write(note)
                self._proc.stdin.flush()
            except BrokenPipeError:
                pass
        self._initialized = True

    # ----- high-level methods -------------------------------------------

    def list_tools(self) -> list[Tool]:
        """Fetch the server's tool list and convert to madcop Tool objects.

        Each tool is wrapped as a `FunctionTool` (the simpler Tool
        subclass — argv is the `arguments` dict from the tool call).
        The wrapper function issues the `tools/call` JSON-RPC when
        invoked.
        """
        if not self._initialized:
            self._handshake()
        resp = self._send("tools/list", {})
        raw_tools = (resp.result or {}).get("tools", [])
        wrapped: list[Tool] = []
        for raw in raw_tools:
            name = raw.get("name")
            if not name:
                continue
            wrapped.append(self._wrap_tool(name, raw))
        logger.info("[mcp] list_tools: %d tool(s)", len(wrapped))
        return wrapped

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Invoke a tool by name. Returns the result content.

        The result is a list of content blocks (text/image/etc).
        For text-only tools, callers can just take the first block.
        """
        if not self._initialized:
            self._handshake()
        resp = self._send("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        return resp.result

    # ----- tool wrapping ------------------------------------------------

    def _wrap_tool(self, name: str, raw: dict[str, Any]) -> Tool:
        """Convert a JSON-RPC tool descriptor into a madcop Tool."""
        description = raw.get("description", "")
        schema = raw.get("inputSchema", {"type": "object", "properties": {}})

        def fn(**kwargs: Any) -> Any:
            return self.call_tool(name, kwargs)

        return FunctionTool(
            name=name,
            description=description,
            fn=fn,
            parameters_schema=schema,
        )


# --------------------------------------------------------------------------- #
# Convenience: client manager
# --------------------------------------------------------------------------- #


class MCPClientManager:
    """Manages multiple MCP clients and aggregates their tools.

    Usage:
        mgr = MCPClientManager()
        mgr.add("github", ["python", "github_mcp.py"])
        mgr.add("filesystem", ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
        mgr.connect_all()
        try:
            for tool in mgr.all_tools():
                registry.register(tool)
        finally:
            mgr.close_all()
    """

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}

    def add(self, name: str, command: list[str], **kwargs: Any) -> None:
        self._clients[name] = MCPClient(command, **kwargs)

    def connect_all(self) -> None:
        for name, client in self._clients.items():
            try:
                client.connect()
            except MCPError as e:
                logger.error("[mcp] failed to connect %s: %s", name, e)

    def close_all(self) -> None:
        for client in self._clients.values():
            client.close()

    def all_tools(self) -> list[Tool]:
        out: list[Tool] = []
        for client in self._clients.values():
            try:
                out.extend(client.list_tools())
            except MCPError as e:
                logger.warning("[mcp] list_tools failed: %s", e)
        return out


__all__ = [
    "MCPClient",
    "MCPClientManager",
    "MCPError",
    "MCPTimeoutError",
    "MCP_PROTOCOL_VERSION",
]
