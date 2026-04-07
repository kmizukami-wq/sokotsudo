#!/usr/bin/env python3
"""
条件緩和バックテスト比較（FXTF 4ペア: AUDJPY, EURUSD, EURJPY, USDJPY）
現行条件 vs 緩和条件を並べて比較
"""

import numpy as np
import pandas as pd
import yfinance as yf
from collections import defaultdict

# ============================================================
# 共通パラメータ
# ============================================================
INITIAL_CAPITAL = 200_000   # 実運用に合わせて20万円
RISK_PER_TRADE = 0.008
RR_RATIO = 2.0
MARTIN_MULTIPLIERS = [1.0, 1.5, 2.0]
MAX_MARTIN_STAGE = 3
BE_TRIGGER_RR = 1.0
PARTIAL_CLOSE_RR = 1.5
PARTIAL_CLOSE_PCT = 0.5
TRAIL_ATR_MULT = 0.5
MAX_HOLDING_BARS = 20
MONTHLY_DD_LIMIT = -0.15
ANNUAL_DD_LIMIT = -0.20
TRADING_HOUR_START = 0   # UTC（日本時間9時〜）
TRADING_HOUR_END = 21    # UTC（日本時間6時まで）

SL_ATR_MULT = {
    'BB_reversal': 2.0,
    'Fast_BB': 1.8,
    'Pullback': 1.5,
}

# 4ペア（FXTF実運用中）
PAIRS = {
    'AUDJPY=X': {'name': 'AUD/JPY', 'pip': 0.01, 'spread_pips': 0.5, 'quote_to_jpy': 1.0},
    'EURUSD=X': {'name': 'EUR/USD', 'pip': 0.0001, 'spread_pips': 0.3, 'quote_to_jpy': 150.0},
    'EURJPY=X': {'name': 'EUR/JPY', 'pip': 0.01, 'spread_pips': 0.5, 'quote_to_jpy': 1.0},
    'USDJPY=X': {'name': 'USD/JPY', 'pip': 0.01, 'spread_pips': 0.3, 'quote_to_jpy': 1.0},
}

# ============================================================
# 条件セット定義
# ============================================================
CONDITIONS = {
    '現行': {
        'bb_sigma': 2.5,
        'fbb_sigma': 2.0,
        'rsi_bb_buy': 38, 'rsi_bb_sell': 62,
        'rsi_fbb_buy': 42, 'rsi_fbb_sell': 58,
        'rsi_pb_buy': (35, 45), 'rsi_pb_sell': (55, 65),
        'sma_gap_mult': 2.0,        # SMA gap >= ATR * 2.0
        'atr_filter_mult': 2.2,
    },
    '緩和A（RSI拡大）': {
        'bb_sigma': 2.5,
        'fbb_sigma': 2.0,
        'rsi_bb_buy': 42, 'rsi_bb_sell': 58,     # 38→42, 62→58
        'rsi_fbb_buy': 48, 'rsi_fbb_sell': 52,   # 42→48, 58→52
        'rsi_pb_buy': (30, 50), 'rsi_pb_sell': (50, 70),  # 幅を広げる
        'sma_gap_mult': 2.0,
        'atr_filter_mult': 2.2,
    },
    '緩和B（RSI+Gap緩和）': {
        'bb_sigma': 2.5,
        'fbb_sigma': 2.0,
        'rsi_bb_buy': 42, 'rsi_bb_sell': 58,
        'rsi_fbb_buy': 48, 'rsi_fbb_sell': 52,
        'rsi_pb_buy': (30, 50), 'rsi_pb_sell': (50, 70),
        'sma_gap_mult': 1.0,        # 2.0→1.0に緩和
        'atr_filter_mult': 2.5,     # 2.2→2.5に緩和
    },
    '緩和C（BB+RSI+Gap全緩和）': {
        'bb_sigma': 2.0,            # 2.5→2.0（BBタッチしやすく）
        'fbb_sigma': 1.5,           # 2.0→1.5
        'rsi_bb_buy': 45, 'rsi_bb_sell': 55,
        'rsi_fbb_buy': 48, 'rsi_fbb_sell': 52,
        'rsi_pb_buy': (30, 50), 'rsi_pb_sell': (50, 70),
        'sma_gap_mult': 1.0,
        'atr_filter_mult': 2.5,
    },
}


