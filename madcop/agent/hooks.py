"""Pluggable hook chain (Claude hooks + OpenAI hooks semantics).

Hooks fire at well-defined points around LLM/tool/turn events and can:
  - veto a call (continue=False)            → event is denied/skipped
  - modify input (return dict → rewritten args)
  - append an observation after the fact
  - run synchronously or asynchronously (sync is the safe default)

Hooks are matched by event + optional name and run in priority order
(lowest priority fires first). Failures in any single hook are
swallowed — a buggy hook must never break the engine.

Two shipped hooks demonstrate the API + the multi-contributor pattern:
  - SafetyHook: deny `rm -rf` / `mkfs` etc. (PreToolUse on bash)
  - FormatterHook: PostToolUse on write_file → run prettier on the file
  - AuditHintHook: PostToolUse on mutating tools → append the inverse
    capability to the observation so the model knows the step is
    revertible (paper §3.1 — make reversibility visible to the LLM)

EXTENSION GUIDE
---------------
To add a new cross-cutting behaviour without touching the engine:

    from madcop.agent.hooks import Hook, HookContext, HookResult, HookEvent

    class MyHook:
        name = "myname:tag"
        def __call__(self, ctx: HookContext) -> HookResult | None:
            if ctx.event != HookEvent.PRE_TOOL_USE: return None
            ...
            return HookResult(continue_=True, modified_input=new_input,
                              extra_observation="FYI: ...")

    chain = ctx.hooks  # or chat_v4 builds it
    chain.add(Hook(name=MyHook.name, event=HookEvent.PRE_TOOL_USE, fn=MyHook()))

Multiple contributors per event are normal — they all fire in priority
order. Their decisions are folded: any continue_=False wins; the
last non-None modified_input wins; extra_observations are concatenated.
"""
from __future__ import annotations

import logging
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
#
# The deny-list lives in ~/.madcop/exec_policy.json (seeded from these
# defaults on first run) — see madcop/harness/exec_policy.py. Editing
# that file takes effect on the next tool call (mtime hot-reload).


class SafetyHook:
    """PreToolUse hook for the `bash` tool — enforce the exec policy.

    Codex parity: the rule list is user-editable JSON, not compiled-in
    regexes. `deny` vetoes the call with the matched rule's reason;
    `warn` lets it run but appends the rule notice to the observation
    so the model (and the user) sees which rule was tripped.
    """

    name = "safety:exec-policy"

    def __call__(self, ctx: HookContext) -> HookResult | None:
        if ctx.event != HookEvent.PRE_TOOL_USE or ctx.tool_name != "bash":
            return None
        cmd = (ctx.tool_input.get("command") or
               ctx.tool_input.get("cmd") or "")
        if not cmd:
            return HookResult()
        from madcop.harness.exec_policy import get_policy
        decision = get_policy().check(cmd)
        if decision.action == "deny":
            return HookResult(
                continue_=False,
                error=(
                    "[exec-policy] 拒绝执行：命中规则 "
                    f"'{decision.rule_id}'（{decision.reason}）。"
                    f"命令={cmd[:120]!r}。如需放行请在 "
                    "~/.madcop/exec_policy.json 调整该规则。"
                ),
            )
        if decision.action == "warn":
            return HookResult(
                extra_observation=(
                    f"[exec-policy] 提示：命中规则 '{decision.rule_id}'"
                    f"（{decision.reason}）。"
                ),
            )
        return HookResult()


class FormatterHook:
    """PostToolUse hook for `write_file` / `edit_file` — actually RUN a
    formatter on the written file (best-effort): prettier via npx for
    web files, black for Python. Opt-in via MADCOP_AUTO_FORMAT=1; off
    by default so demos never stall on a missing formatter. Failures
    (missing binary, parse error) degrade to an advisory observation.
    """

    name = "fmt:run"

    _WEB_EXT = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
                ".html", ".htm", ".css", ".scss", ".less", ".json", ".md", ".yaml", ".yml"}

    def __call__(self, ctx: HookContext) -> HookResult | None:
        if ctx.event != HookEvent.POST_TOOL_USE:
            return None
        if ctx.tool_name not in ("write_file", "edit_file"):
            return None
        path = ctx.tool_input.get("path") or ctx.tool_input.get("file")
        if not path:
            return None

        import os
        if os.environ.get("MADCOP_AUTO_FORMAT", "").strip() != "1":
            return HookResult(
                continue_=True,
                extra_observation=f"[fmt] {path} 已写入（自动格式化未开启，设 MADCOP_AUTO_FORMAT=1 启用）。",
            )

        import subprocess
        from pathlib import Path as _P
        p = _P(str(path))
        suffix = p.suffix.lower()
        try:
            if suffix == ".py":
                cmd = ["black", "-q", str(p)]
            elif suffix in self._WEB_EXT:
                # --no-install: fail fast when prettier isn't a local dep
                cmd = ["npx", "--no-install", "prettier", "--write", str(p)]
            else:
                return HookResult(continue_=True,
                                  extra_observation=f"[fmt] {path} 已写入（无匹配格式化器）。")
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                return HookResult(
                    continue_=True,
                    extra_observation=f"[fmt] {path} 已格式化（{cmd[0]}）。",
                )
            return HookResult(
                continue_=True,
                extra_observation=f"[fmt] {path} 格式化跳过（{cmd[0]} 不可用或解析失败）。",
            )
        except Exception as e:
            return HookResult(
                continue_=True,
                extra_observation=f"[fmt] {path} 格式化跳过（{type(e).__name__}）。",
            )


__all__ = [
    "HookEvent", "HookContext", "HookResult", "Hook", "HookChain",
    "SafetyHook", "FormatterHook", "AuditHintHook",
]


class AuditHintHook:
    """PostToolUse: hint to the LLM that the side effect is REVERTIBLE.

    P3 — the MEA auditor's "soft revert" only works when the model
    keeps writing consistent content after a blocked step. If the model
    doesn't know its file changes are revertible, it often races to
    re-write the same thing in a way that *overrides* the prior
    snapshot. By appending a one-line hint on every mutating tool
    call's observation, the LLM learns the safety net exists and stays
    calm during audit-blocked retries.

    This is the third demo contrib in the multi-contributor pattern:
    multiple hooks per event, all fire in priority order, decisions
    fold (any continue_=False wins, latest modified_input wins,
    extra_observations concatenate).
    """

    name = "audit:revert-hint"

    _MUTATING = {"write_file", "edit_file", "write_xlsx", "write_pptx"}

    def __call__(self, ctx: HookContext) -> HookResult | None:
        if ctx.event != HookEvent.POST_TOOL_USE:
            return None
        if ctx.tool_name not in self._MUTATING:
            return None
        if ctx.is_error:
            return None
        return HookResult(
            extra_observation=(
                "（审计层会在审核不过时自动恢复此文件改动；"
                "你不必手动重写。）"
            ),
        )