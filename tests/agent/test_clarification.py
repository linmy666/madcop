"""v1.0.0 — Tests for ClarificationMiddleware."""
from __future__ import annotations

import pytest

from madcop.agent.clarification import (
    ClarificationMiddleware,
    ClarificationRequested,
    clarification_directive,
)
from madcop.agent.middleware import (
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    Directive,
    HookContext,
)


# ---------------------------------------------------------------------------
# Direct needs_clarification API
# ---------------------------------------------------------------------------


def test_empty_goal_needs_clarification():
    mw = ClarificationMiddleware()
    q = mw.needs_clarification("")
    assert q is not None
    assert "empty" in q.lower()


def test_whitespace_only_goal_needs_clarification():
    mw = ClarificationMiddleware()
    assert mw.needs_clarification("    \n\t  ") is not None


def test_short_goal_needs_clarification():
    mw = ClarificationMiddleware(min_length=10)
    q = mw.needs_clarification("fix it")
    assert q is not None
    assert "characters" in q.lower() or "specific" in q.lower()


def test_short_goal_with_specific_min_length_passes():
    mw = ClarificationMiddleware(min_length=5)
    # 9 chars, all content words — should pass
    assert mw.needs_clarification("fix the bug") is None


def test_all_stopwords_needs_clarification():
    mw = ClarificationMiddleware()
    q = mw.needs_clarification("the is a an")  # all stopwords
    assert q is not None
    assert "vague" in q.lower() or "content" in q.lower()


def test_specific_goal_passes():
    mw = ClarificationMiddleware()
    assert mw.needs_clarification("Diagnose the OMS cancel spike in the last 4 hours") is None


def test_cjk_goal_with_sufficient_chars_passes():
    mw = ClarificationMiddleware(min_length=8, min_content_words=2)
    # Chinese 12 chars, all content (no stopwords): passes
    assert mw.needs_clarification("诊断OMS取消峰值") is None


def test_short_cjk_with_stopwords_needs_clarification():
    """All Chinese stopwords like '的' / '了' should trigger clarification."""
    mw = ClarificationMiddleware()
    q = mw.needs_clarification("的了在了在了")
    assert q is not None


# ---------------------------------------------------------------------------
# Whitelist: known-OK short patterns
# ---------------------------------------------------------------------------


def test_whitelist_madcop_doctor_passes():
    mw = ClarificationMiddleware()
    assert mw.needs_clarification("madcop doctor") is None


def test_whitelist_madcop_resume_passes():
    mw = ClarificationMiddleware()
    assert mw.needs_clarification("madcop resume run.json") is None


def test_whitelist_madcop_plan_with_long_goal_passes():
    mw = ClarificationMiddleware()
    # The whitelist matches "madcop plan X" where X is anything non-empty
    assert mw.needs_clarification("madcop plan diagnose the spike") is None


# ---------------------------------------------------------------------------
# Custom questions
# ---------------------------------------------------------------------------


def test_custom_questions_take_precedence():
    def custom(g: str) -> str:
        return f"custom question for {g!r}"
    mw = ClarificationMiddleware(custom_questions=custom)
    assert mw.needs_clarification("Diagnose the OMS cancel spike in the last 4 hours") == "custom question for 'Diagnose the OMS cancel spike in the last 4 hours'"


def test_custom_questions_can_return_none():
    """Custom hook returning None means 'no clarification needed'."""
    def custom(g: str) -> str | None:
        return None
    mw = ClarificationMiddleware(custom_questions=custom)
    # Even vague goal — custom returns None
    assert mw.needs_clarification("fix it") is None


# ---------------------------------------------------------------------------
# Middleware hook integration
# ---------------------------------------------------------------------------


def test_middleware_emits_clarify_directive_on_ambiguous_goal():
    mw = ClarificationMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="fix it")
    mw(ctx)
    assert any(d.kind == "CLARIFY" for d in ctx.directives)


def test_middleware_silent_on_clear_goal():
    mw = ClarificationMiddleware()
    ctx = HookContext(hook=HOOK_PLAN_START, goal="Diagnose the OMS cancel spike in the last 4 hours")
    mw(ctx)
    assert ctx.directives == []


def test_middleware_only_runs_on_plan_start():
    mw = ClarificationMiddleware()
    # Even an ambiguous goal, but on a non-plan_start hook
    ctx = HookContext(hook=HOOK_PLAN_END, goal="fix it")
    mw(ctx)
    assert ctx.directives == []


def test_clarification_directive_helper():
    d = clarification_directive("what?")
    assert d.kind == "CLARIFY"
    assert d.detail == "what?"


def test_clarification_requested_exception_carries_question():
    e = ClarificationRequested("what do you mean?")
    assert e.question == "what do you mean?"
    assert str(e) == "what do you mean?"


# ---------------------------------------------------------------------------
# Content words extraction
# ---------------------------------------------------------------------------


def test_content_words_skips_stopwords():
    mw = ClarificationMiddleware()
    # "fix the bug" → ["fix", "bug"] (skip "the")
    words = mw._content_words("fix the bug")
    assert "fix" in words
    assert "bug" in words
    assert "the" not in words


def test_content_words_handles_mixed_cjk_and_ascii():
    mw = ClarificationMiddleware()
    words = mw._content_words("诊断 OMS 取消 spike")
    # CJK chars split, ASCII kept
    assert "诊断" in words
    assert "oms" in words  # lowercased
    assert "取消" in words
    assert "spike" in words
