"""v1.7.0 — Context summarization middleware.

SummarizationMiddleware monitors the accumulated step outputs in
``ctx.shared["step_outcomes"]`` and, when total estimated tokens
exceed a threshold, replaces older outputs with LLM-generated
one-sentence summaries.

This is the same idea as DeerFlow's SummarizationMiddleware: keep
the most recent K steps verbatim, summarize the rest. The goal is
"context peak per run < N tokens" (default 30K).

Why a middleware?
  - The plan-execute loop doesn't know about token budgets.
  - The context_compactor in strategy/ computes *what* to summarize;
    this middleware *does* the summarization (calls the LLM).
  - Composes with tracing, streaming, and reflection.

How it works:
  At HOOK_STEP_END:
    1. Sum up estimated tokens of all step outputs.
    2. If total > max_tokens:
       a. Select the oldest K steps to summarize.
       b. Call LLM to produce one-sentence summaries.
       c. Replace the full outputs with summaries in
          ctx.shared["step_outcomes"].
    3. Log the compaction.

Token estimation:
  Uses the same heuristic as strategy/context_compactor.py:
  CJK chars / 2 + other chars / 4.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Sequence

from .middleware import (
    HOOK_STEP_END,
    HookContext,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 30_000
DEFAULT_KEEP_RECENT = 3  # always keep last N steps verbatim
DEFAULT_MIN_SUMMARIZE = 2  # don't summarize if fewer than this many old steps


def _estimate_tokens(text: str) -> int:
    """Heuristic: CJK chars / 2 + other chars / 4."""
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return cjk // 2 + other // 4


def _total_tokens(outputs: list[str]) -> int:
    return sum(_estimate_tokens(o) for o in outputs)


class SummarizationMiddleware:
    """Summarize old step outputs when context exceeds token budget.

    Args:
        client: An OpenAI-compat LLM client (anything with .chat()).
        max_tokens: Token budget. When exceeded, summarize oldest steps.
            Default 30,000.
        keep_recent: Number of recent steps to keep verbatim. Default 3.
        model: Optional model name for the summarization call.
        temperature: LLM temperature for summaries. Default 0.0.
    """

    name = "summarize"

    def __init__(
        self,
        client: Any,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        keep_recent: int = DEFAULT_KEEP_RECENT,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self._client = client
        self._max_tokens = max_tokens
        self._keep_recent = max(1, keep_recent)
        self._model = model
        self._temperature = temperature
        self._compaction_log: list[dict[str, Any]] = []

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook != HOOK_STEP_END:
            return

        # Gather step outputs from shared context
        step_outcomes = ctx.shared.get("step_outcomes", {})
        if not step_outcomes:
            return

        # Build ordered list of (step_name, output_text, token_count)
        steps: list[tuple[str, str, int]] = []
        for name, outcome in step_outcomes.items():
            output = getattr(outcome, "output", "") if outcome else ""
            if isinstance(output, str) and output:
                tokens = _estimate_tokens(output)
                steps.append((name, output, tokens))

        if len(steps) <= self._keep_recent:
            return  # not enough to summarize

        total = sum(t for _, _, t in steps)
        if total <= self._max_tokens:
            return  # under budget

        # Select steps to summarize (all except the most recent K)
        to_summarize = steps[: -self._keep_recent]
        if len(to_summarize) < DEFAULT_MIN_SUMMARIZE:
            return

        # Summarize each old step
        summaries_created = 0
        tokens_saved = 0
        for step_name, output, orig_tokens in to_summarize:
            try:
                summary = self._summarize_one(step_name, output)
                if summary and len(summary) < len(output):
                    # Replace the output in shared context
                    outcome = step_outcomes.get(step_name)
                    if outcome is not None:
                        # Mutate the outcome's output field
                        # (it's a SimpleNamespace in tests, or StepOutcome in prod)
                        try:
                            outcome.output = f"[summarized] {summary}"
                        except AttributeError:
                            pass  # frozen dataclass — skip
                    new_tokens = _estimate_tokens(summary)
                    tokens_saved += orig_tokens - new_tokens
                    summaries_created += 1
            except Exception as e:
                logger.warning(
                    "SummarizationMiddleware: failed to summarize %s: %s",
                    step_name, e,
                )

        if summaries_created > 0:
            self._compaction_log.append({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "steps_summarized": summaries_created,
                "tokens_before": total,
                "tokens_saved": tokens_saved,
                "tokens_after": total - tokens_saved,
            })
            logger.info(
                "SummarizationMiddleware: summarized %d steps, saved ~%d tokens",
                summaries_created, tokens_saved,
            )

    def _summarize_one(self, step_name: str, output: str) -> str | None:
        """Ask the LLM to produce a one-sentence summary of a step output."""
        prompt = (
            f"Summarize the following agent step output in ONE sentence "
            f"(max 50 words). Keep only the key finding or result.\n\n"
            f"Step: {step_name}\n"
            f"Output: {output[:2000]}\n\n"
            f"Summary:"
        )
        messages = [
            {"role": "system", "content": "You produce extremely concise summaries. One sentence only."},
            {"role": "user", "content": prompt},
        ]
        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._model is not None:
            kwargs["model"] = self._model

        try:
            response = self._client.chat(**kwargs)
            content = _extract_content(response)
            return content.strip() if content else None
        except Exception as e:
            logger.warning("Summarize LLM call failed for %s: %s", step_name, e)
            return None

    @property
    def compaction_log(self) -> list[dict[str, Any]]:
        return list(self._compaction_log)


def _extract_content(response: Any) -> str:
    """Extract text content from various LLM response formats."""
    # OpenAI-compat dict format
    if isinstance(response, dict):
        choices = response.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content", "")
    # Object with .choices
    if hasattr(response, "choices"):
        try:
            return response.choices[0].message.content
        except (AttributeError, IndexError):
            pass
    # Object with .content
    if hasattr(response, "content"):
        return response.content
    return str(response)


__all__ = [
    "SummarizationMiddleware",
    "DEFAULT_MAX_TOKENS",
    "_estimate_tokens",
]
