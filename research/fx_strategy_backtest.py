#!/usr/bin/env python3
"""
FX多因子適応型戦略バックテスト
==============================
特性分析の結果を活用した複合戦略
- Z-score平均回帰（VR<1の短期回帰性を活用）
- ドンチャンブレイクアウト（トレンド型ペア向け）
- レジームオーバーレイ（リスクオン/オフ判定）
- 相関フィルター付きポジション管理

ウォークフォワード検証: 5年訓練 / 1年テスト
"""

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# Part 1: データロード
# ============================================================
def load_data(path='research/data_fx_long.csv'):
    df = pd.read_csv(path, parse_dates=['date'])
    df.set_index('date', inplace=True)
    df = df.sort_index()
    df['GBP/AUD'] = df['GBP/USD'] / df['AUD/USD']
    df['GBP/NZD'] = df['GBP/USD'] / df['NZD/USD']
    return df

TARGET_PAIRS = [
    'EUR/USD', 'USD/JPY', 'EUR/JPY', 'GBP/USD', 'GBP/JPY',
    'AUD/JPY', 'NZD/JPY', 'CHF/JPY', 'USD/CHF', 'AUD/USD',
    'EUR/GBP', 'NZD/USD', 'USD/CAD', 'CAD/JPY', 'AUD/CHF',
    'EUR/AUD', 'AUD/NZD', 'EUR/CAD', 'EUR/CHF', 'GBP/AUD',
    'AUD/CAD', 'EUR/NZD', 'GBP/CAD', 'GBP/CHF', 'GBP/NZD',
]

JPY_PAIRS = [p for p in TARGET_PAIRS if p.endswith('/JPY')]

# ============================================================
# Part 2: シグナル生成
# ============================================================
def zscore_signals(prices, window=30, entry_z=1.5, exit_z=0.5, stop_z=4.0):
    """Z-score逆張りシグナル: +1=ロング, -1=ショート, 0=フラット"""
    mean = prices.rolling(window).mean()
    std = prices.rolling(window).std()
    z = (prices - mean) / std
    signals = pd.Series(0.0, index=prices.index)
    pos = 0
    for i in range(window, len(z)):
        zi = z.iloc[i]
        if pd.isna(zi):
            signals.iloc[i] = pos
            continue
        if pos == 0:
            if zi > entry_z:
                pos = -1
            elif zi < -entry_z:
                pos = 1
        elif pos == 1:
            if zi > -exit_z or zi < -stop_z:
                pos = 0
        elif pos == -1:
            if zi < exit_z or zi > stop_z:
                pos = 0
        signals.iloc[i] = pos
    return signals

def donchian_signals(prices, entry_period=20, exit_period=10):
    """ドンチャンブレイクアウト: 高値更新→ロング、安値更新→ショート"""
    high_n = prices.rolling(entry_period).max()
    low_n = prices.rolling(entry_period).min()
    exit_low = prices.rolling(exit_period).min()
    exit_high = prices.rolling(exit_period).max()
    signals = pd.Series(0.0, index=prices.index)
    pos = 0
    for i in range(entry_period, len(prices)):
        p = prices.iloc[i]
        if pd.isna(p):
            signals.iloc[i] = pos
            continue
        if pos == 0:
            if p >= high_n.iloc[i-1]:
                pos = 1
            elif p <= low_n.iloc[i-1]:
                pos = -1
        elif pos == 1:
            if p <= exit_low.iloc[i-1]:
                pos = 0
        elif pos == -1:
            if p >= exit_high.iloc[i-1]:
                pos = 0
        signals.iloc[i] = pos
    return signals

def regime_indicator(df, window=20):
    """リスクオン/オフ: JPYクロス合成指数の20日移動平均"""
    jpy_cols = [p for p in JPY_PAIRS if p in df.columns]
    if not jpy_cols:
        return pd.Series(0, index=df.index)
    log_ret = np.log(df[jpy_cols] / df[jpy_cols].shift(1))
    composite = log_ret.mean(axis=1)
    rolling_m = composite.rolling(window).mean()
    regime = pd.Series(0, index=df.index)
    regime[rolling_m > 0] = 1
    regime[rolling_m <= 0] = -1
    return regime

