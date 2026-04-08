#!/usr/bin/env python3
"""
BB σ値比較バックテスト（2.5σ vs 3.0σ）
FXTF 4ペア・15分足・緩和A条件
"""

import numpy as np
import pandas as pd
import yfinance as yf
from collections import defaultdict

INITIAL_CAPITAL = 200_000
RISK_PER_TRADE = 0.008
RR_RATIO = 2.0
MARTIN_MULTIPLIERS = [1.0, 1.5, 2.0]
MAX_MARTIN_STAGE = 3
BE_TRIGGER_RR = 1.0
PARTIAL_CLOSE_RR = 1.5
PARTIAL_CLOSE_PCT = 0.5
TRAIL_ATR_MULT = 0.5
MAX_HOLDING_BARS = 20
TRADING_HOUR_START = 0
TRADING_HOUR_END = 21

SL_ATR_MULT = {'BB_reversal': 2.5, 'Fast_BB': 2.2, 'Pullback': 1.8}

PAIRS = {
    'AUDJPY=X': {'name': 'AUD/JPY', 'pip': 0.01, 'spread_pips': 0.5, 'quote_to_jpy': 1.0},
    'EURUSD=X': {'name': 'EUR/USD', 'pip': 0.0001, 'spread_pips': 0.3, 'quote_to_jpy': 150.0},
    'EURJPY=X': {'name': 'EUR/JPY', 'pip': 0.01, 'spread_pips': 0.5, 'quote_to_jpy': 1.0},
    'USDJPY=X': {'name': 'USD/JPY', 'pip': 0.01, 'spread_pips': 0.3, 'quote_to_jpy': 1.0},
}

CONFIGS = {
    'BB 2.5σ（現行）': {'bb_sigma': 2.5, 'fbb_sigma': 2.0},
    'BB 3.0σ': {'bb_sigma': 3.0, 'fbb_sigma': 2.0},
    'BB 3.0σ + FBB 2.5σ': {'bb_sigma': 3.0, 'fbb_sigma': 2.5},
}

# 緩和A RSI条件
RSI_BB_BUY = 42; RSI_BB_SELL = 58
RSI_FBB_BUY = 48; RSI_FBB_SELL = 52
RSI_PB_BUY = (30, 50); RSI_PB_SELL = (50, 70)
SMA_GAP_MULT = 2.0
ATR_FILTER_MULT = 2.5


def calc_indicators(df, bb_sigma, fbb_sigma):
    c = df['Close'].values.astype(float)
    h = df['High'].values.astype(float)
    l = df['Low'].values.astype(float)
    df['SMA200'] = pd.Series(c).rolling(200).mean().values
    df['SMA50'] = pd.Series(c).rolling(50).mean().values
    df['SMA20'] = pd.Series(c).rolling(20).mean().values
    sma20 = pd.Series(c).rolling(20).mean()
    std20 = pd.Series(c).rolling(20).std()
    df['BB_upper'] = (sma20 + bb_sigma * std20).values
    df['BB_lower'] = (sma20 - bb_sigma * std20).values
    sma10 = pd.Series(c).rolling(10).mean()
    std10 = pd.Series(c).rolling(10).std()
    df['FBB_upper'] = (sma10 + fbb_sigma * std10).values
    df['FBB_lower'] = (sma10 - fbb_sigma * std10).values
    delta = pd.Series(c).diff()
    gain = delta.clip(lower=0).rolling(10).mean()
    loss = (-delta.clip(upper=0)).rolling(10).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = (100 - 100 / (1 + rs)).values
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    df['ATR'] = pd.Series(tr).rolling(14).mean().values
    df['ATR_MA100'] = pd.Series(df['ATR']).rolling(100).mean().values
    df['SMA200_up'] = df['SMA200'] > pd.Series(df['SMA200']).shift(5).values
    df['SMA50_up'] = df['SMA50'] > pd.Series(df['SMA50']).shift(5).values
    return df


class RowProxy:
    def __init__(self, data, name):
        self._data = data
        self.name = name
    def __getitem__(self, key): return self._data[key]
    def get(self, key, default=None): return self._data.get(key, default)


