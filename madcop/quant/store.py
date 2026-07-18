"""Local storage under ~/.madcop/quant (or MADCOP_QUANT_DIR)."""

from __future__ import annotations

import os
from pathlib import Path


def quant_root() -> Path:
    override = os.environ.get("MADCOP_QUANT_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".madcop" / "quant").resolve()


def ensure_quant_dirs() -> Path:
    root = quant_root()
    for sub in ("cache", "reports"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root
