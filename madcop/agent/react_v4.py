"""
v4.0 — ReAct Engine V4.

Outputs unified AgentStep (not the old ReActStep).
Implements: COT enforcement, thought blocks, tool lifecycle,
stuck-loop reflection, FINAL_ANSWER streaming detection.

Reuses the parsing + prompt logic from the existing react_engine.py
but with a clean AgentStep output interface.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Iterator

from .runtime import AgentEngine, AgentStep, RunContext, StepKind

# Reuse existing parsers (battle-tested)
from ..agent_network.react_engine import (
    REACT_SYSTEM_PROMPT,
    parse_react_response,
    normalize_final_answer,
)
from ..llm.client import Message


# Protocol markers to strip from reasoning text
_PROTOCOL_RE = re.compile(
    r"(Thought|Action\s*Input|Action|Observation)"
    r"\s*[:：]\s*",
    re.IGNORECASE,
)
_FA_MARKER = re.compile(
    r"(?:Action\s*[:：]\s*)?FINAL_ANSWER\b\s*[:：\n]",
    re.IGNORECASE,
)
_AI_MARKER = re.compile(r"Action\s*Input\s*[:：]", re.IGNORECASE)
_BARE_FA_RE = re.compile(r"FINAL_ANSWER\s*[:：]\s*(.*)", re.DOTALL | re.IGNORECASE)


class ReActEngineV4(AgentEngine):
    """Standard ReAct engine with unified AgentStep output.

    Features (carried over from v3):
    - COT enforcement (no empty thoughts)
    - Thought blocks (Grok-Build-style independent segments)
    - FINAL_ANSWER streaming detection
    - Stuck-loop reflection (same tool 3+, research tools 4+)
    - Pydantic safety guardrails (via tool_executor)
    """

    def run(self, ctx: RunContext) -> Iterator[AgentStep]:
        messages = self._build_messages(ctx)
        max_steps = ctx.max_steps or 12
        thought_counter = 0
        thought_active = False
        cur_tid = ""
        steps_log: list[str] = []  # for loop detection
        fa_streamed = False

        for step_num in range(1, max_steps + 1):
            step_start = time.time()

            # --- LLM call with streaming + FINAL_ANSWER detection ---
            raw = ""
            stream_state = 0  # 0=reasoning, 1=saw FA, 2=answer body

            try:
                if hasattr(ctx.client, "stream"):
                    for chunk in ctx.client.stream(
                        messages,
                        model=ctx.model,
                        temperature=0.1,
                        max_tokens=2048,
                    ):
                        text = getattr(chunk, "text", "") or ""
                        if not text:
                            fr = getattr(chunk, "finish_reason", None)
                            if fr:
                                break
                            continue
                        raw += text

                        if stream_state == 0:
                            if _FA_MARKER.search(raw):
                                stream_state = 2
                                # Close current thought block
                                if thought_active:
                                    thought_active = False
                                    yield AgentStep(
                                        kind=StepKind.THOUGHT_END,
                                        thought_id=cur_tid,
                                        elapsed_ms=int((time.time() - step_start) * 1000),
                                    )
                                # Emit post-marker tail as answer
                                m = _FA_MARKER.search(raw)
                                if m:
                                    tail = raw[m.end():].lstrip(" \t\n")
                                    if tail:
                                        fa_streamed = True
                                        yield AgentStep(kind=StepKind.TEXT_DELTA, content=tail)
                            else:
                                emit = _PROTOCOL_RE.sub("", text)
                                if emit:
                                    if not thought_active:
                                        thought_active = True
                                        thought_counter += 1
                                        cur_tid = f"thought-{thought_counter}"
                                        yield AgentStep(
                                            kind=StepKind.THOUGHT_START,
                                            thought_id=cur_tid,
                                        )
                                    yield AgentStep(
                                        kind=StepKind.THOUGHT_DELTA,
                                        thought_id=cur_tid,
                                        content=emit,
                                    )
                        elif stream_state == 2:
                            clean = text
                            if not fa_streamed:
                                clean = clean.lstrip(" \t\n")
                                if clean:
                                    fa_streamed = True
                            if clean:
                                yield AgentStep(kind=StepKind.TEXT_DELTA, content=clean)

                        fr = getattr(chunk, "finish_reason", None)
                        if fr:
                            break
                else:
                    resp = ctx.client.chat(
                        messages, model=ctx.model,
                        temperature=0.1, max_tokens=2048,
                    )
                    raw = getattr(resp, "content", "") or str(resp)
            except Exception as e:
                yield AgentStep(
                    kind=StepKind.ERROR,
                    content=f"LLM call failed: {e}",
                )
                return

            # --- Parse response ---
            thought, action, action_input = parse_react_response(raw)

            # Close any open thought block
            if thought_active:
                thought_active = False
                yield AgentStep(
                    kind=StepKind.THOUGHT_END,
                    thought_id=cur_tid,
                    elapsed_ms=int((time.time() - step_start) * 1000),
                )

            # --- COT enforcement ---
            if action.upper() != "FINAL_ANSWER" and not thought.strip():
                reflection = (
                    "你刚才尝试调用工具但没有先思考。"
                    "请先用 Thought 分析当前状况，然后再写 Action。"
                )
                messages.append(Message(role="assistant", content=raw))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue

            # --- Stuck-loop detection ---
            recent = steps_log[-3:] + ([action] if action.upper() != "FINAL_ANSWER" else [])
            is_same_loop = (
                len(recent) >= 3
                and all(a == recent[0] for a in recent[-3:])
            )
            is_research_loop = (
                len(recent) >= 4
                and all(a in ("web_search", "web_fetch", "query_rag", "recall_memory")
                        for a in recent)
            )
            if is_same_loop or is_research_loop:
                reflection = "你已经连续调用了多次同一类工具。请停止，换工具或直接 FINAL_ANSWER。"
                messages.append(Message(role="assistant", content=raw))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue

            steps_log.append(action)

            # --- FINAL_ANSWER ---
            if action.upper() == "FINAL_ANSWER":
                answer = normalize_final_answer(action_input)
                if answer and not fa_streamed:
                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=answer)
                yield AgentStep(kind=StepKind.TEXT_END)
                yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")
                return

            # --- Tool call ---
            tool_use_id = f"tool-{step_num}"
            # Parse args
            try:
                args = json.loads(action_input) if action_input.strip() else {}
            except json.JSONDecodeError:
                args = {"path": action_input.strip(), "query": action_input.strip()}

            yield AgentStep(
                kind=StepKind.TOOL_START,
                tool_name=action,
                tool_input=args,
                tool_use_id=tool_use_id,
            )

            # Execute tool
            observation = ""
            is_error = False
            try:
                if ctx.tool_executor:
                    observation = str(ctx.tool_executor(action, action_input, ctx.work_dir))
                else:
                    observation = f"[Tool '{action}' not available]"
            except Exception as e:
                observation = f"Error: {e}"
                is_error = True

            yield AgentStep(
                kind=StepKind.TOOL_END,
                tool_name=action,
                tool_use_id=tool_use_id,
                tool_result=observation[:2000],
                is_error=is_error,
            )

            # Feed observation back to LLM
            messages.append(Message(role="assistant", content=raw))
            messages.append(Message(role="user", content=f"Observation: {observation}"))

        # --- Max steps exhausted ---
        yield AgentStep(
            kind=StepKind.TEXT_DELTA,
            content=f"我已经连续尝试了 {max_steps} 步但仍未收敛。请换用「深度」模式重试。",
        )
        yield AgentStep(kind=StepKind.TEXT_END)
        yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")

    def _build_messages(self, ctx: RunContext) -> list:
        """Build initial [system, user] messages."""
        sys_text = REACT_SYSTEM_PROMPT.format(
            tools_desc=self._format_tools(ctx.tool_schemas)
        )
        if ctx.system_prefix:
            sys_text = f"{ctx.system_prefix}\n\n{sys_text}"
        user_text = ctx.messages[-1].content if ctx.messages else ""
        if ctx.context:
            user_text = f"{user_text}\n\n--- 上下文 ---\n{ctx.context}"
        return [
            Message(role="system", content=sys_text),
            Message(role="user", content=user_text),
        ]

    @staticmethod
    def _format_tools(schemas: list[dict]) -> str:
        """Render tool schemas as text for the system prompt."""
        lines = []
        for s in schemas:
            fn = s.get("function", s)
            name = fn.get("name", "?")
            desc = fn.get("description", "")[:80]
            lines.append(f"  - {name}: {desc}")
        return "\n".join(lines) if lines else "  (无工具)"


__all__ = ["ReActEngineV4"]
