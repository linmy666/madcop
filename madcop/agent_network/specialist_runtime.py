"""Transparent specialist runtime for deep multi-agent mode.

Goal: make deep-mode specialists *materially* different from a single
ReAct loop, without requiring the customer to configure anything.

- Each role gets a **hard tool allowlist** (not just prompt labels).
- Specialists run a **short mini-ReAct** when tools are available.
- Synthesizer stays pure LLM (merge only — no tools).
- **Single-LLM users**: same active model for every role; still get
  different tools + different role prompts + parallel structure.
- **Zero UI**: no new settings surface; fails open to pure completion.

This module is internal plumbing — the chat UI still just shows
sub-agents and tool cards if the host forwards events.
"""

from __future__ import annotations

from typing import Any

# Role → tool names the specialist is allowed to call.
# Keep lists short so mini-ReAct stays cheap and focused.
ROLE_TOOL_ALLOWLIST: dict[str, list[str]] = {
    # Planner: ground the plan in real files when a workspace exists.
    "planner": ["read_file", "get_time"],
    # Coder: read/write/edit in workspace (the real differentiator).
    "coder": [
        "read_file", "write_file", "edit_file", "write_xlsx",
        "get_time",
    ],
    # Designer: may sketch HTML/CSS to preview dir via write_file.
    "designer": ["read_file", "write_file", "get_time"],
    # Researcher: search + fetch (not code writes).
    "researcher": ["web_search", "web_fetch", "read_file", "get_time"],
    # Reviewer: read-only inspection.
    "reviewer": ["read_file", "get_time"],
    # Writing / generic assistant specialists: light research only.
    "assistant": ["web_search", "web_fetch", "get_time"],
    # Synthesizer intentionally omitted → no tools.
}

# Cap ReAct steps so deep mode does not explode cost vs single ReAct.
ROLE_MAX_STEPS: dict[str, int] = {
    "planner": 3,
    "coder": 6,
    "designer": 4,
    "researcher": 5,
    "reviewer": 4,
    "assistant": 3,
}

# Role-specific framing injected *before* the shared ReAct template.
# Customers never see these as settings — they are product defaults.
ROLE_SYSTEM_PREFIX: dict[str, str] = {
    "planner": (
        "你是「规划师」。先弄清目标与约束，必要时用工具查看项目结构，"
        "再输出可执行步骤清单（编号）。不要实现细节代码，不要长篇散文。"
    ),
    "coder": (
        "你是「编码专家」。优先用工具读取/写入真实文件再给结论。"
        "需要落盘时必须调用 write_file 或 edit_file（可用相对路径，会写入工作区）。"
        "禁止谎称「已保存」却未成功调用工具。输出应包含：改动说明 + 文件路径。"
        "不要编造未读到的文件内容。"
    ),
    "designer": (
        "你是「设计助手」。产出界面结构、组件层级与关键 CSS/HTML 片段。"
        "如需落盘预览，可 write_file 到工作区或预览目录。避免装饰性 emoji。"
    ),
    "researcher": (
        "你是「研究员」。需要事实时先 web_search / web_fetch，"
        "报告须区分「已核实」与「推测」，并尽量带来源线索。"
        "不要写生产代码。"
    ),
    "reviewer": (
        "你是「审查员」。只读检查：正确性、安全、边界与可维护性。"
        "用严重度分级（高/中/低）列问题，给出可操作建议。"
        "不要重写整份实现，不要替编码专家完成开发。"
    ),
    "assistant": (
        "你是「助手」。在需要外部信息时用搜索；最终给出清晰完整的文稿。"
    ),
}


def tools_for_role(role: str) -> list[str]:
    """Return allowlisted tool names for a role (empty → pure LLM)."""
    # synthesizer node id maps to assistant agent but must not get tools
    # when called as synthesizer — callers pass node_id for that.
    return list(ROLE_TOOL_ALLOWLIST.get(role, []))


def max_steps_for_role(role: str) -> int:
    return int(ROLE_MAX_STEPS.get(role, 4))


def system_prefix_for_role(role: str, agent_name: str = "", description: str = "") -> str:
    base = ROLE_SYSTEM_PREFIX.get(role, f"你是「{agent_name or role}」。")
    if description:
        return f"{base}\n角色说明: {description}"
    return base


def filter_tool_schemas(
    schemas: list[dict[str, Any]],
    allow: list[str],
) -> list[dict[str, Any]]:
    """Filter OpenAI-style tool schemas to an allowlist of names."""
    if not allow:
        return []
    allow_set = set(allow)
    out: list[dict[str, Any]] = []
    for s in schemas:
        name = s.get("name") or (s.get("function") or {}).get("name")
        if name in allow_set:
            out.append(s)
    return out


def role_should_use_tools(role: str, node_id: str = "") -> bool:
    """Synthesizer / merge never use tools; others follow allowlist."""
    if node_id in ("synthesizer", "output", "input", "merge"):
        return False
    if role in ("synthesizer",):
        return False
    return bool(tools_for_role(role))


def build_role_tool_schemas(
    role: str,
    workspace_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Build filtered tool schemas for a role from the default registry."""
    allow = tools_for_role(role)
    if not allow:
        return []
    try:
        from madcop.tools import default_registry
    except Exception:
        return []
    try:
        reg = default_registry(workspace_dir=workspace_dir)
        return filter_tool_schemas(reg.openai_schemas(), allow)
    except Exception:
        return []