# ============================================================
# Part 3: ポジション管理
# ============================================================
def parse_pair(pair):
    return pair.split('/')

def check_currency_exposure(positions, new_pair, max_exposure=3):
    """同一通貨のエクスポージャー制限"""
    base, quote = parse_pair(new_pair)
    count_base = 0
    count_quote = 0
    for p in positions:
        b, q = parse_pair(p)
        if b == base or q == base:
            count_base += 1
        if b == quote or q == quote:
            count_quote += 1
    return count_base < max_exposure and count_quote < max_exposure

def check_correlation(returns_window, positions, new_pair, threshold=0.6):
    """既存ポジションとの相関チェック"""
    if not positions or new_pair not in returns_window.columns:
        return True
    for p in positions:
        if p not in returns_window.columns:
            continue
        corr = returns_window[new_pair].corr(returns_window[p])
        if abs(corr) > threshold:
            return False
    return True

# ============================================================
# Part 4: 単一戦略バックテスト（ベースライン）
# ============================================================
def backtest_single_strategy(df, pair, strategy='zscore', params=None):
    """単一ペア・単一戦略のバックテスト"""
    if params is None:
        params = {}
    prices = df[pair].dropna()
    log_ret = np.log(prices / prices.shift(1))

    if strategy == 'zscore':
        sigs = zscore_signals(prices, **{k: v for k, v in params.items()
                                         if k in ['window','entry_z','exit_z','stop_z']})
    else:
        sigs = donchian_signals(prices, **{k: v for k, v in params.items()
                                           if k in ['entry_period','exit_period']})

    # ポジション変化時にトレード記録
    risk_pct = params.get('risk_pct', 0.03)
    trades = []
    equity = 1.0
    entry_price = None
    entry_date = None
    direction = 0

    for i in range(1, len(sigs)):
        prev_sig = sigs.iloc[i-1]
        curr_sig = sigs.iloc[i]
        date = sigs.index[i]
        try:
            price = float(prices.loc[date])
        except (KeyError, TypeError):
            continue
        if np.isnan(price):
            continue

        # ポジションクローズ
        if direction != 0 and curr_sig != direction:
            if entry_price is not None and entry_price > 0:
                ret = np.log(price / entry_price) * direction
                pnl = ret * risk_pct / 0.02  # 2%リスク基準でスケーリング
                equity *= (1 + pnl)
                trades.append({
                    'pair': pair, 'entry_date': entry_date, 'exit_date': date,
                    'direction': 'LONG' if direction == 1 else 'SHORT',
                    'entry_price': entry_price, 'exit_price': price,
                    'pnl_pct': pnl * 100, 'equity': equity
                })
            direction = 0
            entry_price = None

        # ポジションオープン
        if direction == 0 and curr_sig != 0:
            direction = int(curr_sig)
            entry_price = price
            entry_date = date

    return pd.DataFrame(trades) if trades else pd.DataFrame()

