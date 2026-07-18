"""Local paper (simulated) brokerage — no real money, no broker APIs.

State lives under ~/.madcop/quant/paper/account.json.
Fills are marked at the last research quote (or explicit price).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .store import ensure_quant_dirs

DEFAULT_CASH = 1_000_000.0  # virtual CNY/USD units — label only
_DISCLAIMER = (
    "PAPER TRADING ONLY — simulated fills, not investment advice, "
    "no real broker connection."
)


def paper_dir() -> Path:
    root = ensure_quant_dirs()
    d = root / "paper"
    d.mkdir(parents=True, exist_ok=True)
    return d


def account_path() -> Path:
    return paper_dir() / "account.json"


def _empty_account(cash: float = DEFAULT_CASH) -> dict[str, Any]:
    return {
        "cash": float(cash),
        "currency": "PAPER",
        "positions": {},  # symbol -> {qty, avg_cost}
        "trades": [],  # recent fills (cap 200)
        "updated_at": time.time(),
        "disclaimer": _DISCLAIMER,
    }


def load_account() -> dict[str, Any]:
    path = account_path()
    if not path.exists():
        acc = _empty_account()
        save_account(acc)
        return acc
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "cash" not in data or "positions" not in data:
            return _empty_account()
        data.setdefault("trades", [])
        data.setdefault("currency", "PAPER")
        data.setdefault("disclaimer", _DISCLAIMER)
        return data
    except Exception:  # noqa: BLE001
        return _empty_account()


def save_account(acc: dict[str, Any]) -> None:
    acc["updated_at"] = time.time()
    acc["disclaimer"] = _DISCLAIMER
    path = account_path()
    path.write_text(json.dumps(acc, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_account(cash: float = DEFAULT_CASH) -> dict[str, Any]:
    acc = _empty_account(cash)
    save_account(acc)
    return acc


def mark_to_market(
    acc: dict[str, Any],
    prices: dict[str, float],
) -> dict[str, Any]:
    """Compute equity using provided last prices for open symbols."""
    pos_value = 0.0
    detail = []
    for sym, p in (acc.get("positions") or {}).items():
        qty = float(p.get("qty") or 0)
        avg = float(p.get("avg_cost") or 0)
        px = prices.get(sym)
        if px is None:
            mkt = qty * avg
            upl = 0.0
        else:
            mkt = qty * float(px)
            upl = (float(px) - avg) * qty
        pos_value += mkt
        detail.append(
            {
                "symbol": sym,
                "qty": qty,
                "avg_cost": avg,
                "last": px,
                "market_value": round(mkt, 4),
                "unrealized_pnl": round(upl, 4),
            }
        )
    cash = float(acc.get("cash") or 0)
    equity = cash + pos_value
    return {
        "cash": round(cash, 4),
        "positions_value": round(pos_value, 4),
        "equity": round(equity, 4),
        "positions": detail,
        "n_trades": len(acc.get("trades") or []),
        "currency": acc.get("currency", "PAPER"),
        "disclaimer": _DISCLAIMER,
    }


def place_order(
    *,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    fee_bps: float = 5.0,
) -> dict[str, Any]:
    """Market-style paper fill at ``price``."""
    symbol = (symbol or "").strip().upper()
    side = (side or "").strip().lower()
    if side not in ("buy", "sell"):
        return {"error": "side must be buy or sell", "disclaimer": _DISCLAIMER}
    if not symbol:
        return {"error": "symbol required", "disclaimer": _DISCLAIMER}
    try:
        qty = float(qty)
        price = float(price)
        fee_bps = float(fee_bps)
    except (TypeError, ValueError):
        return {"error": "qty/price/fee_bps must be numbers", "disclaimer": _DISCLAIMER}
    if qty <= 0 or price <= 0:
        return {"error": "qty and price must be > 0", "disclaimer": _DISCLAIMER}

    acc = load_account()
    fee_rate = fee_bps / 10_000.0
    notional = qty * price
    fee = notional * fee_rate
    positions: dict[str, Any] = dict(acc.get("positions") or {})
    pos = dict(positions.get(symbol) or {"qty": 0.0, "avg_cost": 0.0})
    held = float(pos.get("qty") or 0)
    avg = float(pos.get("avg_cost") or 0)
    cash = float(acc.get("cash") or 0)

    if side == "buy":
        cost = notional + fee
        if cost > cash + 1e-9:
            return {
                "error": f"insufficient paper cash: need {cost:.2f}, have {cash:.2f}",
                "disclaimer": _DISCLAIMER,
            }
        new_qty = held + qty
        new_avg = ((held * avg) + notional) / new_qty if new_qty else 0.0
        cash -= cost
        positions[symbol] = {"qty": new_qty, "avg_cost": new_avg}
    else:
        if qty > held + 1e-9:
            return {
                "error": f"insufficient position: have {held}, sell {qty}",
                "disclaimer": _DISCLAIMER,
            }
        proceeds = notional - fee
        cash += proceeds
        new_qty = held - qty
        if new_qty <= 1e-12:
            positions.pop(symbol, None)
        else:
            positions[symbol] = {"qty": new_qty, "avg_cost": avg}

    trade = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "fee": round(fee, 6),
        "fee_bps": fee_bps,
        "paper": True,
    }
    trades = list(acc.get("trades") or [])
    trades.append(trade)
    trades = trades[-200:]

    acc["cash"] = cash
    acc["positions"] = positions
    acc["trades"] = trades
    save_account(acc)

    return {
        "ok": True,
        "trade": trade,
        "cash": round(cash, 4),
        "position": positions.get(symbol),
        "disclaimer": _DISCLAIMER,
    }
