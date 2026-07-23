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
    # v3.10 — Grok-Build-style thought blocks. Each segment of
    # reasoning gets a unique thought_id so the frontend can render
    # it as an independent block. Tool calls between thoughts
    # create natural boundaries (finish_thinking → new block).
    is_token: bool = False
    token: str = ""
    is_final_answer_token: bool = False
    # v3.10 — thought lifecycle events:
    #   'thought_start' — first token of a new thought segment
    #   'thought_delta' — subsequent tokens in the same segment
    #   'thought_end'   — thought segment finished (tool call or
    #                     FINAL_ANSWER started)
    thought_event: str = ""   # "" | "thought_start" | "thought_delta" | "thought_end"
    thought_id: str = ""      # unique id for the current thought segment


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
你是 MadCop 的智能体。通过"思考-行动-观察"循环解决用户问题。

每一步严格按以下格式输出:

Thought: <一句话描述你的推理，比如"用户需要X，我先查Y">
Action: <工具名称 或 FINAL_ANSWER>
Action Input: <工具参数JSON；FINAL_ANSWER 时直接写答案>

可用的工具:
{tools_desc}

规则:
1. **Thought 必须简短（1-2 句话）**，只描述"我要做什么、为什么"，用口语化的自然语言。
   禁止在 Thought 里写代码、命令、文件内容、JSON。代码只出现在 Action Input 里。
   ✅ 好的 Thought: "用户要写爬虫，我先搜一下 requests 库的用法"
   ❌ 坏的 Thought: "import requests\\nresponse = requests.get(url)..."（代码不该出现在 Thought 里）
