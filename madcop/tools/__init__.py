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
from .clarify import ClarifyTool


def default_registry(store: MemoryStore | None = None) -> ToolRegistry:
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
