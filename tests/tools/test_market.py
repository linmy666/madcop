"""Tests for market tools (mocked Yahoo chart)."""

from __future__ import annotations

import json
from unittest.mock import patch

from madcop.tools.market import (
    MarketHistoryTool,
    MarketQuoteTool,
    normalize_symbol,
    parse_chart,
)


def test_normalize_symbol_us():
    assert normalize_symbol("aapl") == "AAPL"


def test_normalize_symbol_cn_ss():
    assert normalize_symbol("600519") == "600519.SS"


def test_normalize_symbol_cn_sz():
    assert normalize_symbol("000001") == "000001.SZ"


def test_normalize_symbol_hk():
    assert normalize_symbol("0700", "HK") == "0700.HK"
    assert normalize_symbol("0700.HK") == "0700.HK"


def test_quote_schema():
    t = MarketQuoteTool()
    assert t.name == "market_quote"
    assert "symbol" in t.parameters_schema["properties"]


def _sample_chart(symbol: str = "AAPL", last: float = 200.0) -> dict:
    # 5 daily bars ending at last
    closes = [180.0, 185.0, 190.0, 195.0, last]
    n = len(closes)
    # fixed timestamps
    base = 1_700_000_000
    ts = [base + i * 86400 for i in range(n)]
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": symbol,
                        "currency": "USD",
                        "exchangeName": "NMS",
                        "regularMarketPrice": last,
                        "chartPreviousClose": 195.0,
                        "regularMarketTime": ts[-1],
                    },
                    "timestamp": ts,
                    "indicators": {
                        "quote": [
                            {
                                "open": closes,
                                "high": [c + 1 for c in closes],
                                "low": [c - 1 for c in closes],
                                "close": closes,
                                "volume": [1_000_000] * n,
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def test_parse_chart_quote_and_bars():
    parsed = parse_chart(_sample_chart("AAPL", 200.0), "AAPL")
    assert parsed["symbol"] == "AAPL"
    assert parsed["price"] == 200.0
    assert parsed["change_pct"] is not None
    assert len(parsed["bars"]) == 5
    assert parsed["bars"][-1]["c"] == 200.0
    assert "disclaimer" in parsed


def test_market_quote_mocked():
    t = MarketQuoteTool()
    with patch("madcop.tools.market.fetch_chart", return_value=_sample_chart()):
        with patch("madcop.tools.market._read_cache", return_value=None):
            with patch("madcop.tools.market._write_cache"):
                out = json.loads(t(symbol="AAPL"))
    assert out["price"] == 200.0
    assert out["symbol"] == "AAPL"
    assert out.get("error") is None


def test_market_quote_empty_symbol():
    t = MarketQuoteTool()
    out = json.loads(t(symbol=""))
    assert "error" in out


def test_market_history_tail():
    t = MarketHistoryTool()
    t.max_bars_in_response = 3
    with patch("madcop.tools.market.fetch_chart", return_value=_sample_chart()):
        with patch("madcop.tools.market._read_cache", return_value=None):
            out = json.loads(t(symbol="AAPL", range="1y"))
    assert out["count"] == 5
    assert len(out["bars_tail"]) == 3
    assert out["last"]["c"] == 200.0
