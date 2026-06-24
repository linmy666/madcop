"""L4 — Supply chain planning primitives.

Four canonical formulas every planner needs:

1. `safety_stock`     — buffer against demand variability + lead-time variability
2. `reorder_point`    — when to place the next order
3. `eoq`              — economic order quantity (Wilson formula)
4. `abc_classify`     — Pareto classification by annual consumption value

Pure functions, no I/O. All randomness is the caller's problem.

Why a separate module from L2 anomaly rules: planning answers a different
question. Rules ask "what just went wrong?"; planning asks "what should
we have ordered and when?". The agent layer (L5) ties them together:
an anomaly in the demand stream can trigger a planning recompute.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


# --------------------------------------------------------------------------- #
# Service-level z-scores (one-sided normal CDF)
# --------------------------------------------------------------------------- #
# A 95% service level means we want to cover demand variability 95% of the
# time → z = 1.645. These are industry-standard values; hard-coding them
# avoids pulling in scipy just for norm.ppf.
_Z_TABLE: dict[float, float] = {
    0.50: 0.000,
    0.75: 0.674,
    0.80: 0.842,
    0.85: 1.036,
    0.90: 1.282,
    0.95: 1.645,
    0.97: 1.881,
    0.98: 2.054,
    0.99: 2.326,
    0.999: 3.090,
}


def z_for_service_level(sl: float) -> float:
    """Return the one-sided z-score for a target service level.

    The service level is the probability that demand during lead time
    does NOT exceed the inventory available (i.e., we don't stock out).

    Accepts any value in [0.50, 0.999]. Outside that range raises.
    """
    if not 0.50 <= sl <= 0.999:
        raise ValueError(
            f"service_level must be in [0.50, 0.999], got {sl}"
        )
    # Snap to nearest table entry; finer granularity isn't worth a table here.
    closest = min(_Z_TABLE.keys(), key=lambda k: abs(k - sl))
    return _Z_TABLE[closest]


# --------------------------------------------------------------------------- #
# 1. Safety stock
# --------------------------------------------------------------------------- #

def safety_stock(
    service_level: float,
    sigma_demand_per_day: float,
    lead_time_days: float,
) -> float:
    """Safety stock = z × σ_LT, where σ_LT = σ_d × √L.

    This is the "demand variability only" form, which assumes lead time
    is fixed. When lead time is also variable, σ_LT = √(L × σ_d² + D̄² × σ_LT²).
    We use the simpler form because it matches what 95% of textbooks and
    inventory tools (SAP, Oracle) default to.

    Returns units (pieces / cases / pallets).
    """
    if sigma_demand_per_day < 0:
        raise ValueError("sigma_demand_per_day must be non-negative")
    if lead_time_days < 0:
        raise ValueError("lead_time_days must be non-negative")
    z = z_for_service_level(service_level)
    return z * sigma_demand_per_day * math.sqrt(lead_time_days)


# --------------------------------------------------------------------------- #
# 2. Reorder point
# --------------------------------------------------------------------------- #

def reorder_point(
    avg_demand_per_day: float,
    lead_time_days: float,
    safety_stock_units: float,
) -> float:
    """ROP = D̄ × L + SS.

    When inventory drops to ROP, place a new order. The order will arrive
    `lead_time_days` later; safety_stock covers demand variability during
    that window.
    """
    if avg_demand_per_day < 0:
        raise ValueError("avg_demand_per_day must be non-negative")
    if lead_time_days < 0:
        raise ValueError("lead_time_days must be non-negative")
    if safety_stock_units < 0:
        raise ValueError("safety_stock_units must be non-negative")
    return avg_demand_per_day * lead_time_days + safety_stock_units


# --------------------------------------------------------------------------- #
# 3. Economic Order Quantity (Wilson 1934)
# --------------------------------------------------------------------------- #

def eoq(
    annual_demand: float,
    ordering_cost: float,
    holding_cost_per_unit_per_year: float,
) -> float:
    """EOQ = √(2 × D × K / h).

    The order quantity that minimises total annual inventory cost
    (ordering + holding). Holds when demand is deterministic and
    independent of price (no quantity discounts).
    """
    if annual_demand < 0:
        raise ValueError("annual_demand must be non-negative")
    if ordering_cost < 0:
        raise ValueError("ordering_cost must be non-negative")
    if holding_cost_per_unit_per_year < 0:
        raise ValueError("holding_cost_per_unit_per_year must be non-negative")
    if holding_cost_per_unit_per_year == 0 or annual_demand == 0:
        # Degenerate case: zero holding cost → infinite EOQ; we return 0
        # because there's no optimum and the caller likely means "no stock"
        return 0.0
    return math.sqrt(2.0 * annual_demand * ordering_cost / holding_cost_per_unit_per_year)


# --------------------------------------------------------------------------- #
# 4. ABC classification
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ABCItem:
    """One SKU for ABC analysis."""
    sku: str
    annual_demand: float       # units/year
    unit_cost: float           # ¥/unit


@dataclass(frozen=True)
class ABCBucket:
    """The aggregate bucket, with the items that fall into it."""
    name: str                  # "A", "B", "C"
    items: tuple[ABCItem, ...]
    share_of_value: float      # 0..1


def abc_classify(
    items: Iterable[ABCItem],
    *,
    a_cutoff: float = 0.80,
    b_cutoff: float = 0.95,
) -> list[ABCBucket]:
    """Pareto-classify items by annual consumption value (D × cost).

    Default cutoffs (industry-standard):
        A: top items contributing to a_cutoff (default 80%) of value
        B: next items up to b_cutoff (default 95%)
        C: the rest

    Returns three buckets, sorted by descending value. Items with
    zero value go to C.
    """
    if not 0 < a_cutoff < b_cutoff < 1:
        raise ValueError(
            f"cutoffs must satisfy 0 < a_cutoff < b_cutoff < 1, "
            f"got a={a_cutoff}, b={b_cutoff}"
        )
    items_list = list(items)
    if not items_list:
        return [
            ABCBucket(name="A", items=(), share_of_value=0.0),
            ABCBucket(name="B", items=(), share_of_value=0.0),
            ABCBucket(name="C", items=(), share_of_value=0.0),
        ]

    valued = sorted(
        items_list,
        key=lambda it: it.annual_demand * it.unit_cost,
        reverse=True,
    )
    values = [it.annual_demand * it.unit_cost for it in valued]
    total = sum(values)
    if total <= 0:
        return [
            ABCBucket(name="A", items=(), share_of_value=0.0),
            ABCBucket(name="B", items=(), share_of_value=0.0),
            ABCBucket(name="C", items=tuple(valued), share_of_value=0.0),
        ]

    cumulative = 0.0
    a_items: list[ABCItem] = []
    b_items: list[ABCItem] = []
    c_items: list[ABCItem] = []
    a_val = b_val = 0.0
    for it, v in zip(valued, values):
        share = v / total
        if cumulative + share <= a_cutoff:
            a_items.append(it)
            a_val += share
            cumulative += share
        elif cumulative + share <= b_cutoff:
            b_items.append(it)
            b_val += share
            cumulative += share
        else:
            c_items.append(it)

    return [
        ABCBucket(name="A", items=tuple(a_items), share_of_value=round(a_val, 6)),
        ABCBucket(name="B", items=tuple(b_items), share_of_value=round(b_val, 6)),
        ABCBucket(name="C", items=tuple(c_items), share_of_value=round(1 - a_val - b_val, 6)),
    ]