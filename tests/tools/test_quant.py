"""Tests for quant factors/backtest tools and pure helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

from madcop.quant.backtest import simple_backtest
from madcop.quant.factors import compute_factors
from madcop.tools.quant import QuantBacktestSimpleTool, QuantFactorsTool


def _bars(n: int = 60, start: float = 100.0) -> list[dict]:
    bars = []
    px = start
    for i in range(n):
        # gentle uptrend with small noise
        px = px * (1.002 if i % 3 else 0.999)
        bars.append(
            {
                "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                "o": px,
                "h": px * 1.01,
                "l": px * 0.99,
                "c": px,
                "v": 1_000_000,
            }
        )
    return bars


def test_compute_factors_trend():
    f = compute_factors(_bars(80), sma_fast=5, sma_slow=20, mom_days=10)
    assert f.get("error") is None
    assert f["last_close"] > 0
    assert f["sma_5"] is not None
    assert f["sma_20"] is not None
    assert f["trend"] in ("above_both_sma", "below_both_sma", "mixed")


def test_compute_factors_empty():
    assert "error" in compute_factors([])


def test_simple_backtest_both():
    r = simple_backtest(_bars(80), strategy="both", sma_fast=5, sma_slow=15)
    assert "strategies" in r
    assert "buy_hold" in r["strategies"]
    assert "sma_cross" in r["strategies"]
    assert "total_return_pct" in r["strategies"]["buy_hold"]
    assert "caveats" in r


def test_quant_factors_tool_mocked():
    t = QuantFactorsTool()
    hist = {"symbol": "AAPL", "bars": _bars(80)}
    with patch(
        "madcop.tools.quant.load_bars_from_cache_or_fetch",
        return_value=hist,
    ):
        out = json.loads(t(symbol="AAPL", range="1y"))
    assert out["symbol"] == "AAPL"
    assert out["last_close"] > 0
    assert "disclaimer" in out


def test_quant_backtest_tool_mocked():
    t = QuantBacktestSimpleTool()
    hist = {"symbol": "AAPL", "bars": _bars(80)}
    with patch(
        "madcop.tools.quant.load_bars_from_cache_or_fetch",
        return_value=hist,
    ):
        out = json.loads(t(symbol="AAPL", strategy="both"))
    assert "strategies" in out
    assert "buy_hold" in out["strategies"]


def test_gushen_builtin_registered():
    from madcop.agent.subagent.builtins import GUSHEN, get_builtin

    assert get_builtin("gushen") is GUSHEN
    assert "market_quote" in (GUSHEN.tools or ())
    assert "paper_order" in (GUSHEN.tools or ())
    assert "bash" not in (GUSHEN.tools or ())
    assert "bash" in GUSHEN.disallowed_tools


def test_default_registry_has_market_tools():
    from madcop.tools import default_registry

    reg = default_registry()
    names = set(reg.names())
    for n in (
        "market_quote",
        "market_history",
        "quant_factors",
        "quant_backtest_simple",
        "paper_account",
        "paper_order",
        "paper_reset",
    ):
        assert n in names
        assert reg.get(n).name == n
