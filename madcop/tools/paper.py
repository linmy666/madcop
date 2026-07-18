"""Paper trading tools for Gushen — simulated only, never hits a real broker."""

from __future__ import annotations

import json
from typing import Any

from madcop.quant.paper import (
    load_account,
    mark_to_market,
    place_order,
    reset_account,
)
from madcop.tools.market import MarketQuoteTool, quant_enabled

from .registry import Tool

_DISCLAIMER = (
    "PAPER TRADING ONLY — simulated fills using research quotes. "
    "Not investment advice. No real broker."
)


def _json_out(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _last_price(symbol: str, market: str = "auto") -> tuple[float | None, str | None]:
    """Fetch research quote; return (price, error)."""
    raw = MarketQuoteTool()(symbol=symbol, market=market)
    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        return None, f"quote parse failed: {e}"
    if data.get("error"):
        return None, str(data["error"])
    px = data.get("price")
    if px is None:
        return None, "no price in quote"
    return float(px), None


class PaperAccountTool(Tool):
    name = "paper_account"
    description = (
        "Show the local PAPER trading account (virtual cash + positions). "
        "Optional mark-to-market via research quotes. NOT a real broker."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mark": {
                    "type": "boolean",
                    "description": "If true, refresh prices for open positions (default true)",
                },
            },
            "required": [],
        }

    def __call__(self, **kwargs: Any) -> str:
        if not quant_enabled():
            return _json_out({"error": "quant tools disabled", "disclaimer": _DISCLAIMER})
        acc = load_account()
        mark = kwargs.get("mark", True)
        if mark is False or str(mark).lower() in ("0", "false", "no"):
            return _json_out(
                {
                    "cash": acc.get("cash"),
                    "positions": acc.get("positions"),
                    "recent_trades": (acc.get("trades") or [])[-10:],
                    "disclaimer": _DISCLAIMER,
                }
            )
        prices: dict[str, float] = {}
        errors: dict[str, str] = {}
        for sym in (acc.get("positions") or {}):
            px, err = _last_price(sym)
            if px is not None:
                prices[sym] = px
            elif err:
                errors[sym] = err
        summary = mark_to_market(acc, prices)
        if errors:
            summary["quote_errors"] = errors
        summary["recent_trades"] = (acc.get("trades") or [])[-10:]
        return _json_out(summary)


class PaperOrderTool(Tool):
    name = "paper_order"
    description = (
        "Place a PAPER (simulated) market order filled at the latest research quote. "
        "side=buy|sell. NEVER sends orders to a real broker. "
        "Always remind the user this is virtual."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "qty": {"type": "number", "description": "Share quantity > 0"},
                "market": {
                    "type": "string",
                    "enum": ["auto", "US", "HK", "CN"],
                },
                "price": {
                    "type": "number",
                    "description": "Optional override fill price; default = market_quote",
                },
                "fee_bps": {"type": "number", "description": "Fee per side in bps, default 5"},
            },
            "required": ["symbol", "side", "qty"],
        }

    def __call__(self, **kwargs: Any) -> str:
        if not quant_enabled():
            return _json_out({"error": "quant tools disabled", "disclaimer": _DISCLAIMER})
        symbol = str(kwargs.get("symbol", "")).strip()
        side = str(kwargs.get("side", "")).strip()
        qty = kwargs.get("qty")
        market = str(kwargs.get("market", "auto") or "auto")
        fee_bps = float(kwargs.get("fee_bps") if kwargs.get("fee_bps") is not None else 5)
        price = kwargs.get("price")
        if price is None:
            px, err = _last_price(symbol, market)
            if err or px is None:
                return _json_out(
                    {
                        "error": err or "no price",
                        "symbol": symbol,
                        "disclaimer": _DISCLAIMER,
                    }
                )
            price = px
        else:
            price = float(price)
        result = place_order(
            symbol=symbol,
            side=side,
            qty=float(qty),
            price=float(price),
            fee_bps=fee_bps,
        )
        return _json_out(result)


class PaperResetTool(Tool):
    name = "paper_reset"
    description = (
        "Reset the PAPER trading account to starting virtual cash "
        f"(default 1_000_000). Destructive for sim history only."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cash": {
                    "type": "number",
                    "description": "Starting virtual cash (default 1000000)",
                },
            },
            "required": [],
        }

    def __call__(self, **kwargs: Any) -> str:
        if not quant_enabled():
            return _json_out({"error": "quant tools disabled", "disclaimer": _DISCLAIMER})
        cash = kwargs.get("cash")
        if cash is None:
            acc = reset_account()
        else:
            acc = reset_account(float(cash))
        return _json_out(
            {
                "ok": True,
                "cash": acc["cash"],
                "positions": acc["positions"],
                "disclaimer": _DISCLAIMER,
            }
        )
