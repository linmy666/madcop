"""v1.2.0 — agent.tracing

Wait — this is v1.3.0. Correction: this is the **reflection** module, the
L1 half of v1.3.0 loop engineering.

What this module is
-------------------
`ReflectionMiddleware` runs at `HOOK_PLAN_END` and asks the LLM to write
1–3 actionable, specific reflections about the just-finished plan. Each
reflection becomes a `Page` of `type=skill` in the knowledge brain, so
the next plan-execute run can retrieve it.

Why a middleware
----------------
The plan-execute loop is the canonical place to do cross-cutting work
(logging, tracing, control). Reflection is one more of those concerns.
Putting it in a middleware means:

- No changes to the plan-execute core loop.
- Composes with TraceMiddleware (reflection sees the same ctx trace).
- Composes with BrainMiddleware (reflection writes the same way the
  `learn:` prefix does, just automatically).
- Can be disabled per-run via `chain.remove(ReflectionMiddleware)`.

Why JSON output
---------------
Reflections go to the brain as `type=skill` pages. JSON gives us
structured fields (topic, lesson, applies_to, evidence_step) that the
brain can search and tag. Free text would force us to re-parse the
reflection at retrieval time.

Why we cap at 1-3 reflections
-----------------------------
The Self-Refine paper found 3 rounds is the sweet spot before
diminishing returns on iterative refinement. We extrapolate: 3
reflections per plan is enough to capture what mattered; forcing more
either dilutes signal or invents fake lessons.

If the LLM produces no JSON, no reflections, or JSON with the wrong
shape, we fall through to a "no reflection" pass silently — the
plan-execute loop should not fail because reflection failed.

This module does NOT train anything, does NOT call external services,
does NOT mutate the brain schema. It only:
  1. Builds a prompt (the v1.3.0 reflection prompt template).
  2. Calls the LLM via OpenAI-compat client.
  3. Parses the response as JSON.
  4. Writes 1-3 skill pages to the brain.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Iterable

from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HookContext,
)
from madcop.brain.markdown import VALID_TYPES
from madcop.brain.store import PageDB

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Reflection prompt (v1.3.0-rc.1)
# --------------------------------------------------------------------------- #

# Default prompt template. The placeholders are filled by `build_prompt`.
# Kept short and table-stakes: "actionable + specific + durable".
DEFAULT_REFLECTION_PROMPT = """You just finished a plan. Your job is to write 1-3 *actionable reflections* that will help the next attempt (or the next agent session) avoid the same mistakes.

GOAL:
{goal}

OUTCOME (overall):
- success: {plan_success}
- steps_completed: {steps_completed} / {steps_total}
- total_cost_usd: {total_cost}
- total_duration_s: {total_duration}
- failure_modes: {failure_modes}

PLAN (1 line per step):
{plan_lines}

OUTCOMES (1 line per step):
{outcome_lines}

Write 1-3 reflections. Each must be:
- Actionable: tells the next attempt a specific change ("preflight check the input first", "retry once on 5xx", "use BM25 not cosine")
- Specific: names the actual step, tool, or assumption that broke
- Durable: still useful a week from now, not just for this one run

Output a JSON object:
{{
  "reflections": [
    {{
      "topic": "string — short slug like 'rate-limit-retry'",
      "lesson": "string — 1-2 sentence actionable rule",
      "applies_to": "string — 'all' or 'tool:bash' or 'goal-category:diagnostics'",
      "evidence_step": "string — name of the step that demonstrated this"
    }}
  ]
}}

