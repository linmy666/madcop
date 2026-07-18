"""Quant research helpers for the Gushen (股神) agent.

P0: factors + simple backtest only. No broker / live trading.
"""

from .factors import compute_factors
from .backtest import simple_backtest
from .store import quant_root, ensure_quant_dirs
from .paper import load_account, place_order, reset_account, mark_to_market

__all__ = [
    "compute_factors",
    "simple_backtest",
    "quant_root",
    "ensure_quant_dirs",
    "load_account",
    "place_order",
    "reset_account",
    "mark_to_market",
]
