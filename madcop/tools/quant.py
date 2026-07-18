"""Quant factor + simple backtest tools (Gushen P0). Research only."""

from __future__ import annotations

import json
from typing import Any

from madcop.quant.backtest import simple_backtest
from madcop.quant.factors import compute_factors

from .market import load_bars_from_cache_or_fetch, quant_enabled
from .registry import Tool

_DISCLAIMER = (
    "Educational/research only — not investment advice. "
    "Past performance does not predict future results. No live trading."
)


def _json_out(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


class QuantFactorsTool(Tool):
    name = "quant_factors"
    description = (
        "Compute simple technical factors (SMA, momentum, realized vol) from "
        "OHLCV history. Math is done in-tool — do not invent factor numbers. "
        "Uses market history cache or fetches Yahoo chart data."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "range": {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"],
                },
                "market": {
                    "type": "string",
                    "enum": ["auto", "US", "HK", "CN"],
                },
                "sma_fast": {"type": "integer", "description": "default 10"},
                "sma_slow": {"type": "integer", "description": "default 30"},
                "mom_days": {"type": "integer", "description": "default 20"},
            },
            "required": ["symbol"],
        }

    def __call__(self, **kwargs: Any) -> str:
        if not quant_enabled():
            return _json_out({"error": "quant tools disabled (MADCOP_QUANT_ENABLE=0)"})
        symbol = str(kwargs.get("symbol", "")).strip()
        if not symbol:
            return _json_out({"error": "symbol is required"})
        range_ = str(kwargs.get("range", "1y") or "1y")
        market = str(kwargs.get("market", "auto") or "auto")
        sma_fast = int(kwargs.get("sma_fast") or 10)
        sma_slow = int(kwargs.get("sma_slow") or 30)
        mom_days = int(kwargs.get("mom_days") or 20)
        try:
            hist = load_bars_from_cache_or_fetch(
                symbol, range_=range_, interval="1d", market=market
            )
        except Exception as e:  # noqa: BLE001
            return _json_out({"error": str(e), "symbol": symbol, "disclaimer": _DISCLAIMER})
        if hist.get("error"):
            return _json_out({**hist, "disclaimer": _DISCLAIMER})
        factors = compute_factors(
            hist.get("bars") or [],
            sma_fast=sma_fast,
            sma_slow=sma_slow,
            mom_days=mom_days,
        )
        if factors.get("error"):
            return _json_out({**factors, "symbol": hist.get("symbol") or symbol})
        return _json_out(
            {
                "symbol": hist.get("symbol") or symbol,
                "range": range_,
                **factors,
                "disclaimer": _DISCLAIMER,
            }
        )


class QuantBacktestSimpleTool(Tool):
    name = "quant_backtest_simple"
    description = (
        "Minimal single-symbol backtest: buy_hold and/or sma_cross. "
        "Research/education only — not a full production backtester. "
        "Do not invent returns; use this tool's output."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "range": {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"],
                },
                "market": {
                    "type": "string",
                    "enum": ["auto", "US", "HK", "CN"],
                },
                "strategy": {
                    "type": "string",
                    "enum": ["buy_hold", "sma_cross", "both"],
                    "description": "default both",
                },
                "sma_fast": {"type": "integer"},
                "sma_slow": {"type": "integer"},
                "fee_bps": {"type": "number", "description": "fee per side in bps, default 5"},
            },
            "required": ["symbol"],
        }

    def __call__(self, **kwargs: Any) -> str:
        if not quant_enabled():
            return _json_out({"error": "quant tools disabled (MADCOP_QUANT_ENABLE=0)"})
        symbol = str(kwargs.get("symbol", "")).strip()
        if not symbol:
            return _json_out({"error": "symbol is required"})
        range_ = str(kwargs.get("range", "1y") or "1y")
        market = str(kwargs.get("market", "auto") or "auto")
        strategy = str(kwargs.get("strategy", "both") or "both")
        sma_fast = int(kwargs.get("sma_fast") or 10)
        sma_slow = int(kwargs.get("sma_slow") or 30)
        fee_bps = float(kwargs.get("fee_bps") if kwargs.get("fee_bps") is not None else 5)
        try:
            hist = load_bars_from_cache_or_fetch(
                symbol, range_=range_, interval="1d", market=market
            )
        except Exception as e:  # noqa: BLE001
            return _json_out({"error": str(e), "symbol": symbol, "disclaimer": _DISCLAIMER})
        if hist.get("error"):
            return _json_out({**hist, "disclaimer": _DISCLAIMER})
        result = simple_backtest(
            hist.get("bars") or [],
            strategy=strategy,
            sma_fast=sma_fast,
            sma_slow=sma_slow,
            fee_bps=fee_bps,
        )
        if result.get("error"):
            return _json_out({**result, "symbol": hist.get("symbol") or symbol})
        return _json_out(
            {
                "symbol": hist.get("symbol") or symbol,
                "range": range_,
                **result,
                "disclaimer": _DISCLAIMER,
            }
        )
