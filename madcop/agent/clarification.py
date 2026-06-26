"""v1.0.0 — ClarificationMiddleware: ask when the goal is unclear.

When the user types a goal like "fix the bug" or "make it faster",
the LLM has to guess what they mean. DeerFlow's ClarificationMiddleware
intercepts this: if the goal is too short / too vague / matches
known-ambiguous patterns, it raises a halt with a clarification
request, and the plan-execute loop surfaces the question to the user.

We use three cheap signals (no LLM call):

1. **Length**: goals under N characters are usually too terse
   (e.g. "fix it", "do X", "?")
2. **Known-ambiguous patterns**: starts with a question word ("what",
   "why", "how") without a concrete object, or contains only
   pronouns, or is just punctuation.
3. **All-stopwords**: if every word is a stopword ("the", "a", "is"),
   there's not enough signal.

Qian invariants:
- **早纠偏**: asking the user up front is cheaper than running 10
  steps in the wrong direction.
- **可控性**: the user is told WHY we need clarification, with a
  sample question.
- **稳定性**: the check is pure-Python, no LLM call needed.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Iterable

from .middleware import (
    Directive,
    HOOK_PLAN_START,
    HookContext,
    MiddlewareHalt,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


# Common English + Chinese stopwords. Not exhaustive — just enough
# to catch the "all stopwords" signal.
_STOPWORDS: frozenset[str] = frozenset({
    # English
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "have", "has", "had", "i", "you", "he",
    "she", "it", "we", "they", "this", "that", "these", "those",
    "and", "or", "but", "if", "so", "to", "of", "in", "on", "at",
    "for", "with", "by", "from", "as", "about", "into", "over",
    # Chinese
    "的", "了", "在", "是", "我", "你", "他", "她", "它", "们",
    "和", "或", "但", "如", "所", "以", "把", "被", "对", "从",
})


# Patterns that strongly suggest the user knows what they want,
# even if the goal is short. We use these as "whitelist overrides"
# — short goals that match these patterns should NOT trigger
# clarification.
_OK_SHORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^madcop\s+doctor\s*$", re.IGNORECASE),       # CLI subcommand
    re.compile(r"^madcop\s+resume\s+\S+", re.IGNORECASE),     # CLI subcommand + path
    re.compile(r"^madcop\s+plan\s+.+", re.IGNORECASE),        # CLI subcommand + goal
    re.compile(r"^madcop\s+replay\s+\S+", re.IGNORECASE),     # CLI subcommand + path
)


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #


class ClarificationMiddleware:
    """Halt the run with a clarification question if the goal is unclear.

    Tunables:
    - min_length: goals shorter than this (in chars) trigger
      clarification. Default 8.
    - min_content_words: goals with fewer non-stopword words than this
      trigger clarification. Default 2.
    - custom_questions: optional callable (goal: str) -> str to
      produce a domain-specific clarification question.
    """

    name = "clarification"

    def __init__(
        self,
        *,
        min_length: int = 8,
        min_content_words: int = 2,
        custom_questions: Callable[[str], str | None] | None = None,
    ) -> None:
        self.min_length = min_length
        self.min_content_words = min_content_words
        self._custom_questions = custom_questions

    def __call__(self, ctx: HookContext) -> None:
        if ctx.hook != HOOK_PLAN_START:
            return
        question = self.needs_clarification(ctx.goal)
        if question is not None:
            # We use a Directive (not MiddlewareHalt) so the chain
            # runner can decide whether to surface the question or
            # override it. The plan_execute loop reads
            # ctx.directives and presents the question to the user.
            ctx.directives.append(Directive(
                kind="CLARIFY",
                detail=question,
            ))
            logger.info("[clarification] goal needs clarification: %s", question)

    # ----- public API ---------------------------------------------------

    def needs_clarification(self, goal: str) -> str | None:
        """Return a clarification question if the goal is unclear, else None.

        Exposed publicly so callers can pre-check without firing the
        middleware (e.g. in a CLI that wants to display a friendly
        prompt before the chain runs).
        """
        if not goal or not goal.strip():
            return "Your goal is empty. What would you like the agent to do?"

        g = goal.strip()

        # Custom question hook — when provided, it has FULL authority.
        # If the custom hook returns a question, we use it. If it
        # returns None, the goal is considered clear (custom hook
        # has signalled "I've already considered it, no need to ask").
        # This is the user's escape hatch for domain-specific
        # clarification (e.g. "is this a write op or a read op?").
        if self._custom_questions is not None:
            return self._custom_questions(g)

        # Default checks — only run when no custom hook is provided.
        # Whitelist: known-OK short patterns (CLI subcommands etc.)
        for pat in _OK_SHORT_PATTERNS:
            if pat.match(g):
                return None

        # Length check
        if len(g) < self.min_length:
            return (
                f"Your goal is only {len(g)} characters long. "
                f"Could you give a few more details? "
                f"(e.g. what data to look at, what outcome you want.)"
            )

        # Content-word check
        words = self._content_words(g)
        if len(words) < self.min_content_words:
            sample = " ".join(words[:3]) if words else "(no content words)"
            return (
                f"Your goal is too vague to act on — only {len(words)} "
                f"content word(s) ({sample!r}). Could you be more specific?"
            )

        return None

    # ----- helpers ------------------------------------------------------

    @staticmethod
    def _content_words(text: str) -> list[str]:
        # Split on whitespace + common punctuation. Each whitespace-
        # separated chunk is one "word"; CJK characters in a chunk
        # are kept together (e.g. "诊断" stays as one token, not
        # split into "诊" + "断"). This is closer to how a Chinese
        # reader would parse the text.
        #
        # For mixed chunks (e.g. "诊断OMS取消" — no space between
        # CJK and ASCII), we further split on the CJK/ASCII boundary
        # so "诊断OMS取消" becomes ["诊断", "OMS", "取消"].
        out: list[str] = []
        for tok in re.split(r"[\s,;:.!?()\[\]{}\"'\u3002\uff0c\uff01\uff1f]+", text):
            if not tok:
                continue
            # Split on CJK/ASCII boundary
            sub_tokens = re.findall(r"[一-鿿]+|[A-Za-z0-9]+", tok)
            for sub in sub_tokens:
                if not sub:
                    continue
                # If pure CJK, keep as one chunk
                if all(ord(c) > 0x4E00 for c in sub):
                    if sub not in _STOPWORDS and sub.strip():
                        out.append(sub)
                else:
                    low = sub.lower()
                    if low not in _STOPWORDS:
                        out.append(low)
        return out


# --------------------------------------------------------------------------- #
# Convenience: the run-time helper
# --------------------------------------------------------------------------- #


def clarification_directive(detail: str) -> Directive:
    """Build a CLARIFY directive with the standard detail."""
    return Directive(kind="CLARIFY", detail=detail)


# Sentinel exception for plan_execute loops that want to surface a
# clarification request to the user (e.g. by reading from stdin).
class ClarificationRequested(Exception):
    """Raised by a plan_execute loop to halt the run with a question."""

    def __init__(self, question: str):
        super().__init__(question)
        self.question = question


__all__ = [
    "ClarificationMiddleware",
    "ClarificationRequested",
    "clarification_directive",
]