# ============================================================
# インジケーター計算（BB σを可変に）
# ============================================================
def calc_indicators(df, bb_sigma=2.5, fbb_sigma=2.0):
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


# ============================================================
# シグナル判定（条件パラメータを外部から受ける）
# ============================================================
def check_signals(row, prev_row, cond):
    close = row['Close']
    rsi = row['RSI']

    if pd.isna(row['ATR']) or pd.isna(row['ATR_MA100']):
        return None
    if row['ATR'] >= row['ATR_MA100'] * cond['atr_filter_mult']:
        return None

    hour = row.name.hour if hasattr(row.name, 'hour') else 0
    if hour < TRADING_HOUR_START or hour >= TRADING_HOUR_END:
        return None

    required = ['SMA200', 'SMA50', 'SMA20', 'BB_upper', 'BB_lower',
                'FBB_upper', 'FBB_lower', 'RSI', 'ATR']
    if any(pd.isna(row[k]) for k in required):
        return None
    if prev_row is not None and any(pd.isna(prev_row.get(k, np.nan)) for k in ['Close', 'BB_upper', 'BB_lower']):
        return None

    sma200_up = row['SMA200_up']

    # シグナル1: BB逆張り
    if prev_row is not None:
        prev_close = prev_row['Close']
        if sma200_up and prev_close <= prev_row['BB_lower'] and close > row['BB_lower'] and rsi < cond['rsi_bb_buy']:
            return ('BUY', 'BB_reversal')
        if not sma200_up and prev_close >= prev_row['BB_upper'] and close < row['BB_upper'] and rsi > cond['rsi_bb_sell']:
            return ('SELL', 'BB_reversal')

    # シグナル2: 高速BB
    sma50_up = row['SMA50_up']
    if sma200_up and sma50_up and close <= row['FBB_lower'] and rsi < cond['rsi_fbb_buy']:
        return ('BUY', 'Fast_BB')
    if not sma200_up and not sma50_up and close >= row['FBB_upper'] and rsi > cond['rsi_fbb_sell']:
        return ('SELL', 'Fast_BB')

    # シグナル3: 押し目
    sma20 = row['SMA20']
    sma50 = row['SMA50']
    atr = row['ATR']
    sma_gap = abs(sma20 - sma50)
    if sma_gap >= atr * cond['sma_gap_mult']:
        if sma200_up:
            lower_band = min(sma20, sma50)
            upper_band = max(sma20, sma50)
            pb_lo, pb_hi = cond['rsi_pb_buy']
            if lower_band <= close <= upper_band and pb_lo <= rsi <= pb_hi:
                return ('BUY', 'Pullback')
        if not sma200_up:
            lower_band = min(sma20, sma50)
            upper_band = max(sma20, sma50)
            pb_lo, pb_hi = cond['rsi_pb_sell']
            if lower_band <= close <= upper_band and pb_lo <= rsi <= pb_hi:
                return ('SELL', 'Pullback')

    return None


# ============================================================
# バックテストエンジン（簡略版）
# ============================================================
class RowProxy:
    def __init__(self, data, name):
        self._data = data
        self.name = name
    def __getitem__(self, key):
        return self._data[key]
    def get(self, key, default=None):
        return self._data.get(key, default)


