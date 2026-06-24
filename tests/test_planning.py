"""Tests for the planning primitives."""

from __future__ import annotations

import math

import pytest

from madcop.planning import (
    ABCBucket,
    ABCItem,
    abc_classify,
    eoq,
    reorder_point,
    safety_stock,
    z_for_service_level,
)


# --------------------------------------------------------------------------- #
# z_for_service_level
# --------------------------------------------------------------------------- #

def test_z_95_is_1_645() -> None:
    # Industry-standard: 95% service level → z = 1.645
    assert z_for_service_level(0.95) == pytest.approx(1.645, abs=1e-3)


def test_z_99_is_2_326() -> None:
    assert z_for_service_level(0.99) == pytest.approx(2.326, abs=1e-3)


def test_z_50_is_zero() -> None:
    assert z_for_service_level(0.50) == 0.0


def test_z_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        z_for_service_level(0.49)
    with pytest.raises(ValueError):
        z_for_service_level(1.0)
    with pytest.raises(ValueError):
        z_for_service_level(-0.1)


# --------------------------------------------------------------------------- #
# safety_stock
# --------------------------------------------------------------------------- #

def test_safety_stock_formula() -> None:
    # SS = z × σ × √L = 1.645 × 10 × 2 = 32.9
    assert safety_stock(0.95, 10.0, 4.0) == pytest.approx(32.9, abs=0.1)


def test_safety_stock_zero_when_zero_inputs() -> None:
    assert safety_stock(0.95, 0.0, 5.0) == 0.0
    assert safety_stock(0.95, 10.0, 0.0) == 0.0


def test_safety_stock_rejects_negative() -> None:
    with pytest.raises(ValueError):
        safety_stock(0.95, -1.0, 5.0)
    with pytest.raises(ValueError):
        safety_stock(0.95, 10.0, -1.0)


def test_safety_stock_grows_with_lead_time() -> None:
    s1 = safety_stock(0.95, 10.0, 1.0)
    s4 = safety_stock(0.95, 10.0, 4.0)
    s9 = safety_stock(0.95, 10.0, 9.0)
    # SS scales with sqrt(L): 1→2→3 ratio
    assert s4 / s1 == pytest.approx(2.0)
    assert s9 / s1 == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# reorder_point
# --------------------------------------------------------------------------- #

def test_reorder_point_simple() -> None:
    # ROP = D̄ × L + SS = 100 × 5 + 50 = 550
    assert reorder_point(100.0, 5.0, 50.0) == pytest.approx(550.0)


def test_reorder_point_with_zero_safety_stock() -> None:
    # Without safety stock, ROP is just average demand over lead time
    assert reorder_point(20.0, 7.0, 0.0) == pytest.approx(140.0)


def test_reorder_point_rejects_negative() -> None:
    with pytest.raises(ValueError):
        reorder_point(-1.0, 5.0, 10.0)
    with pytest.raises(ValueError):
        reorder_point(100.0, -1.0, 10.0)
    with pytest.raises(ValueError):
        reorder_point(100.0, 5.0, -1.0)


# --------------------------------------------------------------------------- #
# eoq
# --------------------------------------------------------------------------- #

def test_eoq_classic_formula() -> None:
    # EOQ = √(2 × D × K / h) = √(2 × 10000 × 50 / 2) = √500000 ≈ 707.1
    assert eoq(10000.0, 50.0, 2.0) == pytest.approx(math.sqrt(500000.0))


def test_eoq_unit_demand_returns_zero() -> None:
    # If demand is zero, no orders needed
    assert eoq(0.0, 50.0, 2.0) == 0.0


def test_eoq_zero_holding_cost_returns_zero() -> None:
    # Degenerate case: infinite optimal Q; we return 0 by convention
    assert eoq(10000.0, 50.0, 0.0) == 0.0


def test_eoq_rejects_negative() -> None:
    with pytest.raises(ValueError):
        eoq(-1.0, 50.0, 2.0)
    with pytest.raises(ValueError):
        eoq(100.0, -1.0, 2.0)
    with pytest.raises(ValueError):
        eoq(100.0, 50.0, -1.0)


def test_eoq_grows_with_demand() -> None:
    # EOQ scales with √D
    assert eoq(40000.0, 50.0, 2.0) == pytest.approx(2.0 * eoq(10000.0, 50.0, 2.0))


# --------------------------------------------------------------------------- #
# abc_classify
# --------------------------------------------------------------------------- #

def test_abc_empty_input() -> None:
    out = abc_classify([])
    assert len(out) == 3
    assert all(len(b.items) == 0 for b in out)


def test_abc_classic_pareto() -> None:
    """The classic 80/20 split: a few items dominate value."""
    items = [
        ABCItem("A1", 100, 100),   # value 10000
        ABCItem("A2", 50, 100),    # value 5000
        ABCItem("B1", 200, 5),     # value 1000
        ABCItem("B2", 100, 5),     # value 500
        ABCItem("C1", 5, 1),       # value 5
        ABCItem("C2", 3, 1),       # value 3
        ABCItem("C3", 1, 1),       # value 1
    ]
    buckets = abc_classify(items)
    a, b, c = buckets
    # Total value = 16509. A1 alone is 10000/16509 ≈ 61%; A1+A2 = 91%.
    # The greedy "stop once cumulative exceeds 80%" rule puts only A1 in A
    # because adding A2 would overshoot to 91%. We assert A's share is at
    # least the largest single item (61%) — the practical property we care about.
    a_value = sum(it.annual_demand * it.unit_cost for it in a.items)
    assert a_value / 16509 >= 10000 / 16509  # at least the top item
    # A ∪ B ∪ C must cover all items
    total = sum(len(bk.items) for bk in buckets)
    assert total == len(items)


def test_abc_all_zero_value_to_c() -> None:
    """Items with zero value go to C."""
    items = [ABCItem("X", 0, 100), ABCItem("Y", 0, 50)]
    buckets = abc_classify(items)
    a, b, c = buckets
    assert len(c.items) == 2
    assert len(a.items) == 0
    assert len(b.items) == 0


def test_abc_invalid_cutoffs() -> None:
    items = [ABCItem("X", 1, 1)]
    with pytest.raises(ValueError):
        abc_classify(items, a_cutoff=0.0, b_cutoff=0.5)
    with pytest.raises(ValueError):
        abc_classify(items, a_cutoff=0.5, b_cutoff=0.5)
    with pytest.raises(ValueError):
        abc_classify(items, a_cutoff=0.9, b_cutoff=0.9)
    with pytest.raises(ValueError):
        abc_classify(items, a_cutoff=0.9, b_cutoff=0.5)


def test_abc_share_sums_to_one() -> None:
    items = [
        ABCItem("A1", 100, 100),
        ABCItem("A2", 50, 100),
        ABCItem("B1", 200, 5),
        ABCItem("C1", 5, 1),
    ]
    a, b, c = abc_classify(items)
    assert a.share_of_value + b.share_of_value + c.share_of_value == pytest.approx(1.0)


def test_abc_buckets_have_correct_names() -> None:
    items = [ABCItem("X", 10, 10)]
    a, b, c = abc_classify(items)
    assert a.name == "A"
    assert b.name == "B"
    assert c.name == "C"