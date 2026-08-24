"""Pluggable hook chain (Claude hooks + OpenAI hooks semantics).

Hooks fire at well-defined points around LLM/tool/turn events and can:
  - veto a call (continue=False)            → event is denied/skipped
  - modify input (return dict → rewritten args)
  - append an observation after the fact
  - run synchronously or asynchronously (sync is the safe default)

Hooks are matched by event + optional name and run in priority order
(lowest priority fires first). Failures in any single hook are
swallowed — a buggy hook must never break the engine.

Two shipped hooks demonstrate the API:
  - SafetyHook: deny `rm -rf` / `mkfs` etc. (PreToolUse on bash)
  - FormatterHook: PostToolUse on write_file → run prettier on the file
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ─── Event taxonomy (subset mirroring Claude hooks) ────────────────────────
class HookEvent:
    PRE_LLM = "PreLLM"           # before each LLM call
    POST_LLM = "PostLLM"         # after each LLM call completes
    PRE_TOOL_USE = "PreToolUse"   # before a tool executes
    POST_TOOL_USE = "PostToolUse" # after a tool returns
    PRE_COMPACT = "PreCompact"   # before context compaction
    STOP = "Stop"                # end of turn / agent


@dataclass
class HookContext:
    """One hook invocation's input. Hooks may mutate fields; the engine
    reads the (possibly modified) context after each hook runs."""
    event: str
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    is_error: bool = False
    turn_id: str = ""
    conversation_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """What a hook returned to the engine."""
    continue_: bool = True        # False → veto the call / pause the agent
    modified_input: dict[str, Any] | None = None  # rewritten tool_input
    extra_observation: str = ""    # appended to the observation feed
    error: str = ""               # synthetic error to surface instead


# Hook signature: (HookContext) -> HookResult | None
HookFn = Callable[[HookContext], HookResult | None]


@dataclass
class Hook:
    name: str
    event: str
    fn: HookFn
    # Optional tool-name filter: None → fires for every tool; else only
    # when tool_name matches (e.g. PreToolUse for "bash").
    tool_filter: str | None = None
    priority: int = 0


class HookChain:
    """Ordered, runnable collection of hooks."""

    def __init__(self, hooks: list[Hook] | None = None):
        self.hooks: list[Hook] = list(hooks or [])

    def add(self, hook: Hook) -> None:
        self.hooks.append(hook)

    def run(self, ctx: HookContext) -> HookResult:
        """Fire every matching hook; fold their decisions into a single
        final HookResult (continue=False wins; latest modified_input
        wins; observations concatenated)."""
        out = HookResult()
        applicable = sorted(
            (h for h in self.hooks
             if h.event == ctx.event
             and (h.tool_filter is None or h.tool_filter == ctx.tool_name)),
            key=lambda h: h.priority,
        )
        for h in applicable:
            try:
                res = h.fn(ctx) or HookResult()
            except Exception as e:
                # A buggy hook must never break the engine — log and
                # continue with the previous effective decision.
                logger.warning("hook %s raised: %s", h.name, e)
                continue
            if not res.continue_:
                out.continue_ = False
            if res.modified_input is not None:
                out.modified_input = dict(res.modified_input)
            if res.extra_observation:
                out.extra_observation = (
                    out.extra_observation + ("\n" if out.extra_observation else "") + res.extra_observation
                )
            if res.error:
                out.error = res.error
        return out


# ─── Shipped hooks (demonstrate the API) ───────────────────────────────────

_DANGEROUS_PATTERNS = [
    r"\brm\s+-rf?[\s/]",                          # rm -rf /, rm -r /etc
    r"\bmkfs(\.[a-z0-9]+)?\b",
    r"\bdd\s+if=.+of=/dev/(sd|nvme|hd)",
    r"\b(shutdown|reboot|halt)\b",
    r"\bcurl[^|]*\|\s*(bash|sh|zsh)\b",  # pipe to shell
    r":\(\)\s*\{\s*:\|:&\s*\};:",        # fork bomb
]


class SafetyHook:
    """PreToolUse hook for the `bash` tool — deny destructive patterns.

    Replaces `cmd` with a no-op echo and surfaces a clear error so the
    user sees what was blocked without the engine executing it.
    """

    name = "safety:dangerous-bash"

    def __init__(self):
        self._res = [re.compile(p, re.IGNORECASE) for p in _DANGEROUS_PATTERNS]

    def __call__(self, ctx: HookContext) -> HookResult | None:
        if ctx.event != HookEvent.PRE_TOOL_USE or ctx.tool_name != "bash":
            return None
        cmd = (ctx.tool_input.get("command") or
               ctx.tool_input.get("cmd") or "")
        for pat in self._res:
            if pat.search(cmd):
                return HookResult(
                    continue_=False,
                    error=(
                        "[safety] 拒绝执行：检测到高危命令模式。"
                        f"规则={pat.pattern}; 命令={cmd[:120]!r}"
                    ),
                )
        return HookResult()


class FormatterHook:
    """PostToolUse hook for `write_file` / `edit_file` — surface a
    formatting advisory as extra_observation. The actual formatter
    execution stays opt-in; the advisory lets the user / next-step
    model know the file just changed."""

    name = "fmt:notice"

    def __call__(self, ctx: HookContext) -> HookResult | None:
        if ctx.event != HookEvent.POST_TOOL_USE:
            return None
        if ctx.tool_name not in ("write_file", "edit_file"):
            return None
        path = ctx.tool_input.get("path") or ctx.tool_input.get("file")
        if not path:
            return None
        return HookResult(
            continue_=True,
            extra_observation=f"[fmt] {path} 已写入；UI 可提示运行 prettier/black 自动格式化。",
        )


__all__ = [
    "HookEvent", "HookContext", "HookResult", "Hook", "HookChain",
    "SafetyHook", "FormatterHook",
]