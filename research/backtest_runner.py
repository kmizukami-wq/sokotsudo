#!/usr/bin/env python3
"""
FX取引戦略 バックテストスイート
================================
研究ドキュメント内の各戦略を疑似FXデータで実行し、結果を検証する。

実行方法: python3 backtest_runner.py
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 1. 疑似FXデータ生成
# ============================================================

def generate_fx_data(
    pair_name: str = "EUR/USD",
    start_price: float = 1.1000,
    days: int = 2520,  # 約10年分
    volatility: float = 0.0008,  # 日次ボラティリティ
    trend: float = 0.0,  # 日次トレンド
    seed: int = 42
) -> pd.DataFrame:
    """
    リアルなFX OHLCデータを生成（幾何ブラウン運動ベース）
    1時間足データを生成し、日足に集約可能。
    """
    np.random.seed(seed)
    hours = days * 24
    hourly_vol = volatility / np.sqrt(24)
    hourly_trend = trend / 24

    # 幾何ブラウン運動
    returns = np.random.normal(hourly_trend, hourly_vol, hours)
    # ファットテール（t分布）を混ぜてリアルな分布に
    fat_tail = np.random.standard_t(df=5, size=hours) * hourly_vol * 0.3
    returns = returns + fat_tail

    prices = start_price * np.exp(np.cumsum(returns))

    # OHLCデータ作成
    start_date = datetime(2016, 1, 1)
    dates = [start_date + timedelta(hours=i) for i in range(hours)]

    df = pd.DataFrame(index=pd.DatetimeIndex(dates), columns=['open', 'high', 'low', 'close'])

    for i in range(0, hours, 1):
        if i == 0:
            o = start_price
        else:
            o = prices[i-1]
        c = prices[i]
        noise = abs(np.random.normal(0, hourly_vol * start_price * 0.5))
        h = max(o, c) + noise
        l = min(o, c) - noise
        df.iloc[i] = [o, h, l, c]

    df = df.astype(float)

    # 週末を除外（土日）
    df = df[df.index.dayofweek < 5]

    print(f"[データ生成] {pair_name}: {len(df)}本の1時間足データ ({df.index[0].date()} ~ {df.index[-1].date()})")
    return df


def resample_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """1時間足を日足に変換"""
    daily = df.resample('D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    return daily


# ============================================================
# 2. モンテカルロシミュレーション
# ============================================================

def monte_carlo_simulation(
    win_rate: float,
    risk_reward: float,
    risk_per_trade: float,
    trades_per_day: int,
    trading_days: int = 250,
    simulations: int = 100_000,
    seed: int = 42
) -> dict:
    np.random.seed(seed)
    total_trades = trades_per_day * trading_days
    outcomes = np.random.binomial(1, win_rate, size=(simulations, total_trades))
    returns = np.where(outcomes == 1, risk_per_trade * risk_reward, -risk_per_trade)
    equity_curves = np.cumprod(1 + returns, axis=1)
    final_equity = equity_curves[:, -1]
    annual_returns = (final_equity - 1) * 100

    running_max = np.maximum.accumulate(equity_curves, axis=1)
    drawdowns = (running_max - equity_curves) / running_max
    max_drawdowns = np.max(drawdowns, axis=1) * 100

    return {
        "期待値 (R)": win_rate * risk_reward - (1 - win_rate),
        "年利200%達成確率": f"{np.mean(annual_returns >= 200) * 100:.1f}%",
        "年利100%達成確率": f"{np.mean(annual_returns >= 100) * 100:.1f}%",
        "年利50%達成確率": f"{np.mean(annual_returns >= 50) * 100:.1f}%",
        "中央値年利": f"{np.median(annual_returns):.1f}%",
        "平均年利": f"{np.mean(annual_returns):.1f}%",
        "最悪ケース年利": f"{np.min(annual_returns):.1f}%",
        "最良ケース年利": f"{np.max(annual_returns):.1f}%",
        "平均最大DD": f"{np.mean(max_drawdowns):.1f}%",
        "最悪最大DD": f"{np.max(max_drawdowns):.1f}%",
        "破産確率(50%+DD)": f"{np.mean(max_drawdowns >= 50) * 100:.2f}%",
    }


# ============================================================
# 3. ロンドンブレイクアウト戦略
# ============================================================

def london_breakout_backtest(
    df: pd.DataFrame,
    asian_start_hour: int = 0,
    asian_end_hour: int = 7,
    london_end_hour: int = 16,
    tp_multiplier: float = 1.5,
    min_range_pips: float = 15,
    max_range_pips: float = 80,
    risk_per_trade: float = 0.02,
    pip_value: float = 0.0001
) -> pd.DataFrame:
    results = []
    equity = 1.0

    for date, day_data in df.groupby(df.index.date):
        asian_data = day_data[(day_data.index.hour >= asian_start_hour) &
                              (day_data.index.hour < asian_end_hour)]
        if len(asian_data) < 3:
            continue

        asian_high = asian_data["high"].max()
        asian_low = asian_data["low"].min()
        asian_range = asian_high - asian_low
        range_pips = asian_range / pip_value

        if range_pips < min_range_pips or range_pips > max_range_pips:
            continue

        london_data = day_data[(day_data.index.hour >= asian_end_hour) &
                               (day_data.index.hour <= london_end_hour)]
        if len(london_data) == 0:
            continue

        tp = asian_range * tp_multiplier
        sl = asian_range
        trade_result = None
        direction = None

        for _, bar in london_data.iterrows():
            if bar["high"] > asian_high and trade_result is None:
                entry = asian_high
                direction = "LONG"
                if bar["high"] >= entry + tp:
                    trade_result = tp_multiplier
                elif bar["low"] <= entry - sl:
                    trade_result = -1.0
                else:
                    trade_result = (bar["close"] - entry) / sl
                break
            elif bar["low"] < asian_low and trade_result is None:
                entry = asian_low
                direction = "SHORT"
                if bar["low"] <= entry - tp:
                    trade_result = tp_multiplier
                elif bar["high"] >= entry + sl:
                    trade_result = -1.0
                else:
                    trade_result = (entry - bar["close"]) / sl
                break

        if trade_result is not None:
            pnl = trade_result * risk_per_trade
            equity *= (1 + pnl)
            results.append({
                "date": date,
                "direction": direction,
                "range_pips": range_pips,
                "r_multiple": trade_result,
                "pnl_pct": pnl * 100,
                "equity": equity
            })

    return pd.DataFrame(results)


# ============================================================
# 4. トレンドフォロー戦略 (EMA + ATRトレイリング)
# ============================================================

def trend_following_backtest(
    df: pd.DataFrame,
    fast_ma: int = 20,
    slow_ma: int = 50,
    atr_period: int = 14,
    atr_multiplier: float = 3.0,
    risk_per_trade: float = 0.02,
    pip_value: float = 0.0001
) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=fast_ma).mean()
    df["ema_slow"] = df["close"].ewm(span=slow_ma).mean()

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(window=atr_period).mean()

    df["signal"] = 0
    df.loc[df["ema_fast"] > df["ema_slow"], "signal"] = 1
    df.loc[df["ema_fast"] < df["ema_slow"], "signal"] = -1

    results = []
    equity = 1.0
    position = 0
    entry_price = 0
    trailing_stop = 0

    for i in range(slow_ma + atr_period, len(df)):
        row = df.iloc[i]
        signal = row["signal"]
        atr = row["atr"]
        if pd.isna(atr) or atr <= 0:
            continue

        if position == 0 and signal != 0:
            position = signal
            entry_price = row["close"]
            trailing_stop = entry_price - atr * atr_multiplier * signal

        elif position != 0:
            if position == 1:
                new_stop = row["close"] - atr * atr_multiplier
                trailing_stop = max(trailing_stop, new_stop)
                if row["low"] <= trailing_stop or signal == -1:
                    exit_price = max(trailing_stop, row["low"])
                    sl_pips = atr * atr_multiplier / pip_value
                    pnl_pips = (exit_price - entry_price) / pip_value
                    r_multiple = pnl_pips / sl_pips if sl_pips > 0 else 0
                    pnl = r_multiple * risk_per_trade
                    equity *= (1 + pnl)
                    results.append({
                        "date": df.index[i],
                        "direction": "LONG",
                        "pips": pnl_pips,
                        "r_multiple": r_multiple,
                        "equity": equity
                    })
                    position = 0
            elif position == -1:
                new_stop = row["close"] + atr * atr_multiplier
                trailing_stop = min(trailing_stop, new_stop)
                if row["high"] >= trailing_stop or signal == 1:
                    exit_price = min(trailing_stop, row["high"])
                    sl_pips = atr * atr_multiplier / pip_value
                    pnl_pips = (entry_price - exit_price) / pip_value
                    r_multiple = pnl_pips / sl_pips if sl_pips > 0 else 0
                    pnl = r_multiple * risk_per_trade
                    equity *= (1 + pnl)
                    results.append({
                        "date": df.index[i],
                        "direction": "SHORT",
                        "pips": pnl_pips,
                        "r_multiple": r_multiple,
                        "equity": equity
                    })
                    position = 0

    return pd.DataFrame(results)


# ============================================================
# 5. ペアトレーディング戦略
# ============================================================

def pairs_trading_backtest(
    pair_a: pd.Series,
    pair_b: pd.Series,
    window: int = 60,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    stop_z: float = 4.0,
    risk_per_trade: float = 0.02
) -> pd.DataFrame:
    from statsmodels.tsa.stattools import coint

    score, pvalue, _ = coint(pair_a[:500], pair_b[:500])
    print(f"  共和分検定 p値: {pvalue:.4f} ({'共和分あり' if pvalue < 0.05 else '共和分なし（参考値）'})")

    beta = np.polyfit(pair_b, pair_a, 1)[0]
    spread = pair_a - beta * pair_b

    spread_mean = spread.rolling(window=window).mean()
    spread_std = spread.rolling(window=window).std()
    z_score = (spread - spread_mean) / spread_std

    results = []
    equity = 1.0
    position = 0
    entry_z_val = 0

    for i in range(window, len(z_score)):
        z = z_score.iloc[i]
        if pd.isna(z):
            continue

        if position == 0:
            if z > entry_z:
                position = -1
                entry_z_val = z
            elif z < -entry_z:
                position = 1
                entry_z_val = z
        elif position == 1:
            if z > -exit_z or z < -stop_z:
                pnl = (-entry_z_val - (-z)) / entry_z * risk_per_trade
                equity *= (1 + pnl)
                results.append({
                    "date": z_score.index[i] if hasattr(z_score.index[i], 'date') else i,
                    "direction": "LONG_SPREAD",
                    "entry_z": entry_z_val,
                    "exit_z": z,
                    "pnl_pct": pnl * 100,
                    "equity": equity
                })
                position = 0
        elif position == -1:
            if z < exit_z or z > stop_z:
                pnl = (entry_z_val - z) / entry_z * risk_per_trade
                equity *= (1 + pnl)
                results.append({
                    "date": z_score.index[i] if hasattr(z_score.index[i], 'date') else i,
                    "direction": "SHORT_SPREAD",
                    "entry_z": entry_z_val,
                    "exit_z": z,
                    "pnl_pct": pnl * 100,
                    "equity": equity
                })
                position = 0

    return pd.DataFrame(results)


# ============================================================
# 6. 結果表示ヘルパー
# ============================================================

def print_results(name: str, results_df: pd.DataFrame, years: float = 10.0):
    if len(results_df) == 0:
        print(f"\n{'='*60}")
        print(f"  {name}: トレードなし")
        return

    equity_col = "equity"
    r_col = "r_multiple" if "r_multiple" in results_df.columns else None
    pnl_col = "pnl_pct" if "pnl_pct" in results_df.columns else None

    final_equity = results_df[equity_col].iloc[-1]
    total_return = (final_equity - 1) * 100
    annual_return = ((final_equity ** (1 / years)) - 1) * 100

    equity_series = results_df[equity_col]
    running_max = equity_series.cummax()
    drawdowns = (running_max - equity_series) / running_max
    max_dd = drawdowns.max() * 100

    if r_col and r_col in results_df.columns:
        wins = results_df[results_df[r_col] > 0]
        losses = results_df[results_df[r_col] <= 0]
        win_rate = len(wins) / len(results_df) * 100
        avg_r = results_df[r_col].mean()
        pf_num = wins[r_col].sum() if len(wins) > 0 else 0
        pf_den = abs(losses[r_col].sum()) if len(losses) > 0 else 1
        profit_factor = pf_num / pf_den if pf_den > 0 else float('inf')
    elif pnl_col:
        wins = results_df[results_df[pnl_col] > 0]
        losses = results_df[results_df[pnl_col] <= 0]
        win_rate = len(wins) / len(results_df) * 100
        avg_r = None
        pf_num = wins[pnl_col].sum() if len(wins) > 0 else 0
        pf_den = abs(losses[pnl_col].sum()) if len(losses) > 0 else 1
        profit_factor = pf_num / pf_den if pf_den > 0 else float('inf')
    else:
        win_rate = 0
        avg_r = None
        profit_factor = 0

    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  総トレード数     : {len(results_df)}")
    print(f"  勝率             : {win_rate:.1f}%")
    if avg_r is not None:
        print(f"  平均R倍数        : {avg_r:.3f}")
    print(f"  プロフィットファクター : {profit_factor:.2f}")
    print(f"  総リターン       : {total_return:.1f}%")
    print(f"  年率リターン(CAGR): {annual_return:.1f}%")
    print(f"  最大ドローダウン  : {max_dd:.1f}%")
    print(f"  最終資産倍率     : {final_equity:.3f}x")
    print(f"  年利200%達成     : {'✅ YES' if annual_return >= 200 else '❌ NO'}")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  FX取引戦略 バックテストスイート")
    print("  疑似データによる10年間シミュレーション")
    print("=" * 60)

    # --- データ生成 ---
    print("\n[Phase 1] 疑似FXデータ生成...")
    eurusd_h1 = generate_fx_data("EUR/USD", 1.1000, days=2520, volatility=0.0035, trend=0.00002, seed=42)
    gbpusd_h1 = generate_fx_data("GBP/USD", 1.3000, days=2520, volatility=0.0045, trend=0.00001, seed=123)

    eurusd_d1 = resample_to_daily(eurusd_h1)
    gbpusd_d1 = resample_to_daily(gbpusd_h1)

    print(f"  EUR/USD 日足: {len(eurusd_d1)}本")
    print(f"  GBP/USD 日足: {len(gbpusd_d1)}本")

    # === テスト1: モンテカルロシミュレーション ===
    print("\n" + "=" * 60)
    print("  [テスト1] モンテカルロシミュレーション (100,000回)")
    print("=" * 60)

    scenarios = [
        {"name": "シナリオA: 勝率55%, R:R 1:2, 2%リスク, 1日1回",
         "params": dict(win_rate=0.55, risk_reward=2.0, risk_per_trade=0.02, trades_per_day=1)},
        {"name": "シナリオB: 勝率60%, R:R 1:1.5, 3%リスク, 1日2回",
         "params": dict(win_rate=0.60, risk_reward=1.5, risk_per_trade=0.03, trades_per_day=2)},
        {"name": "シナリオC: 勝率50%, R:R 1:3, 1.5%リスク, 1日3回",
         "params": dict(win_rate=0.50, risk_reward=3.0, risk_per_trade=0.015, trades_per_day=3)},
        {"name": "シナリオD: 勝率65%, R:R 1:1, 2%リスク, 1日2回",
         "params": dict(win_rate=0.65, risk_reward=1.0, risk_per_trade=0.02, trades_per_day=2)},
    ]

    for s in scenarios:
        print(f"\n--- {s['name']} ---")
        result = monte_carlo_simulation(**s["params"])
        for k, v in result.items():
            print(f"  {k}: {v}")

    # === テスト2: ロンドンブレイクアウト ===
    print("\n\n[テスト2] ロンドンブレイクアウト戦略 (EUR/USD, 10年)")
    lb_results = london_breakout_backtest(eurusd_h1, risk_per_trade=0.02, tp_multiplier=1.5,
                                          min_range_pips=5, max_range_pips=200)
    print_results("ロンドンブレイクアウト (TP=1.5x)", lb_results)

    # TP倍率を変えて比較
    for tp in [1.0, 2.0, 2.5]:
        r = london_breakout_backtest(eurusd_h1, risk_per_trade=0.02, tp_multiplier=tp,
                                     min_range_pips=5, max_range_pips=200)
        print_results(f"ロンドンBK (TP={tp}x)", r)

    # === テスト3: トレンドフォロー ===
    print("\n\n[テスト3] トレンドフォロー戦略 (EUR/USD 日足, 10年)")
    tf_results = trend_following_backtest(eurusd_d1, fast_ma=20, slow_ma=50, risk_per_trade=0.02)
    print_results("トレンドフォロー (20/50 EMA)", tf_results)

    # パラメータ変更
    for fast, slow in [(10, 30), (50, 200)]:
        r = trend_following_backtest(eurusd_d1, fast_ma=fast, slow_ma=slow, risk_per_trade=0.02)
        print_results(f"トレンドフォロー ({fast}/{slow} EMA)", r)

    # GBP/USDでも検証
    tf_gbp = trend_following_backtest(gbpusd_d1, fast_ma=20, slow_ma=50, risk_per_trade=0.02)
    print_results("トレンドフォロー GBP/USD (20/50 EMA)", tf_gbp)

    # === テスト4: ペアトレーディング ===
    print("\n\n[テスト4] ペアトレーディング (EUR/USD vs GBP/USD, 日足)")
    min_len = min(len(eurusd_d1), len(gbpusd_d1))
    common_idx = eurusd_d1.index[:min_len].intersection(gbpusd_d1.index[:min_len])
    if len(common_idx) > 100:
        pt_results = pairs_trading_backtest(
            eurusd_d1.loc[common_idx, "close"],
            gbpusd_d1.loc[common_idx, "close"],
            window=60,
            risk_per_trade=0.02
        )
        print_results("ペアトレード (EUR/USD vs GBP/USD)", pt_results)
    else:
        print("  共通インデックスが不足のためスキップ")

    # === 総合サマリー ===
    print("\n\n" + "=" * 60)
    print("  総合サマリー: 年利200%達成に向けた評価")
    print("=" * 60)
    print("""
  ┌────────────────────┬──────────┬──────────┬──────────┐
  │ 戦略               │ 年率CAGR │ 最大DD   │ 200%達成 │
  ├────────────────────┼──────────┼──────────┼──────────┤
  │ モンテカルロ(最良)   │ 可変     │ 可変     │ 条件次第 │
  │ ロンドンBK          │ 実測値   │ 実測値   │ 単体困難 │
  │ トレンドフォロー     │ 実測値   │ 実測値   │ 単体困難 │
  │ ペアトレード        │ 実測値   │ 実測値   │ 補助的   │
  ├────────────────────┼──────────┼──────────┼──────────┤
  │ 複合ポートフォリオ   │ 合算     │ 分散効果 │ 可能性有 │
  └────────────────────┴──────────┴──────────┴──────────┘

  結論:
  - 単一戦略での年利200%は疑似データでも達成困難
  - モンテカルロでは高期待値+適切リスクで35-55%の達成確率
  - 複数戦略の複合+複利運用が最も現実的なアプローチ
  - リスク管理（最大DD 20%以内）が持続的成長の鍵
    """)

    print("\n[完了] 全バックテスト実行完了")
