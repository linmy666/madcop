"""Tests for the welcome banner."""

from __future__ import annotations

import io
import pytest
from rich.console import Console

from madcop.banner import (
    COMMANDS,
    LOGO_LINES,
    render_banner_console,
    render_banner_plain,
)


def test_logo_lines_non_empty() -> None:
    assert len(LOGO_LINES) > 0
    # The block-letter banner should mention both parts of the name
    joined = " ".join(LOGO_LINES)
    assert "MAD" in joined
    assert "COP" in joined


def test_logo_has_supply_chain_elements() -> None:
    joined = " ".join(LOGO_LINES)
    assert "[====]" in joined or "===" in joined  # container helmet
    assert "|||||||||" in joined                # barcode
    assert "(O)" in joined                     # camera eyes
    assert "[MAD]" in joined and "[COP]" in joined
    assert "SUPPLY CHAIN SECURITY" in joined


def test_splash_load_has_siren_marks() -> None:
    from madcop.banner import _splash_frames
    joined = " ".join(_splash_frames())
    assert "🚢" in joined or "[CARG]" in joined
    assert "LOADING SUPPLY MATRIX" in joined


def test_commands_list_includes_v05_features() -> None:
    cmds = " ".join(c for c, _ in COMMANDS)
    assert "skill" in cmds                # skill scaffolder
    assert "eval" in cmds                 # eval harness
    assert "replay" in cmds
    assert "decisions" in cmds
    assert "agent" in cmds


def test_render_banner_plain_has_key_lines() -> None:
    out = render_banner_plain()
    assert "madcop v0.5.0" in out
    assert "DEPT" in out or "LOGISTICS ENFORCEMENT" in out
    assert "MAD" in out and "COP" in out
    assert "Lin Ruihan" in out
    assert "MIT" in out
    assert "I am MADCOP" in out  # the supply-chain greeting


def test_render_banner_console_runs_without_error() -> None:
    """Smoke test: the rich variant doesn't crash on a real console."""
    buf = io.StringIO()
    console = Console(file=buf, width=100, force_terminal=True)
    render_banner_console(console)
    out = buf.getvalue()
    # The colour markup is stripped from output by rich
    assert "MAD" in out or "COP" in out  # at least the ASCII survives
    assert "madcop" in out.lower()