2. 每次只执行一个 Action
3. 信息足够时直接 FINAL_ANSWER，不要过度思考
4. Action Input 调用工具时用合法 JSON；FINAL_ANSWER 时直接写 Markdown 纯文本
5. 连续 3 次工具调用失败就用已有信息 FINAL_ANSWER
6. 禁止对同一工具连续调用超过 2 次
7. 大多数问题不需要工具调用，第一次 Thought 后直接 FINAL_ANSWER
8. 用户问"你是什么模型"时调用 get_current_model
9. 写文件优先一次性写完，禁止对同一文件连续 write_file 两次。修改已有文件用 edit_file。
"""


# ── Parser ─────────────────────────────────────────────────────────── #

_THOUGHT_RE = re.compile(r"Thought:\s*(.*?)(?=\nAction:|$)", re.DOTALL)
_ACTION_RE = re.compile(r"Action:\s*(.*?)(?=\nAction Input:|$)", re.DOTALL)
_ACTION_INPUT_RE = re.compile(r"Action Input:\s*(.*)", re.DOTALL)


# v3.7.3 — bare 'FINAL_ANSWER: <text>' without an 'Action:' prefix.
# Some models learn to skip the Action line when they want to answer
# directly. We treat the body after the marker as the answer text.
_BARE_FA_RE = re.compile(r"FINAL_ANSWER\s*[:：]\s*(.*)", re.DOTALL | re.IGNORECASE)


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

    # v3.7.3 — some models skip the 'Action:' line entirely and
    # emit a bare 'FINAL_ANSWER: <text>' after the Thought. Detect
    # that and route to the FINAL_ANSWER branch.
    if not action:
        _bare = _BARE_FA_RE.search(text)
        if _bare:
            action = "FINAL_ANSWER"
            # Prefer the bare marker's body over any earlier (mismatched)
            # Action Input capture.
            action_input = _bare.group(1).strip()

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
    # Strip the 'FINAL_ANSWER:' / 'Final Answer:' prefix the ReAct
    # prompt asks the model to emit. Some models include the prefix
    # verbatim in the answer body instead of just using it as the
    # Action marker; without this strip the UI shows
    # 'FINAL_ANSWER: <actual reply>' as the reply.
    _FA_PREFIX_RE = re.compile(r"^\s*final[_ ]?answer\s*[:：]\s*", re.IGNORECASE)
    s = _FA_PREFIX_RE.sub("", s, count=1)
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

            # v3.9.1 — COT enforcement + stuck-loop reflection (sync path).
            if action.upper() != "FINAL_ANSWER" and not thought.strip():
                reflection = (
                    "你刚才尝试调用工具但没有先思考。"
                    "请先用 Thought 字段分析当前状况（1-2 句），"
                    "说明你要做什么、为什么。然后再写 Action 和 Action Input。"
                )
                messages.append(Message(role="assistant", content=raw))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue
            # v3.9.4 — loop detection includes the CURRENT step's
            # action. The previous version checked only the last
            # 2 completed steps, which meant the loop was only
            # detected at step 3+, allowing step 2 to be a
            # duplicate. Now we include the action the model is
            # about to take.
            last_actions = [
                s.action for s in steps[-2:]
                if s.action and s.action != "FINAL_ANSWER"
            ]
            # If the current step is non-final, the sequence of
            # recent actions is: last_actions + [action]
            recent = last_actions + ([action] if action.upper() != "FINAL_ANSWER" else [])
            is_same_tool_loop = (
                len(recent) >= 2
                and all(a == recent[0] for a in recent[-2:])
            )
            is_research_loop = (
                len(recent) >= 2
                and all(a in ("web_search", "web_fetch", "query_rag", "recall_memory")
                       for a in recent)
            )
            if is_same_tool_loop or is_research_loop:
                if is_research_loop:
                    reflection = (
                        "你已经连续调用了 2+ 次搜索类工具，"
                        "但还没有写代码或给答案。请停止搜索，"
                        "直接 FINAL_ANSWER 或 write_file。"
                    )
                else:
                    reflection = (
                        f"你已对 '{action}' 连续调用 2 次。"
                        "请停止循环：换工具或直接 FINAL_ANSWER。"
                    )
                messages.append(Message(role="assistant", content=raw))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue

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

            # Check max steps OR a "stuck" heuristic: if the model has been
            # calling tools without ever emitting a final answer, inject
            # the opencode-style "MAX_STEPS_PROMPT" early (on step 3+)
            # so the user doesn't have to wait for max_steps to hit. The
            # standard ReAct prompt's instruction "If you have enough
            # information, action = FINAL_ANSWER" should make this one
            # extra turn do the trick.
            if step_num >= self.max_steps or (
                step_num >= 3
                and final_answer == ""
                and not any(s.action.upper() == "FINAL_ANSWER" for s in steps)
            ):
                status = "max_steps" if step_num >= self.max_steps else "summary_forced"
                # Borrow opencode's MAX_STEPS_PROMPT pattern: inject a
                # synthetic user message asking the model to consolidate
                # what it knows and emit FINAL_ANSWER. One extra LLM
                # call; if it still won't answer, fall through to the
                # existing "max steps" message below.
                messages.append(Message(
                    role="user",
                    content=(
                        "你已调用了多个工具但还没有给出 FINAL_ANSWER。"
                        "请用以上工具的 Observation 总结你的结论并以"
                        "Thought: ... / Action: FINAL_ANSWER / Action Input: <总结> "
                        "格式回复。"
                    ),
                ))
                try:
                    resp = self.client.chat(messages, model=self.model, temperature=0.1)
                    _, f_action, f_input = parse_react_response(
                        getattr(resp, "content", "") or str(resp)
                    )
                    if f_action.upper() == "FINAL_ANSWER":
                        final_answer = normalize_final_answer(f_input)
                    else:
                        # Model still wanted to call a tool — just take
                        # the text content as the answer (it's all we have).
                        final_answer = (f_input or "").strip() or getattr(
                            resp, "content", ""
                        ) or str(resp)
                except Exception:
                    final_answer = "[达到最大步数，未能给出最终答案]"
                steps.append(ReActStep(
                    step_num=step_num,
                    thought="auto-summary after tool loop",
                    action="FINAL_ANSWER",
                    action_input=final_answer,
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                ))
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
        session_id: str | None = None,
    ) -> Iterator[ReActStep]:
        """Yield each step as it completes, for real-time UI updates.

        If ``session_id`` is set, drain mid-run steers between steps
        (Codex-style guidance without aborting the loop).
        """
        messages = self._build_initial_messages(task, context)
        # v3.9.1 — local steps list for stuck-loop detection.
        _steps: list = []
        # v3.10 — Grok-Build-style thought block tracking. Each
        # segment of reasoning gets a unique thought_id. The first
        # token of a new segment emits 'thought_start'; subsequent
        # tokens emit 'thought_delta'; tool call / FINAL_ANSWER
        # emits 'thought_end'.
        _thought_id_counter = 0
        _thought_active = False  # is a thought segment currently open?

        def _new_thought_id():
            nonlocal _thought_id_counter
            _thought_id_counter += 1
            return f"thought-{_thought_id_counter}"

        for step_num in range(1, self.max_steps + 1):
            # Inject steers before each LLM call (including the first after
            # a tool step). First iteration only has steers that arrived
            # after the run started.
            if session_id:
                try:
                    from madcop.server.steer_queue import (
                        drain_steers,
                        format_steer_block,
                    )
                    steers = drain_steers(session_id)
                    if steers:
                        messages.append(Message(
                            role="user",
                            content=format_steer_block(steers),
                        ))
                except Exception:
                    pass

            step_start = time.time()

            # v3.7.2 — Token-level streaming with live FINAL_ANSWER
            # detection. As tokens stream in we watch for the
            # 'Action: FINAL_ANSWER' marker. Once we see it, every
            # subsequent token (after the 'Action Input:' line) is
            # flagged is_final_answer_token=True so the chat handler
            # can route them straight to the assistant message bubble
            # instead of the thinking panel — the user watches the
            # final reply form token-by-token, opencode-style.
            raw = ""
            saw_stream_error = False
            stream_error_msg = ""
            # Streaming parse state:
            #   0 = haven't seen 'Action:' yet (token goes to reasoning)
            #   1 = saw 'Action: FINAL_ANSWER' but not 'Action Input:'
            #       yet (still reasoning — usually whitespace/newline)
            #   2 = past 'Action Input:' — token is final-answer text
            _stream_state = 0
            # Match either 'Action: FINAL_ANSWER' (canonical) or a
            # bare 'FINAL_ANSWER:' that some models emit without the
            # 'Action:' prefix when they want to skip the tool step.
            # v3.7.8 — also match 'FINAL_ANSWER' followed by newline
            # or end-of-text (no colon), because many models write
            # 'Action: FINAL_ANSWER\nAction Input:' — the FINAL_ANSWER
            # token is followed by \n, not ':'.
            _FA_MARKER = re.compile(
                r"(?:Action\s*[:：]\s*)?FINAL_ANSWER\b\s*[:：\n]",
                re.IGNORECASE,
            )
            # The 'Action Input:' marker is only used in the canonical
            # format. When the model emits a bare FINAL_ANSWER:, the
            # answer text follows on the same line / next line. We
            # treat everything after the marker as answer text.
            _AI_MARKER = re.compile(r"Action\s*Input\s*[:：]", re.IGNORECASE)

            try:
                if hasattr(self.client, "stream"):
                    # v3.7.4 — protocol-marker filter for reasoning.
                    # The raw model output contains 'Thought:',
                    # 'Action:', 'Action Input:' markers that are
                    # internal protocol — the user should see only
                    # the natural-language thinking. We strip them
                    # at the regex level after each chunk: any of
                    # these markers (with optional spaces around the
                    # colon) is removed from the emitted text. The
                    # accumulated `raw` is left untouched so the
                    # parser at the end still sees the full structure.
                    _PROTOCOL_RE = re.compile(
                        r"(Thought|Action\s*Input|Action|Observation)"
                        r"\s*[:：]\s*",
                        re.IGNORECASE,
                    )

                    for chunk in self.client.stream(
                        messages,
                        model=self.model,
                        temperature=0.1,
                        max_tokens=2048,
                    ):
                        text = getattr(chunk, "text", "") or ""
                        if text:
                            raw += text
                            if _stream_state == 0:
                                if _FA_MARKER.search(raw):
                                    # v3.10 — close the current thought block
                                    # before switching to final-answer streaming.
                                    if _thought_active:
                                        _thought_active = False
                                        yield ReActStep(
                                            step_num=step_num, is_token=False,
                                            thought_event="thought_end",
                                            thought_id=_cur_tid,
                                        )
                                    # v3.7.8 — FINAL_ANSWER detected.
                                    # Jump straight to state 2 so the
                                    # answer body streams into the
                                    # reply bubble. Skip emitting this
                                    # chunk to reasoning — it only
                                    # contained the marker text.
                                    _stream_state = 2
                                    # If this chunk also has answer
                                    # text past the marker (model put
                                    # it on the same line), emit the
                                    # post-marker tail as a final-
                                    # answer token.
                                    _m = _FA_MARKER.search(raw)
                                    if _m:
                                        _tail = raw[_m.end():]
                                        _tail = _tail.lstrip(" \t\n")
                                        if _tail:
                                            yield ReActStep(
                                                step_num=step_num, is_token=True,
                                                token=_tail,
                                                is_final_answer_token=True,
                                            )
                                            self._fa_leading_trimmed = True
                                else:
                                    # Strip any protocol markers from
                                    # the user-facing reasoning text.
                                    emit = _PROTOCOL_RE.sub("", text)
                                    if emit:
                                        # v3.10 — Grok-Build-style thought
                                        # blocks. First token of a new
                                        # segment → thought_start; rest →
                                        # thought_delta. The frontend uses
                                        # these to render independent
                                        # thinking blocks (not one big
                                        # accumulated string).
                                        if not _thought_active:
                                            _thought_active = True
                                            _cur_tid = _new_thought_id()
                                            yield ReActStep(
                                                step_num=step_num, is_token=True,
                                                token=emit,
                                                is_final_answer_token=False,
                                                thought_event="thought_start",
                                                thought_id=_cur_tid,
                                            )
                                        else:
                                            yield ReActStep(
                                                step_num=step_num, is_token=True,
                                                token=emit,
                                                is_final_answer_token=False,
                                                thought_event="thought_delta",
                                                thought_id=_cur_tid,
                                            )
                            elif _stream_state == 1:
                                if _AI_MARKER.search(raw):
                                    _stream_state = 2
                                elif _FA_MARKER.search(raw):
                                    # v3.7.8 — bare FINAL_ANSWER without
                                    # an 'Action Input:' line. The model
                                    # wrote 'FINAL_ANSWER: <answer>' or
                                    # 'Action: FINAL_ANSWER\n<answer>'
                                    # directly. Switch to final-answer
                                    # streaming so subsequent tokens
                                    # route to the reply bubble, not
                                    # the reasoning panel.
                                    _stream_state = 2
                                else:
                                    emit = _PROTOCOL_RE.sub("", text)
                                    if emit:
                                        yield ReActStep(
                                            step_num=step_num, is_token=True,
                                            token=emit,
                                            is_final_answer_token=False,
                                        )
                            else:  # _stream_state == 2
                                _clean = text
                                if not getattr(self, "_fa_leading_trimmed", False):
                                    _clean = _clean.lstrip(" \t\n")
                                    if _clean:
                                        self._fa_leading_trimmed = True
                                if _clean:
                                    yield ReActStep(
                                        step_num=step_num, is_token=True,
                                        token=_clean,
                                        is_final_answer_token=True,
                                    )
                        fr = getattr(chunk, "finish_reason", None)
                        if fr:
                            break
                    self._fa_leading_trimmed = False
                else:
                    resp = self.client.chat(
                        messages, model=self.model,
                        temperature=0.1, max_tokens=2048,
                    )
                    raw = getattr(resp, "content", "") or str(resp)
            except Exception as e:
                saw_stream_error = True
                stream_error_msg = f"LLM call failed: {e}"

            if saw_stream_error:
                yield ReActStep(
                    step_num=step_num, error=stream_error_msg,
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                )
                return

            thought, action, action_input = parse_react_response(raw)

            # v3.10 — close any open thought block when we transition
            # to a tool call or FINAL_ANSWER. Grok-Build pattern: each
            # tool call boundary ends the current thinking segment.
            if _thought_active:
                _thought_active = False
                yield ReActStep(
                    step_num=step_num, is_token=False,
                    thought_event="thought_end",
                    thought_id=_cur_tid,
                )

            # v3.9.1 — COT enforcement. If the model emitted a tool
            # call without ANY Thought text, don't execute it. Force
            # a reflection turn instead — "you have to think before
            # acting". Skipping this was letting the model call
            # tools 12 times in a row with empty thoughts, which
            # caused the 'write_file repeated 12x' loop the user
            # reported.
            if action.upper() != "FINAL_ANSWER" and not thought.strip():
                reflection = (
                    "你刚才尝试调用工具但没有先思考。"
                    "请先用 Thought 字段分析当前状况（1-2 句），"
                    "说明你要做什么、为什么。然后再写 Action 和 Action Input。"
                )
                yield ReActStep(
                    step_num=step_num, thought=reflection,
                    action="", action_input="",
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                )
                # Inject the reflection as a fake Observation so the
                # next iteration sees it and re-reasons.
                messages.append(Message(role="assistant", content=raw))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue

            # v3.9.1 — stuck-loop reflection. Detect two patterns:
            # (a) the same tool called 2+ times in a row
            # (b) two "research" tools (web_search / web_fetch / query_rag)
            #     called in sequence, suggesting the model is stuck
            #     in a "search more" loop without writing anything.
            # In both cases inject a reflection forcing re-planning.
            # v3.9.4 — include the CURRENT step's action. Previously we
            # only checked the last 2 completed steps, so step 2 of
            # a loop (when only step 1 was completed) was never
            # caught. Now we project the upcoming action into the
            # history before checking.
            last_actions = [
                s.action for s in _steps[-2:]
                if s.action and s.action != "FINAL_ANSWER"
            ]
            recent = last_actions + ([action] if action.upper() != "FINAL_ANSWER" else [])
            is_same_tool_loop = (
                len(recent) >= 2
                and all(a == recent[0] for a in recent[-2:])
            )
            is_research_loop = (
                len(recent) >= 2
                and all(a in ("web_search", "web_fetch", "query_rag", "recall_memory")
                       for a in recent)
            )
            if is_same_tool_loop or is_research_loop:
                if is_research_loop:
                    reflection = (
                        "你已经连续调用了 2+ 次搜索类工具（web_search / web_fetch），"
                        "但还没有尝试写代码或直接给答案。\n"
                        "请停止搜索，直接：\n"
                        "1. 基于已知信息给出最佳答案（用 FINAL_ANSWER）\n"
                        "2. 或调用 write_file 直接写代码\n"
                        "3. 不要再调用任何搜索工具"
                    )
                else:
                    reflection = (
                        f"你已对同一工具 '{action}' 连续调用了 2 次以上。"
                        "请停止这个循环，改为：\n"
                        "1. 反思之前的失败原因（Observation 里有什么错误？）\n"
                        "2. 如果该工具不适合当前任务，**换其他工具**或直接 FINAL_ANSWER\n"
                        "3. 如果必须再试一次，先在 Thought 里说明和上次有什么不同"
                    )
                yield ReActStep(
                    step_num=step_num, thought=reflection,
                    action="", action_input="",
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                )
                messages.append(Message(role="assistant", content=raw))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue

            if action.upper() == "FINAL_ANSWER":
                # Last chance: if user steered while we were generating the
                # final answer, do not exit — inject and continue loop.
                if session_id:
                    try:
                        from madcop.server.steer_queue import (
                            drain_steers,
                            format_steer_block,
                        )
                        steers = drain_steers(session_id)
                        if steers:
                            messages.append(Message(role="assistant", content=raw))
                            messages.append(Message(
                                role="user",
                                content=(
                                    format_steer_block(steers)
                                    + "\n\n请根据上述指引继续，不要立刻结束；"
                                    "需要工具就调用，否则再 FINAL_ANSWER。"
                                ),
                            ))
                            continue
                    except Exception:
                        pass
                step = ReActStep(
                    step_num=step_num, thought=thought,
                    action="FINAL_ANSWER", action_input=action_input,
                    elapsed_ms=round((time.time() - step_start) * 1000, 1),
                )
                yield step
                return

            observation = ""
            error = None
            # v3.9.3 — Human-in-the-Loop gate for destructive tools.
            # Instead of executing directly, return a 'wait for human
            # confirmation' Observation. The model will see this and
            # either: (a) wait for the user's reply via ask_user, or
            # (b) back off and use a safer tool. This keeps the loop
            # safe without requiring frontend HITL infrastructure.
            try:
                from madcop.tools.safety import danger_level, validate_tool_input
                level = danger_level(action)
                if level == "destructive":
                    # Don't execute. Tell the model to ask the user
                    # first via ask_user, or pick a safer tool.
                    observation = (
                        f"工具 {action!r} 被标记为 'destructive' (高危操作)，"
                        "需要用户确认后才能执行。\n"
                        "请改用 ask_user 工具向用户确认是否真的要执行，"
                        "或者改用更安全的工具（如 read_file、web_search）。\n"
                        "如果你认为这个操作很必要，请调用 ask_user 并提供："
                        "\n  question: \"要执行 <具体操作> 吗？\""
                        "\n  options: [\"是，执行\", \"否，换其他方式\"]"
                    )
                    error = "destructive_tool_needs_human_confirmation"
                else:
                    observation = self._execute_tool(action, action_input, work_dir)
            except ImportError:
                observation = self._execute_tool(action, action_input, work_dir)
            except Exception as e:
                error = str(e)
                observation = f"Error: {e}"
            # Tools return a dict — many wrap failures inside
            # {"error": "..."} without raising, so we have to fish
            # the error out explicitly. Without this, plan_step status
            # would always be "completed" even when the file write
            # actually failed.
            if error is None and isinstance(observation, dict):
                _obs_err = observation.get("error")
                if _obs_err:
                    error = str(_obs_err)

            step = ReActStep(
                step_num=step_num, thought=thought,
                action=action, action_input=action_input,
                observation=observation, error=error,
                elapsed_ms=round((time.time() - step_start) * 1000, 1),
            )
            _steps.append(step)  # for stuck-loop detection
            yield step

            messages.append(Message(role="assistant", content=raw))
            messages.append(Message(
                role="user", content=f"Observation: {observation}",
            ))

        # v3.7.3 — Loop exhausted without a FINAL_ANSWER. This used
        # to silently leave _answer empty, which surfaced to the user
        # as "（本轮未产生可见回复...）" — a dead-end. Instead, do one
        # final LLM call with an explicit instruction to synthesise
        # an answer from the observations gathered so far. This is
        # the same pattern the sync run() uses when it detects the
        # agent is looping (see app.py:321 'summary_forced').
        try:
            messages.append(Message(
                role="user",
                content=(
                    "你已达到最大步数上限。请基于上方所有 Observation，"
                    "用 FINAL_ANSWER 给出一个尽量有用的回答。"
                    "如果确实信息不足，也要明确告诉用户当前已收集到什么、"
                    "还缺什么、建议下一步怎么做。禁止再调用工具。"
                ),
            ))
            if hasattr(self.client, "stream"):
                _forced_raw = ""
                for chunk in self.client.stream(
                    messages, model=self.model,
                    temperature=0.2, max_tokens=2048,
                ):
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        _forced_raw += text
                        yield ReActStep(
                            step_num=self.max_steps + 1,
                            is_token=True, token=text,
                            is_final_answer_token=True,
                        )
                    if getattr(chunk, "finish_reason", None):
                        break
            else:
                _forced_resp = self.client.chat(
                    messages, model=self.model,
                    temperature=0.2, max_tokens=2048,
                )
                _forced_raw = getattr(_forced_resp, "content", "") or str(_forced_resp)
                # Parse out the FINAL_ANSWER body if present.
                _, _, _forced_ai = parse_react_response(_forced_raw)
                yield ReActStep(
                    step_num=self.max_steps + 1,
                    thought="", action="FINAL_ANSWER",
                    action_input=_forced_ai,
                    elapsed_ms=0.0,
                )
        except Exception as e:
            # Last-resort: yield a FINAL_ANSWER that explains the loop
            # hit the step limit. Better than silence.
            yield ReActStep(
                step_num=self.max_steps + 1,
                thought="达到步数上限，强制结束。",
                action="FINAL_ANSWER",
                action_input=(
                    f"我已经连续尝试了 {self.max_steps} 步但仍未收敛。"
                    "请尝试把问题拆得更具体一些，或换用「深度」模式重试。"
                    f"（内部错误: {e}）"
                ),
                elapsed_ms=0.0,
            )

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

        # v3.9.2 — Pydantic safety guardrail. Validate the tool input
        # BEFORE execution. If validation fails, return the error as
        # observation (closed-loop repair — the model sees the
        # validation error and can self-correct on the next step).
        from madcop.tools.safety import validate_tool_input, danger_level
        ok, validation_err, _validated = validate_tool_input(tool_name, args)
        if not ok:
            return f"工具 {tool_name!r} 输入校验失败:\n{validation_err}"
        # If the tool is destructive, we require HITL confirmation.
        # The ReActEngine doesn't know about user prompts, so we just
        # NOTE the danger level in the observation and let the
        # chat handler gate the actual execution. (The actual
        # HITL prompt is wired in app.py — see HITL adapter below.)
        level = danger_level(tool_name)
        if level == "destructive":
            # We don't block here; the chat handler may have
            # already gated it. We just tag the observation.
            pass

        # Add work_dir to args for file tools
        if work_dir:
            args.setdefault("work_dir", work_dir)
            args.setdefault("cwd", work_dir)

        # Unknown tool? registry.get() raises KeyError, so check first.
        if tool_name not in registry:
            available = registry.names()
            return f"[Tool '{tool_name}' not found. Available: {', '.join(available)}"

        # Permission check — opencode-style rules. We surface DENY
        # back to the model as an Observation so it can pick a different
        # tool. ASK is currently treated as ALLOW here (we don't have the
        # ask-permission UI plumbing yet — that's a follow-up). Hook
        # is in place so adding `ASK → emit a permission_request event`
        # is a one-line change later.
        try:
            from madcop.tools.tool_permissions import check_tool, ToolPermissionError, ASK
            verdict = check_tool(tool_name)
            if verdict == "deny":
                raise ToolPermissionError(tool_name, tool_name, "deny")
            # verdict == "ask" is logged but currently passed through;
            # the user can re-evaluate by tightening rules in the
            # settings UI when this becomes a real prompt.
            if verdict == "ask":
                import logging as _logging
                _logging.getLogger(__name__).info(
                    "tool %s matches an 'ask' rule; running with default consent",
                    tool_name,
                )
        except ToolPermissionError:
            raise
        except Exception:
            # Permission system must never block tool execution if
            # itself is broken — log and fall through.
            pass

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
