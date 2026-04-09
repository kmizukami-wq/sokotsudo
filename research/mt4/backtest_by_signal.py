#!/usr/bin/env python3
"""
BB_Reversal_Martin: シグナル別 × 5通貨ペア バックテスト
各ロジックを単体で運用した場合の成績を比較
"""

import datetime
import numpy as np
import pandas as pd

# ============================================================
# 通貨ペア別の合成データ生成
# ============================================================
PAIRS = {
    "USDJPY": {"base": 150.0, "vol": 0.00030, "digits": 3, "spread_normal": 0.8, "spread_morning": 4.5},
    "EURJPY": {"base": 163.0, "vol": 0.00035, "digits": 3, "spread_normal": 1.0, "spread_morning": 5.0},
    "GBPJPY": {"base": 192.0, "vol": 0.00045, "digits": 3, "spread_normal": 1.5, "spread_morning": 6.0},
    "AUDJPY": {"base": 98.0,  "vol": 0.00032, "digits": 3, "spread_normal": 1.2, "spread_morning": 5.5},
    "EURUSD": {"base": 1.085, "vol": 0.00028, "digits": 5, "spread_normal": 0.5, "spread_morning": 3.0},
}


def generate_pair_data(pair_name, cfg, bars=8000, seed=None):
    """通貨ペア特性を反映した合成M15データ"""
    if seed is not None:
        np.random.seed(seed)

    dt_minutes = 15
    price = cfg["base"]
    prices = []
    t = datetime.datetime(2025, 1, 1, 0, 0)

    for _ in range(bars):
        if t.weekday() >= 5:
            t += datetime.timedelta(minutes=dt_minutes)
            continue

        hour_jst = (t.hour + 9) % 24  # サーバーGMT+2想定 → JST
        vol = cfg["vol"]

        # セッション別ボラティリティ
        if 6 <= hour_jst < 9:
            vol *= 0.4   # 早朝: 低ボラ
        elif 9 <= hour_jst < 15:
            vol *= 0.9   # 東京
        elif 15 <= hour_jst < 21:
            vol *= 1.5   # ロンドン・NY
        elif 21 <= hour_jst or hour_jst < 3:
            vol *= 1.1   # NY後半

        # トレンド成分（通貨ペアごとに異なる）
        trend = 0
        day_of_year = t.timetuple().tm_yday
        if pair_name in ("USDJPY", "EURJPY", "GBPJPY"):
            trend = 0.00002 * np.sin(2 * np.pi * day_of_year / 60)  # 60日サイクル
        elif pair_name == "AUDJPY":
            trend = -0.00001 * np.sin(2 * np.pi * day_of_year / 45)
        else:  # EURUSD
            trend = 0.00001 * np.sin(2 * np.pi * day_of_year / 90)

        ret = np.random.normal(trend, vol) - 0.000005 * (price - cfg["base"])
        o = price
        c = price * (1 + ret)
        wick = abs(np.random.normal(0, vol * 0.5))
        h = max(o, c) * (1 + wick)
        l = min(o, c) * (1 - wick)

        # スプレッド
        if 6 <= hour_jst < 9:
            spread = np.random.uniform(cfg["spread_morning"] * 0.8, cfg["spread_morning"] * 1.5)
        else:
            spread = np.random.uniform(cfg["spread_normal"] * 0.5, cfg["spread_normal"] * 1.5)

        prices.append({
            "time": t, "open": o, "high": h, "low": l, "close": c,
            "spread_pips": spread
        })
        price = c
        t += datetime.timedelta(minutes=dt_minutes)

    return pd.DataFrame(prices)


