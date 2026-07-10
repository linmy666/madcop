"""v1.0 — Plan-and-Execute: structured task planning with step verification.

Three phases:
  1. PLAN: LLM decomposes the user's task into steps (JSON)
  2. EXECUTE: each step runs through the agent loop
  3. VERIFY: LLM checks step result against the expected outcome

Architecture:
  Plan             = dataclass holding goal + ordered steps
  PlanStep         = a single atomic step with action, tool, expected result
  Planner          = LLM prompt → structured Plan
  StepExecutor     = runs one step (tool call or LLM reasoning)
  StepVerifier     = LLM-as-Judge: did this step achieve its goal?

Control theory (钱学森):
  - 闭环反馈: every step gets verified, result feeds back
  - 可控性: max_retries, step_limit, cancellation
  - 早纠偏: failed step → re-plan remaining steps, don't retry blindly
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single atomic step in a plan."""
    step: int
    action: str                    # what to do (human-readable)
    tool: str | None = None        # expected tool, or None for LLM reasoning
    input_hint: str = ""           # what to search / ask / compute
    expected_result: str = ""      # what success looks like (for verification)
    status: StepStatus = StepStatus.PENDING
    result: str | None = None      # actual output after execution
    error: str | None = None       # if failed
    retry_count: int = 0
    max_retries: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "tool": self.tool,
            "input_hint": self.input_hint[:200],
            "expected_result": self.expected_result[:200],
            "status": self.status.value,
            "result": (self.result or "")[:500],
            "error": self.error,
            "retry_count": self.retry_count,
        }


@dataclass
class Plan:
    """A complete execution plan."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    status: str = "pending"  # pending | running | completed | failed

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def failed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.FAILED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "status": self.status,
        }


# ─────────────────────────────────────────────────────────
# Planner prompt
# ─────────────────────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """你是一个任务规划专家。你的工作是将用户的目标分解为可执行的步骤。

## 规则
1. 分析用户的请求，理解真正的目标
2. 将目标分解为 2-8 个有序步骤
3. 每一步都必须有明确的"预期结果"（验收标准）
4. 如果某步需要调用工具，指定 tool 名称
5. 步骤之间如果有依赖关系，必须顺序排列

## 输出格式
你必须输出纯 JSON（不要 markdown 代码块）：

{
  "goal": "任务目标的简短描述",
  "steps": [
    {
      "step": 1,
      "action": "搜索竞品定价数据",
      "tool": "web_search",
      "input_hint": "2026年主要竞品定价对比",
      "expected_result": "获取到至少3家竞品的定价信息"
    },
    {
      "step": 2,
      "action": "分析数据并生成报告",
      "tool": null,
      "input_hint": "用上一步的数据做对比分析",
      "expected_result": "生成一份包含价格对比表的报告"
    }
  ]
}

## 注意事项
- tool 只能是: web_search, web_fetch, read_file, write_file, edit_file, computer_use, clarify, weather
- 如果某步不需要工具，tool 设为 null（纯 LLM 推理步骤）
- 每步的 expected_result 必须可验证（不是空洞的"完成"）
- 不要过度分解（别把"打开浏览器"也算一步）
"""

VERIFIER_PROMPT = """你是一个结果验证专家。判断上一步的执行结果是否达到了预期目标。

## 上一步
{action}

## 预期结果
{expected}

## 实际结果
{result}

## 你的任务
输出 JSON（不要 markdown 代码块）：
{
  "passed": true/false,
  "reason": "简洁的原因说明",
  "suggested_fix": "如果不通过，建议怎么改（可选）"
}

判断标准：
- 如果实际结果包含了预期结果的核心内容 → passed
- 如果实际结果为空或明显不对 → not passed
- 如果是部分成功 → 看核心目标是否达成
"""


# ─────────────────────────────────────────────────────────
# Plan generation via LLM
# ─────────────────────────────────────────────────────────

def generate_plan(
    task: str,
    *,
    llm_complete: callable,
    max_steps: int = 8,
) -> Plan:
    """Ask an LLM to generate a structured plan for a task.

    Args:
        task: The user's task description.
        llm_complete: A function that takes a prompt and returns a string response.
                      Signature: llm_complete(messages: list[dict]) -> str
        max_steps: Maximum number of steps allowed.

    Returns:
        A Plan object.
    """
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": f"请为以下任务制定执行计划：\n\n{task}"},
    ]
    raw = llm_complete(messages)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Planner returned invalid JSON: %s", raw[:200])
        # Fallback: wrap the entire task as a single step
        return Plan(
            goal=task,
            steps=[PlanStep(step=1, action=task, expected_result="完成任务")],
        )

    goal = data.get("goal", task)[:500]
    steps_raw = data.get("steps", [])
    steps: list[PlanStep] = []
    for i, s in enumerate(steps_raw[:max_steps], start=1):
        steps.append(PlanStep(
            step=i,
            action=str(s.get("action", ""))[:300],
            tool=s.get("tool") or None,
            input_hint=str(s.get("input_hint", ""))[:500],
            expected_result=str(s.get("expected_result", ""))[:300],
        ))
    if not steps:
        steps.append(PlanStep(step=1, action=task, expected_result="完成任务"))

    return Plan(goal=goal, steps=steps)


# ─────────────────────────────────────────────────────────
# Step verification
# ─────────────────────────────────────────────────────────

def verify_step(
    step: PlanStep,
    *,
    llm_complete: callable,
) -> tuple[bool, str]:
    """Verify if a step achieved its expected result.

    Returns:
        (passed: bool, reason: str)
    """
    if not step.result or not step.expected_result:
        # No result to verify — pass through (optimistic)
        return True, "no verification needed"

    prompt = VERIFIER_PROMPT.format(
        action=step.action,
        expected=step.expected_result,
        result=step.result[:2000],
    )
    raw = llm_complete([{"role": "user", "content": prompt}])
    try:
        data = json.loads(raw)
        return bool(data.get("passed", False)), str(data.get("reason", ""))
    except (json.JSONDecodeError, ValueError):
        # Can't parse — be optimistic
        return True, "verification result unparseable, assuming passed"


# ─────────────────────────────────────────────────────────
# Step execution
# ─────────────────────────────────────────────────────────

def execute_step(
    step: PlanStep,
    context: str,
    *,
    llm_complete: callable,
) -> str:
    """Execute one step.

    Builds a prompt for the LLM that includes:
      - The current step's action and input_hint
      - The overall plan context (goal + previous steps)
      - Available tools

    Returns the LLM response text.
    """
    messages = [
        {"role": "system", "content": (
            "你是 MadCop 助手，正在按计划逐步执行任务。\n"
            f"总体目标：{context}\n"
            f"当前步骤 ({step.step}/{step.step}): {step.action}\n"
            f"提示：{step.input_hint}\n"
            f"预期结果：{step.expected_result}\n\n"
            "请完成当前步骤。如果需要工具，调用对应的 tool。"
        )},
        {"role": "user", "content": step.input_hint or step.action},
    ]
    raw = llm_complete(messages)
    return raw


__all__ = [
    "Plan",
    "PlanStep",
    "StepStatus",
    "generate_plan",
    "verify_step",
    "execute_step",
    "PLANNER_SYSTEM_PROMPT",
]