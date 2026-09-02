"""
v4.0 — Unified Tool Executor + Plugin Registry.

All tool calls go through one path:
  validate → HITL check → execute (with timeout) → format result

The result is a structured ``ToolResult`` that the engine can inspect
for ``is_validation_error`` / ``is_timeout`` / ``needs_confirmation``
flags. The ``to_observation()`` text carries an explicit tag prefix
(e.g. ``[validation_error]``) so the LLM can branch on the failure
mode in a closed loop.

Plugins register a handler + schema + danger_level. New tools are
one-line additions; engine code never changes.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from madcop.tools.safety import validate_tool_input, danger_level

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30

# Shared thread pool for sync handlers. Sized modestly so a misbehaving
# tool can't tie up all threads; the executor caps concurrent tool
# calls and prevents thread leaks across many invocations.
_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="tool-exec"
)


# ─── Tool Result ─────────────────────────────────────────────────────────────


@dataclass
class ToolResult:
    """Uniform result from any tool execution."""

    content: str = ""
    error: str = ""
    is_error: bool = False
    is_validation_error: bool = False
    is_timeout: bool = False
    needs_confirmation: bool = False
    elapsed_ms: int = 0
    tool_name: str = ""

    def to_observation(self) -> str:
        """Format as Observation text for the ReAct loop.

        Each failure mode gets an explicit tag prefix so the LLM can
        branch on the error category in its next reasoning step:
          - ``[validation_error]`` — input schema rejected; LLM should
            fix its arguments.
          - ``[needs_confirmation]`` — destructive tool; LLM should
            switch to ``ask_user``.
          - ``[timeout]`` — tool ran past 30s; LLM should retry or pick
            another tool.
          - ``[error]`` — any other failure.
        """
        if self.is_validation_error:
            return f"[validation_error] {self.error}\n请修正后重新调用 {self.tool_name}。"
        if self.needs_confirmation:
            return (
                f"[needs_confirmation] {self.error}\n"
                f"请改用 ask_user 向用户确认后再调用 {self.tool_name}。"
            )
        if self.is_timeout:
            return (
                f"[timeout] 工具 {self.tool_name} 在 {self.elapsed_ms}ms 内未完成。"
                f"请重试或选择更快的工具。"
            )
        if self.is_error:
            return f"[error] {self.error}"
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
    # Reactive coeffects (paper §3.2): context keys this tool REQUIRES.
    # The tool is callable only while every key is bound in the session's
    # CoeffectStore (e.g. "mcp:<server>", "approval.dir:<abs>"). Empty
    # set = always satisfied.
    requires: frozenset[str] = frozenset()


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
        """Back-compat: every registered tool, regardless of coeffect
        satisfaction. Most callers should prefer visible_schemas() so the
        model never hallucinates a tool it can't actually run."""
        return [p.schema for p in self._plugins.values()]

    def visible_schemas(
        self, bound_keys: set[str], phase: str = "all",
    ) -> list[dict]:
        """Schemas the LLM is allowed to see in this turn.

        Paper §3.2 implementation: a tool's specification is gated by its
        coeffect ``requires``. Safe / read-only tools are always visible
        (they don't change the world, so missing context doesn't matter).
        Mutating / bash tools are visible only in the EXECUTE phase of an
        approved plan — exposing them upfront tempts the model to call
        them before the user has committed to the work.

        ``phase``: ``"plan"`` (only safe + reads) | ``"all"`` (any satisfied)
        | ``"auto"`` (safe in plan, all when in execute).
        """
        out: list[dict] = []
        for p in self._plugins.values():
            if p.requires and not (p.requires <= bound_keys):
                continue
            if phase == "plan" and danger_level(p.name) != "safe":
                continue
            if phase == "all" or danger_level(p.name) == "safe":
                out.append(p.schema)
            else:  # "auto"
                out.append(p.schema)
        return out

    def satisfied_schemas(self, bound_keys: set[str]) -> list[dict]:
        return self.visible_schemas(bound_keys, phase="all")

    def unsatisfied_reason(self, name: str, bound_keys: set[str]) -> str:
        p = self._plugins.get(name)
        if p is None:
            return ""
        missing = sorted(p.requires - bound_keys)
        return ", ".join(missing) if missing else ""

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
        raw_input: Any,
        work_dir: str | None = None,
        pre_approved: bool = False,
        effect_key: str | None = None,
    ) -> ToolResult:
        """Execute synchronously (called from ReAct engine thread).

        Pipeline:
          1. Pydantic validation
          2. HITL check
          3. Execute with hard timeout (DEFAULT_TIMEOUT_S)
          4. Format result (success or one of: validation / confirmation /
             timeout / generic error)

        ``effect_key``: when provided (the tool_use_id), mutating file
        tools capture a pre-image snapshot and register an inverse with
        the EffectStore under this key BEFORE execution — enabling
        revertible effects (paper §3.1). bash/run_command are recorded
        as irreversible markers so revert reports stay honest.

        The handler may be sync or async. For sync handlers we wrap in
        ``asyncio.run`` with a 30s ``wait_for`` so a runaway tool cannot
        stall the ReAct loop forever.
        """
        start = time.time()
        tool_name = str(tool_name or "").strip()

        def _elapsed_ms() -> int:
            return int((time.time() - start) * 1000)

        # Parse input
        if isinstance(raw_input, str):
            try:
                args = json.loads(raw_input) if raw_input.strip() else {}
            except json.JSONDecodeError:
                args = {"path": raw_input.strip(), "query": raw_input.strip()}
        else:
            args = raw_input or {}

        # 1. Pydantic validation
        ok, err, _validated = validate_tool_input(tool_name, args)
        if not ok:
            return ToolResult(
                tool_name=tool_name,
                error=f"输入校验失败: {err}",
                is_error=True,
                is_validation_error=True,
                elapsed_ms=_elapsed_ms(),
            )

        # 2. HITL check — the global DANGER_LEVELS table is the safety
        #    policy source of truth. Plugin.danger is the *default*
        #    override, used only when the tool isn't in the global
        #    table (e.g. plugins registered at runtime). This way
        #    ToolPlugin.danger actually has an effect for custom tools,
        #    while built-in tools still get the curated safety policy.
        #
        #    ``pre_approved`` is set when the calling engine ALREADY ran
        #    a HITL gate (e.g. the ReAct engine's confirm card → user
        #    clicked approve). Without this pass-through the executor
        #    rejected the call again after approval and told the model
        #    to use ask_user — a dead end that blocked every build task.
        plugin = self._registry.get(tool_name)
        plugin_default = plugin.danger if plugin and getattr(plugin, 'danger', None) else None
        level = danger_level(tool_name) or plugin_default or 'safe'
        if level == "destructive" and not pre_approved:
            return ToolResult(
                tool_name=tool_name,
                error=(
                    f"工具 {tool_name!r} 是高危操作，需要用户确认。"
                    "请改用 ask_user 工具向用户确认。"
                ),
                is_error=True,
                needs_confirmation=True,
                elapsed_ms=_elapsed_ms(),
            )

        # 3. Get plugin handler
        plugin = self._registry.get(tool_name)
        if not plugin:
            available = ", ".join(self._registry.names())
            return ToolResult(
                tool_name=tool_name,
                error=f"工具 '{tool_name}' 不存在。可用: {available}",
                is_error=True,
                elapsed_ms=_elapsed_ms(),
            )

        # Add work_dir for file tools
        if work_dir:
            args.setdefault("work_dir", work_dir)
            args.setdefault("cwd", work_dir)

        # 3.5 Revertible effects (paper §3.1): snapshot the pre-state of
        # mutating file tools BEFORE execution and register the inverse
        # under `effect_key`. bash/run_command recorded as irreversible.
        if effect_key:
            try:
                from madcop.harness.effects import capture_file_inverse
                capture_file_inverse(tool_name, args, effect_key)
            except Exception as e:  # noqa: BLE001
                logger.warning("[effects] pre-capture failed for %s: %s",
                               tool_name, e)

        timeout_s = max(1, int(plugin.timeout_s or DEFAULT_TIMEOUT_S))

        # 4. Execute with hard timeout
        try:
            result = self._invoke_with_timeout(plugin.handler, args, timeout_s)
        except _ToolTimeout as e:
            return ToolResult(
                tool_name=tool_name,
                error=f"工具 {tool_name} 超时（{timeout_s}s）",
                is_error=True,
                is_timeout=True,
                elapsed_ms=_elapsed_ms(),
            )
        except Exception as e:
            logger.warning("tool %s failed: %s", tool_name, e)
            return ToolResult(
                tool_name=tool_name,
                error=f"工具执行失败: {e}",
                is_error=True,
                elapsed_ms=_elapsed_ms(),
            )

        elapsed = _elapsed_ms()

        # Normalize result to string
        if isinstance(result, str):
            content = result
        elif isinstance(result, (list, dict)):
            content = json.dumps(result, ensure_ascii=False, default=str)[:4000]
        else:
            content = str(result)[:4000]

        # Check for embedded errors returned by the tool itself
        if isinstance(result, dict) and result.get("error"):
            return ToolResult(
                tool_name=tool_name,
                error=str(result["error"]),
                is_error=True,
                elapsed_ms=elapsed,
            )
        if (
            isinstance(result, list)
            and result
            and isinstance(result[0], dict)
            and result[0].get("error")
        ):
            return ToolResult(
                tool_name=tool_name,
                error=str(result[0]["error"]),
                is_error=True,
                elapsed_ms=elapsed,
            )

        return ToolResult(tool_name=tool_name, content=content, elapsed_ms=elapsed)

    @staticmethod
    def _filter_kwargs(handler: Callable, args: dict) -> dict:
        """Drop kwargs the handler doesn't accept.

        The engine injects work_dir/cwd into every call for file tools;
        handlers with narrower signatures (BashTool took command/cwd/
        timeout_s only) blew up with TypeError before, so the whole bash
        tool was dead on arrival. **kwargs handlers pass through
        untouched.
        """
        try:
            sig = inspect.signature(handler)
        except (ValueError, TypeError):
            return args
        params = sig.parameters
        if any(pp.kind is inspect.Parameter.VAR_KEYWORD for pp in params.values()):
            return args
        supported = {
            k: v for k, v in args.items()
            if k in params and params[k].kind is not inspect.Parameter.VAR_POSITIONAL
        }
        dropped = sorted(set(args) - set(supported))
        if dropped:
            logger.info("tool handler ignoring unsupported kwargs: %s", dropped)
        return supported

    @staticmethod
    def _invoke_with_timeout(handler: Callable, args: dict, timeout_s: int) -> Any:
        """Run a (possibly async) handler with a hard timeout.

        - async coroutine: scheduled on a private loop with
          ``asyncio.wait_for``; cancellation propagates.
        - sync callable: scheduled on a shared ``ThreadPoolExecutor``
          via ``concurrent.futures.wait`` so ``time.sleep`` / blocking
          I/O doesn't block the timeout. We don't use
          ``loop.run_in_executor`` because ``asyncio.run`` waits for
          the executor to drain before returning, which would let a
          stalled worker thread inflate the wall-clock timeout.

        On timeout: raises ``_ToolTimeout``. The worker thread may
        continue running in the background until its blocking call
        returns naturally; that's a leak we accept because Python
        can't preempt arbitrary C calls.
        """
        args = ToolExecutor._filter_kwargs(handler, args)
        if inspect.iscoroutinefunction(handler):
            coro = handler(**args)

            async def _runner():
                return await asyncio.wait_for(coro, timeout=timeout_s)

            try:
                return asyncio.run(_runner())
            except asyncio.TimeoutError as e:
                raise _ToolTimeout(timeout_s) from e

        if callable(handler):
            future = _THREAD_POOL.submit(handler, **ToolExecutor._filter_kwargs(handler, args))
            try:
                return future.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError as e:
                # Mark the future but don't block on it — let it
                # finish in the background. The engine moves on.
                logger.warning(
                    "tool handler exceeded %ss timeout; abandoning wait",
                    timeout_s,
                )
                raise _ToolTimeout(timeout_s) from e

        raise TypeError(f"handler {handler!r} is not callable")