def check_signals(row, prev_row):
    close = row['Close']
    rsi = row['RSI']
    if pd.isna(row['ATR']) or pd.isna(row['ATR_MA100']): return None
    if row['ATR'] >= row['ATR_MA100'] * ATR_FILTER_MULT: return None
    hour = row.name.hour if hasattr(row.name, 'hour') else 0
    if hour < TRADING_HOUR_START or hour >= TRADING_HOUR_END: return None
    required = ['SMA200', 'SMA50', 'SMA20', 'BB_upper', 'BB_lower', 'FBB_upper', 'FBB_lower', 'RSI', 'ATR']
    if any(pd.isna(row[k]) for k in required): return None
    if prev_row is not None and any(pd.isna(prev_row.get(k, np.nan)) for k in ['Close', 'BB_upper', 'BB_lower']): return None

    sma200_up = row['SMA200_up']

    if prev_row is not None:
        prev_close = prev_row['Close']
        if sma200_up and prev_close <= prev_row['BB_lower'] and close > row['BB_lower'] and rsi < RSI_BB_BUY:
            return ('BUY', 'BB_reversal')
        if not sma200_up and prev_close >= prev_row['BB_upper'] and close < row['BB_upper'] and rsi > RSI_BB_SELL:
            return ('SELL', 'BB_reversal')

    sma50_up = row['SMA50_up']
    if sma200_up and sma50_up and close <= row['FBB_lower'] and rsi < RSI_FBB_BUY:
        return ('BUY', 'Fast_BB')
    if not sma200_up and not sma50_up and close >= row['FBB_upper'] and rsi > RSI_FBB_SELL:
        return ('SELL', 'Fast_BB')

    sma20 = row['SMA20']; sma50 = row['SMA50']; atr = row['ATR']
    sma_gap = abs(sma20 - sma50)
    if sma_gap >= atr * SMA_GAP_MULT:
        lo = min(sma20, sma50); hi = max(sma20, sma50)
        if sma200_up and lo <= close <= hi and RSI_PB_BUY[0] <= rsi <= RSI_PB_BUY[1]:
            return ('BUY', 'Pullback')
        if not sma200_up and lo <= close <= hi and RSI_PB_SELL[0] <= rsi <= RSI_PB_SELL[1]:
            return ('SELL', 'Pullback')
    return None


