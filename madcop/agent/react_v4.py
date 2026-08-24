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
from madcop.agent_network.react_engine import (
    REACT_SYSTEM_PROMPT,
    parse_react_response,
    normalize_final_answer,
)
from madcop.llm.client import Message


# Protocol markers to strip from reasoning text
_PROTOCOL_RE = re.compile(
    r"(Thought|Action\s*Input|Action|Observation)"
    r"\s*[:：]\s*",
    re.IGNORECASE,
)
_FA_MARKER = re.compile(
    r"(?:Action\s*[:：]\s*)?FINAL_ANSWER\b\s*[:：\n]"
    r"(?:\s*Action\s*Input\s*[:：]\s*)?",  # also consume a following "Action Input:" line
    re.IGNORECASE,
)
_AI_MARKER = re.compile(r"Action\s*Input\s*[:：]", re.IGNORECASE)
_BARE_FA_RE = re.compile(r"FINAL_ANSWER\s*[:：]\s*(.*)", re.DOTALL | re.IGNORECASE)

# D1 fix: strip <think>...</think> blocks before a raw response is appended
# back into the LLM context. Think content is for the DISPLAY layer
# (ThinkSeparator routes it to THOUGHT_DELTA); the next ReAct iteration
# must never re-receive chain-of-thought — it inflates tokens and re-leaks
# reasoning the design says to discard.
_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