class _ToolTimeout(Exception):
    """Raised by ToolExecutor._invoke_with_timeout on hard timeout."""

    def __init__(self, timeout_s: int):
        super().__init__(f"tool timed out after {timeout_s}s")
        self.timeout_s = timeout_s


# ─── Default Registry Builder ────────────────────────────────────────────────


def build_default_registry(
    workspace_dir: str | None = None,
    store: Any = None,
    bound_keys: set[str] | None = None,
) -> tuple[PluginRegistry, ToolExecutor]:
    """Build a registry with all built-in tools and return
    (registry, executor).

    This replaces the old default_registry() + openai_schemas() pattern.
    """
    from madcop.tools import (
        EchoTool, GetTimeTool, GetCurrentModelTool,
        WebSearchTool, WebFetchTool, WeatherTool, ClarifyTool,
        ReadFileTool, WriteFileTool, EditFileTool, WriteXlsxTool,
        WritePptxTool, ReadOfficeTool,
    )
    from madcop.tools.market import MarketQuoteTool, MarketHistoryTool
    from madcop.tools.paper import PaperAccountTool, PaperOrderTool, PaperResetTool
    import os
    from pathlib import Path

    reg = PluginRegistry()

    def _reg(tool_cls, *args, requires=frozenset(), **kwargs):
        """Register a tool class instance."""
        tool = tool_cls(*args, **kwargs)
        reg.register(ToolPlugin(
            name=tool.name,
            handler=tool,
            schema=tool.to_openai_schema(),
            danger=danger_level(tool.name),
            requires=frozenset(requires),
        ))

    # Core tools
    _reg(EchoTool)
    _reg(GetTimeTool)
    _reg(GetCurrentModelTool)
    _reg(WebSearchTool, requires={'net'})
    _reg(WebFetchTool, requires={'net'})
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
    _reg(WritePptxTool, allowed_dirs=_write_dirs)
    _reg(ReadOfficeTool, allowed_dirs=_read_dirs)

    # Shell tool — the agent desktop finally HAS one. Runs through
    # SubprocessSandbox (cwd allowlist + timeout + output cap); danger
    # level is "destructive" so every call hits the HITL confirm card.
    try:
        from madcop.tools.sandbox import BashTool, SubprocessSandbox
        _sandbox = SubprocessSandbox(allowed_dirs=[Path(d) for d in _write_dirs if d])
        _bash = BashTool(_sandbox)
        reg.register(ToolPlugin(
            name=_bash.name,
            handler=_bash,
            schema=_bash.to_openai_schema(),
            danger=danger_level(_bash.name),
            requires=frozenset({'shell'}),
        ))
    except Exception as e:  # pragma: no cover
        logger.warning("bash tool registration failed: %s", e)

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

    # Phase 4: register browser-use / computer-use plugins.
    # Each one is one line; adding a new capability = one more
    # ToolPlugin in plugins_browser.py.
    try:
        from madcop.agent.plugins_browser import register_browser_plugins
        register_browser_plugins(reg)
    except Exception as e:  # pragma: no cover
        logger.warning("failed to register browser plugins: %s", e)

    # Reactive coeffects: gate tools whose declared keys are unbound.
    # bound_keys=None (tests/CLI) means "everything bound" — the chat
    # route passes the session's actual bindings.
    if bound_keys is not None:
        _gated = [n for n, p in reg._plugins.items()
                  if not p.requires <= set(bound_keys)]
        for _n in _gated:
            logger.info("[coeffects] gating tool %s (unbound keys: %s)",
                        _n, sorted(reg._plugins[_n].requires - set(bound_keys)))
            reg._plugins.pop(_n, None)

    executor = ToolExecutor(reg)
    return reg, executor


__all__ = [
    "ToolResult",
    "ToolPlugin",
    "PluginRegistry",
    "ToolExecutor",
    "build_default_registry",
]