# ============================================================
# Part 5: ウォークフォワード多因子バックテスト
# ============================================================
def walk_forward_backtest(df, pairs, train_days=1260, test_days=252, step_days=252):
    """
    ウォークフォワード検証:
    1. 訓練期間でペアごとに最適戦略・パラメータを選定
    2. テスト期間でアウトオブサンプル検証
    3. ポジション管理（相関・通貨エクスポージャー制限）
    """
    log_ret = np.log(df[pairs] / df[pairs].shift(1)).dropna(how='all')
    dates = df.index
    n = len(dates)

    all_trades = []
    daily_equity = []
    equity = 1.0

    start = train_days
    period_num = 0

    while start + test_days <= n:
        period_num += 1
        train_start = start - train_days
        train_end = start
        test_start = start
        test_end = min(start + test_days, n)

        train_dates = dates[train_start:train_end]
        test_dates = dates[test_start:test_end]

        # === 訓練フェーズ: 各ペアで最適戦略を選定 ===
        pair_configs = {}
        for pair in pairs:
            if pair not in df.columns:
                continue
            train_prices = df[pair].loc[train_dates[0]:train_dates[-1]].dropna()
            if len(train_prices) < 300:
                continue

            best_sharpe = -999
            best_config = None

            # Z-score パラメータグリッド（小さめ）
            for w in [20, 30, 45]:
                for ez in [1.0, 1.5, 2.0]:
                    tdf = backtest_single_strategy(
                        df.loc[train_dates[0]:train_dates[-1]], pair,
                        'zscore', {'window': w, 'entry_z': ez, 'exit_z': 0.5,
                                   'stop_z': 4.0, 'risk_pct': 0.03})
                    if len(tdf) < 3:
                        continue
                    sharpe = _calc_sharpe(tdf)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_config = ('zscore', {'window': w, 'entry_z': ez,
                                                  'exit_z': 0.5, 'stop_z': 4.0,
                                                  'risk_pct': 0.03})

            # ドンチャン パラメータグリッド
            for ep in [10, 20, 40]:
                for xp in [5, 10]:
                    tdf = backtest_single_strategy(
                        df.loc[train_dates[0]:train_dates[-1]], pair,
                        'donchian', {'entry_period': ep, 'exit_period': xp,
                                     'risk_pct': 0.03})
                    if len(tdf) < 3:
                        continue
                    sharpe = _calc_sharpe(tdf)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_config = ('donchian', {'entry_period': ep,
                                                    'exit_period': xp,
                                                    'risk_pct': 0.03})

            if best_config and best_sharpe > 0:
                pair_configs[pair] = best_config

        # === テストフェーズ: 選定した設定でOOS実行 ===
        test_df = df.loc[test_dates[0]:test_dates[-1]]
        test_ret = log_ret.loc[test_dates[0]:test_dates[-1]]

        # 各ペアのシグナル生成
        pair_signals = {}
        for pair, (strat, params) in pair_configs.items():
            prices = df[pair].loc[:test_dates[-1]].dropna()
            if strat == 'zscore':
                sigs = zscore_signals(prices, **{k: v for k, v in params.items()
                                                  if k != 'risk_pct'})
            else:
                sigs = donchian_signals(prices, **{k: v for k, v in params.items()
                                                    if k != 'risk_pct'})
            pair_signals[pair] = sigs.loc[test_dates[0]:test_dates[-1]]

        # レジーム
        regime = regime_indicator(df.loc[:test_dates[-1]])
        regime = regime.loc[test_dates[0]:test_dates[-1]]

        # 日次シミュレーション
        active_positions = {}  # pair -> {direction, entry_price, entry_date}

        for i, date in enumerate(test_dates):
            if date not in test_df.index:
                continue

            day_pnl = 0.0
            closed_today = []

            # 既存ポジションのチェック
            for pair in list(active_positions.keys()):
                if pair not in pair_signals or date not in pair_signals[pair].index:
                    continue
                try:
                    sig = float(pair_signals[pair].loc[date])
                except (TypeError, ValueError):
                    continue
                pos_info = active_positions[pair]

                if sig != pos_info['direction']:
                    # クローズ
                    try:
                        price = float(df[pair].loc[date])
                    except (KeyError, TypeError):
                        price = None
                    if price and price > 0 and pos_info['entry_price'] > 0:
                        ret = np.log(price / pos_info['entry_price']) * pos_info['direction']
                        pnl = ret * 0.03 / 0.02
                        day_pnl += pnl
                        all_trades.append({
                            'period': period_num, 'pair': pair,
                            'entry_date': pos_info['entry_date'], 'exit_date': date,
                            'direction': 'LONG' if pos_info['direction']==1 else 'SHORT',
                            'pnl_pct': pnl * 100, 'strategy': pos_info['strategy']
                        })
                    del active_positions[pair]
                    closed_today.append(pair)

            # 新規ポジション
            for pair, sigs in pair_signals.items():
                if pair in active_positions or pair in closed_today:
                    continue
                if date not in sigs.index:
                    continue
                try:
                    sig = float(sigs.loc[date])
                except (TypeError, ValueError):
                    continue
                if sig == 0:
                    continue

                # 制限チェック
                if len(active_positions) >= 8:
                    continue
                if not check_currency_exposure(active_positions.keys(), pair):
                    continue

                # 60日相関チェック
                ret_window_end = df.index.get_loc(date)
                ret_window_start = max(0, ret_window_end - 60)
                ret_slice = log_ret.iloc[ret_window_start:ret_window_end]
                if not check_correlation(ret_slice, list(active_positions.keys()), pair):
                    continue

                # レジームフィルター（JPYペアのみ）
                if pair in JPY_PAIRS and date in regime.index:
                    try:
                        r = float(regime.loc[date])
                    except (TypeError, ValueError):
                        r = 0
                    if r == -1 and sig == 1:  # リスクオフでロングは避ける
                        continue
                    if r == 1 and sig == -1:  # リスクオンでショートは避ける
                        continue

                try:
                    price = float(df[pair].loc[date])
                except (KeyError, TypeError):
                    price = None
                if price and price > 0:
                    strat_name = pair_configs[pair][0]
                    active_positions[pair] = {
                        'direction': int(sig), 'entry_price': price,
                        'entry_date': date, 'strategy': strat_name
                    }

            equity *= (1 + day_pnl)
            daily_equity.append({'date': date, 'equity': equity,
                                 'positions': len(active_positions),
                                 'period': period_num})

        start += step_days

    return pd.DataFrame(all_trades), pd.DataFrame(daily_equity)

