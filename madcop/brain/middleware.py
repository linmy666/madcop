"""v1.2.0 — BrainMiddleware: auto-record into the knowledge brain.

A long-running agent learns things as it works. The
`BrainMiddleware` plugs into the v1.0 middleware chain and writes a
"skill"-typed page for each completed plan step (when a) the agent
injects a fact via the shared context, or b) the step outcome
contains a `notes` field with markdown content).

Why a middleware (not a call to `db.save()` inside the loop)?
- A plan-execute loop might be 100 lines and 30 hooks; instrumenting
  it inline is a maintenance burden.
- The middleware chain is the canonical place to add cross-cutting
  concerns (logging, tracing, control). Brain storage is one of them.
- It composes with TraceMiddleware: the brain can later mine the
  trace for self-reflection (v1.3.0 work).

What this middleware does, concretely
-------------------------------------
For every `step_end` hook:
  - If the step outcome's `notes` field starts with `learn:`,
    the middleware treats the rest of the string as markdown content
    and saves it to the brain (with auto-derivation of slug / type).
  - Otherwise it does nothing.

For every `plan_end` hook:
  - If the shared context has `brain_summary=True`, the middleware
    emits one summary page containing all the step outcomes.

Why so narrow?
- v1.2.0 is one milestone; we don't want auto-save on every step
  outcome (most of them are throwaway). The `learn:` prefix is an
  opt-in signal the agent emits when it has something to remember.
- Future work: a `remember()` tool the agent can call directly,
  which is the cleaner affordance.
"""
from __future__ import annotations

import re
from typing import Any

from ..agent.middleware import (
    HOOK_PLAN_END,
    HOOK_STEP_END,
    HookContext,
)
from .markdown import parse as md_parse
from .store import PageDB


LEARN_PREFIX = "learn:"


class BrainMiddleware:
    """Persist `learn:`-prefixed outcomes to a PageDB.

    Args:
        db: A `PageDB` instance to write to.
        source: A free-form source label used in the audit log.
            Defaults to "plan".
    """

    name = "brain"

    def __init__(self, db: PageDB, *, source: str = "plan") -> None:
        self._db = db
        self._source = source

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook == HOOK_STEP_END:
            self._on_step_end(ctx)
        elif ctx.hook == HOOK_PLAN_END:
            self._on_plan_end(ctx)

    # ---- step_end -------------------------------------------------------

    def _on_step_end(self, ctx: HookContext) -> None:
        outcome = ctx.outcome
        if outcome is None:
            return
        notes = getattr(outcome, "notes", None)
        if not isinstance(notes, str) or not notes.strip():
            return
        # Only consume notes that begin with `learn:`.
        if not notes.lstrip().startswith(LEARN_PREFIX):
            return
        body = notes.lstrip()[len(LEARN_PREFIX):].lstrip()
        if not body:
            return
        # Treat the body as markdown. The parser fills in slug/title/type.
        parsed = md_parse(body)
        if not parsed.slug:
            # No resolvable slug; give up and stash under the step name.
            step_name = getattr(ctx.step, "name", None) or "step"
            slug = re.sub(r"[^a-z0-9]+", "-", step_name.lower()).strip("-") or "step"
        else:
            slug = parsed.slug
        if not parsed.type:
            parsed.type = "skill"
        try:
            self._db.save(
                slug=slug,
                title=parsed.title or slug,
                page_type=parsed.type,
                compiled_truth=parsed.compiled_truth,
                timeline=parsed.timeline,
                frontmatter=parsed.frontmatter,
                source=self._source,
                saved_by="brain_middleware",
            )
        except Exception as exc:
            # We never break the agent's run on a brain save failure.
            import logging
            logging.getLogger(__name__).warning(
                "BrainMiddleware save failed: %s", exc
            )

    # ---- plan_end -------------------------------------------------------

    def _on_plan_end(self, ctx: HookContext) -> None:
        if not ctx.shared.get("brain_summary"):
            return
        # Build a short markdown summary of the plan.
        plan = ctx.plan
        if plan is None or not getattr(plan, "steps", None):
            return
        lines = ["## Plan summary", ""]
        for s in plan.steps:
            outcome = ctx.shared.get("step_outcomes", {}).get(getattr(s, "name", ""))
            success = getattr(outcome, "success", None)
            mark = "ok" if success else "fail" if success is False else "?"
            lines.append(f"- `{getattr(s, 'name', '?')}` [{mark}]")
        body = "---\ntitle: Plan summary\ntype: skill\n---\n\n" + "\n".join(lines) + "\n"
        parsed = md_parse(body)
        if not parsed.slug:
            return
        try:
            self._db.save(
                slug=parsed.slug or "plan-summary",
                title=parsed.title or "Plan summary",
                page_type=parsed.type or "skill",
                compiled_truth=parsed.compiled_truth,
                timeline=parsed.timeline,
                frontmatter=parsed.frontmatter,
                source=self._source,
                saved_by="brain_middleware",
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "BrainMiddleware plan summary save failed: %s", exc
            )


__all__ = ["BrainMiddleware", "LEARN_PREFIX"]
