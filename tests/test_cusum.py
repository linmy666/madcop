"""Tests for the CUSUM change-point detector."""

from __future__ import annotations

import pytest

from madcop.anomaly.cusum import (
    CATEGORY_BASELINES,
    CUSUMTracker,
    baseline_for,
    cusum_h_for_arl0,
)


# --------------------------------------------------------------------------- #
# cusum_h_for_arl0
# --------------------------------------------------------------------------- #

def test_h_grows_with_arl0() -> None:
    # Higher target ARL0 means we tolerate longer under H0 → larger h.
    h100 = cusum_h_for_arl0(100.0)
    h1000 = cusum_h_for_arl0(1000.0)
    h10000 = cusum_h_for_arl0(10000.0)
    assert h100 < h1000 < h10000


def test_h_is_at_least_minimum() -> None:
    # For very small ARL0 the formula can dip below 0.5; we floor it.
    h = cusum_h_for_arl0(2.0)
    assert h >= 0.5


def test_h_rejects_invalid_arl0() -> None:
    with pytest.raises(ValueError):
        cusum_h_for_arl0(0.0)
    with pytest.raises(ValueError):
        cusum_h_for_arl0(-5.0)


def test_h_typical_value_for_arl0_1000() -> None:
    # Reference: for k=0.5 Gaussian CUSUM, ARL0=1000 corresponds to h≈4.6
    # in the Siegmund approximation. We use a relaxed upper bound because
    # the user's exact k may differ; the test asserts we're in a sane range.
    h = cusum_h_for_arl0(1000.0)
    assert 3.0 <= h <= 6.0


# --------------------------------------------------------------------------- #
# CUSUMTracker
# --------------------------------------------------------------------------- #

def test_tracker_rejects_invalid_p0() -> None:
    with pytest.raises(ValueError):
        CUSUMTracker(category="x", p0=-0.1)
    with pytest.raises(ValueError):
        CUSUMTracker(category="x", p0=1.1)


def test_tracker_rejects_invalid_k() -> None:
    with pytest.raises(ValueError):
        CUSUMTracker(category="x", p0=0.1, k=0.0)
    with pytest.raises(ValueError):
        CUSUMTracker(category="x", p0=0.1, k=-0.5)


def test_tracker_rejects_invalid_observation() -> None:
    t = CUSUMTracker(category="x", p0=0.1)
    with pytest.raises(ValueError):
        t.update(-0.1)
    with pytest.raises(ValueError):
        t.update(1.5)


def test_cusum_never_goes_negative() -> None:
    t = CUSUMTracker(category="x", p0=0.5)
    # Feeding only zeros should keep CUSUM at 0 (or above; 0 - 0.52 < 0 → clamp to 0)
    for _ in range(100):
        t.update(0.0)
    assert t.cusum_positive == 0.0


def test_cusum_grows_under_persistent_positive_shift() -> None:
    """Feed a stream that's always 1.0 (cancels every time). CUSUM
    grows by (1 - p0 - k) per observation, and crosses h quickly.
    """
    t = CUSUMTracker(category="pharma", p0=0.02, k=0.02, arl0=200.0)
    crossed_at = None
    for i in range(1, 50):
        new_cusum = t.update(1.0)
        if new_cusum >= t.h:
            crossed_at = i
            break
    assert crossed_at is not None
    assert crossed_at < 10  # 100% rate should fire within a handful of obs


def test_cusum_does_not_fire_under_baseline() -> None:
    """Feed a Bernoulli stream with p=p0. With ARL0=2000 and k=0.05,
    the CUSUM should not fire in 200 observations of in-control data.
    """
    import random
    random.seed(42)
    t = CUSUMTracker(category="apparel", p0=0.30, k=0.05, arl0=2000.0)
    fired = False
    for _ in range(200):
        new_cusum = t.update(1.0 if random.random() < 0.30 else 0.0)
        if new_cusum >= t.h:
            fired = True
            break
    # We accept rare false positives inherent to CUSUM calibration;
    # the test may flake on unlucky seeds (we use a fixed seed).
    assert not fired, f"CUSUM fired under H0 after {t.n_updates} obs"


def test_cusum_reset_clears_state() -> None:
    t = CUSUMTracker(category="x", p0=0.1, k=0.05, arl0=100.0)
    for _ in range(5):
        t.update(1.0)
    assert t.cusum_positive > 0
    t.reset()
    assert t.cusum_positive == 0.0


# --------------------------------------------------------------------------- #
# Category baseline lookup
# --------------------------------------------------------------------------- #

def test_baseline_for_known_category() -> None:
    assert baseline_for("pharma") == 0.02
    assert baseline_for("apparel") == 0.30


def test_baseline_for_unknown_category_returns_default() -> None:
    assert baseline_for("nonsense_category") == CATEGORY_BASELINES["default"]


def test_baseline_for_none_returns_default() -> None:
    assert baseline_for(None) == CATEGORY_BASELINES["default"]


def test_baseline_is_case_insensitive() -> None:
    assert baseline_for("DAIRY") == baseline_for("dairy")