def run_backtest(df, spread, q2j):
    capital = float(INITIAL_CAPITAL)
    peak = capital; max_dd = 0.0
    position = None; martin_stage = 0; consecutive_losses = 0
    trades = []; monthly_pnl = defaultdict(float)

    rows = df.to_dict('index'); indices = list(rows.keys())
    for i in range(1, len(indices)):
        idx = indices[i]; prev_idx = indices[i-1]
        row = rows[idx]; prev_row = rows[prev_idx]
        close = float(row['Close']); high = float(row['High']); low = float(row['Low'])
        mk = f"{idx.year}-{idx.month:02d}"

        if position is not None:
            position['bars_held'] += 1
            closed = False; pnl = 0.0; result = ''
            sl = position['sl']; tp = position['tp']; entry = position['entry']
            lots = position['lots']; d = position['direction']; sld = position['sl_distance']

            if d == 'BUY':
                um = high - entry
                if not position['be_activated'] and um >= sld * BE_TRIGGER_RR:
                    position['be_activated'] = True; position['sl'] = entry + spread; sl = position['sl']
                if not position['partial_closed'] and um >= sld * PARTIAL_CLOSE_RR:
                    pp = (sld * PARTIAL_CLOSE_RR - spread) * lots * PARTIAL_CLOSE_PCT * q2j
                    capital += pp; monthly_pnl[mk] += pp
                    position['partial_closed'] = True; position['partial_pnl'] = pp
                    position['lots'] = lots * (1 - PARTIAL_CLOSE_PCT); lots = position['lots']
                    ts = high - float(row['ATR']) * TRAIL_ATR_MULT
                    if ts > sl: position['sl'] = ts; sl = ts
                if position['partial_closed']:
                    ts = high - float(row['ATR']) * TRAIL_ATR_MULT
                    if ts > position['sl']: position['sl'] = ts; sl = position['sl']
                if low <= sl:
                    pnl = (sl - entry - spread) * lots * q2j; closed = True
                    result = 'BE' if (position['be_activated'] and not position['partial_closed']) else ('TRAIL' if position['partial_closed'] else 'SL')
                elif high >= tp:
                    pnl = (tp - entry - spread) * lots * q2j; closed = True; result = 'TP'
            else:
                um = entry - low
                if not position['be_activated'] and um >= sld * BE_TRIGGER_RR:
                    position['be_activated'] = True; position['sl'] = entry - spread; sl = position['sl']
                if not position['partial_closed'] and um >= sld * PARTIAL_CLOSE_RR:
                    pp = (sld * PARTIAL_CLOSE_RR - spread) * lots * PARTIAL_CLOSE_PCT * q2j
                    capital += pp; monthly_pnl[mk] += pp
                    position['partial_closed'] = True; position['partial_pnl'] = pp
                    position['lots'] = lots * (1 - PARTIAL_CLOSE_PCT); lots = position['lots']
                    ts = low + float(row['ATR']) * TRAIL_ATR_MULT
                    if ts < sl: position['sl'] = ts; sl = ts
                if position['partial_closed']:
                    ts = low + float(row['ATR']) * TRAIL_ATR_MULT
                    if ts < position['sl']: position['sl'] = ts; sl = position['sl']
                if high >= sl:
                    pnl = (entry - sl - spread) * lots * q2j; closed = True
                    result = 'BE' if (position['be_activated'] and not position['partial_closed']) else ('TRAIL' if position['partial_closed'] else 'SL')
                elif low <= tp:
                    pnl = (entry - tp - spread) * lots * q2j; closed = True; result = 'TP'

            if not closed and position['bars_held'] >= MAX_HOLDING_BARS:
                if d == 'BUY': pnl = (close - entry - spread) * lots * q2j
                else: pnl = (entry - close - spread) * lots * q2j
                closed = True; result = 'TIME'

            if closed:
                total_pnl = pnl + position.get('partial_pnl', 0)
                capital += pnl; monthly_pnl[mk] += pnl
                trades.append({'pnl': total_pnl, 'result': result, 'signal': position['signal']})
                if result == 'SL':
                    consecutive_losses += 1
                    if consecutive_losses >= MAX_MARTIN_STAGE: martin_stage = 0; consecutive_losses = 0
                    else: martin_stage = min(consecutive_losses, MAX_MARTIN_STAGE - 1)
                else: consecutive_losses = 0; martin_stage = 0
                position = None
                if capital > peak: peak = capital
                dd = (peak - capital) / peak
                if dd > max_dd: max_dd = dd
            if position is not None: continue

        row_p = RowProxy(row, idx); prev_p = RowProxy(prev_row, prev_idx)
        signal = check_signals(row_p, prev_p)
        if signal is None: continue
        direction, signal_type = signal
        atr = float(row['ATR'])
        sl_mult = SL_ATR_MULT.get(signal_type, 1.8)
        sl_distance = atr * sl_mult; tp_distance = sl_distance * RR_RATIO
        if direction == 'BUY':
            ep = close + spread/2; slp = ep - sl_distance; tpp = ep + tp_distance
        else:
            ep = close - spread/2; slp = ep + sl_distance; tpp = ep - tp_distance
        ra = capital * RISK_PER_TRADE * MARTIN_MULTIPLIERS[martin_stage]
        if sl_distance <= 0: continue
        lots = ra / (sl_distance * q2j)
        position = {'direction': direction, 'entry': ep, 'sl': slp, 'tp': tpp,
                    'sl_distance': sl_distance, 'lots': lots, 'signal': signal_type,
                    'stage': martin_stage, 'bars_held': 0, 'be_activated': False,
                    'partial_closed': False, 'partial_pnl': 0}

    return trades, capital, monthly_pnl, max_dd


