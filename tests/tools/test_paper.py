"""Paper trading unit tests (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from madcop.quant import paper as paper_mod
from madcop.tools.paper import PaperAccountTool, PaperOrderTool, PaperResetTool


@pytest.fixture()
def paper_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MADCOP_QUANT_DIR", str(tmp_path / "quant"))
    # reset any cached paths by re-import usage via env
    yield tmp_path


def test_paper_buy_sell_flow(paper_tmp):
    acc = paper_mod.reset_account(100_000)
    assert acc["cash"] == 100_000
    r = paper_mod.place_order(symbol="AAPL", side="buy", qty=10, price=100.0, fee_bps=0)
    assert r.get("ok") is True
    acc = paper_mod.load_account()
    assert acc["positions"]["AAPL"]["qty"] == 10
    assert acc["cash"] == 99_000
    r2 = paper_mod.place_order(symbol="AAPL", side="sell", qty=10, price=110.0, fee_bps=0)
    assert r2.get("ok") is True
    acc = paper_mod.load_account()
    assert "AAPL" not in acc["positions"]
    assert acc["cash"] == 100_100  # +100 pnl


def test_paper_insufficient_cash(paper_tmp):
    paper_mod.reset_account(50)
    r = paper_mod.place_order(symbol="AAPL", side="buy", qty=10, price=100.0)
    assert "error" in r


def test_paper_order_tool_with_price_override(paper_tmp):
    paper_mod.reset_account(50_000)
    t = PaperOrderTool()
    out = json.loads(t(symbol="AAPL", side="buy", qty=5, price=200.0, fee_bps=0))
    assert out.get("ok") is True
    assert out["trade"]["price"] == 200.0


def test_paper_account_and_reset(paper_tmp):
    paper_mod.reset_account(10_000)
    paper_mod.place_order(symbol="X", side="buy", qty=1, price=100.0, fee_bps=0)
    with patch("madcop.tools.paper._last_price", return_value=(120.0, None)):
        acc = json.loads(PaperAccountTool()(mark=True))
    assert acc["equity"] == 10_020.0  # 9900 cash + 120 pos
    reset = json.loads(PaperResetTool()(cash=1_000))
    assert reset["ok"] is True
    assert reset["cash"] == 1_000
    assert reset["positions"] == {}
