"""v1.2.0 — Tests for the prescreen (sensitive content detection)."""
from __future__ import annotations

import pytest

from madcop.brain.prescreen import (
    Hit,
    Pattern,
    is_clean,
    list_patterns,
    queue_hits,
    scan,
)
from madcop.brain.store import PageDB


# ---------------------------------------------------------------------------
# Pattern catalogue
# ---------------------------------------------------------------------------


def test_pattern_catalogue_has_minimum_coverage():
    patterns = list_patterns()
    assert len(patterns) >= 12  # we promised 12+


def test_pattern_catalogue_contains_key_categories():
    names = {p.name for p in list_patterns()}
    # Cloud / API / Tokens / DB / Network
    assert "aws_access_key" in names
    assert "openai_api_key" in names
    assert "anthropic_key" in names
    assert "pypi_token" in names
    assert "github_pat" in names
    assert "jwt_3part" in names
    assert "pem_private_key" in names
    assert "db_connection_string" in names


# ---------------------------------------------------------------------------
# scan()
# ---------------------------------------------------------------------------


def test_scan_clean_text_returns_empty():
    assert scan("This is a perfectly innocent sentence.") == []


def test_scan_empty_text_returns_empty():
    assert scan("") == []


def test_scan_finds_aws_access_key():
    hits = scan("Key is AKIAIOSFODNN7EXAMPLE")
    assert any(h.pattern == "aws_access_key" for h in hits)


def test_scan_finds_openai_key():
    hits = scan("Use sk-abcdef1234567890abcdef1234")
    assert any(h.pattern == "openai_api_key" for h in hits)


def test_scan_finds_pypi_token():
    hits = scan("pypi-AgEIcHlwaS5vcmc" + "x" * 60)
    assert any(h.pattern == "pypi_token" for h in hits)


def test_scan_finds_pem_block():
    hits = scan("see -----BEGIN RSA PRIVATE KEY-----\nfoo")
    assert any(h.pattern == "pem_private_key" for h in hits)


def test_scan_finds_db_connection_string():
    hits = scan("use postgres://user:secret@host:5432/db")
    assert any(h.pattern == "db_connection_string" for h in hits)


def test_scan_finds_jwt():
    # Three base64url chunks joined by dots
    hits = scan("eyJabc1234567.eyJabc1234567.signaturepart12345")
    assert any(h.pattern == "jwt_3part" for h in hits)


def test_scan_redacts_snippet():
    text = "key is AKIAIOSFODNN7EXAMPLE"
    hits = scan(text)
    assert "redacted" in hits[0].snippet
    # The full secret should NOT leak in the snippet.
    assert "AKIAIOSFODNN7EXAMPLE" not in hits[0].snippet


def test_scan_returns_sorted_by_position():
    text = "first AKIAIOSFODNN7EXAMPLE then eyJabc12345.eyJabc12345.sigpart1234567"
    hits = scan(text)
    positions = [h.start for h in hits]
    assert positions == sorted(positions)


def test_scan_handles_multiple_hits_of_same_pattern():
    text = "AKIAIOSFODNN7EXAMPLE and AKIAIOSFODNN8EXAMPLE"
    hits = scan(text)
    assert sum(1 for h in hits if h.pattern == "aws_access_key") == 2


def test_is_clean_true_for_safe_text():
    assert is_clean("Madcop v1.2.0 was released today.") is True


def test_is_clean_false_for_dangerous_text():
    assert is_clean("password sk-abcdefghijklmnopqrstuv") is False


def test_scan_handles_chinese_phone():
    hits = scan("call me at 13812345678")
    assert any(h.pattern == "cn_mobile" for h in hits)


def test_scan_handles_internal_ip():
    hits = scan("server is at 192.168.1.1")
    assert any(h.pattern == "internal_ip" for h in hits)


def test_scan_handles_env_kv_pair():
    hits = scan("AWS_SECRET_ACCESS_KEY=abcdefghijklmnopqrstuv")
    assert any(h.pattern == "env_kv" for h in hits)


# ---------------------------------------------------------------------------
# queue_hits()
# ---------------------------------------------------------------------------


def test_queue_hits_writes_to_review_queue(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    ids = queue_hits(
        db._conn,
        slug="leaked",
        page_type="person",
        text="use sk-abcdefghijklmnopqrstuv and AKIAIOSFODNN7EXAMPLE",
    )
    assert len(ids) >= 2
    n = db._conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
    assert n == len(ids)
    db.close()


def test_queue_hits_clean_text_writes_nothing(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    ids = queue_hits(
        db._conn,
        slug="safe",
        page_type="person",
        text="This is a totally normal sentence.",
    )
    assert ids == []
    n = db._conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
    assert n == 0
    db.close()


def test_queue_hits_records_pattern_and_reason(tmp_path):
    db = PageDB(tmp_path / "brain.db")
    queue_hits(
        db._conn,
        slug="x",
        page_type="person",
        text="AKIAIOSFODNN7EXAMPLE",
    )
    row = db._conn.execute(
        "SELECT reason, pattern, slug FROM review_queue LIMIT 1"
    ).fetchone()
    assert row["pattern"] == "prescreen"
    assert "aws_access_key" in row["reason"]
    assert row["slug"] == "x"
    db.close()
