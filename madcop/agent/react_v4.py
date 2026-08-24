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
        # P1-5: token usage summed across this run's LLM calls; attached
        # to the DONE step for the UI's context budget indicator.
        _run_usage: dict[str, Any] = {}
        # P2-9: trace root for this turn (the chat route creates a
        # user_input root and passes its id via ctx; MEA/fallbacks get
        # their own turn node). All llm/tool spans parent to it.
        _trace_root_id = getattr(ctx, "_trace_root_id", None)
        if not _trace_root_id:
            try:
                from madcop.agent.trace import start_span
                _trace_root_id = start_span(
                    ctx.session_id or "", None, "turn",
                    label=(ctx.messages[-1].content or "")[:60] if ctx.messages else "",
                )
            except Exception:
                _trace_root_id = None

        for step_num in range(1, max_steps + 1):
            step_start = time.time()
            _step_usage: dict[str, Any] = {}
            # P2-9: one llm_call span per engine step.
            try:
                from madcop.agent.trace import start_span as _ts
                _llm_span_id = _ts(
                    ctx.session_id or "", _trace_root_id, "llm_call",
                    label=f"step {step_num}",
                    input_data={"messages": len(messages)},
                )
            except Exception:
                _llm_span_id = None

            # --- LLM call with streaming + FINAL_ANSWER detection ---
            raw = ""
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
            oa_tc_id: str | None = None
            # P0-3: accumulate ALL tool_calls by index so parallel calls
            # execute instead of being dropped after index 0.
            oa_calls: dict[int, dict] = {}
            # P0-1: providers report length-stops via finish_reason on the
            # final chunk. Tracked so the parse stage can void tool calls
            # whose arguments may have been cut mid-stream.
            _finish_reason: str | None = None

            try:
                if hasattr(ctx.client, "stream"):
                    # P1-8 — replay-safe retry: connection-level
                    # failures (zero chunks received) retry with backoff;
                    # mid-stream failures propagate and surface as a
                    # resumable ERROR instead of silently restarting the
                    # stream (duplicated content). cf. OpenAI Agents SDK
                    # retry.py's approve_unsafe_replay split.
                    from madcop.llm.retry import stream_with_retry
                    _chunk_iter = stream_with_retry(
                        lambda: ctx.client.stream(
                            messages,
                            model=ctx.model,
                            temperature=0.1,
                            max_tokens=8192,
                            tools=ctx.tool_schemas or None,
                        ),
                        label=f"react-step-{step_num}",
                    )
                    for chunk in _chunk_iter:
                        _fr_chunk = getattr(chunk, "finish_reason", None)
                        if _fr_chunk:
                            _finish_reason = _fr_chunk
                        # Capture OpenAI-style tool_call deltas if any.
                        # P0-3: accumulate per-index so parallel calls all
                        # reach execution; oa_tc_name/oa_tc_args keep the
                        # index-0 view for the existing single-call logic.
                        for d in (getattr(chunk, "tool_call_deltas", None) or ()):
                            if not isinstance(d, dict):
                                continue
                            _slot = oa_calls.setdefault(
                                d.get("index", 0) or 0,
                                {"id": None, "name": None, "args": ""},
                            )
                            if d.get("id"):
                                _slot["id"] = d["id"]
                                oa_tc_id = d["id"]
                            if d.get("name"):
                                _slot["name"] = d["name"]
                            if d.get("arguments"):
                                _slot["args"] += d["arguments"]
                        # Non-streaming fallback (some clients only emit
                        # the full tool_call at the end).
                        end_tc = getattr(chunk, "tool_call", None)
                        if end_tc is not None and not oa_calls:
                            if hasattr(end_tc, "name"):
                                oa_calls[0] = {
                                    "id": getattr(end_tc, "id", None),
                                    "name": end_tc.name,
                                    "args": (
                                        json.dumps(end_tc.arguments, ensure_ascii=False)
                                        if not isinstance(end_tc.arguments, str)
                                        else end_tc.arguments
                                    ),
                                }
                            elif isinstance(end_tc, dict):
                                _fn = end_tc.get("function", {}) or {}
                                a = _fn.get("arguments")
                                oa_calls[0] = {
                                    "id": end_tc.get("id"),
                                    "name": _fn.get("name"),
                                    "args": a if isinstance(a, str) or a is None else json.dumps(a, ensure_ascii=False),
                                }
                        if 0 in oa_calls:
                            oa_tc_name = oa_calls[0]["name"] or oa_tc_name
                            oa_tc_args = oa_calls[0]["args"] or oa_tc_args

                        text = getattr(chunk, "text", "") or ""
                        # P1-5: capture token usage (providers send it on
                        # the final chunk; we drain the stream instead of
                        # breaking on finish_reason so it isn't missed).
                        _u = getattr(chunk, "usage", None)
                        if _u:
                            if isinstance(_u, dict):
                                _step_usage = dict(_u)
                            else:  # dataclass-style usage object
                                _step_usage = {
                                    "prompt_tokens": getattr(_u, "prompt_tokens", 0) or 0,
                                    "completion_tokens": getattr(_u, "completion_tokens", 0) or 0,
                                    "total_tokens": getattr(_u, "total_tokens", 0) or 0,
                                }
                        if not text:
                            fr = getattr(chunk, "finish_reason", None)
                            if fr:
                                _finish_reason = fr
                            continue
                        raw += text

                        # P0-2: text flows through exactly ONE router —
                        # the ThinkSeparator. <think> content goes to the
                        # THOUGHT channel live; post-think text buffers
                        # and streams out progressively while it stays
                        # free of text-protocol markers. The old state-0/
                        # state-2 machine (FA-marker scanning, mid-stream
                        # protocol stripping) is deleted: native
                        # tool_calls are the PRIMARY protocol, and the
                        # text protocol is parsed once at stream end as a
                        # fallback for providers without function calling.
                        _reasoning_chunk, _answer_chunk = _think_sep.feed(text)

                        # Route reasoning → THOUGHT_DELTA (visible thinking)
                        if _reasoning_chunk:
                            _emit_r = re.sub(
                                r'</?think>', '',
                                _PROTOCOL_RE.sub("", _reasoning_chunk),
                            )
                            if _emit_r:
                                if not _think_block_open:
                                    _think_block_open = True
                                    thought_active = True
                                    thought_counter += 1
                                    cur_tid = f"thought-{thought_counter}"
                                    yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=cur_tid)
                                yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=cur_tid, content=_emit_r)

                        # If we just exited <think>, close the thought block.
                        if _answer_chunk and _think_block_open and not _think_sep.in_think:
                            yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=cur_tid,
                                            elapsed_ms=int((time.time() - step_start) * 1000))
                            thought_active = False
                            _think_block_open = False

                        # Post-think text → buffered answer, streamed
                        # progressively ONLY while free of protocol
                        # markers (buffered protocol text is parsed at
                        # stream end — streaming it raw would leak
                        # "Action: ..." into the answer).
                        if _answer_chunk:
                            self._v4_answer_buf = getattr(self, '_v4_answer_buf', '') + _answer_chunk
                            _full_answer = self._v4_answer_buf
                            _has_react_markers = bool(re.search(
                                r'(Action\s*[:：]|Action\s*Input\s*[:：]|FINAL_ANSWER\s*[:：]|Thought\s*[:：])',
                                _full_answer, re.IGNORECASE
                            ))
                            if not _has_react_markers:
                                if not fa_streamed and len(_full_answer) > 30:
                                    fa_streamed = True
                                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=_full_answer.lstrip(" \t\n"))
                                elif fa_streamed:
                                    yield AgentStep(kind=StepKind.TEXT_DELTA, content=_answer_chunk)
                            # else: markers present → keep buffering for
                            # the stream-end text-protocol parse.

                        # Drain to the iterator's natural end (the client
                        # appends a final usage-bearing chunk after
                        # finish_reason — breaking here used to miss it).
                        fr = getattr(chunk, "finish_reason", None)
                        if fr:
                            _finish_reason = fr
                else:
                    resp = ctx.client.chat(
                        messages, model=ctx.model,
                        temperature=0.1, max_tokens=2048,
                    )
                    raw = getattr(resp, "content", "") or str(resp)
            except Exception as e:
                from madcop.llm.retry import classify_stream_error
                _err_info = classify_stream_error(e)
                yield AgentStep(
                    kind=StepKind.ERROR,
                    content=f"LLM call failed ({_err_info.category}): {e}",
                    # P1-8: mid-stream failures are replayable-by-user —
                    # the frontend can offer a retry button knowing the
                    # category; the engine never auto-replays them.
                    metadata={
                        "error_category": _err_info.category,
                        "replay_safe": False,
                    },
                )
                return

            # P1-5: fold this call's usage into the run total (prompt
            # tokens of later calls already include earlier context —
            # the LAST call's prompt_tokens + sum(completion) is the
            # closest proxy for live context size; we keep both views).
            if _step_usage:
                _prev_prompt = _run_usage.get("prompt_tokens", 0)
                _run_usage = {
                    "prompt_tokens": max(_prev_prompt, _step_usage.get("prompt_tokens", 0)),
                    "completion_tokens": (
                        _run_usage.get("completion_tokens", 0)
                        + _step_usage.get("completion_tokens", 0)
                    ),
                }
                _run_usage["total_tokens"] = (
                    _run_usage["prompt_tokens"] + _run_usage["completion_tokens"]
                )

            # P2-9: close this step's llm_call span with its summary.
            try:
                from madcop.agent.trace import finish_span as _fs
                _fs(_llm_span_id, {
                    "finish_reason": _finish_reason,
                    "usage": _step_usage,
                    "tool_calls": [c.get("name") for c in oa_calls.values() if c.get("name")],
                    "answer_chars": len(getattr(self, "_v4_answer_buf", "") or ""),
                })
            except Exception:
                pass

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
                yield AgentStep(kind=StepKind.DONE, model=ctx.model or "",
                        metadata={"usage": _run_usage})
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
                    yield AgentStep(kind=StepKind.DONE, model=ctx.model or "",
                        metadata={"usage": _run_usage})
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

            # Text-protocol fallback only: surface the parsed Thought as a
            # visible thought block. Live streaming isn't possible for
            # buffered protocol text, but the reasoning shouldn't vanish
            # from the timeline either. (<think>-tag models streamed theirs
            # above; this is only for providers without function calling.)
            # The oa-override stuffs raw (tag-bearing) text into `thought`
            # for the COT check — strip think tags before displaying.
            _fb_thought = _context_clean(thought).strip()
            if _fb_thought and not _think_block_open and not fa_streamed:
                thought_counter += 1
                cur_tid = f"thought-{thought_counter}"
                yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=cur_tid)
                yield AgentStep(
                    kind=StepKind.THOUGHT_DELTA, thought_id=cur_tid,
                    content=_fb_thought[:2000],
                )
                yield AgentStep(
                    kind=StepKind.THOUGHT_END, thought_id=cur_tid,
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
                yield AgentStep(kind=StepKind.DONE, model=ctx.model or "",
                        metadata={"usage": _run_usage})
                return

            # --- Tool calls — batch execution (P0-3) ---
            # The batch is ALL native tool_calls when the provider sent
            # any, else the single text-protocol call. Free (non-danger)
            # calls run in a bounded concurrent pool; confirm-needed
            # calls run sequentially, one HITL card at a time (Claude
            # Code style). A single failing call never cancels its
            # siblings (failure isolation, cf. OpenAI Agents SDK
            # tool_execution.py).
            _native = [
                {"name": c["name"], "raw": c["args"]}
                for _, c in sorted(oa_calls.items()) if c.get("name")
            ]
            _calls = _native if _native else [{"name": action, "raw": action_input}]
            for _i, _c in enumerate(_calls):
                _c["use_id"] = (
                    f"tool-{step_num}" if len(_calls) == 1
                    else f"tool-{step_num}-{_i + 1}"
                )

            # If the batch contains ask_user/clarify it PAUSES the loop —
            # run only that call (the user's next send re-enters run()).
            _clarify_idx = next(
                (i for i, c in enumerate(_calls)
                 if (c["name"] or "").strip().lower() in ("ask_user", "clarify")),
                None,
            )
            if _clarify_idx is not None:
                _calls = [_calls[_clarify_idx]]

            def _parse_call_args(raw_args: str) -> tuple[dict, str]:
                """Parse one call's args → (args, error).

                Clean JSON → nested-brace extraction (HTML/JS payloads)
                → first flat block (concat JSON) → CLEAN failure (never
                execute with stuffed defaults).
                """
                args: dict = {}
                ai = (raw_args or "").strip()
                if not ai:
                    return {}, ""
                try:
                    return json.loads(ai), ""
                except json.JSONDecodeError:
                    pass
                m = re.search(r'\{.*\}', ai, re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group(0)), ""
                    except json.JSONDecodeError:
                        m2 = re.search(r'\{[^{}]*\}', m.group(0), re.DOTALL)
                        if m2:
                            try:
                                return json.loads(m2.group(0)), ""
                            except json.JSONDecodeError:
                                pass
                return (
                    {"_raw": ai[:200]},
                    "[error] 工具参数 JSON 解析失败（常见原因：字符串值内的"
                    "引号/换行未转义）。请重新调用并用合法 JSON 传参，大段"
                    "文本内容请确保内部双引号转义为 \\\" 。",
                )

            def _exec_one(name: str, args: dict, approved: bool):
                """Execute one tool via ctx.tool_executor → (obs, is_err, meta)."""
                obs, is_err, meta = "", False, {}
                # P2-9: tool_call span under this step's llm span.
                try:
                    from madcop.agent.trace import start_span as _ts2
                    _tool_span = _ts2(
                        ctx.session_id or "",
                        _llm_span_id or _trace_root_id,
                        "tool_call", label=name, input_data=args,
                    )
                except Exception:
                    _tool_span = None
                _t0 = time.time()
                try:
                    if ctx.tool_executor:
                        _exec_input = (
                            json.dumps(args, ensure_ascii=False) if args else ""
                        )
                        try:
                            raw_result = ctx.tool_executor(
                                name, _exec_input, ctx.work_dir,
                                pre_approved=approved,
                            )
                        except TypeError:
                            raw_result = ctx.tool_executor(name, _exec_input, ctx.work_dir)
                        if hasattr(raw_result, "to_observation") and hasattr(raw_result, "is_error"):
                            from madcop.agent.tool_executor import ToolResult as _TR
                            if isinstance(raw_result, _TR):
                                obs = raw_result.to_observation()
                                is_err = bool(raw_result.is_error)
                                meta = {
                                    "is_validation_error": raw_result.is_validation_error,
                                    "is_timeout": raw_result.is_timeout,
                                    "needs_confirmation": raw_result.needs_confirmation,
                                    "elapsed_ms": raw_result.elapsed_ms,
                                }
                            else:
                                obs = str(raw_result)
                        else:
                            obs = str(raw_result)
                    else:
                        obs = f"[Tool '{name}' not available]"
                except Exception as e:  # failure isolation for the pool
                    obs, is_err = f"[error] {e}", True
                try:
                    from madcop.agent.trace import finish_span as _fs2
                    _fs2(_tool_span, {
                        "ok": not is_err,
                        "elapsed_ms": int((time.time() - _t0) * 1000),
                        "output": (obs or "")[:300],
                    })
                except Exception:
                    pass
                return obs, is_err, meta

            # Phase A — parse args, split free vs confirm-needed.
            _results: list[tuple[dict, str, bool, dict]] = []  # (call, obs, is_err, meta)
            _free: list[tuple[dict, dict]] = []
            _confirm: list[tuple[dict, dict]] = []
            _needs_conf_fn = None
            if ctx.confirm_handler:
                try:
                    from madcop.tools.safety import needs_confirmation as _needs_conf_fn
                except Exception:
                    _needs_conf_fn = None

            for _c in _calls:
                _args, _perr = _parse_call_args(_c["raw"])
                if _perr:
                    yield AgentStep(
                        kind=StepKind.TOOL_START,
                        tool_name=_c["name"], tool_input=_args,
                        tool_use_id=_c["use_id"],
                    )
                    yield AgentStep(
                        kind=StepKind.TOOL_END,
                        tool_name=_c["name"], tool_use_id=_c["use_id"],
                        tool_result=_perr, is_error=True,
                        metadata={"is_validation_error": True},
                    )
                    _results.append((_c, _perr, True, {"is_validation_error": True}))
                    continue
                # P2-12: PreToolUse hooks fire BEFORE the free/confirm
                # split so they can veto ANY tool call (including the
                # HITL-confirm ones, where the engine would otherwise
                # block on user approval for a destructive op).
                _veto = False
                if getattr(ctx, "hooks", None):
                    from .hooks import HookEvent, HookContext
                    _hr = ctx.hooks.run(HookContext(
                        event=HookEvent.PRE_TOOL_USE,
                        tool_name=_c["name"],
                        tool_input=dict(_args),
                        turn_id=str(step_num),
                        conversation_id=ctx.session_id or "",
                    ))
                    if not _hr.continue_:
                        _err = _hr.error or "[hook] 调用被拒绝"
                        yield AgentStep(
                            kind=StepKind.TOOL_START,
                            tool_name=_c["name"], tool_input=_args,
                            tool_use_id=_c["use_id"],
                        )
                        yield AgentStep(
                            kind=StepKind.TOOL_END,
                            tool_name=_c["name"], tool_use_id=_c["use_id"],
                            tool_result=_err, is_error=True,
                            metadata={"is_hook_rejected": True},
                        )
                        _results.append((_c, _err, True, {"is_hook_rejected": True}))
                        _veto = True
                    else:
                        if _hr.modified_input is not None:
                            _args = _hr.modified_input
                            _c["raw"] = json.dumps(_args, ensure_ascii=False)
                        if _hr.extra_observation:
                            _c["hook_obs"] = _hr.extra_observation
                if _veto:
                    continue
                if _needs_conf_fn and _needs_conf_fn(_c["name"]):
                    _confirm.append((_c, _args))
                else:
                    _free.append((_c, _args))

            # Phase B — free calls run concurrently (bounded pool).
            if _free:
                for _c, _a in _free:
                    yield AgentStep(
                        kind=StepKind.TOOL_START,
                        tool_name=_c["name"], tool_input=_a,
                        tool_use_id=_c["use_id"],
                    )
                import concurrent.futures as _cf
                with _cf.ThreadPoolExecutor(max_workers=min(4, len(_free))) as _pool:
                    _futs = {
                        _pool.submit(_exec_one, _c["name"], _a, True): _c
                        for _c, _a in _free
                    }
                    for _fut in _cf.as_completed(_futs):
                        _c = _futs[_fut]
                        _obs, _ierr, _meta = _fut.result()
                        # P2-12: PostToolUse hooks may append observations
                        if getattr(ctx, "hooks", None):
                            from .hooks import HookEvent, HookContext as _HC
                            _pr = ctx.hooks.run(_HC(
                                event=HookEvent.POST_TOOL_USE,
                                tool_name=_c["name"], tool_input=dict(_a),
                                tool_result=_obs, is_error=_ierr,
                                turn_id=str(step_num),
                                conversation_id=ctx.session_id or "",
                            ))
                            if _pr.extra_observation and _obs is not None:
                                _obs = str(_obs) + "\n" + _pr.extra_observation
                        yield AgentStep(
                            kind=StepKind.TOOL_END,
                            tool_name=_c["name"], tool_use_id=_c["use_id"],
                            tool_result=(_obs or "")[:2000],
                            is_error=_ierr, metadata=_meta,
                        )
                        _results.append((_c, _obs, _ierr, _meta))

            # Phase C — confirm-needed calls: one HITL card at a time.
            for _c, _a in _confirm:
                yield AgentStep(
                    kind=StepKind.TOOL_START,
                    tool_name=_c["name"], tool_input=_a,
                    tool_use_id=_c["use_id"],
                )
                yield AgentStep(
                    kind=StepKind.TOOL_CONFIRM_REQUEST,
                    tool_name=_c["name"], tool_input=_a,
                    tool_use_id=_c["use_id"],
                )
                _approved = True
                try:
                    _approved = ctx.confirm_handler(_c["name"], _a, _c["use_id"])
                except Exception:
                    _approved = True
                if not _approved:
                    yield AgentStep(
                        kind=StepKind.TOOL_END,
                        tool_name=_c["name"], tool_use_id=_c["use_id"],
                        tool_result="[用户拒绝了此操作]", is_error=True,
                    )
                    _results.append((_c, "[用户拒绝了此操作]", True, {}))
                    continue
                _obs, _ierr, _meta = _exec_one(_c["name"], _a, True)
                # P2-12: PostToolUse hooks may append observations
                # (e.g. "the file just changed — consider formatting").
                if getattr(ctx, "hooks", None):
                    from .hooks import HookEvent, HookContext
                    _pctx = HookContext(
                        event=HookEvent.POST_TOOL_USE,
                        tool_name=_c["name"],
                        tool_input=dict(_a),
                        tool_result=_obs, is_error=_ierr,
                        turn_id=str(step_num),
                        conversation_id=ctx.session_id or "",
                    )
                    _pr = ctx.hooks.run(_pctx)
                    if _pr.extra_observation and _obs is not None:
                        _obs = str(_obs) + "\n" + _pr.extra_observation
                yield AgentStep(
                    kind=StepKind.TOOL_END,
                    tool_name=_c["name"], tool_use_id=_c["use_id"],
                    tool_result=(_obs or "")[:2000],
                    is_error=_ierr, metadata=_meta,
                )
                _results.append((_c, _obs, _ierr, _meta))

            # loop-detection bookkeeping for parallel calls
            for _c, *_rest in _results[1:]:
                steps_log.append(_c["name"])

            # P2-4 — ask_user / clarify: render the question bubble and
            # PAUSE the loop; the user's next send re-enters run().
            if (
                len(_results) == 1
                and (_results[0][0]["name"] or "").strip().lower() in ("ask_user", "clarify")
                and not _results[0][2]
            ):
                try:
                    _clarify_payload = json.loads(_results[0][1])
                except Exception:
                    _clarify_payload = {}
                if isinstance(_clarify_payload, dict) and _clarify_payload.get("__clarify_pending__"):
                    yield AgentStep(
                        kind=StepKind.CLARIFY,
                        tool_name=_results[0][0]["name"],
                        tool_use_id=_results[0][0]["use_id"],
                        question=_clarify_payload.get("question", ""),
                        options=list(_clarify_payload.get("options", []) or []),
                    )
                    return

            # Feed observations back to the LLM (combined when N > 1).
            messages.append(Message(role="assistant", content=_context_clean(raw)))
            if len(_results) == 1:
                messages.append(Message(
                    role="user",
                    content=f"Observation: {(_results[0][1] or '')[:2000]}",
                ))
            elif _results:
                _combined = "Observation: " + f"{len(_results)} 个工具调用结果：\n" + "\n".join(
                    f"[{i + 1}] {c['name']}: {(obs or '')[:800]}"
                    for i, (c, obs, _e, _m) in enumerate(_results)
                )
                messages.append(Message(role="user", content=_combined))

        # --- Max steps exhausted ---
        yield AgentStep(
            kind=StepKind.TEXT_DELTA,
            content=f"我已经连续尝试了 {max_steps} 步但仍未收敛。请换用「深度」模式重试。",
        )
        yield AgentStep(kind=StepKind.TEXT_END)
        yield AgentStep(kind=StepKind.DONE, model=ctx.model or "",
                        metadata={"usage": _run_usage})

    def _build_messages(self, ctx: RunContext) -> list:
        """Build initial [system, user] messages.

        Supports multi-turn history: the full ctx.messages list is
        included as a conversation block in the user prompt so the
        LLM sees prior turns.
        """
        from datetime import datetime, timezone, timedelta
        tz_cn = timezone(timedelta(hours=8))
        now_str = datetime.now(tz_cn).strftime('%Y年%m月%d日 %H:%M 北京时间 (UTC+8)')
        utc_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        # P1-7 (Claude SDK exclude_dynamic_sections): the system prompt
        # stays byte-stable within a session for provider prefix caches.
        # Volatile context (time) is injected on the last user message
        # by the chat route — once for ALL engines, single source.
        sys_text = REACT_SYSTEM_PROMPT.format(
            tools_desc=self._format_tools(ctx.tool_schemas),
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
