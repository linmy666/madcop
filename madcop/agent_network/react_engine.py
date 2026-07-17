"""ReAct execution engine — Thought -> Action -> Observation loop.

This is the single-agent reasoning core. Unlike the multi-agent DAG
engine (engine.py), ReAct runs one LLM in a loop where it:

1. **Thinks** about the problem (reasoning step)
2. **Acts** by requesting a tool call (read_file, run_command, etc.)
3. **Observes** the tool result and loops back to step 1

The loop terminates when the agent emits a FINAL_ANSWER action or
hits the max_steps limit.

Design:
  - Uses the existing madcop.tools registry for tool dispatch
  - Streams intermediate steps for UI visualization
  - Fully synchronous (no asyncio) since tool calls are blocking
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from madcop.llm import Message
from madcop.llm.client import ChatClient, MockClient, ToolCall


# ── Step types ─────────────────────────────────────────────────────── #

@dataclass
class ReActStep:
    """One step in the ReAct loop."""
    step_num: int
    thought: str = ""
    action: str = ""          # tool name or "FINAL_ANSWER"
    action_input: str = ""    # tool args (JSON string or plain text)
    observation: str = ""
    elapsed_ms: float = 0.0
    error: str | None = None


@dataclass
class ReActResult:
    """Full ReAct execution result."""
    task: str
    final_answer: str
    steps: list[ReActStep] = field(default_factory=list)
    status: str = "completed"  # completed | max_steps | error
    total_elapsed_ms: float = 0.0
    tool_calls: int = 0
    started_at: str = ""


# ── System prompt ──────────────────────────────────────────────────── #

REACT_SYSTEM_PROMPT = """\
你是 MadCop 的 ReAct agent。你需要通过"思考-行动-观察"循环来解决用户的问题。

每一步你必须严格按照以下格式输出（不要输出其他内容）:

Thought: <你的推理过程，分析当前状况，决定下一步做什么>
Action: <工具名称 或 FINAL_ANSWER>
Action Input: <工具参数，JSON格式；如果是 FINAL_ANSWER 则直接输出最终答案>

可用的工具:
{tools_desc}

规则:
1. 每次只执行一个 Action
2. 如果信息足够回答问题，Action 设为 FINAL_ANSWER
3. Action Input：调用工具时用合法 JSON；FINAL_ANSWER 时直接写 Markdown 纯文本，
   不要包成 {{"message":"..."}} JSON，不要用 \\n 转义换行
