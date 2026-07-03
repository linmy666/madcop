"""v2.8.0 — Dynamic mode orchestrator.

When a user selects a multi-agent mode (swarm/parallel/hierarchical/etc),
this module runs BEFORE the actual mode:

1. Requirement Analysis Agent: understands what the user wants
2. Role Generator: decides what expert roles are needed
3. Task Decomposer: breaks the request into sub-tasks for each role
4. Dynamic Execution: spawns the right agents with the right prompts

Example:
  User: "做个植物大战僵尸的游戏"
  Mode: Swarm

  Step 1 — Requirement Agent analyzes:
    "用户要做一个2D塔防游戏(PvZ风格), 需要:
     - 游戏设计(关卡/植物/僵尸属性)
     - 前端开发(Canvas渲染/交互)
     - 后端逻辑(游戏循环/碰撞检测)
     - 美术资源(角色设计/场景)
     - 测试(平衡性/性能)"

  Step 2 — Role Generator creates 5 expert agents dynamically:
    - 🎮 Game Designer: 设计关卡和数值
    - 💻 Frontend Dev: Canvas + 输入处理
    - ⚙️ Backend Dev: 游戏循环 + 物理
    - 🎨 Art Director: 视觉风格 + 资源清单
    - 🧪 QA Engineer: 测试策略

  Step 3 — Each agent gets a tailored prompt and works in parallel

  Step 4 — Orchestrator collects all outputs and synthesizes

This replaces the static "3 fixed experts" approach with dynamic,
task-aware role generation.
"""
from __future__ import annotations

import json
from typing import Any

from .base import NodeBase, NodeContext, NodeResult, resolve_variables


# --------------------------------------------------------------------------- #
# Requirement Analysis Prompt
# --------------------------------------------------------------------------- #

REQUIREMENT_ANALYSIS_PROMPT = """你是需求分析专家。用户想用"{mode_name}"模式完成以下任务:

任务: {user_input}

请分析并返回 JSON (不要加 markdown 代码块标记, 直接输出 JSON):

{{
  "summary": "一句话总结用户要做什么",
  "complexity": "simple|medium|complex",
  "domain": "技术|商业|创意|研究|综合",
  "roles": [
    {{
      "name": "角色名(中文, 2-4字)",
      "icon": "emoji",
      "expertise": "专业领域(一句话)",
      "task": "这个角色具体要做什么(针对用户的任务定制)",
      "prompt": "给这个角色的完整提示词(包含任务背景和具体要求)"
    }}
  ],
  "execution_order": "parallel|sequential|mixed",
  "estimated_steps": 3-8的数字,
  "needs_clarification": false,
  "clarification_question": "如果需要用户补充信息, 写在这里"
}}

规则:
- 角色数量根据任务复杂度决定: simple=1-2, medium=3-4, complex=5-6
- 每个角色的 task 必须针对用户的具体任务定制, 不能是通用的
- prompt 要足够详细, 让角色知道自己的职责和交付物
- 如果任务太模糊无法分析, 设 needs_clarification=true 并提问"""


# --------------------------------------------------------------------------- #
# RequirementAnalysisNode — runs before any multi-agent mode
# --------------------------------------------------------------------------- #

class RequirementAnalysisNode(NodeBase):
    """Analyze the user's request and dynamically determine what
    expert agents are needed.

    This replaces fixed-role templates with dynamic role generation.
    """
    type = "requirement_analysis"
    label = "需求分析"
    description = "分析用户需求, 动态生成专家角色和任务分配"
    category = "orchestrator"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        mode_name = data.get("mode", "multi-agent")
        user_input = ""

        # Get user input from workflow_input
        wf_input = context.workflow_input
        if isinstance(wf_input, dict):
            user_input = str(wf_input.get("input", wf_input))
        elif isinstance(wf_input, str):
            user_input = wf_input

        # Call LLM for requirement analysis
        prompt = REQUIREMENT_ANALYSIS_PROMPT.format(
            mode_name=mode_name,
            user_input=user_input[:2000],
        )

        try:
            from madcop.config import settings as settings_store
            from madcop.config.settings import get_active_client_config
            from madcop.llm.client import OpenAICompatClient
            from madcop.llm import Message

            s = settings_store.load_settings()
            cfg = get_active_client_config(s)
            if not cfg:
                return NodeResult(success=False, error="No active provider")

            client = OpenAICompatClient(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model=cfg["model"],
            )

            resp = client.chat(
                messages=[Message(role="user", content=prompt)],
                model=cfg["model"],
                temperature=0.3,
            )
            raw = resp.content or ""

            # Parse JSON (handle markdown code blocks)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            analysis = json.loads(raw)

            return NodeResult(
                success=True,
                output={
                    "analysis": analysis,
                    "raw_response": raw,
                },
            )

        except json.JSONDecodeError as e:
            return NodeResult(
                success=False,
                error=f"Failed to parse analysis JSON: {e}\nRaw: {raw[:500]}",
            )
        except Exception as e:
            return NodeResult(success=False, error=f"Requirement analysis failed: {e}")


