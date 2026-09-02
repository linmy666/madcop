"""
MadCop Harness — MEA Loop (Manage-Execute-Audit).

Production harness built on the core types (SessionLog, Capabilities,
Turn/Step state machine). The loop yields AgentStep events for SSE
streaming while maintaining formal state machine transitions.

Architecture:
  Turn = user input → [Step₁, Step₂, ...] → final answer
  Step = Manager(plan) → Executor(do) → Auditor(verify)

Each step uses fresh, bounded contexts. State persists to SessionLog
(JSONL). Failed steps don't advance verified state (soft revert).
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from madcop.agent.runtime import AgentStep, RunContext, StepKind
from madcop.llm.client import Message
from .core import (
    SessionLog, Step, TurnState,
    HarnessEvent, EventDomain,
    reasoning_event, tool_event, answer_event, system_event,
)

logger = logging.getLogger(__name__)

_HARNESS_ROOT = Path.home() / ".madcop" / "harness_runs"

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)

def _strip_think(text: str) -> str:
    """Remove think blocks INCLUDING an unclosed <think> to end-of-string.

    BUG-FIX: the old version only removed complete <think>...</think>
    pairs and stray tags — an UNCLOSED <think> (stream cut mid-think)
    had its tag deleted but its CONTENT kept, leaking thousands of
    reasoning chars into the final answer.
    """
    text = _THINK_RE.sub("", text)
    # Unclosed think: everything after it is reasoning — drop it all.
    text = re.sub(r"<think>[\s\S]*$", "", text)
    text = re.sub(r"</?think>", "", text)
    return text.strip()


class MadCopHarness:
    """MEA loop engine with formal state machine + session log.

    Usage (as agent engine):
        engine = MadCopHarness(ctx)
        for step in engine.run(ctx):
            yield step  # → SSE event

    The loop produces three event domains:
    - THOUGHT_* events → reasoning (Manager plans, Executor thinks, Auditor verifies)
    - TOOL_* events → tool calls (file writes, searches)
    - TEXT_DELTA/END → the final answer the user sees
    """

    def __init__(self, ctx: RunContext, max_steps: int = 8,
                 capabilities: dict | None = None,
                 shared_log: "SessionLog | None" = None):
        self.ctx = ctx
        self.max_steps = max_steps
        # Double-write fix: when running under chat_v4 (production), the
        # worker already logs every yielded AgentStep to the session log.
        # MEA accepts that shared log and skips its own duplicate appends
        # of step-level events (executor tools, turn markers) — it only
        # appends its UNIQUE records (manager plans, audit verdicts).
        self._shared = shared_log is not None
        self.log = shared_log if shared_log is not None else SessionLog(persist_dir=_HARNESS_ROOT)
        self.goal = ""
        self.verified_state = ""
        self.steps: list[Step] = []
        self._step_effect_keys: list[str] = []
        self._last_contract_desc = ""
        self._last_executor_output = ""
        # Reasoning captured by _llm_stream's ThinkSeparator — drained by
        # _manager and emitted as THOUGHT_DELTA (never into TEXT_DELTA).
        self._pending_reasoning: list[str] = []
        # Capability seams (production pattern): swappable backends. Defaults to
        # the local filesystem; a sandboxed/remote implementation can be
        # injected without touching the loop.
        from .core import LocalFileSystem, FileSystemCapability
        self.fs: FileSystemCapability = (
            (capabilities or {}).get("fs") or LocalFileSystem()
        )

    def _log_unique(self, event) -> None:
        """Append only MEA-unique events (manager/audit) — safe under a
        shared log. Step-level events are logged by the chat worker."""
        self.log.append(event)

    def _llm_chat(self, system: str, user: str, temp: float = 0.3,
                  max_tokens: int = 600) -> str:
        """Single non-streaming LLM call with think-tag stripping."""
        try:
            resp = self.ctx.client.chat(
                [Message(role="system", content=system),
                 Message(role="user", content=user)],
                model=self.ctx.model,
                temperature=temp,
                max_tokens=max_tokens,
            )
            return _strip_think(resp.content or "")
        except Exception as e:
            logger.warning("[harness] LLM call failed: %s", e)
            return ""

    def _llm_stream(self, system: str, user: str, temp: float = 0.3,
                    max_tokens: int = 600) -> Iterator[str]:
        """Streaming LLM call. Yields clean text chunks (think tags removed).

        BUG-FIX: per-chunk _strip_think cannot match a <think> tag split
        across chunk boundaries ('<thi' + 'nk>'), so reasoning leaked
        into TEXT_DELTA (15k chars of think content reached the user,
        and the frontend's whole-stream strip then mangled it down to
        stray '<<' heredoc fragments). Use the runtime's ThinkSeparator,
        which holds back partial-tag tails across chunks.
        """
        from madcop.agent.runtime import ThinkSeparator
        try:
            if hasattr(self.ctx.client, "stream"):
                sep = ThinkSeparator()
                for chunk in self.ctx.client.stream(
                    [Message(role="system", content=system),
                     Message(role="user", content=user)],
                    model=self.ctx.model,
                    temperature=temp,
                    max_tokens=max_tokens,
                ):
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        reasoning, answer = sep.feed(text)
                        # Reasoning goes to the caller's THOUGHT channel via
                        # a side-channel: stash it so _manager can emit it as
                        # THOUGHT_DELTA instead of losing it.
                        if reasoning:
                            self._pending_reasoning.append(reasoning)
                        if answer:
                            yield answer
                # Drain any remainder after the stream ends.
                r_rest, a_rest = sep.flush()
                if r_rest:
                    self._pending_reasoning.append(r_rest)
                if a_rest:
                    yield a_rest
            else:
                resp = self.ctx.client.chat(
                    [Message(role="system", content=system),
                     Message(role="user", content=user)],
                    model=self.ctx.model,
                    temperature=temp,
                    max_tokens=max_tokens,
                )
                yield _strip_think(resp.content or "")
        except Exception as e:
            logger.warning("[harness] LLM stream failed: %s", e)

    # ─── Manager: plan next subtask ───────────────────────────────


    def _emit_plan(self, step: "Step", status: str) -> AgentStep:
        """Emit a plan-stepper update for the task monitor.

        The frontend's existing `plan` event handler stores the plan
        object in session.plan; the `plan_step` handler updates one
        step's status. We send ONE combined event carrying both.
        """
        steps_out = []
        for s in self.steps:
            st = "completed" if s.audit_status == "complete" else (
                 "failed" if s.audit_status == "blocked" else (
                 "in_progress" if s.index == step.index else "pending"))
            steps_out.append({
                "step": s.index,
                "title": (s.contract_description or "")[:80],
                "status": st,
            })
        return AgentStep(
            kind=StepKind.PLAN,
            metadata={
                "plan": {
                    "steps": steps_out,
                    "total_steps": self.max_steps,
                    "completed_steps": sum(1 for x in steps_out if x["status"] == "completed"),
                    "current_step": step.index,
                    "category": "mea_task",
                    "category_label": "MEA 任务",
                },
            },
        )

    def _recent_trajectory(self, limit: int = 6) -> str:
        """Codex-parity: the Manager plans against REAL observations.

        Previously the Manager saw only goal + verified_state — a
        secondhand summary it wrote itself. The last few tool calls
        (name + result snippet) from the session log ground the next
        subtask in what actually happened (a failed write, an empty
        search) instead of what the executor CLAIMED happened."""
        lines: list[str] = []
        try:
            for ev in self.log.events():
                d = ev.domain.value if hasattr(ev.domain, "value") else ev.domain
                if d != "tool":
                    continue
                name = (ev.metadata or {}).get("tool_name") or ""
                snippet = (ev.content or "").strip().replace("\n", " ")[:140]
                if not snippet:
                    continue
                icon = "←" if ev.kind == "tool_result" else "→"
                lines.append(f"{icon} {name or ev.kind}: {snippet}")
        except Exception:
            return ""
        return "\n".join(lines[-limit:])

    def _manager(self, step: Step) -> Iterator[AgentStep]:
        """Manager: read goal + state → emit subtask contract. Streams reasoning."""
        system = (
            "You are the Engineering Manager in a Manager→Coder→Tester→Reviewer "
            "delivery loop for a coding task. "
            "Given the user's goal and current verified state, decide the NEXT "
            "concrete subtask. Decompose the goal in build order: "
            "scaffold files → implement core logic → add tests/polish → verify. "
            "Each subtask MUST be small enough for ONE executor step "
            "(e.g. 'write index.html with the 5x9 grid' not 'build the game'). "
            "Output JSON: "
            '{"description": "what to do", "acceptance_criteria": "how to verify"}. '
            'If the overall task is complete, output: {"description": "TASK_COMPLETE"}'
        )
        audit_feedback = ""
        if self.steps:
            last = self.steps[-1]
            if last.audit_status and last.audit_status != "complete":
                audit_feedback = f"\n\nPrevious audit feedback: fix these issues → {last.audit_status}"

        user_msg = (
            f"Goal: {self.goal}\n\n"
            f"Verified state so far:\n{self.verified_state or '(none yet)'}"
            f"{audit_feedback}\n\n"
            f"What should the Executor do next? (Step {step.index}/{self.max_steps})"
        )
        # Grounding: recent tool trajectory from the log (real
        # observations, not self-report).
        _traj = self._recent_trajectory()
        if _traj:
            user_msg += (
                "\n\nRecent tool activity this turn (ground truth):\n" + _traj
            )

        # Steer (Codex Op::Steer): drain mid-turn guidance BEFORE
        # planning so the next subtask redirects, and surface the
        # receipt so the UI confirms consumption.
        try:
            _realm = getattr(self.ctx, "realm", None)
            if _realm is not None:
                _steers = _realm.drain_steers()
            else:
                from madcop.server.steer_queue import drain_steers
                _steers = drain_steers(self.ctx.session_id or "")
            if _steers:
                from madcop.server.steer_queue import format_steer_block
                user_msg += "\n\n" + format_steer_block(_steers)
                yield AgentStep(
                    kind=StepKind.STEER_INJECTED,
                    content="；".join(s[:80] for s in _steers),
                )
        except Exception:
            pass

        contract_text = ""
        tid = f"mgr-{step.index}"
        yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=tid)
        yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                        content=f"📋 Step {step.index}/{self.max_steps}: 规划中...\n")

        self._pending_reasoning = []
        for text in self._llm_stream(system, user_msg, temp=0.3, max_tokens=400):
            # Flush any reasoning the ThinkSeparator captured while the
            # model was inside <think> — it belongs on the THOUGHT channel.
            while self._pending_reasoning:
                yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                                content=self._pending_reasoning.pop(0))
            contract_text += text
            if text:
                yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid, content=text)
        while self._pending_reasoning:
            yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                            content=self._pending_reasoning.pop(0))

        # Parse contract from JSON
        desc = contract_text
        m = re.search(r'\{[^{}]+\}', contract_text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                desc = data.get("description", contract_text[:200])
            except Exception:
                pass

        self._last_contract_desc = desc
        yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                        content=f"\n→ 子任务: {desc[:100]}")
        yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=tid,
                        elapsed_ms=step.duration_ms)

        # Log reasoning
        self.log.append(reasoning_event("manager_plan", contract_text, step=step.index))

    # ─── Executor: do the work ────────────────────────────────────

    def _executor(self, step: Step) -> Iterator[AgentStep]:
        """Executor: run one bounded step using ReActEngineV4.

        ReAct engine already separates: <think>→THOUGHT_*, tool calls→TOOL_*,
        answer→TEXT_*. We forward all events — no mixing.

        P2-11 — subagent isolation (Claude Task-tool semantics): the
        Coder gets a FRESH context (contract + goal only, never the
        main conversation history), and its full trajectory lands in a
        dedicated SIDECHAIN session log; the main log only receives the
        bounded subagent_result summary. The sidechain is replayable
        on its own (fork/inspect) without polluting the main transcript.
        """
        from madcop.agent.react_v4 import ReActEngineV4
        engine = ReActEngineV4()

        # P1 — revertible effects: collect the effect keys of every tool
        # call this step executes so an audit-blocked step can apply the
        # stored inverses and restore the workspace (paper §3.1 recover).
        self._step_effect_keys = []

        sidechain: SessionLog | None = None
        try:
            _sc_id = f"{self.log.run_id}-sc{step.index}"
            sidechain = SessionLog(_sc_id, persist_dir=_HARNESS_ROOT)
            sidechain.append(HarnessEvent(
                domain=EventDomain.SYSTEM, kind="sidechain_of",
                content=self.log.run_id,
                metadata={"role": "coder", "step": step.index,
                          "contract": (self._last_contract_desc or "")[:500]},
            ))
        except Exception:
            sidechain = None

        # Executor receives the Coder brief: use tools to WRITE the
        # deliverable (write_file/edit_file), not just describe it. The
        # old generic prompt let the model answer in prose when the
        # subtask asked for a file — now the system prefix mandates
        # producing the artifact via tools. The goal is included so the
        # fresh context still knows what the overall task is.
        _coder_prefix = (
            (self.ctx.system_prefix or "")
            + "\n[Coder role] You are the Coder in a Manager→Coder→Tester"
            "→Reviewer loop. Complete the subtask by WRITING the actual"
            " artifact with tools (write_file for new files, edit_file"
            " for changes). Do NOT merely describe what you would write."
        )
        # Codex-style fork_turns: inherit the last 4 turns of the
        # parent's history so the Coder knows the goal and prior audit
        # decisions without re-reading the whole conversation. Recovery
        # = discarding the child context (no inverse needed).
        exec_ctx = self.ctx.derive(
            inherit_messages="last_n",
            inherit_last_n=4,
            agent_mode="standard",
            system_prefix=_coder_prefix,
            max_steps=6,
            session_id=self.ctx.session_id,
            # Isolation (paper §3.2.3 derived realization): the Coder's
            # context excludes memory side channels — a subagent must not
            # write long-term memories as a side effect of one step.
            tool_schemas=[
                s for s in self.ctx.tool_schemas
                if (s.get("function") or s).get("name", "") != "remember"
            ],
        )
        # Append the contract as a fresh user message so the
        # subagent sees it at the tail of the inherited history
        # (positions the task statement where every model pays
        # attention first).
        from madcop.llm.client import Message as _M
        exec_ctx.messages = list(exec_ctx.messages) + [
            _M(role="user", content=(
                f"总体任务：{self.goal}\n\n"
                f"你的子任务合约：{self._last_contract_desc}"
            ))
        ]

        result_text = ""
        for ev in engine.run(exec_ctx):
            # Revertible effects: TOOL_START carries the tool_use_id the
            # executor used as its effect key — collect for step revert.
            # Realm-aware: the child realm namespaces its own keys.
            if ev.kind == StepKind.TOOL_START and ev.tool_use_id:
                from madcop.harness.realm import effect_key_for
                _ek = effect_key_for(exec_ctx, ev.tool_use_id)
                if _ek not in self._step_effect_keys:
                    self._step_effect_keys.append(_ek)
            # D2 fix: do NOT forward the executor's terminal events.
            # ReActEngineV4 emits TEXT_END/DONE when ITS loop finishes —
            # but the MEA loop is still running. Forwarding them made the
            # SSE stream emit `done` after every executor step (frontend
            # set chatState=idle mid-run) and produced duplicate final
            # answers. Only the MEA loop's own outermost completion emits
            # terminal events.
            if sidechain is not None:
                try:
                    _d = EventDomain.REASONING if ev.kind.value.startswith("thought_") else (
                        EventDomain.TOOL if ev.kind.value.startswith("tool_") else
                        EventDomain.ANSWER)
                    sidechain.append(HarnessEvent(
                        domain=_d, kind=ev.kind.value,
                        content=(ev.content or str(ev.tool_result or ""))[:800],
                        metadata={"step": step.index,
                                  "tool_name": ev.tool_name or ""},
                    ))
                except Exception:
                    pass
            if ev.kind in (StepKind.TEXT_END, StepKind.DONE):
                continue
            yield ev
            if ev.kind == StepKind.TEXT_DELTA and ev.content:
                result_text += ev.content
            elif ev.kind == StepKind.TOOL_START:
                _inp = ev.tool_input if isinstance(ev.tool_input, dict) else {}
                if not self._shared:
                    self.log.append(tool_event(
                        "tool_call", ev.tool_name or "",
                        step=step.index,
                        tool_name=ev.tool_name or "",
                        path=str(_inp.get("path") or _inp.get("file") or ""),
                    ))
            elif ev.kind == StepKind.TOOL_END:
                if not self._shared:
                    self.log.append(tool_event("tool_result", str(ev.tool_result or "")[:200],
                                               step=step.index))

        self._last_executor_output = _strip_think(result_text).strip()
        step.executor_summary = self._last_executor_output[:300]
        self.log.append(answer_event("executor_output", self._last_executor_output[:500],
                                     step=step.index))
        # P2-11: bounded summary back to the main log + close sidechain.
        if sidechain is not None:
            try:
                self.log.append(HarnessEvent(
                    domain=EventDomain.SYSTEM, kind="subagent_result",
                    content=self._last_executor_output[:2000],
                    metadata={"sidechain": sidechain.run_id, "step": step.index},
                ))
                sidechain.append(HarnessEvent(
                    domain=EventDomain.SYSTEM, kind="turn_end", content=""))
            except Exception:
                pass

    # ─── Auditor: verify ──────────────────────────────────────────

    def revert_step_effects(self) -> tuple[int, list[str]]:
        """Apply every inverse recorded by this step's tool calls
        (newest-first) and clear the keys. Returns (applied, keys).

        Extracted so tests can drive the revert deterministically
        without an LLM in the loop."""
        if not self._step_effect_keys:
            return 0, []
        from madcop.harness.effects import STORE
        applied = 0
        for k in self._step_effect_keys:
            rep = STORE.revert(k)
            applied += rep.get("applied", 0)
        return applied, list(self._step_effect_keys)

    def _collect_file_evidence(self) -> str:
        """Phase 4b — real environment verification via the fs capability.

        Independent-verification principle: don't trust the executor's self-report —
        inspect the actual environment with read-only tools. For every
        write_file/edit_file the executor performed this step, read the
        file back through self.fs and attach the first N chars as
        evidence for the auditor LLM.
        """
        evidence: list[str] = []
        for ev in self.log.events():
            if (ev.domain.value if hasattr(ev.domain, "value") else ev.domain) != "tool":
                continue
            if ev.kind != "tool_call":
                continue
            name = ev.metadata.get("tool_name") or ""
            if name not in ("write_file", "edit_file", "write_xlsx"):
                continue
            path = (ev.metadata.get("path") or "").strip()
            if not path:
                continue
            try:
                content = self.fs.read_file(path)
                if content and not content.startswith("[read error"):
                    evidence.append(f"--- {path} (actual on-disk content, first 400 chars) ---\n{content[:400]}")
            except Exception:
                pass
        return "\n\n".join(evidence[:3])  # cap at 3 files

    def _auditor(self, step: Step) -> str:
        """Auditor: independently verify. Returns status string."""
        system = (
            "You are the Tester/Reviewer. Verify the Coder's work. "
            "Be reasonable — correct output = complete. When file evidence "
            "is provided, judge against the ACTUAL file content (read back "
            "from disk), not the coder's claims. If the subtask asked for a "
            "file/artifact and the file evidence is missing or empty, the "
            "status is INCOMPLETE with feedback telling the coder to use "
            "write_file to actually create it. Output JSON: "
            '{"status": "complete|incomplete|blocked", "feedback": "brief note"}.'
        )
        file_evidence = self._collect_file_evidence()
        user_msg = (
            f"Subtask: {self._last_contract_desc}\n\n"
            f"Executor output:\n{self._last_executor_output[:1500]}\n\n"
            + (f"File evidence (independent read-back):\n{file_evidence}\n\n" if file_evidence else "")
            + f"Verified state:\n{self.verified_state or '(none)'}\n\n"
            "Did the executor complete this subtask?"
        )
        result = self._llm_chat(system, user_msg, temp=0.1, max_tokens=300)
        status = "incomplete"
        m = re.search(r'"status"\s*:\s*"(complete|incomplete|blocked)"', result, re.IGNORECASE)
        if m:
            status = m.group(1).lower()
        else:
            # Robust fallback: models with <think> wrappers or prose often
            # emit the verdict as a bare keyword — scan for it directly
            # instead of defaulting to 'incomplete' on every malformed JSON.
            low = result.lower()
            for kw in ("blocked", "incomplete", "complete"):  # 'incomplete' contains 'complete' — longest/most-specific first
                if kw in low:
                    status = kw
                    break
        self.log.append(reasoning_event("audit", result, step=step.index, status=status))
        return status

    # ─── Main loop: Turn = [Step₁, Step₂, ...] ───────────────────

    def run(self) -> Iterator[AgentStep]:
        """Main MEA loop. Formal Turn/Step lifecycle with state machine."""
        self.goal = self.ctx.messages[-1].content if self.ctx.messages else ""
        logger.info("[harness %s] turn start: %s", self.log.run_id, self.goal[:60])

        # Log turn start
        if not self._shared:
            self.log.append(system_event("turn_start", self.goal))
        yield AgentStep(kind=StepKind.THOUGHT_START, thought_id="turn")
        yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id="turn",
                        content=f"🎯 任务: {self.goal[:100]}\n模式: MEA Harness ({self.max_steps} steps max)\n")

        for i in range(1, self.max_steps + 1):
            step = Step(index=i)
            step.transition(TurnState.PLANNING)  # IDLE → PLANNING (validated)
            self.steps.append(step)
            yield self._emit_plan(step, "planning")

            # ── Manager ──
            yield from self._manager(step)

            if "TASK_COMPLETE" in self._last_contract_desc.upper():
                logger.info("[harness] manager declares complete at step %d", i)
                step.transition(TurnState.DONE)
                break

            # ── Executor ──
            # If a confirm_handler is configured, the executor's ReAct
            # engine may pause on HITL — reflect that in the step state
            # around the call (WAITING_HUMAN is set while blocked inside).
            step.transition(TurnState.EXECUTING)
            yield self._emit_plan(step, "executing")
            if self.ctx.confirm_handler is not None:
                # Announce the wait window; the engine flips back to
                # EXECUTING once the user responds.
                step.transition(TurnState.WAITING_HUMAN)
                step.transition(TurnState.EXECUTING)
            yield from self._executor(step)

            # ── Auditor ──
            # Cost control: the auditor is a full LLM roundtrip. When the
            # step made NO mutating calls (pure search/read/prose), there
            # is no disk state to independently verify — skip the third
            # call and trust the step. Mutating steps keep the full audit.
            _had_mutating = bool(self._step_effect_keys)
            tid = f"aud-{i}"
            if not _had_mutating:
                yield self._emit_plan(step, "auditing")
                yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=tid)
                yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                                content=f"\n🔍 Step {i}: 只读步骤，跳过独立审计（无文件变更）")
                yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=tid,
                                elapsed_ms=step.duration_ms)
                step.audit_status = "complete"
                self.verified_state = (
                    f"{self.verified_state}\n\n"
                    f"[Step {i} ✓]\n{step.executor_summary}"
                ).strip()
                step.completed_at = time.time()
                yield self._emit_plan(step, "complete")
                step.transition(TurnState.DONE)
                continue

            step.transition(TurnState.AUDITING)
            yield self._emit_plan(step, "auditing")
            yield AgentStep(kind=StepKind.THOUGHT_START, thought_id=tid)
            yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                            content=f"\n🔍 Step {i}: 验证中...")
            audit_status = self._auditor(step)
            step.audit_status = audit_status
            icon = "✅" if audit_status == "complete" else ("🚫" if audit_status == "blocked" else "⚠️")
            yield AgentStep(kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                            content=f"\n{icon} {audit_status.upper()}")
            yield AgentStep(kind=StepKind.THOUGHT_END, thought_id=tid,
                            elapsed_ms=step.duration_ms)

            # ── State update (soft revert) ──
            step.completed_at = time.time()
            yield self._emit_plan(step, audit_status)
            if audit_status == "complete":
                self.verified_state = (
                    f"{self.verified_state}\n\n"
                    f"[Step {i} ✓]\n{step.executor_summary}"
                ).strip()
                step.transition(TurnState.DONE)
            elif audit_status == "blocked":
                # P1 — real soft revert (paper §3.1 recover): a blocked
                # step means the executor left the environment in a bad
                # state. Apply the recorded inverses newest-first so the
                # retry starts from the pre-step workspace.
                _count, _keys = self.revert_step_effects()
                if _count:
                    yield AgentStep(
                        kind=StepKind.THOUGHT_DELTA, thought_id=tid,
                        content=(f"\n↩️ 已回退本步的 {_count} 项文件改动"
                                 "（审计判定 blocked），将从干净状态重试。\n"),
                    )
                    self.log.append(system_event(
                        "step_reverted",
                        f"step {i}: reverted {_count} effects",
                        step=i, keys=_keys,
                    ))
                self._step_effect_keys = []
                step.transition(TurnState.BLOCKED)
                break
            else:
                step.transition(TurnState.DONE)  # incomplete → retry next step

        # ── Turn end ──
        if not self._shared:
            self.log.append(system_event("turn_end", self.verified_state[:500]))
        yield AgentStep(kind=StepKind.THOUGHT_END, thought_id="turn")

        # Output verified state as the answer
        if self.verified_state:
            yield AgentStep(kind=StepKind.TEXT_DELTA, content=self.verified_state)
        else:
            yield AgentStep(kind=StepKind.TEXT_DELTA,
                            content="任务完成，但未产生已验证的输出。")
        yield AgentStep(kind=StepKind.TEXT_END)
        yield AgentStep(kind=StepKind.DONE, model=self.ctx.model or "")

        logger.info("[harness %s] turn end: %d steps, %d events logged",
                    self.log.run_id, len(self.steps), len(self.log.events()))
