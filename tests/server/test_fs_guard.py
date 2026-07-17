"""Unit tests for shared filesystem allowlist."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from madcop.server.compat.fs_guard import check_path_allowed


def test_home_allowed():
    p = check_path_allowed(Path.home())
    assert p == Path.home().resolve()


def test_madcop_blocked():
    with pytest.raises(HTTPException) as ei:
        check_path_allowed(Path.home() / ".madcop" / "settings.json")
    assert ei.value.status_code == 403


def test_etc_blocked():
    with pytest.raises(HTTPException) as ei:
        check_path_allowed(Path("/etc/passwd"))
    assert ei.value.status_code == 403
