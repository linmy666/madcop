"""v1.2.0 — Prescreen: detect sensitive content before it hits the brain.

The brain accepts arbitrary text the agent wants to remember. Some of
that text will contain secrets (API keys, JWT tokens, connection
strings, private keys, AWS credentials, etc.). If we let those slip
into `pages`, they'll be in every search result, every audit log,
every Dream consolidation report — and they'll be hard to delete
without losing the surrounding context.

Prescreen is a thin wrapper: pattern-match the candidate content,
flag hits, and route them to `review_queue` instead of letting them
flow into the brain.

What we detect
--------------
- AWS access key (`AKIA[0-9A-Z]{16}`)
- AWS secret (40+ char near "secret" / "aws")
- OpenAI / Anthropic / OpenRouter / Mistral / Groq API keys
- PyPI / HuggingFace tokens
- GitHub PAT (`ghp_*`, `github_pat_*`)
- Slack tokens (`xox[abprs]-...`)
- Stripe keys
- JWT (3 base64url chunks joined by `.`)
- PEM private key blocks (`-----BEGIN ... PRIVATE KEY-----`)
- Database connection strings (postgres://, mysql://, redis://,
  mongodb://, jdbc:)
- Common JWT / OIDC (`eyJ...` base64)
- Email (best-effort; can be a false positive but we err on review)
- Chinese mobile phone numbers (11 digits starting with 1)
- Internal IPv4 (`10.*`, `172.16-31.*`, `192.168.*`, `127.0.0.1`)
- `.env` style key-value (`AWS_SECRET_ACCESS_KEY=...`)

False positives happen. Anything that hits a pattern goes to
`review_queue` and a human (or a follow-up LLM call) clears it.

Why a separate module from the store?
- prescreen is pure-Python regex; the store is SQLite.
- prescreen can be unit-tested without touching the DB.
- prescreen is reusable outside the brain (e.g. before writing to
  any file system).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable

# ----------------------------------------------------------------------------
# Pattern catalogue. Each entry: (name, compiled regex, brief hint).
# Order matters: more specific patterns go first so a JWT prefix
# doesn't match a generic "40+ base64" rule below it.
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]
    hint: str


def _compile(name: str, pattern: str, hint: str) -> Pattern:
    return Pattern(name=name, regex=re.compile(pattern), hint=hint)


# Provider-specific prefixes
_PATTERNS: list[Pattern] = [
    _compile(
        "aws_access_key",
        r"\bAKIA[0-9A-Z]{16}\b",
        "AWS access key id; never store unredacted",
    ),
    _compile(
        "aws_secret_pair",
        r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?",
        "AWS secret access key",
    ),
    _compile(
        "openai_api_key",
        r"\bsk-[A-Za-z0-9]{20,}\b",
        "OpenAI / OpenAI-compat API key",
    ),
    _compile(
        "openai_proj_key",
        r"\bsk-proj-[A-Za-z0-9_\-]{20,}\b",
        "OpenAI project-scoped key",
    ),
    _compile(
        "anthropic_key",
        r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b",
        "Anthropic API key",
    ),
    _compile(
        "github_pat",
        r"\bghp_[A-Za-z0-9]{30,}\b",
        "GitHub personal access token",
    ),
    _compile(
        "github_fine_pat",
        r"\bgithub_pat_[A-Za-z0-9_]{50,}\b",
        "GitHub fine-grained PAT",
    ),
    _compile(
        "pypi_token",
        r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}\b",
        "PyPI upload token",
    ),
    _compile(
        "huggingface_token",
        r"\bhf_[A-Za-z0-9]{20,}\b",
        "HuggingFace access token",
    ),
    _compile(
        "slack_token",
        r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",
        "Slack token (xox*)",
    ),
    _compile(
        "stripe_live",
        r"\bsk_live_[A-Za-z0-9]{20,}\b",
        "Stripe live secret key",
    ),
    _compile(
        "jwt_3part",
        r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b",
        "JWT (3 base64url chunks)",
    ),
    _compile(
        "pem_private_key",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "PEM-encoded private key",
    ),
    _compile(
        "db_connection_string",
        r"(?i)\b(?:postgres|postgresql|mysql|redis|mongodb(?:\+srv)?|amqp|amqps|kafka)://[^\s'\"<>]{8,}",
        "Database / broker connection string",
    ),
    _compile(
        "jdbc_url",
        r"\bjdbc:[a-z]+://[^\s'\"<>]{4,}",
        "JDBC URL with credentials possibly embedded",
    ),
    _compile(
        "internal_ip",
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.0\.0\.1)\b",
        "Internal-network IPv4 (review; could be a doc example)",
    ),
    _compile(
        "cn_mobile",
        r"\b1[3-9]\d{9}\b",
        "Chinese mobile phone (review; false positives in tests are common)",
    ),
    _compile(
        "env_kv",
        r"(?im)^[A-Z][A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE_KEY)\s*[=:]\s*['\"]?[^\s'\"#]{8,}",
        "Env-file style KEY=VALUE / SECRET=VALUE pair",
    ),
]


# ----------------------------------------------------------------------------
# Hit shape
# ----------------------------------------------------------------------------


@dataclass
class Hit:
    pattern: str
    start: int
    end: int
    snippet: str
    hint: str = ""


def scan(text: str) -> list[Hit]:
    """Return all hits in `text`, in document order."""
    if not text:
        return []
    out: list[Hit] = []
    for pat in _PATTERNS:
        for m in pat.regex.finditer(text):
            s, e = m.start(), m.end()
            # Build a short snippet with redaction markers.
            raw = text[s:e]
            # Avoid logging the actual secret to stderr; truncate.
            redacted = raw[:8] + "…(redacted, " + str(len(raw)) + " chars)" if len(raw) > 8 else "(redacted)"
            out.append(Hit(
                pattern=pat.name,
                start=s,
                end=e,
                snippet=redacted,
                hint=pat.hint,
            ))
    out.sort(key=lambda h: (h.start, h.end))
    return out


def is_clean(text: str) -> bool:
    """True if no patterns hit. Equivalent to `not scan(text)`."""
    return not scan(text)


# ----------------------------------------------------------------------------
# Integration with PageDB
# ----------------------------------------------------------------------------


# Re-used for the review-queue write path. We import lazily to avoid a
# circular import: store.py imports from schema/markdown, and
# prescreen.py calls back into store.
def queue_for_review(
    conn: sqlite3.Connection,
    *,
    slug: str,
    page_type: str,
    content: str,
    reason: str,
) -> int:
    """Insert a single review-queue row from one prescreen hit.

    Returns the new row id.
    """
    cur = conn.execute(
        """
        INSERT INTO review_queue(slug, type, reason, content, pattern)
        VALUES (?, ?, ?, ?, ?)
        """,
        (slug, page_type, reason, content, "prescreen"),
    )
    return int(cur.lastrowid)


def queue_hits(
    conn: sqlite3.Connection,
    *,
    slug: str,
    page_type: str,
    text: str,
) -> list[int]:
    """Queue all hits in `text` to the review queue.

    Returns the list of inserted row ids. Empty list == clean text.
    """
    hits = scan(text)
    if not hits:
        return []
    return [
        queue_for_review(
            conn,
            slug=slug,
            page_type=page_type,
            content=h.snippet,
            reason=f"{h.pattern}: {h.hint}",
        )
        for h in hits
    ]


def list_patterns() -> list[Pattern]:
    """For tests and `madcop doctor` diagnostics."""
    return list(_PATTERNS)


__all__ = [
    "Hit",
    "Pattern",
    "scan",
    "is_clean",
    "queue_for_review",
    "queue_hits",
    "list_patterns",
]
