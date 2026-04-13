"""Signal generator for the zero-spread micro mean-reversion scalper.

The core function `evaluate_bar` is pure: given the most recent bar history,
the per-pair config, the currently open position (if any), and the day's risk
state, it returns a `Signal` describing what to do at the *next* bar's open.

This separation lets the same code drive both `backtest.py` (offline replay)
and a future live runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Literal, Optional

import numpy as np
import pandas as pd

from . import indicators as ind


# -- pip conventions ---------------------------------------------------------
# JPY-quoted pairs use 0.01 as a pip; non-JPY majors use 0.0001.
PIP_SIZE = {
    "USD/JPY": 0.01,
    "EUR/JPY": 0.01,
    "EUR/USD": 0.0001,
}


def pip_size(pair: str) -> float:
    if pair not in PIP_SIZE:
        raise KeyError(f"unsupported pair: {pair}")
    return PIP_SIZE[pair]


# -- data classes ------------------------------------------------------------
Action = Literal["ENTRY_LONG", "ENTRY_SHORT", "EXIT", "HOLD"]


@dataclass
class Position:
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    sl_price: float
    tp_price: float
    entry_time: pd.Timestamp
    sl_pips: float
    lot_units: int


@dataclass
class DailyState:
    date: Optional[pd.Timestamp] = None
    trades_today: int = 0
    realised_pnl_pct: float = 0.0  # cumulative within the day, fraction of equity
    peak_equity: float = 0.0       # all-time high used for trailing DD
    halted_today: bool = False
    halted_permanent: bool = False
    open_positions_total: int = 0  # across all pairs


@dataclass
class Signal:
    action: Action
    reason: str = ""
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    sl_pips: Optional[float] = None
    direction: Optional[Literal["LONG", "SHORT"]] = None


# -- helpers -----------------------------------------------------------------
def _in_window(now_jst: time, windows: list[dict]) -> bool:
    """True if `now_jst` falls inside any of the configured campaign windows.

    Each window is `{"weekday": [1..7], "start": "HH:MM", "end": "HH:MM"}`.
    Weekday matching is left to the caller (we only check the time-of-day
    range here so backtests can decide weekday separately).
    """
    for w in windows:
        start = _parse_hm(w["start"])
        end = _parse_hm(w["end"])
        if start <= now_jst <= end:
            return True
    return False


def _parse_hm(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def _within_news_blackout(ts: pd.Timestamp, blackouts: list[dict]) -> bool:
    """`blackouts` is a list of `{"time_utc": "ISO", "minutes": 3}` entries."""
    for b in blackouts:
        center = pd.Timestamp(b["time_utc"], tz="UTC")
        delta = abs((ts.tz_convert("UTC") - center).total_seconds()) / 60.0
        if delta <= b.get("minutes", 3):
            return True
    return False


# -- main signal generator ---------------------------------------------------
def evaluate_bar(
    bars: pd.DataFrame,
    pair: str,
    pair_cfg: dict,
    open_position: Optional[Position],
    daily: DailyState,
    campaign_windows_jst: list[dict],
    news_blackouts: Optional[list[dict]] = None,
    vol_regime_band: Optional[tuple[float, float]] = None,
) -> Signal:
    """Decide what to do given bar history ending at the most recent CLOSED bar.

    `bars` must be tz-aware UTC, columns: ['open','high','low','close']. The
    last row is the bar that just closed; entries fire at the next bar's open
    (handled in the backtester). The function only emits ENTRY/EXIT/HOLD.
    """
    if daily.halted_permanent or daily.halted_today:
        return Signal("HOLD", reason="halted")

    last = bars.iloc[-1]
    ts = bars.index[-1]
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    # ---- exit logic for an open position -----------------------------------
    if open_position is not None:
        # Time-stop
        bars_held = int((ts - open_position.entry_time) / pd.Timedelta(minutes=1))
        if bars_held >= pair_cfg.get("time_stop_bars", 30):
            return Signal("EXIT", reason="time_stop")
        # SL / TP intra-bar (conservative: SL first)
        if open_position.direction == "LONG":
            if last["low"] <= open_position.sl_price:
                return Signal("EXIT", reason="sl")
            if last["high"] >= open_position.tp_price:
                return Signal("EXIT", reason="tp")
        else:  # SHORT
            if last["high"] >= open_position.sl_price:
                return Signal("EXIT", reason="sl")
            if last["low"] <= open_position.tp_price:
                return Signal("EXIT", reason="tp")
        return Signal("HOLD", reason="position_open")

    # ---- entry preconditions -----------------------------------------------
    if daily.trades_today >= pair_cfg.get("max_trades_day", 10):
        return Signal("HOLD", reason="daily_trade_cap")
    if daily.open_positions_total >= 3:
        return Signal("HOLD", reason="global_position_cap")

    # JST time window check
    jst_now = (ts + pd.Timedelta(hours=9)).time()
    if not _in_window(jst_now, campaign_windows_jst):
        return Signal("HOLD", reason="outside_window")

    # News blackout
    if news_blackouts and _within_news_blackout(ts, news_blackouts):
        return Signal("HOLD", reason="news_blackout")

    # Need enough history for window + ATR
    window = pair_cfg.get("window", 20)
    atr_window = pair_cfg.get("atr_window", 14)
    need = max(window, atr_window) + 1
    if len(bars) < need:
        return Signal("HOLD", reason="insufficient_history")

    closes = bars["close"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    mu_arr, sigma_arr = ind.rolling_mean_std(closes, window)
    mu = mu_arr[-1]
    sigma = sigma_arr[-1]
    if not np.isfinite(mu) or not np.isfinite(sigma) or sigma <= 0:
        return Signal("HOLD", reason="bad_stats")

    atr_arr = ind.atr(highs, lows, closes, atr_window)
    atr_val = atr_arr[-1]
    if not np.isfinite(atr_val) or atr_val <= 0:
        return Signal("HOLD", reason="bad_atr")

    # Volatility regime band: skip flash spikes / dead markets
    if vol_regime_band is not None:
        rv = ind.realized_vol_5min(closes)
        lo, hi = vol_regime_band
        if rv < lo or rv > hi:
            return Signal("HOLD", reason="vol_regime")

    # Z-score breach + wick rejection
    entry_k = pair_cfg.get("entry_k", 2.0)
    wick_min = pair_cfg.get("wick_ratio", 0.6)
    upper_bound = mu + entry_k * sigma
    lower_bound = mu - entry_k * sigma
    close = float(last["close"])

    pip = pip_size(pair)
    sl_pips = float(np.clip(
        pair_cfg.get("sl_atr_mult", 1.5) * atr_val / pip,
        pair_cfg.get("sl_floor_pips", 2.0),
        pair_cfg.get("sl_cap_pips", 4.0),
    ))
    tp_pips = float(pair_cfg.get("tp_pips", 2.5))

    if close > upper_bound:
        wr = ind.wick_ratio(last["open"], last["high"], last["low"], last["close"], "upper")
        if wr >= wick_min:
            sl_price = close + sl_pips * pip
            # TP: closer of mu (mean reversion) or fixed tp_pips
            tp_price = max(mu, close - tp_pips * pip)
            return Signal(
                "ENTRY_SHORT",
                reason=f"z>{entry_k} wick={wr:.2f}",
                sl_price=sl_price,
                tp_price=tp_price,
                sl_pips=sl_pips,
                direction="SHORT",
            )
    elif close < lower_bound:
        wr = ind.wick_ratio(last["open"], last["high"], last["low"], last["close"], "lower")
        if wr >= wick_min:
            sl_price = close - sl_pips * pip
            tp_price = min(mu, close + tp_pips * pip)
            return Signal(
                "ENTRY_LONG",
                reason=f"z<-{entry_k} wick={wr:.2f}",
                sl_price=sl_price,
                tp_price=tp_price,
                sl_pips=sl_pips,
                direction="LONG",
            )
    return Signal("HOLD", reason="no_setup")


def position_size_units(
    equity_jpy: float,
    risk_pct: float,
    sl_pips: float,
    pip_value_jpy_per_1k: float,
    min_lot: int = 1000,
) -> int:
    """Return position size in base-currency units, rounded down to `min_lot`.

    `pip_value_jpy_per_1k` is the JPY P&L of a 1-pip move on a 1k-unit position.
    For JPY-quoted pairs this is ~¥100; for EUR/USD it's USD/JPY × 0.10.
    """
    if sl_pips <= 0 or pip_value_jpy_per_1k <= 0:
        return 0
    risk_jpy = equity_jpy * (risk_pct / 100.0)
    raw = risk_jpy / (sl_pips * pip_value_jpy_per_1k) * 1000.0
    units = int(raw // min_lot) * min_lot
    return max(0, units)
