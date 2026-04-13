"""Pure indicator functions for the zero-spread scalper.

Kept as plain numpy/pandas — no I/O, no state — so they can be unit-tested
deterministically and reused by both `strategy.py` (live evaluation) and
`backtest.py` (vectorised simulation).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_mean_std(closes: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Rolling mean and (population) std over `window` bars.

    Returns NaN for the first `window - 1` positions. Uses ddof=0 to match the
    z-score conventions in `research/backtest_zscore_all.py`.
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    s = pd.Series(closes, dtype=float)
    mu = s.rolling(window).mean().to_numpy()
    sigma = s.rolling(window).std(ddof=0).to_numpy()
    return mu, sigma


def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, window: int) -> np.ndarray:
    """Average True Range using Wilder-equivalent simple moving average.

    Returns NaN for positions where there are fewer than `window` true ranges.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    prev_c = np.concatenate([[np.nan], c[:-1]])
    tr = np.maximum.reduce([
        h - l,
        np.abs(h - prev_c),
        np.abs(l - prev_c),
    ])
    # The first TR has no prev close → fall back to high-low.
    tr[0] = h[0] - l[0]
    return pd.Series(tr).rolling(window).mean().to_numpy()


def wick_ratio(open_: float, high: float, low: float, close: float, side: str) -> float:
    """Fraction of the bar's range that is the wick on the given side.

    `side='upper'` returns the upper wick fraction (used to confirm a SHORT fade
    candidate — long upper wick = sellers rejected the high).
    `side='lower'` returns the lower wick fraction (LONG fade candidate).
    Returns 0.0 when the bar has zero range to avoid div-by-zero.
    """
    rng = high - low
    if rng <= 0:
        return 0.0
    body_top = max(open_, close)
    body_bot = min(open_, close)
    if side == "upper":
        return float((high - body_top) / rng)
    if side == "lower":
        return float((body_bot - low) / rng)
    raise ValueError("side must be 'upper' or 'lower'")


def realized_vol_5min(closes_1min: np.ndarray) -> float:
    """Realized volatility over the most recent 5 one-minute closes.

    Returned as the standard deviation of log returns (unitless). Returns 0.0
    if fewer than 5 bars are supplied.
    """
    arr = np.asarray(closes_1min[-5:], dtype=float)
    if arr.size < 5 or np.any(arr <= 0):
        return 0.0
    rets = np.diff(np.log(arr))
    return float(np.std(rets, ddof=0))
