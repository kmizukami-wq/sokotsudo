import math

import numpy as np
import pytest

from research.zero_spread import indicators as ind


def test_rolling_mean_std_window_validation():
    with pytest.raises(ValueError):
        ind.rolling_mean_std(np.array([1.0, 2.0]), window=1)


def test_rolling_mean_std_basic():
    closes = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    mu, sigma = ind.rolling_mean_std(closes, window=3)
    assert math.isnan(mu[0]) and math.isnan(mu[1])
    assert math.isclose(mu[2], 2.0)
    assert math.isclose(mu[3], 3.0)
    assert math.isclose(mu[4], 4.0)
    # population std of [1,2,3] = sqrt(2/3)
    assert math.isclose(sigma[2], math.sqrt(2 / 3), rel_tol=1e-9)


def test_atr_constant_range():
    # All bars have range 1.0 → ATR should be 1.0 once warmed up.
    n = 20
    highs = np.full(n, 101.0)
    lows = np.full(n, 100.0)
    closes = np.full(n, 100.5)
    atr = ind.atr(highs, lows, closes, window=5)
    # First (window - 1) entries are NaN; from window-1 onwards we get 1.0.
    assert math.isnan(atr[3])
    assert math.isclose(atr[4], 1.0, abs_tol=1e-9)
    assert math.isclose(atr[-1], 1.0, abs_tol=1e-9)


def test_wick_ratio_pure_doji():
    # Open=close, all body collapsed; equal wicks.
    assert math.isclose(ind.wick_ratio(100, 102, 98, 100, "upper"), 0.5)
    assert math.isclose(ind.wick_ratio(100, 102, 98, 100, "lower"), 0.5)


def test_wick_ratio_full_upper():
    # Bear bar with long upper wick: open=99, high=105, low=98, close=99
    # range=7, upper wick = 105 - max(99,99) = 6 → 6/7
    assert math.isclose(ind.wick_ratio(99, 105, 98, 99, "upper"), 6 / 7)


def test_wick_ratio_zero_range():
    assert ind.wick_ratio(100, 100, 100, 100, "upper") == 0.0


def test_wick_ratio_invalid_side():
    with pytest.raises(ValueError):
        ind.wick_ratio(1, 2, 0, 1, "sideways")


def test_realized_vol_5min_constant():
    # Constant prices → vol = 0
    assert ind.realized_vol_5min(np.array([100.0] * 6)) == 0.0


def test_realized_vol_5min_short_input():
    assert ind.realized_vol_5min(np.array([1.0, 2.0])) == 0.0


def test_realized_vol_5min_positive():
    closes = np.array([100.0, 100.1, 100.0, 100.2, 100.1])
    rv = ind.realized_vol_5min(closes)
    assert rv > 0
