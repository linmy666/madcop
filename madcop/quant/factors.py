"""Simple technical factors from OHLCV bars (tool-side math only)."""

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


def _sma(values: Sequence[float], window: int) -> float | None:
    if window <= 0 or len(values) < window:
        return None
    chunk = values[-window:]
    return sum(chunk) / window


def compute_factors(
    bars: Sequence[dict[str, Any]],
    *,
    sma_fast: int = 10,
    sma_slow: int = 30,
    mom_days: int = 20,
    vol_days: int = 20,
) -> dict[str, Any]:
    """Compute SMA / momentum / realized vol from close series.

    ``bars`` items need at least ``c`` (or ``close``) and preferably ``date``.
    """
    closes = _closes(bars)
    if not closes:
        return {"error": "no close prices in bars"}

    last = closes[-1]
    sma_f = _sma(closes, sma_fast)
    sma_s = _sma(closes, sma_slow)

    mom: float | None = None
    if mom_days > 0 and len(closes) > mom_days:
        base = closes[-(mom_days + 1)]
        if base:
            mom = (last / base - 1.0) * 100.0

    vol_ann: float | None = None
    if vol_days > 1 and len(closes) > vol_days:
        rets: list[float] = []
        window = closes[-(vol_days + 1) :]
        for i in range(1, len(window)):
            if window[i - 1]:
                rets.append(window[i] / window[i - 1] - 1.0)
        if len(rets) >= 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            # annualize daily vol (252 trading days)
            vol_ann = (var ** 0.5) * (252 ** 0.5) * 100.0

    if sma_f is not None and sma_s is not None:
        if last >= sma_f and last >= sma_s:
            trend = "above_both_sma"
        elif last < sma_f and last < sma_s:
            trend = "below_both_sma"
        else:
            trend = "mixed"
    else:
        trend = "insufficient_data"

    as_of = None
    if bars:
        as_of = bars[-1].get("date") or bars[-1].get("t")

    return {
        "last_close": round(last, 6),
        f"sma_{sma_fast}": None if sma_f is None else round(sma_f, 6),
        f"sma_{sma_slow}": None if sma_s is None else round(sma_s, 6),
        f"momentum_{mom_days}d_pct": None if mom is None else round(mom, 4),
        f"volatility_{vol_days}d_ann_pct": None if vol_ann is None else round(vol_ann, 4),
        "trend": trend,
        "as_of_bar": as_of,
        "n_bars": len(closes),
    }