def _calc_sharpe(trades_df):
    if len(trades_df) < 2:
        return -999
    pnls = trades_df['pnl_pct'].values / 100
    if np.std(pnls) == 0:
        return 0
    return np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls))

# ============================================================
# Part 6: メトリクス計算 & レポート
# ============================================================
def compute_metrics(equity_df, trades_df, years):
    eq = equity_df['equity'].values
    final = eq[-1] if len(eq) > 0 else 1.0
    total_ret = (final - 1) * 100
    cagr = ((final ** (1/years)) - 1) * 100 if years > 0 else 0

    # MaxDD
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd = np.max(dd) * 100 if len(dd) > 0 else 0

    # Sharpe
    daily_ret = np.diff(eq) / eq[:-1]
    if len(daily_ret) > 1 and np.std(daily_ret) > 0:
        sharpe = np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252)
    else:
        sharpe = 0

    # Calmar
    calmar = cagr / max_dd if max_dd > 0 else 0

    # Trade stats
    n_trades = len(trades_df)
    if n_trades > 0:
        wins = (trades_df['pnl_pct'] > 0).sum()
        losses = (trades_df['pnl_pct'] <= 0).sum()
        win_rate = wins / n_trades * 100
        avg_win = trades_df.loc[trades_df['pnl_pct']>0, 'pnl_pct'].mean() if wins > 0 else 0
        avg_loss = trades_df.loc[trades_df['pnl_pct']<=0, 'pnl_pct'].mean() if losses > 0 else 0
        gross_profit = trades_df.loc[trades_df['pnl_pct']>0, 'pnl_pct'].sum()
        gross_loss = abs(trades_df.loc[trades_df['pnl_pct']<=0, 'pnl_pct'].sum())
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    else:
        wins = losses = 0
        win_rate = avg_win = avg_loss = pf = 0

    return {
        'total_return': total_ret, 'cagr': cagr, 'max_dd': max_dd,
        'sharpe': sharpe, 'calmar': calmar, 'n_trades': n_trades,
        'wins': wins, 'losses': losses, 'win_rate': win_rate,
        'avg_win': avg_win, 'avg_loss': avg_loss, 'profit_factor': pf,
        'final_equity': final
    }

