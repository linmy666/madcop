"""Market data tools for the Gushen (股神) research agent.

P0 provider: Yahoo Finance chart API (delayed, no API key, research-grade).
No live trading. Numbers must come from this module — never invent prices.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import Tool

_ssl_ctx_unverified = ssl.create_default_context()
_ssl_ctx_unverified.check_hostname = False
_ssl_ctx_unverified.verify_mode = ssl.CERT_NONE

_DISCLAIMER = "Not investment advice. Delayed research quote/history only. No live trading."

# Yahoo chart base (v8)
_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"

_VALID_RANGES = ("1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max")
_VALID_INTERVALS = ("1d", "1wk", "1mo")


def quant_enabled() -> bool:
    return os.environ.get("MADCOP_QUANT_ENABLE", "1").strip() not in ("0", "false", "False", "no")


def normalize_symbol(symbol: str, market: str = "auto") -> str:
    """Map common user inputs to Yahoo-style symbols."""
    s = (symbol or "").strip().upper()
    if not s:
        return s
    # already has exchange suffix
    if "." in s:
        return s
    m = (market or "auto").strip().upper()
    # 6-digit A-share
    if re.fullmatch(r"\d{6}", s):
        if m == "HK":
            return f"{s.lstrip('0') or '0'}.HK" if len(s) <= 4 else f"{s}.HK"
        # Shanghai 5/6, Shenzhen 0/3
        if s.startswith(("5", "6", "9")):
            return f"{s}.SS"
        return f"{s}.SZ"
    # 4-digit often HK without leading zeros style 0700 → 0700.HK
    if re.fullmatch(r"\d{4}", s) and m in ("AUTO", "HK"):
        return f"{s}.HK"
    # 1–5 digit numeric → treat as HK if market HK or auto-ish short code
    if re.fullmatch(r"\d{1,5}", s) and m == "HK":
        return f"{s.zfill(4)}.HK"
    return s


def _cache_dir() -> Path:
    from madcop.quant.store import ensure_quant_dirs

    return ensure_quant_dirs() / "cache"


def _cache_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key)
    return _cache_dir() / f"{safe}.json"


def _read_cache(key: str, ttl_sec: float) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(raw.get("_cached_at", 0)) > ttl_sec:
            return None
        return raw.get("data")
    except Exception:  # noqa: BLE001
        return None


def _write_cache(key: str, data: dict[str, Any]) -> None:
    try:
        path = _cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"_cached_at": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass


def fetch_chart(
    symbol: str,
    *,
    range_: str = "1y",
    interval: str = "1d",
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch Yahoo chart JSON. Exposed for tests to monkeypatch."""
    if range_ not in _VALID_RANGES:
        range_ = "1y"
    if interval not in _VALID_INTERVALS:
        interval = "1d"
    safe = urllib.parse.quote(symbol, safe="")
    qs = urllib.parse.urlencode({"range": range_, "interval": interval})
    url = f"{_CHART_BASE}{safe}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MadCop/1.0; research)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx_unverified) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code} for {symbol}: {body}") from e
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"fetch failed for {symbol}: {e}") from e
    return json.loads(raw)


