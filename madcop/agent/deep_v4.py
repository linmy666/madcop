"""
v4.0 — Deep Engine (multi-specialist DAG).

Outputs unified AgentStep. Each specialist runs a mini-ReAct loop
internally (reusing ReActEngineV4's logic). Results are synthesised
into a final answer.

The DAG shape is: input → planner → specialists (parallel) → synthesizer → output
Classification and DAG construction reuse the existing engine.py functions.
"""

from __future__ import annotations

import json
import time
from typing import Iterator

from .runtime import AgentEngine, AgentStep, RunContext, StepKind
from .react_v4 import ReActEngineV4
from ..llm.client import Message

# Reuse existing classification + network builder
from ..agent_network.engine import classify_task, build_network_for_task


class DeepEngineV4(AgentEngine):
    """Multi-specialist DAG engine with unified AgentStep output.

    Flow:
    1. Classify task → get specialist roster
    2. Planner generates a plan (text_delta)
    3. Each specialist runs a mini-ReAct (thought blocks + tool calls)
    4. Synthesiser combines specialist outputs → final answer (text_delta)
    """

    def run(self, ctx: RunContext) -> Iterator[AgentStep]:
        task = ctx.messages[-1].content if ctx.messages else ""

        # 1. Classify
        try:
            category, specialist_ids = classify_task(task)
        except Exception:
            category, specialist_ids = "general", []

        # 2. Build network
        try:
            network = build_network_for_task(task)
        except Exception:
            network = {"nodes": [], "edges": []}

        specialist_names = {
            "planner": "规划",
            "coder": "编码",
            "designer": "设计",
            "researcher": "调研",
            "reviewer": "审查",
            "assistant": "综合",
        }

        # Emit deep_route info as a thought block
        route_tid = "deep-route"
        yield AgentStep(
            kind=StepKind.THOUGHT_START,
            thought_id=route_tid,
        )
        route_text = f"任务分类: {category}\n专家组合: {', '.join(specialist_names.get(s, s) for s in specialist_ids) or '通用'}"
        yield AgentStep(
            kind=StepKind.THOUGHT_DELTA,
            thought_id=route_tid,
            content=route_text,
        )
        yield AgentStep(
            kind=StepKind.THOUGHT_END,
            thought_id=route_tid,
        )

        # 3. Run planner
        planner_tid = "planner"
        yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=planner_tid)
        planner_engine = self._make_specialist_engine(ctx, "planner", task)
        planner_output = ""
        for step in planner_engine.run(ctx):
            if step.kind == StepKind.TEXT_DELTA:
                planner_output += step.content
                yield AgentStep(
                    kind=StepKind.THOUGHT_DELTA,
                    thought_id=planner_tid,
                    content=step.content,
                )
            elif step.kind == StepKind.TOOL_START:
                yield step
            elif step.kind == StepKind.TOOL_END:
                yield step
        yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=planner_tid)

        # 4. Run specialists in sequence (parallel is complex with sync
        #    iterators; sequential is simpler and correct)
        specialist_outputs: dict[str, str] = {"planner": planner_output}
        for sid in specialist_ids:
            spec_tid = f"spec-{sid}"
            yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=spec_tid)

            spec_engine = self._make_specialist_engine(ctx, sid, task)
            spec_output = ""
            for step in spec_engine.run(ctx):
                if step.kind == StepKind.TEXT_DELTA:
                    spec_output += step.content
                    yield AgentStep(
                        kind=StepKind.THOUGHT_DELTA,
                        thought_id=spec_tid,
                        content=step.content,
                    )
                elif step.kind in (StepKind.TOOL_START, StepKind.TOOL_END):
                    yield step

            specialist_outputs[sid] = spec_output
            yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=spec_tid)

        # 5. Synthesise
        synth_tid = "synthesizer"
        yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=synth_tid)

        synth_context = self._build_synth_context(task, specialist_outputs)
        synth_ctx = RunContext(
            messages=ctx.messages,
            model=ctx.model,
            agent_mode="quick",  # synthesiser is a single LLM call
            client=ctx.client,
            tool_executor=None,
            tool_schemas=[],
            system_prefix=self._synth_prompt(specialist_outputs),
            context=synth_context,
        )
        from .runtime import QuickEngine
        synth_engine = QuickEngine()
        synth_answer = ""
        for step in synth_engine.run(synth_ctx):
            if step.kind == StepKind.TEXT_DELTA:
                synth_answer += step.content
                yield AgentStep(
                    kind=StepKind.THOUGHT_DELTA,
                    thought_id=synth_tid,
                    content=step.content,
                )

        yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=synth_tid)

        # 6. Emit final answer
        if synth_answer:
            yield AgentStep(kind=StepKind.TEXT_DELTA, content=synth_answer)
        yield AgentStep(kind=StepKind.TEXT_END)
        yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")

    def _make_specialist_engine(
        self, ctx: RunContext, role: str, task: str
    ) -> ReActEngineV4:
        """Create a ReAct engine for a specialist role."""
        engine = ReActEngineV4()
        # Override system prefix with role-specific instructions
        role_prompts = {
            "planner": "你是规划专家。分析任务，拆解为可执行的子任务列表。不要写代码，只做规划。",
            "coder": "你是编码专家。根据规划写出高质量代码。优先用 write_file 写入文件。",
            "designer": "你是设计专家。设计 UI 布局、配色、交互方案。",
            "researcher": "你是调研专家。用 web_search 查找最新信息，整理成结构化报告。",
            "reviewer": "你是审查专家。检查代码质量、逻辑漏洞，给出改进建议。",
            "assistant": "你是综合助手。整理各方信息，生成最终文档。",
        }
        # Mutate ctx in-place (hacky but works for sequential execution)
        ctx.system_prefix = role_prompts.get(role, "你是专家助手。")
        return engine

    @staticmethod
    def _build_synth_context(
        task: str, outputs: dict[str, str]
    ) -> str:
        """Build context text for the synthesiser."""
        lines = [f"原始任务: {task}\n"]
        for role, output in outputs.items():
            if output.strip():
                lines.append(f"### {role}\n{output[:2000]}\n")
        return "\n".join(lines)

    @staticmethod
    def _synth_prompt(outputs: dict[str, str]) -> str:
        return (
            "你是综合专家。根据下方各专家的输出，生成一份完整、连贯的最终回答。"
            "保留关键信息，去除重复，确保逻辑清晰。直接输出最终答案，不要用 Action 格式。"
        )


__all__ = ["DeepEngineV4"]