def print_report(metrics, trades_df, equity_df, years):
    m = metrics
    print(f"\n{'='*70}")
    print(f"  多因子適応型戦略 バックテスト結果")
    print(f"{'='*70}")
    print(f"  総リターン     : {m['total_return']:>+.2f}%")
    print(f"  CAGR           : {m['cagr']:>+.2f}%")
    print(f"  最大DD         : {m['max_dd']:.2f}%")
    print(f"  シャープレシオ : {m['sharpe']:.3f}")
    print(f"  カルマーレシオ : {m['calmar']:.3f}")
    print(f"  取引回数       : {m['n_trades']}")
    print(f"  勝率           : {m['win_rate']:.1f}% ({m['wins']}勝 / {m['losses']}敗)")
    print(f"  平均勝ち       : {m['avg_win']:+.2f}%")
    print(f"  平均負け       : {m['avg_loss']:+.2f}%")
    print(f"  プロフィットF  : {m['profit_factor']:.2f}")
    print(f"  最終資産倍率   : {m['final_equity']:.3f}x")

    # ペア別
    if len(trades_df) > 0:
        print(f"\n{'='*70}")
        print(f"  ペア別成績")
        print(f"{'='*70}")
        print(f"  {'Pair':<10} {'戦略':>8} {'回数':>4} {'勝率':>6} {'損益%':>8} {'PF':>6}")
        print(f"  {'-'*48}")
        for pair in sorted(trades_df['pair'].unique()):
            pt = trades_df[trades_df['pair'] == pair]
            n = len(pt)
            wr = (pt['pnl_pct'] > 0).mean() * 100
            total_pnl = pt['pnl_pct'].sum()
            gp = pt.loc[pt['pnl_pct']>0, 'pnl_pct'].sum()
            gl = abs(pt.loc[pt['pnl_pct']<=0, 'pnl_pct'].sum())
            pf = gp / gl if gl > 0 else float('inf')
            strat = pt['strategy'].mode().iloc[0] if 'strategy' in pt.columns and len(pt) > 0 else '?'
            print(f"  {pair:<10} {strat:>8} {n:>4} {wr:>5.1f}% {total_pnl:>+8.2f} {pf:>6.2f}")

    # 年別
    if len(equity_df) > 0:
        print(f"\n{'='*70}")
        print(f"  年別パフォーマンス")
        print(f"{'='*70}")
        edf = equity_df.copy()
        edf['year'] = pd.to_datetime(edf['date']).dt.year
        print(f"  {'年':>6} {'リターン':>8} {'取引数':>6} {'最大DD':>7}")
        print(f"  {'-'*30}")
        prev_eq = 1.0
        for year in sorted(edf['year'].unique()):
            yd = edf[edf['year'] == year]
            end_eq = yd['equity'].iloc[-1]
            yr_ret = (end_eq / prev_eq - 1) * 100
            yr_trades = len(trades_df[pd.to_datetime(trades_df['exit_date']).dt.year == year]) if len(trades_df) > 0 else 0
            yr_peak = np.maximum.accumulate(yd['equity'].values)
            yr_dd = ((yr_peak - yd['equity'].values) / yr_peak).max() * 100
            marker = " !" if yr_ret < 0 else ""
            print(f"  {year:>6} {yr_ret:>+8.2f}% {yr_trades:>6} {yr_dd:>6.2f}%{marker}")
            prev_eq = end_eq

    # ウォークフォワード期間別
    if len(equity_df) > 0 and 'period' in equity_df.columns:
        print(f"\n{'='*70}")
        print(f"  ウォークフォワード期間別")
        print(f"{'='*70}")
        prev_eq = 1.0
        for period in sorted(equity_df['period'].unique()):
            pd_data = equity_df[equity_df['period'] == period]
            start_d = pd_data['date'].iloc[0]
            end_d = pd_data['date'].iloc[-1]
            end_eq = pd_data['equity'].iloc[-1]
            p_ret = (end_eq / prev_eq - 1) * 100
            p_trades = len(trades_df[trades_df['period'] == period]) if len(trades_df) > 0 else 0
            print(f"  期間{period:>2}: {str(start_d)[:10]} ~ {str(end_d)[:10]}  ret={p_ret:>+7.2f}%  trades={p_trades}")
            prev_eq = end_eq