def main():
    print("=" * 85)
    print("  BB σ値比較バックテスト（FXTF 4ペア・15分足・60日・資金20万円）")
    print("  SL倍率: BB=2.5, FBB=2.2, PB=1.8（広め設定）")
    print("=" * 85)

    try:
        usdjpy = yf.download('USDJPY=X', period='1d', interval='1d', progress=False)
        if isinstance(usdjpy.columns, pd.MultiIndex): usdjpy.columns = usdjpy.columns.get_level_values(0)
        PAIRS['EURUSD=X']['quote_to_jpy'] = float(usdjpy['Close'].iloc[-1])
    except: pass

    print("\n>>> データ取得中...")
    data_cache = {}
    for ticker, cfg in PAIRS.items():
        try:
            df = yf.download(ticker, period='60d', interval='15m', progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            data_cache[ticker] = df
            print(f"  {cfg['name']}: {len(df)}本")
        except Exception as e:
            print(f"  {cfg['name']}: Error - {e}")

    all_results = {}

    for config_name, config in CONFIGS.items():
        print(f"\n{'#'*85}")
        print(f"  {config_name}  (BB={config['bb_sigma']}σ  FBB={config['fbb_sigma']}σ)")
        print(f"{'#'*85}")

        pair_results = []
        for ticker, cfg in PAIRS.items():
            if ticker not in data_cache: continue
            df = data_cache[ticker].copy()
            df = calc_indicators(df, config['bb_sigma'], config['fbb_sigma'])
            spread = cfg['spread_pips'] * cfg['pip']
            q2j = cfg['quote_to_jpy']
            trades, final_cap, monthly_pnl, max_dd = run_backtest(df, spread, q2j)
            total = len(trades)
            if total > 0:
                wins = sum(1 for t in trades if t['pnl'] > 0)
                gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
                gl = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
                pf = gp / gl if gl > 0 else float('inf')
                net = final_cap - INITIAL_CAPITAL
                sig_counts = defaultdict(int)
                for t in trades: sig_counts[t['signal']] += 1
                pair_results.append({'pair': cfg['name'], 'trades': total, 'win_rate': wins/total*100,
                    'pf': pf, 'max_dd': max_dd, 'net': net, 'sig': dict(sig_counts)})
            else:
                pair_results.append({'pair': cfg['name'], 'trades': 0, 'win_rate': 0,
                    'pf': 0, 'max_dd': 0, 'net': 0, 'sig': {}})

        print(f"\n  {'ペア':<10s} {'取引':>4s} {'月換算':>5s} {'勝率':>6s} {'PF':>6s} {'DD':>6s} {'純損益':>11s}  {'BB':>3s} {'FBB':>3s} {'PB':>3s}")
        print(f"  {'-'*10} {'-'*4} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*11}  {'-'*3} {'-'*3} {'-'*3}")
        total_net = 0; total_trades = 0
        for r in sorted(pair_results, key=lambda x: x['pf'], reverse=True):
            m = r['trades'] / 2
            bb = r['sig'].get('BB_reversal', 0); fbb = r['sig'].get('Fast_BB', 0); pb = r['sig'].get('Pullback', 0)
            print(f"  {r['pair']:<10s} {r['trades']:4d} {m:5.0f} {r['win_rate']:5.1f}% {r['pf']:6.2f} {r['max_dd']:5.1%} ¥{r['net']:>+10,.0f}  {bb:3d} {fbb:3d} {pb:3d}")
            total_net += r['net']; total_trades += r['trades']

        prs = [p for p in pair_results if p['trades'] > 0]
        avg_pf = np.mean([p['pf'] for p in prs]) if prs else 0
        avg_dd = np.mean([p['max_dd'] for p in prs]) if prs else 0
        all_results[config_name] = {'trades': total_trades, 'net': total_net, 'avg_pf': avg_pf, 'avg_dd': avg_dd}
        print(f"\n  合計: {total_trades}件（月{total_trades/2:.0f}件）  純損益 ¥{total_net:>+,.0f}")

    print(f"\n{'='*85}")
    print(f"  比較サマリー")
    print(f"{'='*85}")
    print(f"  {'条件':<25s} {'取引数':>5s} {'月換算':>5s} {'合計損益':>12s} {'Avg PF':>7s} {'Avg DD':>7s}")
    print(f"  {'-'*25} {'-'*5} {'-'*5} {'-'*12} {'-'*7} {'-'*7}")
    for name, data in all_results.items():
        print(f"  {name:<25s} {data['trades']:5d} {data['trades']/2:5.0f} ¥{data['net']:>+11,.0f} {data['avg_pf']:7.2f} {data['avg_dd']:6.1%}")
    print()


if __name__ == '__main__':
    main()