# --------------------------------------------------------------------------- #
# Dynamic Expert Node — created at runtime based on requirement analysis
# --------------------------------------------------------------------------- #

class DynamicExpertNode(NodeBase):
    """An expert agent whose role and prompt are determined at runtime
    by the RequirementAnalysisNode.

    Data fields:
      - expert_name: str
      - expert_prompt: str (full prompt from requirement analysis)
      - user_task: str (original user input)
    """
    type = "dynamic_expert"
    label = "专家 Agent"
    description = "动态生成的专家角色, 根据需求分析定制"
    category = "orchestrator"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        expert_prompt = data.get("expert_prompt", "")
        user_task = data.get("user_task", "")

        # Get the user's original input
        wf_input = context.workflow_input
        if isinstance(wf_input, dict):
            user_input = str(wf_input.get("input", wf_input))
        else:
            user_input = str(wf_input)

        full_prompt = f"{expert_prompt}\n\n用户的任务: {user_input}\n\n请给出你的专业分析和建议:"

        try:
            from madcop.config import settings as settings_store
            from madcop.config.settings import get_active_client_config
            from madcop.llm.client import OpenAICompatClient
            from madcop.llm import Message

            s = settings_store.load_settings()
            cfg = get_active_client_config(s)
            if not cfg:
                return NodeResult(success=False, error="No active provider")

            model = data.get("model") or cfg.get("model") or ""
            client = OpenAICompatClient(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model=model,
            )

            resp = client.chat(
                messages=[
                    Message(role="system", content="你是专业顾问, 用中文回答。"),
                    Message(role="user", content=full_prompt),
                ],
                model=model,
                temperature=0.7,
            )

            return NodeResult(
                success=True,
                output={
                    "expert": data.get("expert_name", "Expert"),
                    "text": resp.content or "",
                },
            )

        except Exception as e:
            return NodeResult(success=False, error=f"Expert {data.get('expert_name', '?')} failed: {e}")


# --------------------------------------------------------------------------- #
# Synthesis Node — combines all expert outputs
# --------------------------------------------------------------------------- #

class SynthesisNode(NodeBase):
    """Combine outputs from all expert agents into a final deliverable."""
    type = "synthesis"
    label = "综合输出"
    description = "整合所有专家的分析结果"
    category = "orchestrator"

    async def execute(self, context: NodeContext) -> NodeResult:
        upstream = context.upstream_outputs

        # Collect all expert outputs
        expert_outputs = []
        for node_id, output in upstream.items():
            if isinstance(output, dict) and "text" in output:
                expert_outputs.append({
                    "expert": output.get("expert", node_id),
                    "content": output["text"],
                })

        if not expert_outputs:
            return NodeResult(success=True, output={"text": "No expert outputs to synthesize."})

        # Build synthesis prompt
        expert_summaries = "\n\n---\n\n".join([
            f"### {e['expert']}\n{e['content'][:2000]}"
            for e in expert_outputs
        ])

        user_input = ""
        wf_input = context.workflow_input
        if isinstance(wf_input, dict):
            user_input = str(wf_input.get("input", wf_input))
        else:
            user_input = str(wf_input)

        prompt = (
            f"用户的需求: {user_input[:500]}\n\n"
            f"以下是多位专家的分析结果:\n\n{expert_summaries}\n\n"
            f"请综合以上所有专家的观点, 给出:\n"
            f"1. 完整的执行方案 (分步骤)\n"
            f"2. 每个步骤的负责人和交付物\n"
            f"3. 风险点和注意事项\n"
            f"4. 用 Markdown 格式输出"
        )

        try:
            from madcop.config import settings as settings_store
            from madcop.config.settings import get_active_client_config
            from madcop.llm.client import OpenAICompatClient
            from madcop.llm import Message

            s = settings_store.load_settings()
            cfg = get_active_client_config(s)
            if not cfg:
                return NodeResult(success=False, error="No active provider")

            client = OpenAICompatClient(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model=cfg["model"],
            )

            resp = client.chat(
                messages=[
                    Message(role="system", content="你是项目整合专家, 擅长把多人的分析汇总成可执行的方案。"),
                    Message(role="user", content=prompt),
                ],
                model=cfg["model"],
                temperature=0.5,
            )

            return NodeResult(
                success=True,
                output={"text": resp.content or "", "experts_count": len(expert_outputs)},
            )

        except Exception as e:
            return NodeResult(success=False, error=f"Synthesis failed: {e}")


__all__ = [
    "RequirementAnalysisNode",
    "DynamicExpertNode",
    "SynthesisNode",
    "REQUIREMENT_ANALYSIS_PROMPT",
]