def run_backtest(df, spread, quote_to_jpy, cond):
    capital = float(INITIAL_CAPITAL)
    peak = capital
    max_dd = 0.0
    position = None
    martin_stage = 0
    consecutive_losses = 0
    trades = []
    monthly_pnl = defaultdict(float)

    rows = df.to_dict('index')
    indices = list(rows.keys())

    for i in range(1, len(indices)):
        idx = indices[i]
        prev_idx = indices[i - 1]
        row = rows[idx]
        prev_row = rows[prev_idx]
        close = float(row['Close'])
        high = float(row['High'])
        low = float(row['Low'])
        month_key = f"{idx.year}-{idx.month:02d}"

        if position is not None:
            position['bars_held'] += 1
            closed = False
            pnl = 0.0
            result = ''
            sl = position['sl']
            tp = position['tp']
            entry = position['entry']
            lots = position['lots']
            direction = position['direction']
            sl_distance = position['sl_distance']

            if direction == 'BUY':
                unrealized = high - entry
                if not position['be_activated'] and unrealized >= sl_distance * BE_TRIGGER_RR:
                    position['be_activated'] = True
                    position['sl'] = entry + spread
                    sl = position['sl']
                if not position['partial_closed'] and unrealized >= sl_distance * PARTIAL_CLOSE_RR:
                    partial_pnl = (sl_distance * PARTIAL_CLOSE_RR - spread) * lots * PARTIAL_CLOSE_PCT * quote_to_jpy
                    capital += partial_pnl
                    monthly_pnl[month_key] += partial_pnl
                    position['partial_closed'] = True
                    position['partial_pnl'] = partial_pnl
                    position['lots'] = lots * (1 - PARTIAL_CLOSE_PCT)
                    lots = position['lots']
                    trail_sl = high - float(row['ATR']) * TRAIL_ATR_MULT
                    if trail_sl > sl:
                        position['sl'] = trail_sl
                        sl = trail_sl
                if position['partial_closed']:
                    trail_sl = high - float(row['ATR']) * TRAIL_ATR_MULT
                    if trail_sl > position['sl']:
                        position['sl'] = trail_sl
                        sl = position['sl']
                if low <= sl:
                    pnl = (sl - entry - spread) * lots * quote_to_jpy
                    closed = True
                    result = 'BE' if (position['be_activated'] and not position['partial_closed']) else ('TRAIL' if position['partial_closed'] else 'SL')
                elif high >= tp:
                    pnl = (tp - entry - spread) * lots * quote_to_jpy
                    closed = True
                    result = 'TP'
            else:
                unrealized = entry - low
                if not position['be_activated'] and unrealized >= sl_distance * BE_TRIGGER_RR:
                    position['be_activated'] = True
                    position['sl'] = entry - spread
                    sl = position['sl']
                if not position['partial_closed'] and unrealized >= sl_distance * PARTIAL_CLOSE_RR:
                    partial_pnl = (sl_distance * PARTIAL_CLOSE_RR - spread) * lots * PARTIAL_CLOSE_PCT * quote_to_jpy
                    capital += partial_pnl
                    monthly_pnl[month_key] += partial_pnl
                    position['partial_closed'] = True
                    position['partial_pnl'] = partial_pnl
                    position['lots'] = lots * (1 - PARTIAL_CLOSE_PCT)
                    lots = position['lots']
                    trail_sl = low + float(row['ATR']) * TRAIL_ATR_MULT
                    if trail_sl < sl:
                        position['sl'] = trail_sl
                        sl = trail_sl
                if position['partial_closed']:
                    trail_sl = low + float(row['ATR']) * TRAIL_ATR_MULT
                    if trail_sl < position['sl']:
                        position['sl'] = trail_sl
                        sl = position['sl']
                if high >= sl:
                    pnl = (entry - sl - spread) * lots * quote_to_jpy
                    closed = True
                    result = 'BE' if (position['be_activated'] and not position['partial_closed']) else ('TRAIL' if position['partial_closed'] else 'SL')
                elif low <= tp:
                    pnl = (entry - tp - spread) * lots * quote_to_jpy
                    closed = True
                    result = 'TP'

            if not closed and position['bars_held'] >= MAX_HOLDING_BARS:
                if direction == 'BUY':
                    pnl = (close - entry - spread) * lots * quote_to_jpy
                else:
                    pnl = (entry - close - spread) * lots * quote_to_jpy
                closed = True
                result = 'TIME'

            if closed:
                total_pnl = pnl + position.get('partial_pnl', 0)
                capital += pnl
                monthly_pnl[month_key] += pnl
                trades.append({'pnl': total_pnl, 'result': result, 'signal': position['signal']})
                if result == 'SL':
                    consecutive_losses += 1
                    if consecutive_losses >= MAX_MARTIN_STAGE:
                        martin_stage = 0
                        consecutive_losses = 0
                    else:
                        martin_stage = min(consecutive_losses, MAX_MARTIN_STAGE - 1)
                else:
                    consecutive_losses = 0
                    martin_stage = 0
                position = None
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak
                if dd > max_dd:
                    max_dd = dd

            if position is not None:
                continue

        row_p = RowProxy(row, idx)
        prev_p = RowProxy(prev_row, prev_idx)
        signal = check_signals(row_p, prev_p, cond)
        if signal is None:
            continue

        direction, signal_type = signal
        atr = float(row['ATR'])
        sl_mult = SL_ATR_MULT.get(signal_type, 1.5)
        sl_distance = atr * sl_mult
        tp_distance = sl_distance * RR_RATIO

        if direction == 'BUY':
            entry_price = close + spread / 2
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            entry_price = close - spread / 2
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        risk_amount = capital * RISK_PER_TRADE * MARTIN_MULTIPLIERS[martin_stage]
        if sl_distance <= 0:
            continue
        lots = risk_amount / (sl_distance * quote_to_jpy)

        position = {
            'direction': direction, 'entry': entry_price, 'sl': sl_price,
            'tp': tp_price, 'sl_distance': sl_distance, 'lots': lots,
            'signal': signal_type, 'stage': martin_stage,
            'bars_held': 0, 'be_activated': False, 'partial_closed': False, 'partial_pnl': 0,
        }

    return trades, capital, monthly_pnl, max_dd