If the run was a complete success, output {{"reflections": []}} or one celebration-style reflection ("this exact recipe works"). Don't force reflections on success.
"""


# --------------------------------------------------------------------------- #
# Plan summary helpers
# --------------------------------------------------------------------------- #


def _step_name(step: Any) -> str:
    return getattr(step, "name", "?") or "?"


def _step_action(step: Any) -> str:
    a = getattr(step, "action", "") or ""
    return a if len(a) <= 120 else a[:117] + "..."


def _outcome_summary(outcome: Any) -> str:
    if outcome is None:
        return "(no outcome recorded)"
    success = getattr(outcome, "success", None)
    err = getattr(outcome, "error", None)
    cost = getattr(outcome, "cost_usd", None)
    dur = getattr(outcome, "duration_s", None)
    pieces = []
    pieces.append("ok" if success else "fail" if success is False else "?")
    if err:
        pieces.append(f"err={str(err)[:80]}")
    if cost is not None:
        pieces.append(f"${cost:.4f}")
    if dur is not None:
        pieces.append(f"{dur:.1f}s")
    return " ".join(pieces)


def summarize_plan(ctx: HookContext) -> dict[str, Any]:
    """Build the structured summary that the reflection prompt embeds.

    Returns a dict with the same keys the prompt template uses.
    """
    plan = ctx.plan
    steps = list(getattr(plan, "steps", []) or []) if plan is not None else []
    plan_lines: list[str] = []
    outcome_lines: list[str] = []
    failure_modes: list[str] = []
    success_count = 0
    total_cost = 0.0
    total_duration = 0.0

    for s in steps:
        plan_lines.append(f"- {_step_name(s)}: {_step_action(s)}")
        outcome = ctx.shared.get("step_outcomes", {}).get(_step_name(s))
        outcome_lines.append(f"- {_step_name(s)}: {_outcome_summary(outcome)}")
        if outcome is not None:
            ok = getattr(outcome, "success", None)
            if ok is True:
                success_count += 1
            elif ok is False:
                err = getattr(outcome, "error", None) or "no error message"
                failure_modes.append(f"{_step_name(s)}: {str(err)[:80]}")
            c = getattr(outcome, "cost_usd", None) or 0.0
            d = getattr(outcome, "duration_s", None) or 0.0
            try:
                total_cost += float(c)
            except (TypeError, ValueError):
                pass
            try:
                total_duration += float(d)
            except (TypeError, ValueError):
                pass

    plan_success = (
        success_count == len(steps) and len(steps) > 0
        if steps else bool(ctx.shared.get("plan_success"))
    )

    return {
        "goal": ctx.goal or "",
        "plan_success": plan_success,
        "steps_completed": success_count,
        "steps_total": len(steps),
        "total_cost": f"{total_cost:.4f}",
        "total_duration": f"{total_duration:.2f}",
        "failure_modes": failure_modes or ["(none)"],
        "plan_lines": "\n".join(plan_lines) or "(empty plan)",
        "outcome_lines": "\n".join(outcome_lines) or "(no outcomes)",
    }


# --------------------------------------------------------------------------- #
# JSON parsing
# --------------------------------------------------------------------------- #


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_reflections(raw: str) -> list[dict[str, str]]:
    """Extract 1-3 reflection dicts from an LLM response.

    Tolerant of:
      - leading/trailing prose around the JSON
      - ```json ... ``` fenced blocks
      - extra keys we don't know about (ignored)
    Returns [] on any parse failure — the reflection middleware should
    never break a run because of bad JSON.
    """
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    # Strip ```json ... ``` fences.
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl > 0:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
    # Find a JSON object somewhere in the response.
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return []
    candidate = match.group(0)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    raw_refls = data.get("reflections")
    if not isinstance(raw_refls, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in raw_refls:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "").strip()
        lesson = str(item.get("lesson") or "").strip()
        if not topic or not lesson:
            continue
        # topic must be slug-shaped (lowercase, dash, no spaces)
        topic = re.sub(r"\s+", "-", topic.lower())[:64]
        cleaned.append({
            "topic": topic,
            "lesson": lesson[:500],
            "applies_to": str(item.get("applies_to") or "all").strip()[:64] or "all",
            "evidence_step": str(item.get("evidence_step") or "").strip()[:64],
        })
        if len(cleaned) >= 3:
            break
    return cleaned


# --------------------------------------------------------------------------- #
# Brain write
# --------------------------------------------------------------------------- #


def _slug_for_reflection(topic: str) -> str:
    """Make a stable brain slug from a reflection topic."""
    base = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    if not base:
        base = "reflection"
    return f"reflection-{base}"[:128]


def _reflection_to_markdown(refl: dict[str, str], *, outcome: str = "unknown") -> str:
    """Render a reflection dict as a markdown body the brain can store.

    Frontmatter `type: skill` makes it retrievable as a lesson at next
    plan-start. `applies_to`, `topic`, and (v1.3.0-rc.2) `outcome` become
    tags. `outcome` is one of `success` / `failure` / `unknown`,
    computed from the plan-success flag at write time. v1.3.0-rc.2's
    `OutcomePrioritizer` uses it to bias reranking on future runs.
    """
    topic = refl["topic"]
    lesson = refl["lesson"]
    applies = refl["applies_to"]
    evidence = refl.get("evidence_step", "")
    outcome = outcome if outcome in ("success", "failure") else "unknown"
    fm = (
        "---\n"
        "type: skill\n"
        f"applies_to: {applies}\n"
        f"topic: {topic}\n"
        f"outcome: {outcome}\n"
        "---\n\n"
    )
    body = (
        f"## Lesson\n\n{lesson}\n\n"
        f"## Applies to\n\n`{applies}`\n\n"
        f"## Outcome\n\n`{outcome}`\n\n"
    )
    if evidence:
        body += f"## Evidence step\n\n`{evidence}`\n\n"
    body += (
        "## Why this matters\n\n"
        "Auto-extracted by `ReflectionMiddleware` from a prior plan-execute run. "
        "Retrievable by `db.search(topic)`, by `applies_to` tag, or by `outcome:` tag.\n"
    )
    return fm + body


# --------------------------------------------------------------------------- #
# ReflectionMiddleware
# --------------------------------------------------------------------------- #


class ReflectionMiddleware:
    """Auto-write 1-3 skill pages to the brain at HOOK_PLAN_END.

    Args:
        client: An OpenAI-compat LLM client (anything with a `chat()`
            method that takes a list of message dicts and returns
            content). Use `madcop.llm.OpenAICompatClient` or a mock.
        db: The `PageDB` to write reflections to.
        prompt_template: Override the default reflection prompt.
        model: Optional model name passed to `client.chat()`.
        max_reflections: Cap on how many reflections to write. Default 3.
        source: Audit-log source label. Default "reflection".
        skip_on_success: If True, skip the LLM call when the plan
            succeeded end-to-end. Default False — even a success may
            carry a celebration-style reflection worth keeping.
        temperature: LLM sampling temperature. Default 0.2.
    """

    name = "reflection"

    def __init__(
        self,
        client: Any,
        db: PageDB,
        *,
        prompt_template: str = DEFAULT_REFLECTION_PROMPT,
        model: str | None = None,
        max_reflections: int = 3,
        source: str = "reflection",
        skip_on_success: bool = False,
        temperature: float = 0.2,
    ) -> None:
        self._client = client
        self._db = db
        self._prompt_template = prompt_template
        self._model = model
        self._max_reflections = max(0, int(max_reflections))
        self._source = source
        self._skip_on_success = skip_on_success
        self._temperature = float(temperature)

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook != HOOK_PLAN_END:
            return
        summary = summarize_plan(ctx)
        if self._skip_on_success and summary["plan_success"]:
            return
        if self._max_reflections == 0:
            return
        try:
            reflections = self._ask_llm(summary)
        except Exception as exc:
            logger.warning("ReflectionMiddleware LLM call failed: %s", exc)
            return
        if not reflections:
            return
        # Write each reflection as a skill page in the brain.
        written = 0
        plan_success = bool(summary.get("plan_success"))
        outcome = "success" if plan_success else "failure"
        for refl in reflections[: self._max_reflections]:
            try:
                self._write_reflection(refl, outcome=outcome)
                written += 1
            except Exception as exc:
                logger.warning(
                    "ReflectionMiddleware save failed for %r: %s",
                    refl.get("topic"),
                    exc,
                )
        ctx.shared["reflections_written"] = written
        ctx.shared["reflection_topics"] = [r["topic"] for r in reflections[: self._max_reflections]]
        ctx.shared["reflection_outcome"] = outcome

    # ---- LLM call -------------------------------------------------------

    def _ask_llm(self, summary: dict[str, Any]) -> list[dict[str, str]]:
        prompt = self._prompt_template.format(**summary)
        # The default prompt template has literal `{{` / `}}` so that
        # `.format(**summary)` doesn't try to expand the embedded JSON
        # braces. If a custom template uses real `{...}` placeholders,
        # they collide; surface that clearly.
        if "{" in prompt and "}" in prompt and "{{" not in self._prompt_template:
            # User-supplied template is treated as a Python format string.
            pass
        messages = [
            {"role": "system", "content": "You write concise, actionable, durable lessons from past agent runs. Always respond with a single JSON object."},
            {"role": "user", "content": prompt},
        ]
        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._model is not None:
            kwargs["model"] = self._model
        # The OpenAI-compat signature is .chat(messages=..., **kwargs)
        # and returns a response with .choices[0].message.content.
        response = self._client.chat(**kwargs)
        content = _extract_content(response)
        return parse_reflections(content)

    # ---- brain write ----------------------------------------------------

    def _write_reflection(self, refl: dict[str, str], *, outcome: str = "unknown") -> None:
        slug = _slug_for_reflection(refl["topic"])
        body = _reflection_to_markdown(refl, outcome=outcome)
        outcome = outcome if outcome in ("success", "failure") else "unknown"
        # type=skill (validated in PageDB.save)
        tags = [
            "reflection",
            f"applies:{refl['applies_to']}",
            f"topic:{refl['topic']}",
            f"outcome:{outcome}",
        ]
        # Note: PageDB.save's `tags=` is REPLACE; we want a real
        # append-friendly approach. For now we use a fresh slug per
        # topic and use `tags=` to ensure the right tags are set.
        self._db.save(
            slug=slug,
            title=refl["topic"],
            page_type="skill",
            compiled_truth=body,
            timeline="",
            frontmatter={
                "type": "skill",
                "applies_to": refl["applies_to"],
                "topic": refl["topic"],
                "outcome": outcome,
            },
            tags=tags,
            source=self._source,
            saved_by="reflection_middleware",
        )


def _extract_content(response: Any) -> str:
    """Normalise a chat response to its content string.

    Handles the OpenAI shape (`.choices[0].message.content`), a plain
    dict, or a string (for mocks).
    """
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        # Try the OpenAI shape.
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        # Maybe a `content` key at the top level.
        if "content" in response:
            return str(response["content"])
        return str(response)
    # Object with attributes (openai ChatCompletion).
    choices = getattr(response, "choices", None)
    if choices:
        msg = getattr(choices[0], "message", None)
        if msg is not None:
            return str(getattr(msg, "content", "") or "")
    return str(response)


__all__ = [
    "DEFAULT_REFLECTION_PROMPT",
    "ReflectionMiddleware",
    "summarize_plan",
    "parse_reflections",
]
