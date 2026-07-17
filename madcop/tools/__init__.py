"""L7 — Tool registry for agent tool use."""

from ..memory import MemoryStore
from ..llm import ToolCall
from .registry import (
    EchoTool,
    FunctionTool,
    GetTimeTool,
    Tool,
    ToolRegistry,
    ToolResult,
)
from .sandbox import BashTool, SandboxResult, SubprocessSandbox
from .deferred import DeferredToolCatalog, ToolEntry
from .mcp import (
    MCP_PROTOCOL_VERSION,
    MCPClient,
    MCPClientManager,
    MCPError,
    MCPTimeoutError,
)
from .permissions import (
    ActionLevel,
    PermissionManager,
    Permission,
    level_for_action,
    level_for_computer_action,
)
from .computer import ComputerUseTool, ActionLogEntry
# v1.6.0 — web + files + cron
from .web import WebSearchTool, WebFetchTool
from .files import ReadFileTool, WriteFileTool, EditFileTool, WriteXlsxTool
from .cron import CronJob, CronStore, CronScheduler, parse_cron, should_run
# v1.9.0 — docker + eventbus
from .docker_sandbox import DockerSandbox, DockerConfig, DEFAULT_IMAGE as DEFAULT_DOCKER_IMAGE
from .eventbus import (
    Event,
    EventBus,
    WebhookSub,
    EventCallback,
    get_default_bus,
    emit,
)
# v2.1.0 — weather tool for chat
from .weather import WeatherTool
from .clarify import ClarifyTool


def default_registry(store: MemoryStore | None = None, workspace_dir: str | None = None) -> ToolRegistry:
    """Build a ToolRegistry pre-loaded with the built-in chat tools.

    If `store` is provided, the LLM-managed memory tools (store/recall/forget)
    are also registered so the agent can write to its own long-term memory.
    """
    reg = ToolRegistry()
    reg.register(EchoTool())
    reg.register(GetTimeTool())
    reg.register(WebSearchTool())
    reg.register(WebFetchTool())
    reg.register(WeatherTool())
    reg.register(ClarifyTool())  # v2.6.3.3 — ask_user for clarifying questions
    import os as _os
    from pathlib import Path as _P
    _user_home = str(_P.home())
    # Determine write directories: prefer the user-selected workspace
    # (so the agent can drop files where the user is working) over the
    # server's cwd. Fall back to cwd + user home if no workspace is
    # selected yet. Callers (especially the chat endpoint) should pass
    # `workspace_dir` so the agent's tools honor the user's pick.
    _write_dirs: list[str] = []
    if workspace_dir:
        _write_dirs.append(workspace_dir)
    _preview_dir = str(_P.home() / ".madcop" / "preview")
    _write_dirs.append(_preview_dir)
    _write_dirs.extend([_os.getcwd(), _user_home])
    _read_dirs: list[str] = [_user_home, _os.getcwd(), _preview_dir]
    if workspace_dir:
        _read_dirs.insert(0, workspace_dir)
    reg.register(ReadFileTool(allowed_dirs=_read_dirs))   # v2.7.0 — include active workspace
    reg.register(WriteFileTool(allowed_dirs=_write_dirs))  # v3.0 — write to user's workspace
    reg.register(EditFileTool(allowed_dirs=_write_dirs))   # v3.0 — edit in user's workspace
    reg.register(WriteXlsxTool(allowed_dirs=_write_dirs))  # v3.0 — generate xlsx output
    if store is not None:
        from .memory import default_memory_tools
        for tool in default_memory_tools(store):
            reg.register(tool)
    return reg


__all__ = [
    "EchoTool",
    "FunctionTool",
    "GetTimeTool",
    "Tool",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
    "BashTool",
    "SandboxResult",
    "SubprocessSandbox",
    "DeferredToolCatalog",
    "ToolEntry",
    "MCPClient",
    "MCPClientManager",
    "MCPError",
    "MCPTimeoutError",
    "MCP_PROTOCOL_VERSION",
    # v1.5.0
    "ActionLevel",
    "ActionLogEntry",
    "ComputerUseTool",
    "Permission",
    "PermissionManager",
    "level_for_action",
    "level_for_computer_action",
    # v1.6.0
    "WebSearchTool",
    "WebFetchTool",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "WriteXlsxTool",
    "CronJob",
    "CronStore",
    "CronScheduler",
    "parse_cron",
    "should_run",
    # v1.9.0
    "DockerSandbox",
    "DockerConfig",
    "DEFAULT_DOCKER_IMAGE",
    "Event",
    "EventBus",
    "WebhookSub",
    "EventCallback",
    "get_default_bus",
    "emit",
    # v2.1.0
    "WeatherTool",
    # v2.6.3.3
    "ClarifyTool",
    "default_registry",
]