# ============================================================
# Part 7: ベンチマーク比較
# ============================================================
def run_benchmarks(df, years):
    print(f"\n{'='*70}")
    print(f"  ベンチマーク比較")
    print(f"{'='*70}")

    # 1. EUR/USD バイ&ホールド
    p = df['EUR/USD'].dropna()
    bh_ret = (p.iloc[-1] / p.iloc[0] - 1) * 100
    bh_cagr = ((p.iloc[-1] / p.iloc[0]) ** (1/years) - 1) * 100
    print(f"  EUR/USD B&H     : {bh_ret:>+7.2f}% (CAGR {bh_cagr:>+.2f}%)")

    # 2. USD/JPY バイ&ホールド
    p = df['USD/JPY'].dropna()
    bh_ret = (p.iloc[-1] / p.iloc[0] - 1) * 100
    bh_cagr = ((p.iloc[-1] / p.iloc[0]) ** (1/years) - 1) * 100
    print(f"  USD/JPY B&H     : {bh_ret:>+7.2f}% (CAGR {bh_cagr:>+.2f}%)")

    # 3. EUR/GBP Z-score単独
    tdf = backtest_single_strategy(df, 'EUR/GBP', 'zscore',
                                   {'window':30,'entry_z':1.5,'exit_z':0.5,
                                    'stop_z':4.0,'risk_pct':0.03})
    if len(tdf) > 0:
        final = tdf['equity'].iloc[-1]
        cagr = ((final ** (1/years)) - 1) * 100
        wr = (tdf['pnl_pct'] > 0).mean() * 100
        print(f"  EUR/GBP Zscore  : {(final-1)*100:>+7.2f}% (CAGR {cagr:>+.2f}%, WR={wr:.0f}%)")

    # 4. 全ペア均等Z-score
    total_eq = 1.0
    total_trades = 0
    for pair in TARGET_PAIRS:
        if pair not in df.columns:
            continue
        tdf = backtest_single_strategy(df, pair, 'zscore',
                                       {'window':30,'entry_z':1.5,'exit_z':0.5,
                                        'stop_z':4.0,'risk_pct':0.01})
        if len(tdf) > 0:
            pair_eq = tdf['equity'].iloc[-1]
            total_eq *= pair_eq
            total_trades += len(tdf)
    cagr = ((total_eq ** (1/years)) - 1) * 100
    print(f"  全ペアZscore均等: {(total_eq-1)*100:>+7.2f}% (CAGR {cagr:>+.2f}%, {total_trades}trades)")

# ============================================================
# Main
# ============================================================
def main():
    print("=" * 70)
    print("  FX多因子適応型戦略 ウォークフォワードバックテスト")
    print("=" * 70)

    df = load_data()
    years = (df.index[-1] - df.index[0]).days / 365.25
    print(f"  データ: {df.index[0].date()} ~ {df.index[-1].date()} ({years:.1f}年)")
    print(f"  対象: {len(TARGET_PAIRS)}ペア")
    print(f"  ウォークフォワード: 5年訓練 / 1年テスト / 1年ステップ")
    print(f"\n  実行中...")

    available = [p for p in TARGET_PAIRS if p in df.columns]
    trades_df, equity_df = walk_forward_backtest(df, available)
    test_years = len(equity_df) / 252 if len(equity_df) > 0 else 1
    metrics = compute_metrics(equity_df, trades_df, test_years)

    print_report(metrics, trades_df, equity_df, test_years)
    run_benchmarks(df, years)

    print(f"\n{'='*70}")
    print(f"  [完了]")
    print(f"{'='*70}")

if __name__ == '__main__':
    main()
