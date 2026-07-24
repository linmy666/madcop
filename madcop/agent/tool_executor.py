"""
v4.0 — Unified Tool Executor + Plugin Registry.

All tool calls go through one path:
  validate → HITL check → execute (with timeout) → format result

New tools register as plugins — handler + schema + danger_level.
No need to touch engine code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from madcop.tools.safety import validate_tool_input, danger_level

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30


# ─── Tool Result ─────────────────────────────────────────────────────────────


@dataclass
class ToolResult:
    """Uniform result from any tool execution."""

    content: str = ""
    error: str = ""
    is_error: bool = False
    is_validation_error: bool = False
    needs_confirmation: bool = False
    elapsed_ms: int = 0

    def to_observation(self) -> str:
        """Format as Observation text for the ReAct loop."""
        if self.is_error:
            return f"Error: {self.error}"
        return self.content or "(empty result)"


# ─── Plugin Definition ───────────────────────────────────────────────────────


@dataclass
class ToolPlugin:
    """A registered tool. Handler + schema + metadata."""

    name: str
    handler: Callable[..., Any]  # (**kwargs) → str | list | dict
    schema: dict  # OpenAI function schema
    danger: str = "safe"  # safe | mutating | destructive
    timeout_s: int = DEFAULT_TIMEOUT_S


class PluginRegistry:
    """Central registry for all tool plugins."""

    def __init__(self):
        self._plugins: dict[str, ToolPlugin] = {}

    def register(self, plugin: ToolPlugin) -> None:
        self._plugins[plugin.name] = plugin
        logger.debug("registered tool plugin: %s", plugin.name)

    def get(self, name: str) -> ToolPlugin | None:
        return self._plugins.get(name)

    def get_all_schemas(self) -> list[dict]:
        """Return OpenAI function schemas for all registered tools."""
        return [p.schema for p in self._plugins.values()]

    def names(self) -> list[str]:
        return list(self._plugins.keys())


# ─── Unified Executor ────────────────────────────────────────────────────────


class ToolExecutor:
    """Execute a tool call through the unified pipeline.

    Steps:
    1. Pydantic validation (safety guardrail)
    2. HITL check (destructive tools need confirmation)
    3. Execute with timeout
    4. Format result (success or error → observation text)
    """

    def __init__(self, registry: PluginRegistry):
        self._registry = registry

    def execute(
        self,
        tool_name: str,
        raw_input: str | dict,
        work_dir: str | None = None,
    ) -> ToolResult:
        """Execute synchronously (called from ReAct engine thread)."""
        start = time.time()

        # Parse input
        if isinstance(raw_input, str):
            try:
                args = json.loads(raw_input) if raw_input.strip() else {}
            except json.JSONDecodeError:
                args = {"path": raw_input.strip(), "query": raw_input.strip()}
        else:
            args = raw_input

        # 1. Pydantic validation
        ok, err, _validated = validate_tool_input(tool_name, args)
        if not ok:
            return ToolResult(
                error=f"输入校验失败: {err}",
                is_error=True,
                is_validation_error=True,
                elapsed_ms=int((time.time() - start) * 1000),
            )

        # 2. HITL check
        level = danger_level(tool_name)
        if level == "destructive":
            return ToolResult(
                error=(
                    f"工具 {tool_name!r} 是高危操作，需要用户确认。"
                    "请改用 ask_user 工具向用户确认。"
                ),
                is_error=True,
                needs_confirmation=True,
                elapsed_ms=int((time.time() - start) * 1000),
            )

        # 3. Get plugin handler
        plugin = self._registry.get(tool_name)
        if not plugin:
            available = ", ".join(self._registry.names())
            return ToolResult(
                error=f"工具 '{tool_name}' 不存在。可用: {available}",
                is_error=True,
                elapsed_ms=int((time.time() - start) * 1000),
            )

        # Add work_dir for file tools
        if work_dir:
            args.setdefault("work_dir", work_dir)
            args.setdefault("cwd", work_dir)

        # 4. Execute with timeout
        try:
            result = plugin.handler(**args)
            elapsed = int((time.time() - start) * 1000)

            # Normalize result to string
            if isinstance(result, str):
                content = result
            elif isinstance(result, (list, dict)):
                content = json.dumps(result, ensure_ascii=False, default=str)[:4000]
            else:
                content = str(result)[:4000]

            # Check for embedded errors
            if isinstance(result, dict) and result.get("error"):
                return ToolResult(
                    error=str(result["error"]),
                    is_error=True,
                    elapsed_ms=elapsed,
                )
            if isinstance(result, list) and result and isinstance(result[0], dict) and result[0].get("error"):
                return ToolResult(
                    error=str(result[0]["error"]),
                    is_error=True,
                    elapsed_ms=elapsed,
                )

            return ToolResult(content=content, elapsed_ms=elapsed)

        except TimeoutError:
            return ToolResult(
                error=f"工具 {tool_name} 超时（{plugin.timeout_s}s）",
                is_error=True,
                elapsed_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            logger.warning("tool %s failed: %s", tool_name, e)
            return ToolResult(
                error=f"工具执行失败: {e}",
                is_error=True,
                elapsed_ms=int((time.time() - start) * 1000),
            )


# ─── Default Registry Builder ────────────────────────────────────────────────


def build_default_registry(
    workspace_dir: str | None = None,
    store: Any = None,
) -> tuple[PluginRegistry, ToolExecutor]:
    """Build a registry with all built-in tools and return
    (registry, executor).

    This replaces the old default_registry() + openai_schemas() pattern.
    """
    from madcop.tools import (
        EchoTool, GetTimeTool, GetCurrentModelTool,
        WebSearchTool, WebFetchTool, WeatherTool, ClarifyTool,
        ReadFileTool, WriteFileTool, EditFileTool, WriteXlsxTool,
    )
    from madcop.tools.market import MarketQuoteTool, MarketHistoryTool
    from madcop.tools.paper import PaperAccountTool, PaperOrderTool, PaperResetTool
    import os
    from pathlib import Path

    reg = PluginRegistry()

    def _reg(tool_cls, *args, **kwargs):
        """Register a tool class instance."""
        tool = tool_cls(*args, **kwargs)
        reg.register(ToolPlugin(
            name=tool.name,
            handler=tool,
            schema=tool.to_openai_schema(),
            danger=danger_level(tool.name),
        ))

    # Core tools
    _reg(EchoTool)
    _reg(GetTimeTool)
    _reg(GetCurrentModelTool)
    _reg(WebSearchTool)
    _reg(WebFetchTool)
    _reg(WeatherTool)
    _reg(ClarifyTool)

    # Market / paper tools
    _reg(MarketQuoteTool)
    _reg(MarketHistoryTool)
    _reg(PaperAccountTool)
    _reg(PaperOrderTool)
    _reg(PaperResetTool)

    # File tools with workspace allowlist
    _home = str(Path.home())
    _write_dirs = [workspace_dir] if workspace_dir else []
    _write_dirs.extend([
        str(Path.home() / ".madcop" / "preview"),
        os.getcwd(), _home,
        str(Path.home() / "Downloads"),
        str(Path.home() / "Desktop"),
        "/tmp",
    ])
    _read_dirs = ([workspace_dir] if workspace_dir else []) + _write_dirs

    _reg(ReadFileTool, allowed_dirs=_read_dirs)
    _reg(WriteFileTool, allowed_dirs=_write_dirs)
    _reg(EditFileTool, allowed_dirs=_write_dirs)
    _reg(WriteXlsxTool, allowed_dirs=_write_dirs)

    # Memory tools (optional)
    if store is not None:
        from madcop.tools.memory import default_memory_tools
        for tool in default_memory_tools(store):
            reg.register(ToolPlugin(
                name=tool.name,
                handler=tool,
                schema=tool.to_openai_schema(),
                danger=danger_level(tool.name),
            ))

    executor = ToolExecutor(reg)
    return reg, executor


__all__ = [
    "ToolResult",
    "ToolPlugin",
    "PluginRegistry",
    "ToolExecutor",
    "build_default_registry",
]
