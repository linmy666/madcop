"""Guardian — LLM pre-review of risky commands (codex full mechanism set).

Codex's guardian stands between the agent and the approval card: when a
command would interrupt the user (MadCop: every `bash` call pops a HITL
card), a fast, tool-less LLM review decides:

    allow     → run without the card (low-risk, unblocks long runs)
    deny      → refuse with a reason + ANTI-WORKAROUND instruction
                (the model must not try to achieve the same effect by
                another route — verbatim codex GUARDIAN_REJECTION
                semantics)
    escalate  → fall through to the human HITL card (unsure / high
                risk / anything suspicious)

Full mechanism set ported from codex-rs/core/src/guardian/:
  - review with structured output + timeout          (review.rs)
  - verdict cache keyed by normalized command        (review_session.rs)
  - denial circuit breaker: N denials in a window
    stops auto-deciding, everything escalates        (metrics/policy)
  - graceful degradation: any error/timeout/missing
    client → escalate (never harder-blocks than HITL)

NOT ported (OpenAI-infra coupling, meaningless locally): analytics/otel
metric emission, plan-type feature gating, extension-API integration.

Gate: MADCOP_GUARDIAN=0 disables entirely (default on). Layering:
exec_policy regex deny → tokenized safety net → guardian → HITL card.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from typing import Any, Callable

logger = logging.getLogger(__name__)

REVIEW_TIMEOUT_S = 12
CACHE_TTL_S = 30 * 60
CACHE_MAX = 256
# Circuit breaker (codex AUTO_REVIEW_DENIAL_WINDOW_SIZE semantics):
# this many guardian DENIALS inside the review window means the model
# is pushing against the user's intent — stop auto-allowing and hand
# every subsequent decision to the human card.
DENIAL_WINDOW_SIZE = 20
DENIAL_CIRCUIT_LIMIT = 3

GUARDIAN_SYSTEM_PROMPT = (
    "You are the Guardian: a strict but fair safety reviewer for a local "
    "coding agent. You receive ONE shell command the agent wants to run. "
    "Decide:\n"
    '  allow    — read-only or clearly safe for a dev workspace '
    "(ls, cat, grep, python script.py, npm test, git status, pip install, "
    "running tests, writing files inside the project...)\n"
    "  deny     — destructive or clearly against the user's interest "
    "(deleting outside workspace, exfiltrating secrets, killing the "
    "system, publishing/forcing git, installing backdoors...)\n"
    "  escalate — genuinely ambiguous, unusual, or high-blast-radius; "
    "a human should look at it\n"
    "Lean allow for normal development commands; the user already runs "
    "a local agent. Output ONLY JSON: "
    '{"decision": "allow|deny|escalate", "risk": "low|medium|high", '
    '"reason": "one short sentence"}'
)

# Verbatim codex semantics: a guardian denial must not invite workarounds.
ANTI_WORKAROUND_NOTE = (
    "[guardian] 该命令被安全审查拒绝：{reason}。"
    "不得尝试用其他命令或方式达成同样效果（那是绕过安全审查）；"
    "请调整方案或向用户说明。"
)


def _normalize(command: str) -> str:
    return re.sub(r"\s+", " ", (command or "").strip())


def _enabled() -> bool:
    return (os.environ.get("MADCOP_GUARDIAN", "1").strip() != "0")


class GuardianVerdict:
    __slots__ = ("decision", "risk", "reason", "source")

    def __init__(self, decision: str, risk: str = "", reason: str = "",
                 source: str = "llm"):
        self.decision = decision  # allow | deny | escalate
        self.risk = risk
        self.reason = reason
        self.source = source


class GuardianReviewer:
    """LLM command reviewer with cache, circuit breaker and timeout.

    ``client_getter`` is lazy — resolved at review time (the chat route
    passes its _get_client; engines pass ctx.client getter). A missing
    or broken client degrades to escalate (HITL card), never to allow.
    """

    def __init__(self, client_getter: Callable[[], Any] | None = None,
                 model: str | None = None):
        self._client_getter = client_getter
        self._model = model
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, GuardianVerdict]] = {}
        self._recent_denials: deque[float] = deque()
        self._reviews = 0

    # ── public ──────────────────────────────────────────────────────
    def review(self, command: str, force_refresh: bool = False) -> GuardianVerdict:
        """One review. Never raises; never returns 'allow' on failure."""
        if not _enabled():
            return GuardianVerdict("escalate", source="disabled")
        cmd = _normalize(command)
        if not cmd:
            return GuardianVerdict("escalate", reason="empty command",
                                   source="guard")
        now = time.time()
        with self._lock:
            self._reviews += 1
            while self._recent_denials and now - self._recent_denials[0] > CACHE_TTL_S:
                self._recent_denials.popleft()
            if len(self._recent_denials) >= DENIAL_CIRCUIT_LIMIT:
                return GuardianVerdict(
                    "escalate",
                    reason="审查器近期多次拒绝，已切换为人工确认模式",
                    source="circuit-breaker")
            hit = self._cache.get(cmd)
            if hit and not force_refresh and now - hit[0] < CACHE_TTL_S:
                return hit[1]
            if len(self._cache) > CACHE_MAX:
                self._cache.clear()

        verdict = self._review_llm(cmd)
        with self._lock:
            self._cache[cmd] = (time.time(), verdict)
            if verdict.decision == "deny":
                self._recent_denials.append(time.time())
        return verdict

    # ── internals ───────────────────────────────────────────────────
    def _review_llm(self, cmd: str) -> GuardianVerdict:
        client = None
        try:
            client = self._client_getter() if self._client_getter else None
        except Exception:  # noqa: BLE001
            client = None
        if client is None or not hasattr(client, "chat"):
            return GuardianVerdict("escalate", reason="无审查模型，转人工确认",
                                   source="no-client")
        result: dict[str, Any] = {}

        def _call():
            try:
                from madcop.llm.client import Message
                resp = client.chat(
                    [Message(role="system", content=GUARDIAN_SYSTEM_PROMPT),
                     Message(role="user", content=f"命令：{cmd}")],
                    model=self._model, temperature=0.0, max_tokens=200,
                )
                result["text"] = getattr(resp, "content", "") or ""
            except Exception as e:  # noqa: BLE001
                result["error"] = str(e)

        worker = threading.Thread(target=_call, daemon=True)
        worker.start()
        worker.join(timeout=REVIEW_TIMEOUT_S)
        if worker.is_alive():
            return GuardianVerdict("escalate", reason="审查超时，转人工确认",
                                   source="timeout")
        if result.get("error"):
            return GuardianVerdict("escalate", reason="审查模型调用失败",
                                   source="error")
        return self._parse_verdict(result.get("text", ""))

    @staticmethod
    def _parse_verdict(text: str) -> GuardianVerdict:
        """Parse the JSON verdict; tolerate <think> wrappers and prose.
        Anything unparseable escalates (fail-closed)."""
        from madcop.harness.mea_loop import _strip_think
        cleaned = _strip_think(text or "")
        m = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        decision = ""
        reason = ""
        risk = ""
        if m:
            try:
                import json
                data = json.loads(m.group(0))
                decision = str(data.get("decision", "")).lower().strip()
                risk = str(data.get("risk", "")).lower().strip()
                reason = str(data.get("reason", "")).strip()[:200]
            except Exception:  # noqa: BLE001
                decision = ""
        if decision not in ("allow", "deny", "escalate"):
            low = cleaned.lower()
            if re.search(r"\bdeny\b", low):
                decision = "deny"
            elif re.search(r"\ballow\b", low):
                decision = "allow"
            else:
                decision = "escalate"
        return GuardianVerdict(decision, risk=risk, reason=reason)


def anti_workaround_observation(verdict: GuardianVerdict) -> str:
    """The observation fed to the model when guardian denies."""
    return ANTI_WORKAROUND_NOTE.format(reason=verdict.reason or "高风险命令")


__all__ = [
    "GuardianReviewer", "GuardianVerdict", "anti_workaround_observation",
    "REVIEW_TIMEOUT_S", "DENIAL_WINDOW_SIZE", "DENIAL_CIRCUIT_LIMIT",
    "GUARDIAN_SYSTEM_PROMPT",
]
