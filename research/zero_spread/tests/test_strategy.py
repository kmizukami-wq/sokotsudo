import numpy as np
import pandas as pd
import pytest

from research.zero_spread import strategy as strat
from research.zero_spread.strategy import DailyState, Position


PAIR_CFG = {
    "window": 20, "entry_k": 2.0, "wick_ratio": 0.6,
    "atr_window": 14, "tp_pips": 2.5, "sl_atr_mult": 1.5,
    "sl_floor_pips": 2.0, "sl_cap_pips": 4.0,
    "max_trades_day": 10, "time_stop_bars": 30,
}
WINDOWS_ALWAYS = [{"weekday": [1, 2, 3, 4, 5, 6, 7], "start": "00:00", "end": "23:59"}]
WINDOWS_NEVER = [{"weekday": [1, 2, 3, 4, 5, 6, 7], "start": "03:00", "end": "03:01"}]


def _make_bars(closes, base_time="2025-01-06 00:00", spread=0.005):
    """Build an OHLC DataFrame from a closes series. Each bar has a tiny range."""
    idx = pd.date_range(base_time, periods=len(closes), freq="1min", tz="UTC")
    df = pd.DataFrame({
        "open":  closes,
        "high":  [c + spread for c in closes],
        "low":   [c - spread for c in closes],
        "close": closes,
    }, index=idx)
    return df


def test_pip_size_table():
    assert strat.pip_size("USD/JPY") == 0.01
    assert strat.pip_size("EUR/JPY") == 0.01
    assert strat.pip_size("EUR/USD") == 0.0001
    with pytest.raises(KeyError):
        strat.pip_size("XAU/USD")


def test_position_size_units_basic():
    # ¥500,000 × 0.5% = ¥2,500 risk; SL=2.5pip; pip_value=10 JPY/1k
    # raw = 2500 / (2.5 * 10) * 1000 = 100,000 → rounded to 100k units
    units = strat.position_size_units(500_000, 0.5, 2.5, 10.0)
    assert units == 100_000


def test_position_size_units_too_small():
    assert strat.position_size_units(1000, 0.5, 5.0, 10.0) == 0


def test_evaluate_outside_window_returns_hold():
    bars = _make_bars(np.full(40, 150.0))
    sig = strat.evaluate_bar(
        bars, "USD/JPY", PAIR_CFG, None, DailyState(),
        campaign_windows_jst=WINDOWS_NEVER,
    )
    assert sig.action == "HOLD"
    assert sig.reason == "outside_window"


def test_evaluate_insufficient_history():
    bars = _make_bars(np.linspace(150, 150.1, 5))
    sig = strat.evaluate_bar(
        bars, "USD/JPY", PAIR_CFG, None, DailyState(),
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    assert sig.action == "HOLD"
    assert sig.reason == "insufficient_history"


def test_evaluate_no_setup_when_flat():
    bars = _make_bars(np.full(40, 150.0))
    sig = strat.evaluate_bar(
        bars, "USD/JPY", PAIR_CFG, None, DailyState(),
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    # zero variance → bad_stats branch fires
    assert sig.action == "HOLD"
    assert sig.reason == "bad_stats"


def test_evaluate_short_entry_on_upper_extension():
    # 30 quiet bars, then a sharp upward extension bar with a big upper wick.
    base = list(np.linspace(150.00, 150.01, 30))
    base.append(150.05)  # close — but force a big wick via direct OHLC override
    df = _make_bars(base)
    # Override the last bar to have a long upper wick (rejection).
    last_idx = df.index[-1]
    df.loc[last_idx, "open"] = 150.005
    df.loc[last_idx, "high"] = 150.20
    df.loc[last_idx, "low"] = 150.005
    df.loc[last_idx, "close"] = 150.05
    sig = strat.evaluate_bar(
        df, "USD/JPY", PAIR_CFG, None, DailyState(),
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    assert sig.action == "ENTRY_SHORT"
    assert sig.direction == "SHORT"
    assert sig.sl_price > sig.tp_price
    assert sig.sl_pips > 0


def test_evaluate_long_entry_on_lower_extension():
    base = list(np.linspace(150.00, 150.01, 30))
    base.append(149.95)
    df = _make_bars(base)
    last_idx = df.index[-1]
    df.loc[last_idx, "open"] = 150.005
    df.loc[last_idx, "high"] = 150.005
    df.loc[last_idx, "low"] = 149.80
    df.loc[last_idx, "close"] = 149.95
    sig = strat.evaluate_bar(
        df, "USD/JPY", PAIR_CFG, None, DailyState(),
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    assert sig.action == "ENTRY_LONG"
    assert sig.direction == "LONG"
    assert sig.sl_price < sig.tp_price


def test_evaluate_exit_on_sl_when_long():
    bars = _make_bars(np.full(40, 150.00))
    last_idx = bars.index[-1]
    bars.loc[last_idx, "low"] = 149.80   # blew through SL at 149.95
    pos = Position(
        direction="LONG", entry_price=150.00, sl_price=149.95, tp_price=150.025,
        entry_time=bars.index[-2], sl_pips=5.0, lot_units=10_000,
    )
    sig = strat.evaluate_bar(
        bars, "USD/JPY", PAIR_CFG, pos, DailyState(),
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    assert sig.action == "EXIT"
    assert sig.reason == "sl"


def test_evaluate_exit_time_stop():
    bars = _make_bars(np.full(40, 150.00))
    pos = Position(
        direction="SHORT", entry_price=150.00, sl_price=150.05, tp_price=149.975,
        entry_time=bars.index[0],  # 39 minutes ago > 30
        sl_pips=5.0, lot_units=10_000,
    )
    sig = strat.evaluate_bar(
        bars, "USD/JPY", PAIR_CFG, pos, DailyState(),
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    assert sig.action == "EXIT"
    assert sig.reason == "time_stop"


def test_halted_state_blocks_all():
    bars = _make_bars(np.full(40, 150.0))
    state = DailyState(halted_today=True)
    sig = strat.evaluate_bar(
        bars, "USD/JPY", PAIR_CFG, None, state,
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    assert sig.action == "HOLD"
    assert sig.reason == "halted"


def test_daily_trade_cap():
    bars = _make_bars(np.full(40, 150.0))
    state = DailyState(trades_today=10)
    sig = strat.evaluate_bar(
        bars, "USD/JPY", PAIR_CFG, None, state,
        campaign_windows_jst=WINDOWS_ALWAYS,
    )
    assert sig.action == "HOLD"
    assert sig.reason == "daily_trade_cap"