# ============================================================
# メイン
# ============================================================
def main():
    print("=" * 90)
    print("  条件緩和バックテスト比較（FXTF 4ペア・15分足・60日）")
    print("  初期資金: ¥{:,.0f}".format(INITIAL_CAPITAL))
    print("=" * 90)

    # quote_to_jpy動的取得
    try:
        usdjpy = yf.download('USDJPY=X', period='1d', interval='1d', progress=False)
        if isinstance(usdjpy.columns, pd.MultiIndex):
            usdjpy.columns = usdjpy.columns.get_level_values(0)
        usdjpy_rate = float(usdjpy['Close'].iloc[-1])
        PAIRS['EURUSD=X']['quote_to_jpy'] = usdjpy_rate
        print(f"  USD/JPY rate: {usdjpy_rate:.1f}")
    except:
        pass

    # データ一括取得
    print("\n>>> データ取得中...")
    data_cache = {}
    for ticker, cfg in PAIRS.items():
        try:
            df = yf.download(ticker, period='60d', interval='15m', progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            data_cache[ticker] = df
            print(f"  {cfg['name']}: {len(df)}本")
        except Exception as e:
            print(f"  {cfg['name']}: Error - {e}")

    # 各条件セットでバックテスト
    all_results = {}

    for cond_name, cond in CONDITIONS.items():
        print(f"\n{'#'*90}")
        print(f"  {cond_name}")
        print(f"  BB={cond['bb_sigma']}σ  FBB={cond['fbb_sigma']}σ  "
              f"RSI_BB<{cond['rsi_bb_buy']}/>{ cond['rsi_bb_sell']}  "
              f"RSI_PB={cond['rsi_pb_buy']}  Gap≥ATR*{cond['sma_gap_mult']}  "
              f"ATR_filt={cond['atr_filter_mult']}")
        print(f"{'#'*90}")

        pair_results = []
        all_trades_merged = []

        for ticker, cfg in PAIRS.items():
            if ticker not in data_cache:
                continue
            df = data_cache[ticker].copy()
            df = calc_indicators(df, bb_sigma=cond['bb_sigma'], fbb_sigma=cond['fbb_sigma'])
            spread = cfg['spread_pips'] * cfg['pip']
            q2j = cfg['quote_to_jpy']

            trades, final_cap, monthly_pnl, max_dd = run_backtest(df, spread, q2j, cond)

            total = len(trades)
            if total > 0:
                wins = sum(1 for t in trades if t['pnl'] > 0)
                gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
                gl = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
                pf = gp / gl if gl > 0 else float('inf')
                net = final_cap - INITIAL_CAPITAL

                # シグナル別内訳
                sig_counts = defaultdict(int)
                for t in trades:
                    sig_counts[t['signal']] += 1

                pair_results.append({
                    'pair': cfg['name'], 'trades': total, 'win_rate': wins/total*100,
                    'pf': pf, 'max_dd': max_dd, 'net': net,
                    'sig': dict(sig_counts),
                })
                all_trades_merged.extend(trades)
            else:
                pair_results.append({
                    'pair': cfg['name'], 'trades': 0, 'win_rate': 0,
                    'pf': 0, 'max_dd': 0, 'net': 0, 'sig': {},
                })

        # ペア別サマリー
        print(f"\n  {'ペア':<10s} {'取引数':>5s} {'月換算':>5s} {'勝率':>6s} {'PF':>6s} {'DD':>6s} {'純損益':>11s}  {'BB':>3s} {'FBB':>3s} {'PB':>3s}")
        print(f"  {'-'*10} {'-'*5} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*11}  {'-'*3} {'-'*3} {'-'*3}")
        total_net = 0
        total_trades = 0
        for r in sorted(pair_results, key=lambda x: x['pf'], reverse=True):
            monthly = r['trades'] / 2  # 60日≒2ヶ月
            bb = r['sig'].get('BB_reversal', 0)
            fbb = r['sig'].get('Fast_BB', 0)
            pb = r['sig'].get('Pullback', 0)
            print(f"  {r['pair']:<10s} {r['trades']:5d} {monthly:5.0f} {r['win_rate']:5.1f}% {r['pf']:6.2f} {r['max_dd']:5.1%} ¥{r['net']:>+10,.0f}  {bb:3d} {fbb:3d} {pb:3d}")
            total_net += r['net']
            total_trades += r['trades']

        all_results[cond_name] = {
            'trades': total_trades,
            'net': total_net,
            'pairs': pair_results,
        }

        print(f"\n  合計: {total_trades}件  純損益 ¥{total_net:>+,.0f}  (月換算 {total_trades/2:.0f}件)")

    # ============================================================
    # 最終比較テーブル
    # ============================================================
    print(f"\n{'='*90}")
    print(f"  条件セット比較サマリー")
    print(f"{'='*90}")
    print(f"  {'条件セット':<25s} {'取引数':>5s} {'月換算':>5s} {'合計損益':>12s} {'Avg PF':>7s} {'Avg DD':>7s}")
    print(f"  {'-'*25} {'-'*5} {'-'*5} {'-'*12} {'-'*7} {'-'*7}")

    for cond_name, data in all_results.items():
        prs = [p for p in data['pairs'] if p['trades'] > 0]
        avg_pf = np.mean([p['pf'] for p in prs]) if prs else 0
        avg_dd = np.mean([p['max_dd'] for p in prs]) if prs else 0
        monthly = data['trades'] / 2
        print(f"  {cond_name:<25s} {data['trades']:5d} {monthly:5.0f} ¥{data['net']:>+11,.0f} {avg_pf:7.2f} {avg_dd:6.1%}")

    print()


if __name__ == '__main__':
    main()