def _context_clean(text: str) -> str:
    """Strip think blocks + leftover think tags for LLM-context use."""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = re.sub(r"</?think>", "", cleaned)
    return cleaned.strip()


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
            # ThinkSeparator: MiniMax/DeepSeek/Qwen put reasoning in
            # <think>...</think> tags in content. Split them so reasoning
            # goes to THOUGHT_DELTA (visible thinking) and the answer goes
            # to TEXT_DELTA — instead of dumping everything as thought or
            # leaking <think> tags into the answer.
            from .runtime import ThinkSeparator
            _think_sep = ThinkSeparator()
            _think_block_open = False
            self._v4_answer_buf = ''  # accumulate post-think text for ReAct detection
            # BUG-FIX: when MiniMax / similar OpenAI-compatible models are
            # given a ReAct-style text prompt, they emit tool calls in the
            # wrong shape ("web_searchAction Input: {...}" as plain text),
            # which the Action/Input parser then misreads as a brand-new
            # tool name. Instead, pass `tools=ctx.tool_schemas` so the model
            # uses the standard OpenAI tool_calls field, then prefer that
            # path when present.
            oa_tc_name: str | None = None
            oa_tc_args: str = ""
            # Track per-index args to handle parallel tool_calls — the
            # engine executes ONE tool per step, so we use the FIRST
            # tool call's args (index 0) and ignore later indices.
            oa_tc_seen_indices: set[int] = set()
            oa_tc_id: str | None = None
            # P0-1: providers report length-stops via finish_reason on the
            # final chunk. Tracked so the parse stage can void tool calls
            # whose arguments may have been cut mid-stream.
            _finish_reason: str | None = None

            try:
                if hasattr(ctx.client, "stream"):
                    for chunk in ctx.client.stream(
                        messages,
                        model=ctx.model,
                        temperature=0.1,
                        max_tokens=8192,
                        tools=ctx.tool_schemas or None,
                    ):
                        _fr_chunk = getattr(chunk, "finish_reason", None)
                        if _fr_chunk:
                            _finish_reason = _fr_chunk
                        # Capture OpenAI-style tool_call deltas if any.
                        for d in (getattr(chunk, "tool_call_deltas", None) or ()):
                            if not isinstance(d, dict):
                                continue
                            if d.get("id"):
                                oa_tc_id = d["id"]
                            if d.get("name"):
                                oa_tc_name = d["name"]
                            if d.get("arguments") and d.get("index", 0) == 0:
                                oa_tc_args += d["arguments"]
                        # Non-streaming fallback (some clients only emit
                        # the full tool_call at the end).
                        end_tc = getattr(chunk, "tool_call", None)
                        if end_tc is not None and not oa_tc_name:
                            if hasattr(end_tc, "name"):
                                oa_tc_name = end_tc.name
                                oa_tc_args = (
                                    json.dumps(end_tc.arguments, ensure_ascii=False)
                                    if not isinstance(end_tc.arguments, str)
                                    else end_tc.arguments
                                )
                            elif isinstance(end_tc, dict):
                                oa_tc_name = end_tc.get("function", {}).get("name") or oa_tc_name
                                a = end_tc.get("function", {}).get("arguments")
                                if a:
                                    oa_tc_args = a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)

                        text = getattr(chunk, "text", "") or ""
                        if not text:
                            fr = getattr(chunk, "finish_reason", None)
                            if fr:
                                break
                            continue
                        raw += text

                        # BUG-FIX: MiniMax after </think> often outputs
                        # "Action: web_search\nAction Input: {...}" as TEXT
                        # (not OpenAI tool_calls). ThinkSeparator would route
                        # this as answer text. Instead, detect ReAct protocol
                        # markers in the post-think output and let the legacy
                        # state-0 ReAct parser handle them (which knows how to
                        # extract Action/Action Input and emit tool calls).
                        #
                        # Strategy: feed to ThinkSeparator, but if the ANSWER
                        # portion contains Action:/FINAL_ANSWER:, DON'T stream
                        # it — accumulate it so parse_react_response at stream
                        # end can extract the tool call.
                        _reasoning_chunk, _answer_chunk = _think_sep.feed(text)

                        # Route reasoning → THOUGHT_DELTA (visible thinking)
                        if _reasoning_chunk:
                            _emit_r = _PROTOCOL_RE.sub("", _reasoning_chunk)
                            if _emit_r:
                                if not _think_block_open:
                                    _think_block_open = True
                                    thought_active = True
                                    thought_counter += 1
                                    cur_tid = f"thought-{thought_counter}"
                                    yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=cur_tid)
                                yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=cur_tid, content=_emit_r)

                        # If we just exited <think>, close the thought block
                        # and switch to answer streaming (state 2).
                        if _answer_chunk and _think_block_open and not _think_sep.in_think:
                            yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=cur_tid,
                                            elapsed_ms=int((time.time() - step_start) * 1000))
                            thought_active = False
                            _think_block_open = False
                            stream_state = 2  # switch to answer mode

                        # Route answer → TEXT_DELTA
                        # BUG-FIX: MiniMax after </think> may output a MIX of
                        # prose (": 用户想知道...") AND ReAct protocol
                        # ("Action: web_search\nAction Input: {...}"). We can't
                        # know if it's answer or protocol until we've seen the
                        # full post-think output. So: BUFFER all post-think
                        # text, and only stream it as answer IF we're confident
                        # it's NOT protocol text.
                        #
                        # Strategy: buffer until we either (a) see a protocol
                        # marker (→ keep buffering, let parse_react_response
                        # handle at stream end), or (b) accumulate >30 chars
                        # with NO markers (→ flush buffer as answer, switch to
                        # direct streaming). This prevents the race where "T"
                        # gets streamed before "Thought:" arrives.
                        if _answer_chunk:
                            self._v4_answer_buf = getattr(self, '_v4_answer_buf', '') + _answer_chunk
                            _full_answer = self._v4_answer_buf
                            _has_react_markers = bool(re.search(
                                r'(Action\s*[:：]|Action\s*Input\s*[:：]|FINAL_ANSWER\s*[:：]|Thought\s*[:：])',
                                _full_answer, re.IGNORECASE
                            ))
                            if _has_react_markers:
                                # Protocol text detected — buffer everything.
                                # parse_react_response at stream end handles it.
                                pass
                            elif len(_full_answer) > 30:
                                # 30+ chars with NO protocol markers → this is
                                # a real answer. Flush the buffer and switch to
                                # direct streaming for the rest.
                                if not fa_streamed:
                                    fa_streamed = True
                                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=_full_answer.lstrip(" \t\n"))
                                else:
                                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=_answer_chunk)
                                stream_state = 2
                            # else: <30 chars, no markers yet — keep buffering.

                        # If ThinkSeparator handled this chunk (reasoning or
                        # answer), skip state-0 ReAct logic.
                        _handled = bool(_reasoning_chunk) or bool(_answer_chunk)
                        if _handled:
                            fr = getattr(chunk, "finish_reason", None)
                            if fr:
                                break
                            continue

                        if stream_state == 0:
                            # BUG-FIX: scan the ANSWER buffer (post-think
                            # text only), never `raw` — raw also contains
                            # <think> content, and a model that merely
                            # *mentions* "FINAL_ANSWER" while thinking
                            # used to hijack the stream into answer mode,
                            # then dump raw thinking + <think> tags into
                            # TEXT_DELTA (duplicated thinking, leaked tags).
                            _abuf = getattr(self, '_v4_answer_buf', '')
                            if _FA_MARKER.search(_abuf):
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
                                m = _FA_MARKER.search(_abuf)
                                if m:
                                    tail = _abuf[m.end():].lstrip(" \t\n")
                                    # BUG: models write "Action: FINAL_ANSWER
                                    # \nAction Input:\n\n<answer>" — the tail
                                    # then starts with a stray "Action Input:"
                                    # line that leaked into the answer. Strip
                                    # any leading protocol lines from the tail.
                                    tail = re.sub(
                                        r'^(Action\s*Input|Input|Action|Observation)\s*[:：]\s*',
                                        '', tail, flags=re.IGNORECASE
                                    ).lstrip(" \t\n")
                                    if tail:
                                        fa_streamed = True
                                        yield AgentStep(kind=StepKind.TEXT_DELTA, content=tail)
                            else:
                                emit = _PROTOCOL_RE.sub("", text)
                                # Strip stray think-tag fragments — tag-close
                                # chunks produce empty separator output and
                                # fall through here, leaking "</think>" into
                                # the visible thought stream.
                                emit = re.sub(r'</?think>', '', emit)
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
                            # If the separator is holding back a partial
                            # "<thi"/"</thi" prefix across a chunk boundary,
                            # DON'T emit this chunk — the tag resolves on the
                            # next chunk and leaking the fragment as answer
                            # text corrupts the stream.
                            if getattr(_think_sep, '_buf', ''):
                                fr = getattr(chunk, "finish_reason", None)
                                if fr:
                                    break
                                continue
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
            # BUG-FIX: if ThinkSeparator already streamed the answer (model
            # used <think> tags), DON'T run parse_react_response — the answer
            # is already in the stream. Running the ReAct parser on MiniMax
            # output causes duplicate answer loops.
            #
            # D3 fix: BUT if the model ALSO emitted an OpenAI tool_call
            # (prose like "Let me search that" + tool_call deltas), the
            # tool must win — returning early here dropped the call and
            # the user got neither the search nor a correct answer.
            if fa_streamed and not oa_tc_name:
                yield AgentStep(kind=StepKind.TEXT_END)
                yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")
                return

            # If ThinkSeparator buffered post-think text but didn't stream it
            # (protocol markers detected OR <30 chars), handle at stream end.
            _buf = getattr(self, '_v4_answer_buf', '')
            if _buf and not fa_streamed and not oa_tc_name:
                _has_action = bool(re.search(r'Action\s*[:：]', _buf, re.IGNORECASE))
                if not _has_action:
                    # No Action — model gave up on ReAct. Strip protocol
                    # prefixes (Thought:, :, etc.) and output as answer.
                    _clean = _buf.strip()
                    _clean = re.sub(
                        r'^[\s:：]*(Thought|Action|FINAL_ANSWER|Observation)\s*[:：]\s*',
                        '', _clean, flags=re.IGNORECASE
                    )
                    _clean = re.sub(r'^[\s:：]+', '', _clean).strip()
                    if _clean:
                        yield AgentStep(kind=StepKind.TEXT_DELTA, content=_clean)
                    yield AgentStep(kind=StepKind.TEXT_END)
                    yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")
                    return

            thought, action, action_input = parse_react_response(raw)

            # BUG-FIX: if the LLM emitted a proper OpenAI tool_calls object
            # (via `tools=ctx.tool_schemas` we now pass to client.stream),
            # prefer that over the text-parsed result. This is critical for
            # models like MiniMax that don't follow ReAct text format and
            # would otherwise emit garbage like "web_searchAction Input: {...}"
            # which the parser then misreads as a brand-new tool name.
            if oa_tc_name:
                action = oa_tc_name
                action_input = oa_tc_args or action_input
                # If no text thought was emitted, fall back to the raw text
                # (which is the model's "reasoning" preamble) so COT
                # enforcement below still passes.
                if not thought.strip():
                    thought = raw.strip() or f"Calling {action}"

            # Close any open thought block
            if thought_active:
                thought_active = False
                yield AgentStep(
                    kind=StepKind.THOUGHT_END,
                    thought_id=cur_tid,
                    elapsed_ms=int((time.time() - step_start) * 1000),
                )

            # P0-1 — truncation safety: a length-stopped response may carry
            # tool-call arguments that were cut mid-stream; executing them
            # (e.g. writing half a file) is worse than asking the model to
            # resend. Void ALL tool calls this turn and feed the error back
            # as an observation so the model retries in the next step.
            # (Same policy as pi agent-loop.ts:208-214.)
            if (
                _finish_reason == "length"
                and action.strip()
                and action.upper() != "FINAL_ANSWER"
            ):
                messages.append(Message(role="assistant", content=_context_clean(raw)))
                messages.append(Message(role="user", content=(
                    "Observation: [error] 本次响应因长度上限被截断"
                    "（finish_reason=length），工具调用参数可能不完整，未执行。"
                    "请重新发起该工具调用，可适当精简参数或分步完成。"
                )))
                continue

            # --- COT enforcement ---
            if action.upper() != "FINAL_ANSWER" and not thought.strip():
                reflection = (
                    "你刚才尝试调用工具但没有先思考。"
                    "请先用 Thought 分析当前状况，然后再写 Action。"
                )
                messages.append(Message(role="assistant", content=_context_clean(raw)))
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
                messages.append(Message(role="assistant", content=_context_clean(raw)))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue

            steps_log.append(action)

            # BUG-FIX: if the parser returned an empty action name (happens
            # when the model emits free-form text without 'Action:' markers
            # and without FINAL_ANSWER), don't try to call a tool named ''.
            # Instead treat the raw text as a thought + prompt the model to
            # either call a tool properly or give FINAL_ANSWER.
            if not action.strip():
                reflection = (
                    "你的回复没有包含有效的 Action 或 FINAL_ANSWER。"
                    "请用 'Thought: ...\\nAction: tool_name\\nAction Input: {...}' "
                    "格式调用工具，或 'Action: FINAL_ANSWER\\nFINAL_ANSWER: 你的回答' 结束。"
                )
                messages.append(Message(role="assistant", content=_context_clean(raw)))
                messages.append(Message(role="user", content=f"Observation: {reflection}"))
                continue

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
            # Parse args. BUG-FIX: some models (MiniMax in ReAct mode)
            # occasionally emit MULTIPLE JSON objects concatenated
            # (e.g. {"query":"a"}{"query":"b"}) when they want to fire
            # two searches at once. json.loads rejects that, and the old
            # fallback stuffed the whole blob into {"path": ...} which
            # broke web_search ("path" is not a valid param). Now we try
            # to extract the FIRST valid JSON object via regex; only if
            # that also fails do we fall back to the path/query shape.
            args: dict = {}
            _ai = action_input.strip()
            if _ai:
                try:
                    args = json.loads(_ai)
                except json.JSONDecodeError:
                    # Try to find the first {...} block (handles concat JSON
                    # and surrounding ReAct prose like 'Input: {"query":...}')
                    _m = re.search(r'\{[^{}]*\}', _ai, re.DOTALL)
                    if _m:
                        try:
                            args = json.loads(_m.group(0))
                        except json.JSONDecodeError:
                            args = {"query": _ai[:200], "path": _ai[:200]}
                    else:
                        args = {"query": _ai[:200], "path": _ai[:200]}

            yield AgentStep(
                kind=StepKind.TOOL_START,
                tool_name=action,
                tool_input=args,
                tool_use_id=tool_use_id,
            )

            # HITL confirmation: if the tool is mutating AND confirm_handler
            # is set, ask the user before executing.
            _approved = True
            if ctx.confirm_handler:
                try:
                    from madcop.tools.safety import needs_confirmation
                    if needs_confirmation(action):
                        yield AgentStep(
                            kind=StepKind.TOOL_CONFIRM_REQUEST,
                            tool_name=action,
                            tool_input=args,
                            tool_use_id=tool_use_id,
                        )
                        _approved = ctx.confirm_handler(action, args, tool_use_id)
                except Exception:
                    _approved = True

            if not _approved:
                observation = "[用户拒绝了此操作]"
                is_error = True
                yield AgentStep(
                    kind=StepKind.TOOL_END,
                    tool_name=action,
                    tool_use_id=tool_use_id,
                    tool_result=observation,
                    is_error=True,
                )
                messages.append(Message(role="assistant", content=_context_clean(raw)))
                messages.append(Message(role="user", content=f"Observation: {observation}"))
                continue

            # Execute tool. _approved carries the HITL decision (True
            # when no confirmation was needed OR the user approved the
            # card) — forward it so the executor's destructive gate
            # doesn't reject an already-approved call.
            observation = ""
            is_error = False
            tool_meta: dict[str, Any] = {}
            try:
                if ctx.tool_executor:
                    try:
                        raw_result = ctx.tool_executor(
                            action, action_input, ctx.work_dir,
                            pre_approved=_approved,
                        )
                    except TypeError:
                        # Executor doesn't accept pre_approved (older
                        # bridge) — call without it.
                        raw_result = ctx.tool_executor(action, action_input, ctx.work_dir)
                    # Allow executors to return either a str (legacy) or a
                    # ``ToolResult`` dataclass with structured fields. We
                    # prefer the structured form so the frontend can show
                    # the failure category (validation / timeout / etc).
                    if hasattr(raw_result, "to_observation") and hasattr(raw_result, "is_error"):
                        from madcop.agent.tool_executor import ToolResult as _TR
                        if isinstance(raw_result, _TR):
                            observation = raw_result.to_observation()
                            is_error = bool(raw_result.is_error)
                            tool_meta = {
                                "is_validation_error": raw_result.is_validation_error,
                                "is_timeout": raw_result.is_timeout,
                                "needs_confirmation": raw_result.needs_confirmation,
                                "elapsed_ms": raw_result.elapsed_ms,
                            }
                        else:
                            observation = str(raw_result)
                    else:
                        observation = str(raw_result)
                else:
                    observation = f"[Tool '{action}' not available]"
            except Exception as e:
                observation = f"[error] {e}"
                is_error = True

            yield AgentStep(
                kind=StepKind.TOOL_END,
                tool_name=action,
                tool_use_id=tool_use_id,
                tool_result=observation[:2000],
                is_error=is_error,
                metadata=tool_meta,
            )

            # P2-4 — ask_user / clarify: yield a CLARIFY AgentStep so the
            # frontend can render a question + options bubble, then break
            # out of the loop so the user can actually answer. The
            # legacy ReAct path emits `clarification_request` SSE (see
            # app.py:2599); v4 emits CLARIFY AgentStep which useSSEStream
            # already knows how to render.
            if action.strip().lower() in ("ask_user", "clarify") and not is_error:
                try:
                    _clarify_payload = json.loads(observation)
                except Exception:
                    _clarify_payload = {}
                if isinstance(_clarify_payload, dict) and _clarify_payload.get("__clarify_pending__"):
                    yield AgentStep(
                        kind=StepKind.CLARIFY,
                        tool_name=action,
                        tool_use_id=tool_use_id,
                        question=_clarify_payload.get("question", ""),
                        options=list(_clarify_payload.get("options", []) or []),
                    )
                    return  # pause the loop; the user's next send re-enters run()

            # Feed observation back to LLM
            messages.append(Message(role="assistant", content=_context_clean(raw)))
            messages.append(Message(role="user", content=f"Observation: {observation}"))

        # --- Max steps exhausted ---
        yield AgentStep(
            kind=StepKind.TEXT_DELTA,
            content=f"我已经连续尝试了 {max_steps} 步但仍未收敛。请换用「深度」模式重试。",
        )
        yield AgentStep(kind=StepKind.TEXT_END)
        yield AgentStep(kind=StepKind.DONE, model=ctx.model or "")

    def _build_messages(self, ctx: RunContext) -> list:
        """Build initial [system, user] messages.

        Supports multi-turn history: the full ctx.messages list is
        included as a conversation block in the user prompt so the
        LLM sees prior turns.
        """
        from datetime import datetime, timezone, timedelta
        tz_cn = timezone(timedelta(hours=8))
        now_str = datetime.now(tz_cn).strftime("%Y年%m月%d日 %H:%M 北京时间 (UTC+8)")
        utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sys_text = REACT_SYSTEM_PROMPT.format(
            tools_desc=self._format_tools(ctx.tool_schemas),
            current_time=f"{now_str} / {utc_str}",
        )
        if ctx.system_prefix:
            sys_text = f"{ctx.system_prefix}\n\n{sys_text}"

        # D6 fix: preserve role structure — pass multi-turn history
        # through as native messages instead of flattening everything
        # into one "[role] content" user prompt. Flattening destroyed
        # the user/assistant alternation the model was trained on and
        # made every prior turn look like user input.
        msgs = list(ctx.messages or [])
        if not msgs:
            msgs = [Message(role="user", content="")]

        out = [Message(role="system", content=sys_text)]
        for m in msgs:
            # Sanitize: strip think blocks from any historical assistant
            # turns (D1 — reasoning must never re-enter context).
            content = _context_clean(m.content or "") if m.role == "assistant" else (m.content or "")
            if not content and m.role == "assistant":
                continue  # skip empty assistant turns (all-think content)
            out.append(Message(role=m.role or "user", content=content))

        # Append context as a final user note if present.
        if ctx.context:
            out.append(Message(role="user", content=f"--- 上下文 ---\n{ctx.context}"))
        return out

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
