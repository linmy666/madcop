"""Unit tests for mid-run steer queue."""

from __future__ import annotations

from madcop.server.steer_queue import (
    clear_steers,
    drain_steers,
    format_steer_block,
    pending_count,
    push_steer,
)


def test_push_and_drain_fifo():
    clear_steers("s1")
    assert push_steer("s1", "first")["ok"] is True
    assert push_steer("s1", "second")["ok"] is True
    assert pending_count("s1") == 2
    got = drain_steers("s1")
    assert got == ["first", "second"]
    assert pending_count("s1") == 0
    assert drain_steers("s1") == []


def test_format_block():
    block = format_steer_block(["改成中文输出"])
    assert "Steer" in block or "指引" in block
    assert "改成中文输出" in block


def test_reject_empty():
    assert push_steer("s2", "  ")["ok"] is False
    assert push_steer("", "hi")["ok"] is False
