"""Minimal single-symbol backtests for research / education only."""

from __future__ import annotations

from typing import Any, Sequence


def _closes(bars: Sequence[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for b in bars:
        c = b.get("c", b.get("close"))
        if c is None:
            continue
        out.append(float(c))
    return out


def _max_drawdown(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for x in equity:
        if x > peak:
            peak = x
        if peak > 0:
            dd = x / peak - 1.0
            if dd < max_dd:
                max_dd = dd
    return max_dd * 100.0


def _buy_hold(closes: Sequence[float], fee_bps: float) -> dict[str, Any]:
    if len(closes) < 2:
        return {"error": "need at least 2 bars"}
    fee = fee_bps / 10_000.0
    # enter at first close, exit at last; round-trip fee once each side
    ret = (closes[-1] / closes[0]) * (1 - fee) * (1 - fee) - 1.0
    # equity path for DD (ignore fee path for simplicity on intermediate)
    eq = [c / closes[0] for c in closes]
    return {
        "total_return_pct": round(ret * 100.0, 4),
        "max_drawdown_pct": round(_max_drawdown(eq), 4),
        "n_trades": 1,
    }


def _sma(values: Sequence[float], window: int, end: int) -> float | None:
    if end < window:
        return None
    chunk = values[end - window : end]
    return sum(chunk) / window


def _sma_cross(
    closes: Sequence[float],
    sma_fast: int,
    sma_slow: int,
    fee_bps: float,
) -> dict[str, Any]:
    if len(closes) < sma_slow + 2:
        return {"error": f"need more than {sma_slow + 2} bars"}
    fee = fee_bps / 10_000.0
    cash = 1.0
    shares = 0.0
    equity: list[float] = []
    n_trades = 0
    position = 0  # 0 flat, 1 long

    for i in range(len(closes)):
        px = closes[i]
        fast = _sma(closes, sma_fast, i + 1)
        slow = _sma(closes, sma_slow, i + 1)
        if fast is not None and slow is not None:
            if position == 0 and fast > slow:
                # buy
                shares = (cash * (1 - fee)) / px
                cash = 0.0
                position = 1
                n_trades += 1
            elif position == 1 and fast < slow:
                cash = shares * px * (1 - fee)
                shares = 0.0
                position = 0
                n_trades += 1
        equity.append(cash + shares * px)

    final = equity[-1] if equity else 1.0
    ret = final - 1.0
    return {
        "total_return_pct": round(ret * 100.0, 4),
        "max_drawdown_pct": round(_max_drawdown(equity), 4),
        "n_trades": n_trades,
    }


def simple_backtest(
    bars: Sequence[dict[str, Any]],
    *,
    strategy: str = "both",
    sma_fast: int = 10,
    sma_slow: int = 30,
    fee_bps: float = 5.0,
) -> dict[str, Any]:
    closes = _closes(bars)
    if len(closes) < 2:
        return {"error": "need at least 2 bars with close prices"}

    strategies: dict[str, Any] = {}
    want = strategy if strategy != "both" else "both"

    if want in ("buy_hold", "both"):
        strategies["buy_hold"] = _buy_hold(closes, fee_bps)
    if want in ("sma_cross", "both"):
        strategies["sma_cross"] = _sma_cross(closes, sma_fast, sma_slow, fee_bps)

    return {
        "strategies": strategies,
        "n_bars": len(closes),
        "sma_fast": sma_fast,
        "sma_slow": sma_slow,
        "fee_bps": fee_bps,
        "caveats": [
            "Educational/research only — not investment advice",
            "No full slippage model beyond fee_bps",
            "Past performance does not predict future results",
        ],
    }
