"""v1.2.0 — Knowledge brain (PageDB + markdown + prescreen + Dream + middleware).

A "knowledge brain" is the local-first, long-term memory a personal AI
agent uses across sessions. It lives in a single SQLite database,
indexed by FTS5 for fast text search, with separate tables for links,
timeline entries, tags, version history, and a review queue for
sensitive content.

Public surface (use these, not the modules below)
------------------------------------------------
  PageDB           — CRUD over pages/links/timeline/tags
  Page, SearchHit  — data shapes returned by PageDB methods
  parse            — markdown → page fields
  BrainMiddleware  — drop into the v1.0 middleware chain to auto-record
  scan / is_clean  — sensitive content prescreen
  queue_hits       — route prescreen hits to review_queue
  Dream / maintain — periodic housekeeping
  ConsolidationReport

Why a public surface here?
- We want callers to import `from madcop.brain import PageDB`,
  not `from madcop.brain.store import PageDB`. The latter still works
  but it locks them to a module layout we may refactor.
"""
from __future__ import annotations

from .consolidate import ConsolidationReport, Dream, maintain
from .markdown import ParseResult, VALID_TYPES, extract_inline_tags, parse
from .middleware import LEARN_PREFIX, BrainMiddleware
from .prescreen import (
    Hit,
    Pattern,
    is_clean,
    list_patterns,
    queue_hits,
    queue_for_review,
    scan,
)
from .store import Page, PageDB, SearchHit

__all__ = [
    # markdown
    "ParseResult",
    "VALID_TYPES",
    "extract_inline_tags",
    "parse",
    # store
    "Page",
    "PageDB",
    "SearchHit",
    # prescreen
    "Hit",
    "Pattern",
    "is_clean",
    "list_patterns",
    "queue_hits",
    "queue_for_review",
    "scan",
    # consolidate
    "ConsolidationReport",
    "Dream",
    "maintain",
    # middleware
    "BrainMiddleware",
    "LEARN_PREFIX",
]

# v2.1 — Unified Brain + Memory façade (Gap 10)
from .unified import UnifiedEntry, UnifiedConfig, UnifiedKnowledge
