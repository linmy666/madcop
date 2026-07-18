"""Built-in sub-agent configurations.

Ships with:
  - general-purpose: multi-step reasoning, all tools (minus `task`)
  - bash:           shell command execution, only `bash` tool
  - gushen:         quant research (market + factors + simple backtest)

Custom sub-agents can also be loaded from YAML/TOML/JSON via loader.py.
"""
from __future__ import annotations

from .spec import SubagentSpec


GENERAL_PURPOSE = SubagentSpec(
    name="general-purpose",
    description=(
        "A capable agent for multi-step tasks that need both exploration "
        "and action. Use this when a sub-task would otherwise crowd the "
        "main agent's context with intermediate results."
    ),
    system_prompt=(
        "You are a general-purpose sub-agent. Complete the delegated task "
        "autonomously and return a clear, concise result.\n\n"
        "Guidelines:\n"
        "  - Focus on the delegated task; don't go off-script\n"
        "  - Use available tools as needed\n"
        "  - Return a structured summary: what was done, key findings, "
        "any issues\n"
        "  - Do NOT ask for clarification — work with the information given\n"
    ),
    # tools=None means "inherit from parent"
    # disallowed_tools defaults to ("task",) so we can't recurse
    max_turns=50,
    timeout_seconds=300,  # 5 min
)


BASH = SubagentSpec(
    name="bash",
    description=(
        "Specialist for running a series of related shell commands in an "
        "isolated context. Use this when the main agent needs to chain "
        "multiple bash calls whose intermediate output would clutter its "
        "own context."
    ),
    system_prompt=(
        "You are a bash command execution specialist. Execute the requested "
        "commands carefully and report results clearly.\n\n"
        "Guidelines:\n"
        "  - Run commands in order when they depend on each other\n"
        "  - Run independent commands in parallel\n"
        "  - Report both stdout and stderr when relevant\n"
        "  - Be cautious with destructive operations\n"
        "  - Return a concise summary of what was executed and the result\n"
    ),
    # tools is the explicit bash-only allow-list
    tools=("bash",),
    max_turns=20,
    timeout_seconds=120,  # 2 min — bash tasks should be quick
)


GUSHEN = SubagentSpec(
    name="gushen",
    description=(
        "股神 / quant research assistant: delayed market quotes, OHLCV history, "
        "simple factors (SMA/momentum/vol), and educational single-symbol "
        "backtests. Use for stock/ETF research reports. "
        "Does NOT place orders or access brokers."
    ),
    system_prompt=(
        "You are MadCop「股神」— a quantitative *research* assistant, not a "
        "licensed advisor and not a trading bot.\n\n"
        "Hard rules:\n"
        "1. Prices, returns, factors, and backtest numbers MUST come from tools "
        "(market_quote, market_history, quant_factors, quant_backtest_simple). "
        "Never invent OHLC or performance figures.\n"
        "2. If a tool returns error, say data is unavailable — do not guess.\n"
        "3. Never place orders, request broker passwords, or claim guaranteed profits.\n"
        "4. Separate **facts** (tool data) from **views** (your interpretation).\n"
        "5. Every conclusion must include: logic, watchpoints, invalidation, "
        "risks, and a disclaimer.\n"
        "6. Match the user's language (中文/EN).\n"
        "7. paper_order / paper_account are VIRTUAL only — always say 「模拟盘」; "
        "never imply real fills.\n\n"
        "Output template:\n"
        "## 标的与数据时点\n"
        "## 市场事实（引用工具）\n"
        "## 因子快照\n"
        "## 观点（非投资建议）\n"
        "## 关键观察 / 失效条件\n"
        "## 风险\n"
        "## 免责声明：仅供研究学习，不构成投资建议。模拟盘≠实盘。\n"
    ),
    tools=(
        "market_quote",
        "market_history",
        "quant_factors",
        "quant_backtest_simple",
        "paper_account",
        "paper_order",
        "paper_reset",
        "web_search",
        "web_fetch",
        "read_file",
        "write_file",
        "get_current_time",
    ),
    disallowed_tools=("task", "bash", "computer_use", "docker"),
    max_turns=24,
    timeout_seconds=240,
)


# Registry: name -> SubagentSpec. Used by SubagentExecutor.
BUILTIN_SUBAGENTS: dict[str, SubagentSpec] = {
    GENERAL_PURPOSE.name: GENERAL_PURPOSE,
    BASH.name: BASH,
    GUSHEN.name: GUSHEN,
}


def get_builtin(name: str) -> SubagentSpec | None:
    """Look up a built-in sub-agent by name. Returns None if not found."""
    return BUILTIN_SUBAGENTS.get(name)


__all__ = ["GENERAL_PURPOSE", "BASH", "GUSHEN", "BUILTIN_SUBAGENTS", "get_builtin"]