def parse_chart(payload: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Normalize Yahoo chart payload into quote + bars."""
    chart = (payload or {}).get("chart") or {}
    err = chart.get("error")
    if err:
        return {"error": str(err), "symbol": symbol}
    results = chart.get("result") or []
    if not results:
        return {"error": "empty chart result", "symbol": symbol}
    r0 = results[0]
    meta = r0.get("meta") or {}
    ts = r0.get("timestamp") or []
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    bars: list[dict[str, Any]] = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        try:
            date = datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            date = str(t)
        bars.append(
            {
                "date": date,
                "o": _num(opens[i] if i < len(opens) else None),
                "h": _num(highs[i] if i < len(highs) else None),
                "l": _num(lows[i] if i < len(lows) else None),
                "c": float(c),
                "v": _num(volumes[i] if i < len(volumes) else None),
            }
        )

    price = meta.get("regularMarketPrice")
    if price is None and bars:
        price = bars[-1]["c"]
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    change_pct = None
    if price is not None and prev:
        try:
            change_pct = round((float(price) / float(prev) - 1.0) * 100.0, 4)
        except Exception:  # noqa: BLE001
            change_pct = None

    as_of = None
    rt = meta.get("regularMarketTime")
    if rt:
        try:
            as_of = datetime.fromtimestamp(int(rt), tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            as_of = str(rt)
    elif bars:
        as_of = bars[-1]["date"]

    return {
        "symbol": meta.get("symbol") or symbol,
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
        "price": None if price is None else float(price),
        "previous_close": None if prev is None else float(prev),
        "change_pct": change_pct,
        "as_of": as_of,
        "bars": bars,
        "source": "yahoo_chart",
        "delayed": True,
        "disclaimer": _DISCLAIMER,
    }


def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _json_out(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


class MarketQuoteTool(Tool):
    """Latest delayed quote via Yahoo chart meta."""

    name = "market_quote"
    description = (
        "Get a delayed research quote for a ticker (Yahoo-style symbol). "
        "Examples: AAPL (US), 0700.HK (HK), 600519.SS / 000001.SZ (CN). "
        "Never invent prices — if fetch fails the result contains error. "
        "Not investment advice; no live trading."
    )
    timeout: float = 15.0

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker, e.g. AAPL, 0700.HK, 600519.SS",
                },
                "market": {
                    "type": "string",
                    "description": "auto | US | HK | CN — helps resolve bare codes",
                    "enum": ["auto", "US", "HK", "CN"],
                },
            },
            "required": ["symbol"],
        }

    def __call__(self, **kwargs: Any) -> str:
        if not quant_enabled():
            return _json_out({"error": "quant tools disabled (MADCOP_QUANT_ENABLE=0)"})
        raw_sym = str(kwargs.get("symbol", "")).strip()
        if not raw_sym:
            return _json_out({"error": "symbol is required"})
        market = str(kwargs.get("market", "auto") or "auto")
        symbol = normalize_symbol(raw_sym, market)
        cache_key = f"quote_{symbol}"
        cached = _read_cache(cache_key, ttl_sec=300)
        if cached and "price" in cached:
            cached = {**cached, "cached": True}
            return _json_out(cached)
        try:
            payload = fetch_chart(symbol, range_="5d", interval="1d", timeout=self.timeout)
            parsed = parse_chart(payload, symbol)
        except Exception as e:  # noqa: BLE001
            return _json_out({"error": str(e), "symbol": symbol, "disclaimer": _DISCLAIMER})
        if parsed.get("error"):
            return _json_out(parsed)
        out = {
            "symbol": parsed["symbol"],
            "currency": parsed.get("currency"),
            "exchange": parsed.get("exchange"),
            "price": parsed.get("price"),
            "previous_close": parsed.get("previous_close"),
            "change_pct": parsed.get("change_pct"),
            "as_of": parsed.get("as_of"),
            "source": parsed.get("source"),
            "delayed": True,
            "disclaimer": _DISCLAIMER,
            "cached": False,
        }
        if out["price"] is None:
            return _json_out({"error": "no price in chart meta", "symbol": symbol, "disclaimer": _DISCLAIMER})
        _write_cache(cache_key, out)
        return _json_out(out)


class MarketHistoryTool(Tool):
    """OHLCV history; returns summary + optional cache path for full bars."""

    name = "market_history"
    description = (
        "Fetch daily/weekly OHLCV history for research (Yahoo chart). "
        "Returns bar count, first/last, and a short tail of bars; full series "
        "may be cached under ~/.madcop/quant/cache. Do not invent OHLC data."
    )
    timeout: float = 20.0
    # max bars to embed in the tool message (avoid context blow-up)
    max_bars_in_response: int = 40

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker, e.g. AAPL, 0700.HK"},
                "range": {
                    "type": "string",
                    "description": "History window",
                    "enum": list(_VALID_RANGES),
                },
                "interval": {
                    "type": "string",
                    "enum": list(_VALID_INTERVALS),
                },
                "market": {
                    "type": "string",
                    "enum": ["auto", "US", "HK", "CN"],
                },
            },
            "required": ["symbol"],
        }

    def __call__(self, **kwargs: Any) -> str:
        if not quant_enabled():
            return _json_out({"error": "quant tools disabled (MADCOP_QUANT_ENABLE=0)"})
        raw_sym = str(kwargs.get("symbol", "")).strip()
        if not raw_sym:
            return _json_out({"error": "symbol is required"})
        market = str(kwargs.get("market", "auto") or "auto")
        symbol = normalize_symbol(raw_sym, market)
        range_ = str(kwargs.get("range", "1y") or "1y")
        interval = str(kwargs.get("interval", "1d") or "1d")
        if range_ not in _VALID_RANGES:
            range_ = "1y"
        if interval not in _VALID_INTERVALS:
            interval = "1d"

        cache_key = f"hist_{symbol}_{range_}_{interval}"
        cached = _read_cache(cache_key, ttl_sec=3600)
        if cached and cached.get("bars"):
            return _json_out(self._summarize(cached, from_cache=True))

        try:
            payload = fetch_chart(
                symbol, range_=range_, interval=interval, timeout=self.timeout
            )
            parsed = parse_chart(payload, symbol)
        except Exception as e:  # noqa: BLE001
            return _json_out({"error": str(e), "symbol": symbol, "disclaimer": _DISCLAIMER})
        if parsed.get("error"):
            return _json_out(parsed)

        full = {
            "symbol": parsed["symbol"],
            "range": range_,
            "interval": interval,
            "currency": parsed.get("currency"),
            "bars": parsed.get("bars") or [],
            "source": "yahoo_chart",
            "delayed": True,
            "disclaimer": _DISCLAIMER,
        }
        # persist full series for quant tools / agent read_file
        cache_file = None
        try:
            path = _cache_path(cache_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"_cached_at": time.time(), "data": full}, ensure_ascii=False),
                encoding="utf-8",
            )
            cache_file = str(path)
        except Exception:  # noqa: BLE001
            pass
        full["cache_path"] = cache_file
        return _json_out(self._summarize(full, from_cache=False))

    def _summarize(self, full: dict[str, Any], *, from_cache: bool) -> dict[str, Any]:
        bars = full.get("bars") or []
        tail = bars[-self.max_bars_in_response :]
        return {
            "symbol": full.get("symbol"),
            "range": full.get("range"),
            "interval": full.get("interval"),
            "currency": full.get("currency"),
            "count": len(bars),
            "first": bars[0] if bars else None,
            "last": bars[-1] if bars else None,
            "bars_tail": tail,
            "cache_path": full.get("cache_path"),
            "source": full.get("source", "yahoo_chart"),
            "delayed": True,
            "cached": from_cache,
            "disclaimer": _DISCLAIMER,
            "note": (
                f"Only last {len(tail)} bars embedded; full series at cache_path "
                "or re-fetch. Use quant_factors / quant_backtest_simple for math."
            ),
        }


def load_bars_from_cache_or_fetch(
    symbol: str,
    *,
    range_: str = "1y",
    interval: str = "1d",
    market: str = "auto",
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Helper for quant tools: return full bar list or error dict."""
    symbol = normalize_symbol(symbol, market)
    cache_key = f"hist_{symbol}_{range_}_{interval}"
    path = _cache_path(cache_key)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            data = raw.get("data") or raw
            if data.get("bars"):
                return {"symbol": data.get("symbol") or symbol, "bars": data["bars"]}
        except Exception:  # noqa: BLE001
            pass
    payload = fetch_chart(symbol, range_=range_, interval=interval, timeout=timeout)
    parsed = parse_chart(payload, symbol)
    if parsed.get("error"):
        return parsed
    bars = parsed.get("bars") or []
    # refresh cache
    full = {
        "symbol": parsed["symbol"],
        "range": range_,
        "interval": interval,
        "bars": bars,
        "source": "yahoo_chart",
        "disclaimer": _DISCLAIMER,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"_cached_at": time.time(), "data": full}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"symbol": parsed["symbol"], "bars": bars}
