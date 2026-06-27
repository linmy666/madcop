"""L7 — Tool registry for agent tool use."""

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
from .files import ReadFileTool, WriteFileTool, EditFileTool
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


def default_registry() -> ToolRegistry:
    """Build a ToolRegistry pre-loaded with the built-in chat tools."""
    reg = ToolRegistry()
    reg.register(EchoTool())
    reg.register(GetTimeTool())
    reg.register(WebSearchTool())
    reg.register(WebFetchTool())
    reg.register(WeatherTool())
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
    "default_registry",
]