# ============================================================
# インジケータ計算
# ============================================================
def calc_indicators(df):
    c = df["close"]

    df["sma200"] = c.rolling(200).mean()
    df["sma50"] = c.rolling(50).mean()
    df["sma20"] = c.rolling(20).mean()
    df["sma200_up"] = df["sma200"] > df["sma200"].shift(5)
    df["sma50_up"] = df["sma50"] > df["sma50"].shift(5)

    delta = c.diff()
    gain = delta.clip(lower=0).rolling(10).mean()
    loss = (-delta.clip(upper=0)).rolling(10).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - c.shift(1)).abs(),
        (df["low"] - c.shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["atr14_ma100"] = df["atr14"].rolling(100).mean()

    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    df["bb_upper"] = bb_mid + 2.5 * bb_std
    df["bb_lower"] = bb_mid - 2.5 * bb_std

    fbb_mid = c.rolling(10).mean()
    fbb_std = c.rolling(10).std()
    df["fbb_upper"] = fbb_mid + 2.0 * fbb_std
    df["fbb_lower"] = fbb_mid - 2.0 * fbb_std

    return df.dropna().reset_index(drop=True)


# ============================================================
# シグナル別判定関数
# ============================================================
def check_bb_reversal(row, prev, atr_filter_mult=2.5, max_spread=3.0):
    """シグナル1のみ: BB 2.5σ逆張り"""
    if row["spread_pips"] > max_spread:
        return 0, "spread"
    if row["atr14"] >= row["atr14_ma100"] * atr_filter_mult:
        return 0, "atr"
    c1, c2, rsi = row["close"], prev["close"], row["rsi"]
    up = row["sma200_up"]
    if up and c2 <= prev["bb_lower"] and c1 > row["bb_lower"] and rsi < 42:
        return 1, "BUY_BB"
    if not up and c2 >= prev["bb_upper"] and c1 < row["bb_upper"] and rsi > 58:
        return -1, "SELL_BB"
    return 0, "none"


def check_fast_bb(row, prev, atr_filter_mult=2.5, max_spread=3.0):
    """シグナル2のみ: 高速BB逆張り"""
    if row["spread_pips"] > max_spread:
        return 0, "spread"
    if row["atr14"] >= row["atr14_ma100"] * atr_filter_mult:
        return 0, "atr"
    c1, rsi = row["close"], row["rsi"]
    up200, up50 = row["sma200_up"], row["sma50_up"]
    if up200 and up50 and c1 <= row["fbb_lower"] and rsi < 48:
        return 2, "BUY_FBB"
    if not up200 and not up50 and c1 >= row["fbb_upper"] and rsi > 52:
        return -2, "SELL_FBB"
    return 0, "none"


def check_pullback(row, prev, atr_filter_mult=2.5, max_spread=3.0):
    """シグナル3のみ: 押し目・戻り売り"""
    if row["spread_pips"] > max_spread:
        return 0, "spread"
    if row["atr14"] >= row["atr14_ma100"] * atr_filter_mult:
        return 0, "atr"
    c1, rsi = row["close"], row["rsi"]
    up = row["sma200_up"]
    sma_gap = abs(row["sma20"] - row["sma50"])
    if sma_gap < row["atr14"] * 2:
        return 0, "none"
    lo = min(row["sma20"], row["sma50"])
    hi = max(row["sma20"], row["sma50"])
    if up and lo <= c1 <= hi and 30 <= rsi <= 50:
        return 3, "BUY_PB"
    if not up and lo <= c1 <= hi and 50 <= rsi <= 70:
        return -3, "SELL_PB"
    return 0, "none"


def check_all_signals(row, prev, atr_filter_mult=2.5, max_spread=3.0):
    """全シグナル統合"""
    if row["spread_pips"] > max_spread:
        return 0, "spread"
    if row["atr14"] >= row["atr14_ma100"] * atr_filter_mult:
        return 0, "atr"
    # 優先順: BB逆張り → 高速BB → 押し目
    for func in [check_bb_reversal, check_fast_bb, check_pullback]:
        sig, name = func(row, prev, atr_filter_mult, max_spread=999)  # spread already checked
        if sig != 0:
            return sig, name
    return 0, "none"


# ============================================================
# バックテスト
# ============================================================
def run_backtest(df, signal_func, pip_mult=100, deduct_spread=True, **kwargs):
    sl_mults = {1: 2.0, 2: 1.8, 3: 1.5}
    rr_ratio = 2.0
    max_hold = 20

    trades = []
    i = 1
    while i < len(df) - max_hold:
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        sig, sig_name = signal_func(row, prev, **kwargs)

        if sig == 0:
            i += 1
            continue

        direction = 1 if sig > 0 else -1
        entry = row["close"]
        atr = row["atr14"]
        sl_mult = sl_mults.get(abs(sig), 1.5)
        sl_dist = atr * sl_mult
        tp_dist = sl_dist * rr_ratio
        spread_cost = row["spread_pips"] if deduct_spread else 0

        sl_price = entry - direction * sl_dist
        tp_price = entry + direction * tp_dist

        result = "timeout"
        pnl = 0
        exit_bar = i

        for j in range(1, max_hold + 1):
            if i + j >= len(df):
                break
            bar = df.iloc[i + j]
            if direction == 1:
                if bar["low"] <= sl_price:
                    result, pnl, exit_bar = "SL", -sl_dist * pip_mult - spread_cost, i + j
                    break
                if bar["high"] >= tp_price:
                    result, pnl, exit_bar = "TP", tp_dist * pip_mult - spread_cost, i + j
                    break
            else:
                if bar["high"] >= sl_price:
                    result, pnl, exit_bar = "SL", -sl_dist * pip_mult - spread_cost, i + j
                    break
                if bar["low"] <= tp_price:
                    result, pnl, exit_bar = "TP", tp_dist * pip_mult - spread_cost, i + j
                    break

        if result == "timeout":
            ex = df.iloc[min(i + max_hold, len(df) - 1)]["close"]
            pnl = direction * (ex - entry) * pip_mult - spread_cost

        trades.append({"result": result, "pnl_pips": pnl, "signal": sig_name})
        i = exit_bar + 1

    return trades


def calc_stats(trades):
    if not trades:
        return {"n": 0, "wr": 0, "pnl": 0, "pf": 0, "dd": 0, "avg_w": 0, "avg_l": 0}
    df_t = pd.DataFrame(trades)
    n = len(df_t)
    wins = df_t[df_t["pnl_pips"] > 0]
    losses = df_t[df_t["pnl_pips"] <= 0]
    w = len(wins)
    total_pnl = df_t["pnl_pips"].sum()
    wr = w / n * 100 if n > 0 else 0
    avg_w = wins["pnl_pips"].mean() if len(wins) > 0 else 0
    avg_l = losses["pnl_pips"].mean() if len(losses) > 0 else 0
    gross_profit = wins["pnl_pips"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["pnl_pips"].sum()) if len(losses) > 0 else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    cumsum = df_t["pnl_pips"].cumsum()
    dd = (cumsum - cumsum.cummax()).min()
    return {"n": n, "wr": wr, "pnl": total_pnl, "pf": pf, "dd": dd, "avg_w": avg_w, "avg_l": avg_l}


# ============================================================
# メイン
# ============================================================
def main():
    print("=" * 80)
    print("BB_Reversal_Martin: シグナル別 × 5通貨ペア バックテスト")
    print("=" * 80)

    strategies = {
        "1.BB逆張り": check_bb_reversal,
        "2.高速BB":   check_fast_bb,
        "3.押し目":   check_pullback,
        "全統合":     check_all_signals,
    }

    # 全結果を格納
    all_results = {}

    for pair_name, cfg in PAIRS.items():
        seed = hash(pair_name) % 10000
        print(f"\n--- {pair_name} データ生成中... ", end="")
        df = generate_pair_data(pair_name, cfg, bars=8000, seed=seed)
        df = calc_indicators(df)
        print(f"{len(df)} bars")

        pip_mult = 100 if cfg["digits"] == 3 else 10000  # JPY=100, USD系=10000
        for strat_name, func in strategies.items():
            trades = run_backtest(df, func, pip_mult=pip_mult, deduct_spread=True)
            stats = calc_stats(trades)
            all_results[(pair_name, strat_name)] = stats

    # ============================================================
    # 結果表示: ロジック別テーブル
    # ============================================================
    for strat_name in strategies.keys():
        print(f"\n{'='*80}")
        print(f"  【{strat_name}】")
        print(f"{'='*80}")
        print(f"  {'通貨ペア':>8s}  {'トレード':>6s}  {'勝率':>6s}  {'損益(pips)':>10s}  {'PF':>5s}  {'平均W':>7s}  {'平均L':>7s}  {'最大DD':>8s}")
        print(f"  {'-'*72}")

        total_n, total_pnl = 0, 0
        for pair_name in PAIRS:
            s = all_results[(pair_name, strat_name)]
            total_n += s["n"]
            total_pnl += s["pnl"]
            if s["n"] > 0:
                print(f"  {pair_name:>8s}  {s['n']:>6d}  {s['wr']:>5.1f}%  {s['pnl']:>+10.1f}  {s['pf']:>5.2f}  {s['avg_w']:>+6.1f}  {s['avg_l']:>+6.1f}  {s['dd']:>+7.1f}")
            else:
                print(f"  {pair_name:>8s}  {0:>6d}      -           -      -        -        -         -")

        print(f"  {'-'*72}")
        print(f"  {'合計':>8s}  {total_n:>6d}               {total_pnl:>+10.1f}")

    # ============================================================
    # 通貨ペア横断サマリー
    # ============================================================
    print(f"\n{'='*80}")
    print(f"  【通貨ペア × ロジック クロス集計: 損益(pips)】")
    print(f"{'='*80}")
    strat_names = list(strategies.keys())
    header = f"  {'':>8s}" + "".join(f"  {s:>12s}" for s in strat_names)
    print(header)
    print(f"  {'-'*(8 + 14 * len(strat_names))}")

    strat_totals = {s: 0 for s in strat_names}
    for pair_name in PAIRS:
        row_str = f"  {pair_name:>8s}"
        for sn in strat_names:
            s = all_results[(pair_name, sn)]
            row_str += f"  {s['pnl']:>+11.1f} " if s["n"] > 0 else f"  {'---':>11s} "
            strat_totals[sn] += s["pnl"]
        print(row_str)

    print(f"  {'-'*(8 + 14 * len(strat_names))}")
    total_row = f"  {'合計':>8s}"
    for sn in strat_names:
        total_row += f"  {strat_totals[sn]:>+11.1f} "
    print(total_row)

    # ============================================================
    # 勝率クロス集計
    # ============================================================
    print(f"\n{'='*80}")
    print(f"  【通貨ペア × ロジック クロス集計: 勝率(%)】")
    print(f"{'='*80}")
    print(header)
    print(f"  {'-'*(8 + 14 * len(strat_names))}")

    for pair_name in PAIRS:
        row_str = f"  {pair_name:>8s}"
        for sn in strat_names:
            s = all_results[(pair_name, sn)]
            row_str += f"  {s['wr']:>10.1f}% " if s["n"] > 0 else f"  {'---':>11s} "
        print(row_str)

    # ============================================================
    # PFクロス集計
    # ============================================================
    print(f"\n{'='*80}")
    print(f"  【通貨ペア × ロジック クロス集計: PF】")
    print(f"{'='*80}")
    print(header)
    print(f"  {'-'*(8 + 14 * len(strat_names))}")

    for pair_name in PAIRS:
        row_str = f"  {pair_name:>8s}"
        for sn in strat_names:
            s = all_results[(pair_name, sn)]
            pf_str = f"{s['pf']:.2f}" if s["pf"] < 100 else "inf"
            row_str += f"  {pf_str:>11s} " if s["n"] > 0 else f"  {'---':>11s} "
        print(row_str)

    # ベスト/ワーストの特定
    print(f"\n{'='*80}")
    print(f"  【推奨】")
    print(f"{'='*80}")
    for pair_name in PAIRS:
        best_strat = None
        best_pf = 0
        for sn in list(strategies.keys())[:3]:  # 統合除く
            s = all_results[(pair_name, sn)]
            if s["n"] >= 5 and s["pf"] > best_pf:
                best_pf = s["pf"]
                best_strat = sn
        integrated = all_results[(pair_name, "全統合")]
        if best_strat:
            print(f"  {pair_name}: 最適={best_strat} (PF={best_pf:.2f}), 統合PF={integrated['pf']:.2f}")
        else:
            print(f"  {pair_name}: シグナル不足")

    print(f"\n※合成M15データ（GBM + セッション別ボラ + トレンドサイクル）。実データでの検証推奨。")


if __name__ == "__main__":
    main()
