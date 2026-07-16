"""Task router — auto-classifies user input into quick/standard/deep.

This is the "brain" that decides how complex a task is and which
execution strategy to use, so the user doesn't have to manually
pick a mode.

Heuristics (no LLM needed — pure keyword/length analysis):
  - Quick: short questions, syntax help, explanations, simple lookups
  - Standard: bug fixes, single-file edits, feature additions
  - Deep: multi-file refactors, architecture, system design, "review"

Priority order (important!):
  1. Deep patterns checked FIRST — even short inputs like "重构X" are deep
  2. Quick patterns for pure questions
  3. Standard patterns for action-oriented tasks
  4. Length / file reference heuristics as fallback
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ── Mode constants ─────────────────────────────────────────────────── #

QUICK = "quick"
STANDARD = "standard"
DEEP = "deep"

AUTO = "auto"


# ── Deep patterns (multi-agent triggers) ───────────────────────────── #

_DEEP_PATTERNS = [
    r"重构", r"refactor", r"架构", r"architecture",
    r"模块", r"module", r"系统设计", r"system.design",
    r"端到端", r"end.to.end", r"全栈", r"full.stack",
    r"代码审查", r"code.review", r"审计", r"audit",
    r"安全检查", r"security", r"全面分析", r"comprehensive",
    r"从零开始", r"from.scratch", r"完整.*实现", r"完整.*项目",
    r"搭建", r"scaffold", r"脚手架",
    r"前端.*后端", r"frontend.*backend",
    r"评审", r"评估.*方案",
    # Parallelism signals — tasks that benefit from multiple agents at once.
    r"同时", r"并行", r"分别", r"多个", r"两边",
    r"对比.*方案", r"多.*方案", r"协同",
]

_DEEP_RE = [re.compile(p, re.IGNORECASE) for p in _DEEP_PATTERNS]


# ── Quick patterns (simple Q&A) ────────────────────────────────────── #

_QUICK_PATTERNS = [
    r"什么意思", r"是什么", r"什么是", r"怎么写", r"如何使用",
    r"语法", r"syntax", r"格式", r"区别", r"difference",
    r"翻译", r"translate", r"解释", r"explain", r"说明",
]

_QUICK_RE = [re.compile(p, re.IGNORECASE) for p in _QUICK_PATTERNS]


# ── Standard patterns (action-oriented, single concern) ────────────── #

_STANDARD_PATTERNS = [
    r"修复", r"fix", r"解决", r"solve", r"debug", r"调试",
    r"添加", r"add", r"实现", r"implement",
    r"修改", r"modify", r"change", r"更新", r"update",
    r"删除", r"remove", r"delete",
    r"创建", r"create", r"生成", r"generate",
    r"优化", r"optimize", r"改进", r"improve",
    r"测试", r"test", r"部署", r"deploy",
    r"写", r"write", r"编写", r"编", r"码",
]

_STANDARD_RE = [re.compile(p, re.IGNORECASE) for p in _STANDARD_PATTERNS]


# ── Router ─────────────────────────────────────────────────────────── #

@dataclass
class RouteDecision:
    mode: str
    confidence: float
    reason: str


def route_task(user_input: str, context: str = "") -> RouteDecision:
    """Classify a user task into quick/standard/deep."""
    text = f"{user_input} {context}".strip()
    length = len(user_input.strip())

    # ── Priority 1: Deep patterns (check first, even for short inputs) ── #
    deep_hits = sum(1 for r in _DEEP_RE if r.search(text))
    if deep_hits > 0:
        conf = min(0.6 + deep_hits * 0.15, 0.95)
        # Very long + deep = extra confident
        if length > 200:
            conf = min(conf + 0.05, 0.98)
        return RouteDecision(DEEP, conf, f"匹配 {deep_hits} 个复杂任务模式")

    # ── Priority 2: Length-based quick fast path ── #
    if length < 15:
        has_action = any(r.search(text) for r in _STANDARD_RE)
        if not has_action:
            return RouteDecision(QUICK, 0.8, "短文本无动作词")

    # ── Priority 3: Quick patterns (pure questions) ── #
    quick_hits = sum(1 for r in _QUICK_RE if r.search(text))
    standard_hits = sum(1 for r in _STANDARD_RE if r.search(text))

    if quick_hits > 0 and standard_hits == 0:
        return RouteDecision(QUICK, 0.75, f"匹配 {quick_hits} 个问答模式")

    # ── Priority 4: Standard patterns ── #
    if standard_hits > 0:
        conf = min(0.65 + standard_hits * 0.1, 0.9)
        return RouteDecision(STANDARD, conf, f"匹配 {standard_hits} 个操作模式")

    # ── Fallback heuristics ── #
    if re.search(r"[./]\w+\.\w{1,5}\b|```|文件|file|目录|dir", text, re.IGNORECASE):
        return RouteDecision(STANDARD, 0.7, "包含文件/代码引用")

    sentences = user_input.count("。") + user_input.count(".") + user_input.count("\n")
    if sentences >= 2:
        return RouteDecision(STANDARD, 0.6, f"多句输入({sentences}句)")

    return RouteDecision(STANDARD, 0.5, "默认策略")


# ── Mode → effort/workflow mapping ─────────────────────────────────── #

MODE_TO_EFFORT: dict[str, str] = {
    QUICK: "low",
    STANDARD: "medium",
    DEEP: "high",
}

MODE_TO_WORKFLOW: dict[str, str] = {
    QUICK: "direct",
    STANDARD: "react",
    DEEP: "multi_agent",
}

MODE_LABELS: dict[str, str] = {
    QUICK: "快速",
    STANDARD: "标准",
    DEEP: "深度",
}

MODE_DESCRIPTIONS: dict[str, str] = {
    QUICK: "直接回答，适合简单问答",
    STANDARD: "ReAct 推理循环，读文件/跑命令",
    DEEP: "多 Agent 协作，规划→编码→审查",
}


def get_mode_config(mode: str) -> dict[str, str]:
    return {
        "mode": mode,
        "label": MODE_LABELS.get(mode, mode),
        "description": MODE_DESCRIPTIONS.get(mode, ""),
        "effort": MODE_TO_EFFORT.get(mode, "medium"),
        "workflow": MODE_TO_WORKFLOW.get(mode, "react"),
    }