4. 不要编造观察结果，只能基于真实的 Observation
5. 如果连续 3 次工具调用都失败，直接用已有信息给出 FINAL_ANSWER
6. 禁止无意义地反复调用 echo；需要展示内容时写在 FINAL_ANSWER 里
"""


# ── Parser ─────────────────────────────────────────────────────────── #

_THOUGHT_RE = re.compile(r"Thought:\s*(.*?)(?=\nAction:|$)", re.DOTALL)
_ACTION_RE = re.compile(r"Action:\s*(.*?)(?=\nAction Input:|$)", re.DOTALL)
_ACTION_INPUT_RE = re.compile(r"Action Input:\s*(.*)", re.DOTALL)


def parse_react_response(text: str) -> tuple[str, str, str]:
    """Parse an LLM response into (thought, action, action_input).

    Returns empty strings for missing fields.
    """
    thought = ""
    action = ""
    action_input = ""

    m = _THOUGHT_RE.search(text)
    if m:
        thought = m.group(1).strip()

    m = _ACTION_RE.search(text)
    if m:
        action = m.group(1).strip()

    m = _ACTION_INPUT_RE.search(text)
    if m:
        action_input = m.group(1).strip()

    # Fallback: if no structured format found, treat whole thing as final answer
    if not action and not thought:
        action = "FINAL_ANSWER"
        action_input = text.strip()

    return thought, action, action_input


def normalize_final_answer(text: str) -> str:
    """Unwrap models that put the user-facing reply in JSON.

    Some providers emit FINAL_ANSWER as::

        {"message": "markdown\\nwith\\nescapes"}

    or a double-encoded string. Return clean markdown for the UI.
    """
    if not text:
        return text
    s = text.strip()
    # Strip common code fences
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    for _ in range(3):
        if not (s.startswith("{") and s.endswith("}")) and not (s.startswith('"') and s.endswith('"')):
            break
        try:
            parsed = json.loads(s)
        except Exception:
            break
        if isinstance(parsed, dict):
            for key in ("message", "answer", "content", "text", "final_answer", "result"):
                if key in parsed and isinstance(parsed[key], str) and parsed[key].strip():
                    s = parsed[key].strip()
                    break
            else:
                # No known field — pretty-print remaining dict only if tiny
                break
        elif isinstance(parsed, str):
            s = parsed.strip()
        else:
            break
    # Literal \n sequences left by partial escaping
    if "\\n" in s and s.count("\n") < s.count("\\n"):
        s = s.replace("\\n", "\n").replace("\\t", "\t")
    return s


# ── Engine ─────────────────────────────────────────────────────────── #

class ReActEngine:
    """Single-agent ReAct loop executor.

    Usage:
        engine = ReActEngine(client, tools=tool_list)
        result = engine.run("fix the bug in auth.py", work_dir="/project")

    For streaming:
        for step in engine.run_stream(task, work_dir):
            print(f"Step {step.step_num}: {step.action}")
    """

    def __init__(
        self,
        client: ChatClient,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Callable[..., Any] | None = None,
        max_steps: int = 10,
        model: str | None = None,
        system_prefix: str = "",
    ) -> None:
        self.client = client
        self.tools = tools or []
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        self.model = model
        # Optional role framing (deep-mode specialists) prepended to REACT prompt.
        self.system_prefix = (system_prefix or "").strip()
        # Build tools description for system prompt
        self._tools_desc = self._format_tools_desc()

    def _format_tools_desc(self) -> str:
        """Build the tools list for the system prompt."""
        if not self.tools:
            return "(无可用工具 — 请直接用 FINAL_ANSWER 回答)"
        lines = []
        for t in self.tools:
            name = t.get("name", t.get("function", {}).get("name", "unknown"))
            desc = t.get("description", t.get("function", {}).get("description", ""))
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def run(
        self,
        task: str,
        work_dir: str | None = None,
        context: str = "",
    ) -> ReActResult:
        """Execute the ReAct loop and return the final result.

        Args:
            task: The user's task/question.
            work_dir: Working directory for file operations.
            context: Additional context (previous messages, file tree, etc.)

        Returns:
            ReActResult with all steps and the final answer.
        """
        started = time.time()
        iso_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        steps: list[ReActStep] = []
        messages: list[Message] = self._build_initial_messages(task, context)

        final_answer = ""
        status = "completed"
        tool_calls = 0

        for step_num in range(1, self.max_steps + 1):
            step_start = time.time()

            # Call LLM
            try:
                resp = self.client.chat(
                    messages,
                    model=self.model,
                    temperature=0.1,
                    max_tokens=4096,
                )
                raw = getattr(resp, "content", "") or str(resp)
            except Exception as e:
                steps.append(ReActStep(
                    step_num=step_num, error=f"LLM call failed: {e}",
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                ))
                status = "error"
                final_answer = f"[ReAct engine error: {e}]"
                break

            # Parse response
            thought, action, action_input = parse_react_response(raw)

            # Check for final answer
            if action.upper() == "FINAL_ANSWER":
                final_answer = normalize_final_answer(action_input)
                steps.append(ReActStep(
                    step_num=step_num, thought=thought,
                    action="FINAL_ANSWER", action_input=final_answer,
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                ))
                break

            # Execute tool
            observation = ""
            error = None
            try:
                observation = self._execute_tool(action, action_input, work_dir)
                tool_calls += 1
            except Exception as e:
                error = str(e)
                observation = f"Error executing {action}: {e}"

            step = ReActStep(
                step_num=step_num, thought=thought,
                action=action, action_input=action_input,
                observation=observation,
                error=error,
                elapsed_ms=round((time.time() - step_start) * 1000, 1),
            )
            steps.append(step)

            # Append assistant response + observation to message history
            messages.append(Message(role="assistant", content=raw))
            messages.append(Message(
                role="user",
                content=f"Observation: {observation}",
            ))

            # Check max steps
            if step_num >= self.max_steps:
                status = "max_steps"
                # Ask for final answer with one more call
                messages.append(Message(
                    role="user",
                    content="已达到最大步数。请用已有信息给出 FINAL_ANSWER。",
                ))
                try:
                    resp = self.client.chat(messages, model=self.model, temperature=0.1)
                    _, _, action_input = parse_react_response(
                        getattr(resp, "content", "") or str(resp)
                    )
                    final_answer = action_input
                except Exception:
                    final_answer = "[达到最大步数，未能给出最终答案]"
                break

        total_ms = round((time.time() - started) * 1000, 1)

        return ReActResult(
            task=task,
            final_answer=final_answer,
            steps=steps,
            status=status,
            total_elapsed_ms=total_ms,
            tool_calls=tool_calls,
            started_at=iso_started,
        )

    def run_stream(
        self,
        task: str,
        work_dir: str | None = None,
        context: str = "",
    ) -> Iterator[ReActStep]:
        """Yield each step as it completes, for real-time UI updates."""
        started = time.time()
        messages = self._build_initial_messages(task, context)

        for step_num in range(1, self.max_steps + 1):
            step_start = time.time()

            try:
                resp = self.client.chat(
                    messages, model=self.model,
                    temperature=0.1, max_tokens=2048,
                )
                raw = getattr(resp, "content", "") or str(resp)
            except Exception as e:
                yield ReActStep(
                    step_num=step_num, error=f"LLM call failed: {e}",
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                )
                return

            thought, action, action_input = parse_react_response(raw)

            if action.upper() == "FINAL_ANSWER":
                step = ReActStep(
                    step_num=step_num, thought=thought,
                    action="FINAL_ANSWER", action_input=action_input,
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                )
                yield step
                return

            observation = ""
            error = None
            try:
                observation = self._execute_tool(action, action_input, work_dir)
            except Exception as e:
                error = str(e)
                observation = f"Error: {e}"

            step = ReActStep(
                step_num=step_num, thought=thought,
                action=action, action_input=action_input,
                observation=observation, error=error,
                elapsed_ms=round((time.time() - step_start) * 1000, 1),
            )
            yield step

            messages.append(Message(role="assistant", content=raw))
            messages.append(Message(
                role="user", content=f"Observation: {observation}",
            ))

    def _build_initial_messages(self, task: str, context: str) -> list[Message]:
        """Build the starting message list with system prompt + user task."""
        sys = REACT_SYSTEM_PROMPT.format(tools_desc=self._tools_desc)
        if self.system_prefix:
            sys = f"{self.system_prefix}\n\n{sys}"
        user = task
        if context:
            user = f"{task}\n\n--- 上下文 ---\n{context}"
        return [
            Message(role="system", content=sys),
            Message(role="user", content=user),
        ]

    def _execute_tool(
        self,
        tool_name: str,
        action_input: str,
        work_dir: str | None,
    ) -> str:
        """Execute a tool call and return the observation string.

        Uses the injected tool_executor if available, otherwise falls
        back to the madcop.tools registry.
        """
        if self.tool_executor:
            return str(self.tool_executor(tool_name, action_input, work_dir))

        # Try the madcop tool registry
        try:
            from madcop.tools import default_registry
        except ImportError:
            return f"[Tool '{tool_name}' not available — no registry]"

        # default_registry is a *factory function*; call it (passing
        # work_dir so file tools may write to the active workspace).
        registry = default_registry(workspace_dir=work_dir)

        # Parse args
        try:
            args = json.loads(action_input) if action_input.strip() else {}
        except json.JSONDecodeError:
            # Non-JSON input — treat as a single 'path' or 'query' arg
            args = {"path": action_input.strip(), "query": action_input.strip()}

        # Add work_dir to args for file tools
        if work_dir:
            args.setdefault("work_dir", work_dir)
            args.setdefault("cwd", work_dir)

        # Unknown tool? registry.get() raises KeyError, so check first.
        if tool_name not in registry:
            available = registry.names()
            return f"[Tool '{tool_name}' not found. Available: {', '.join(available)}]"

        # Dispatch via the registry — returns a proper ToolResult with
        # to_message_content(), and converts exceptions into .error.
        result = registry.dispatch(ToolCall(id="", name=tool_name, arguments=args))
        return result.to_message_content()


# ── Convenience ────────────────────────────────────────────────────── #

def build_react_engine(
    model: str | None = None,
    max_steps: int = 10,
) -> ReActEngine:
    """Build a ReActEngine using the active LLM client + default tools."""
    from madcop.config import settings as settings_store
    from madcop.llm.factory import build_client_from_config

    s = settings_store.load_settings()
    cfg = settings_store.get_active_client_config(s)
    if cfg and model:
        cfg = {**cfg, "model": model}

    client = build_client_from_config(
        cfg,
        timeout=120.0,
        mock_message=(
            "Thought: I cannot proceed without API configuration.\n"
            "Action: FINAL_ANSWER\n"
            "Action Input: [No API key configured — ReAct engine disabled]"
        ),
    )
    active_model = model or ((cfg or {}).get("model") if cfg else model)

    # Collect available tools from the registry
    try:
        from madcop.tools import default_registry
        tools = default_registry().openai_schemas()
    except Exception:
        tools = []

    return ReActEngine(
        client=client,
        tools=tools,
        max_steps=max_steps,
        model=active_model,
    )
