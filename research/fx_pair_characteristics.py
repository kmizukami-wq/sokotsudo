#!/usr/bin/env python3
"""
FX通貨ペアの動きのクセ（特性）徹底研究
========================================
26通貨ペア × 27年間の日次終値データを統計分析
データ: ECB公式レート 1999-2026 (7005日)
"""

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# データロード & 派生ペア計算
# ============================================================
def load_data(path='research/data_fx_long.csv'):
    df = pd.read_csv(path, parse_dates=['date'])
    df.set_index('date', inplace=True)
    df = df.sort_index()
    # 派生ペア
    df['GBP/AUD'] = df['GBP/USD'] / df['AUD/USD']
    df['GBP/NZD'] = df['GBP/USD'] / df['NZD/USD']
    return df

def compute_returns(df):
    return np.log(df / df.shift(1)).dropna()

# ============================================================
# 手動実装の統計関数
# ============================================================
def _autocorr(x, lag):
    x = x[~np.isnan(x)]
    n = len(x)
    if n < lag + 10:
        return np.nan
    xm = x - np.mean(x)
    c0 = np.sum(xm ** 2)
    if c0 == 0:
        return 0.0
    ck = np.sum(xm[lag:] * xm[:-lag])
    return ck / c0

def _skewness(x):
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return np.nan
    m = np.mean(x)
    s = np.std(x, ddof=1)
    if s == 0:
        return 0.0
    return np.mean(((x - m) / s) ** 3)

def _kurtosis(x):
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 4:
        return np.nan
    m = np.mean(x)
    s = np.std(x, ddof=1)
    if s == 0:
        return 0.0
    return np.mean(((x - m) / s) ** 4) - 3

def hurst_exponent(series, max_lag=100):
    ts = series.dropna().values
    if len(ts) < max_lag * 2:
        return np.nan
    lags = [int(l) for l in np.logspace(0.7, np.log10(max_lag), 15).astype(int)]
    lags = sorted(set(l for l in lags if l >= 2))
    rs_list = []
    for lag in lags:
        n_chunks = len(ts) // lag
        if n_chunks < 1:
            continue
        rs_vals = []
        for i in range(n_chunks):
            chunk = ts[i * lag:(i + 1) * lag]
            m = np.mean(chunk)
            cumdev = np.cumsum(chunk - m)
            R = np.max(cumdev) - np.min(cumdev)
            S = np.std(chunk, ddof=1)
            if S > 0:
                rs_vals.append(R / S)
        if rs_vals:
            rs_list.append((np.log(lag), np.log(np.mean(rs_vals))))
    if len(rs_list) < 3:
        return np.nan
    x = np.array([r[0] for r in rs_list])
    y = np.array([r[1] for r in rs_list])
    coeffs = np.polyfit(x, y, 1)
    return coeffs[0]

def variance_ratio(returns, period=5):
    r = returns.dropna().values
    n = len(r)
    if n < period * 2:
        return np.nan
    var1 = np.var(r, ddof=1)
    if var1 == 0:
        return 1.0
    k_returns = []
    for i in range(0, n - period + 1, period):
        k_returns.append(np.sum(r[i:i + period]))
    var_k = np.var(k_returns, ddof=1)
    return var_k / (period * var1)

# ============================================================
# スクリーンショット対象ペアリスト（ZAR/JPY除外）
# ============================================================
TARGET_PAIRS = [
    'EUR/USD', 'USD/JPY', 'EUR/JPY', 'GBP/USD', 'GBP/JPY',
    'AUD/JPY', 'NZD/JPY', 'CHF/JPY', 'USD/CHF', 'AUD/USD',
    'EUR/GBP', 'NZD/USD', 'USD/CAD', 'CAD/JPY', 'AUD/CHF',
    'EUR/AUD', 'AUD/NZD', 'EUR/CAD', 'EUR/CHF', 'GBP/AUD',
    'AUD/CAD', 'EUR/NZD', 'GBP/CAD', 'GBP/CHF', 'GBP/NZD',
]
# 注: ZAR/JPYはECBデータに含まれないため除外

# ============================================================
# メイン
# ============================================================
def main():
    df = load_data()
    returns = compute_returns(df)
    years = (df.index[-1] - df.index[0]).days / 365.25

    print("=" * 80)
    print("  FX通貨ペアの動きのクセ（特性）徹底研究")
    print(f"  データ: {df.index[0].date()} ~ {df.index[-1].date()} ({years:.1f}年, {len(df)}日)")
    print(f"  対象: {len(TARGET_PAIRS)}通貨ペア（ZAR/JPYはデータなし除外）")
    print("=" * 80)

    available = [p for p in TARGET_PAIRS if p in df.columns]
    missing = [p for p in TARGET_PAIRS if p not in df.columns]
    if missing:
        print(f"\n  ※ データなし: {', '.join(missing)}")

    # ──────────────────────────────────────────────
    # Section 1: 基本統計量
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  1. 基本統計量（日次対数リターン）")
    print("=" * 80)
    print(f"\n  {'Pair':<10} {'N':>5} {'平均bp':>7} {'Std%':>7} {'年率Vol':>8} {'歪度':>7} {'尖度':>7} {'最小%':>7} {'最大%':>7}")
    print(f"  {'-'*72}")

    stats_data = {}
    for pair in available:
        r = returns[pair].dropna().values
        n = len(r)
        mean_r = np.mean(r)
        std_r = np.std(r, ddof=1)
        ann_vol = std_r * np.sqrt(252)
        skew = _skewness(r)
        kurt = _kurtosis(r)
        mn = np.min(r)
        mx = np.max(r)
        stats_data[pair] = {
            'n': n, 'mean_bp': mean_r * 10000, 'std_pct': std_r * 100,
            'ann_vol': ann_vol * 100, 'skew': skew, 'kurt': kurt,
            'min_pct': mn * 100, 'max_pct': mx * 100
        }
        print(f"  {pair:<10} {n:>5} {mean_r*10000:>+7.2f} {std_r*100:>7.4f} {ann_vol*100:>7.2f}% {skew:>+7.3f} {kurt:>7.2f} {mn*100:>+7.3f} {mx*100:>+7.3f}")

    # ボラティリティランキング
    sorted_vol = sorted(stats_data.items(), key=lambda x: x[1]['ann_vol'], reverse=True)
    print(f"\n  【ボラティリティランキング（年率）】")
    for i, (pair, s) in enumerate(sorted_vol):
        bar = "#" * int(s['ann_vol'] / 0.5)
        print(f"  {i+1:>2}. {pair:<10} {s['ann_vol']:>6.2f}% {bar}")

    # 尖度ランキング（ファットテール）
    sorted_kurt = sorted(stats_data.items(), key=lambda x: x[1]['kurt'], reverse=True)
    print(f"\n  【尖度ランキング（テールリスク）】正規分布=0, 高い=ファットテール")
    for i, (pair, s) in enumerate(sorted_kurt[:10]):
        print(f"  {i+1:>2}. {pair:<10} {s['kurt']:>6.2f}")

    # ──────────────────────────────────────────────
    # Section 2: 自己相関分析
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  2. 自己相関分析（モメンタム vs 平均回帰の傾向）")
    print("=" * 80)
    n_sample = len(returns[available[0]].dropna())
    sig_threshold = 2.0 / np.sqrt(n_sample)
    print(f"  95%有意水準: |AC| > {sig_threshold:.4f}")
    print(f"\n  {'Pair':<10} {'AR(1)':>8} {'AR(2)':>8} {'AR(3)':>8} {'AR(4)':>8} {'AR(5)':>8} {'傾向':>10}")
    print(f"  {'-'*66}")

    ac_data = {}
    for pair in available:
        r = returns[pair].dropna().values
        sig = 2.0 / np.sqrt(len(r))
        acs = [_autocorr(r, lag) for lag in range(1, 6)]
        ac_data[pair] = acs

        # 傾向判定
        ar1 = acs[0]
        if ar1 > sig:
            tendency = "モメンタム"
        elif ar1 < -sig:
            tendency = "平均回帰"
        else:
            tendency = "ランダム"

        marks = ['*' if abs(a) > sig else ' ' for a in acs]
        print(f"  {pair:<10} {acs[0]:>+8.4f}{marks[0]} {acs[1]:>+7.4f}{marks[1]} {acs[2]:>+7.4f}{marks[2]} {acs[3]:>+7.4f}{marks[3]} {acs[4]:>+7.4f}{marks[4]} {tendency:>10}")

    print(f"\n  * = 95%有意")
    print(f"\n  【解釈】")
    print(f"  - AR(1)が有意に正 → 昨日上がれば今日も上がりやすい（モメンタム/トレンド）")
    print(f"  - AR(1)が有意に負 → 昨日上がれば今日は下がりやすい（平均回帰/逆張り有効）")

    # ──────────────────────────────────────────────
    # Section 3: ボラティリティクラスタリング
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  3. ボラティリティクラスタリング（大きな動きの後に大きな動きが来るか）")
    print("=" * 80)
    print(f"\n  二乗リターンの自己相関 = GARCH効果の代理指標")
    print(f"\n  {'Pair':<10} {'AC(1)':>8} {'AC(5)':>8} {'AC(10)':>8} {'AC(20)':>8} {'強度':>8}")
    print(f"  {'-'*54}")

    for pair in available:
        r = returns[pair].dropna().values
        r2 = r ** 2
        ac1 = _autocorr(r2, 1)
        ac5 = _autocorr(r2, 5)
        ac10 = _autocorr(r2, 10)
        ac20 = _autocorr(r2, 20)
        if ac1 > 0.15:
            strength = "強い"
        elif ac1 > 0.08:
            strength = "中程度"
        else:
            strength = "弱い"
        print(f"  {pair:<10} {ac1:>8.4f} {ac5:>8.4f} {ac10:>8.4f} {ac20:>8.4f} {strength:>8}")

    print(f"\n  【解釈】値が高いほどボラティリティが持続する（暴落後に連続して大きく動く）")

    # ──────────────────────────────────────────────
    # Section 4: トレンド vs 平均回帰（ハースト指数 & 分散比）
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  4. トレンド vs 平均回帰の傾向（ハースト指数 & 分散比検定）")
    print("=" * 80)
    print(f"  ハースト指数: H>0.5=トレンド, H=0.5=ランダム, H<0.5=平均回帰")
    print(f"  分散比VR(5): VR>1=トレンド, VR=1=ランダム, VR<1=平均回帰")
    print(f"\n  {'Pair':<10} {'Hurst':>7} {'VR(5)':>7} {'VR(10)':>7} {'VR(20)':>7} {'分類':>12}")
    print(f"  {'-'*58}")

    hurst_data = {}
    for pair in available:
        r = returns[pair].dropna()
        h = hurst_exponent(r)
        vr5 = variance_ratio(r, 5)
        vr10 = variance_ratio(r, 10)
        vr20 = variance_ratio(r, 20)
        hurst_data[pair] = {'hurst': h, 'vr5': vr5, 'vr10': vr10, 'vr20': vr20}

        if h < 0.45:
            cat = "平均回帰"
        elif h > 0.55:
            cat = "トレンド"
        else:
            cat = "ランダム"
        print(f"  {pair:<10} {h:>7.3f} {vr5:>7.3f} {vr10:>7.3f} {vr20:>7.3f} {cat:>12}")

    # 分類サマリー
    mr_pairs = [p for p, d in hurst_data.items() if d['hurst'] < 0.45]
    tr_pairs = [p for p, d in hurst_data.items() if d['hurst'] > 0.55]
    rw_pairs = [p for p, d in hurst_data.items() if 0.45 <= d['hurst'] <= 0.55]
    print(f"\n  【分類サマリー】")
    print(f"  平均回帰型 (H<0.45): {', '.join(mr_pairs) if mr_pairs else 'なし'}")
    print(f"  ランダム型 (0.45-0.55): {', '.join(rw_pairs) if rw_pairs else 'なし'}")
    print(f"  トレンド型 (H>0.55): {', '.join(tr_pairs) if tr_pairs else 'なし'}")

    # ──────────────────────────────────────────────
    # Section 5: 曜日効果
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  5. 曜日効果（曜日ごとのリターン傾向）")
    print("=" * 80)
    day_names = {0: '月', 1: '火', 2: '水', 3: '木', 4: '金'}

    print(f"\n  各ペアの曜日別平均リターン (bp) と有意性")
    for pair in available:
        r = returns[pair].dropna()
        r_idx = r.copy()
        r_idx.index = pd.to_datetime(r_idx.index)
        overall_mean = r_idx.mean()
        overall_std = r_idx.std()

        print(f"\n  {pair}:")
        print(f"  {'曜日':>4} {'平均bp':>8} {'Std%':>8} {'勝率':>6} {'N':>6} {'有意':>4}")
        sig_days = []
        for dow in range(5):
            day_r = r_idx[r_idx.index.dayofweek == dow]
            if len(day_r) == 0:
                continue
            m = day_r.mean()
            s = day_r.std()
            wr = (day_r > 0).mean() * 100
            n = len(day_r)
            t_stat = (m - overall_mean) / (s / np.sqrt(n)) if s > 0 else 0
            sig = "*" if abs(t_stat) > 1.96 else ""
            if sig:
                sig_days.append(day_names[dow])
            print(f"  {day_names[dow]:>4} {m*10000:>+8.2f} {s*100:>8.4f} {wr:>5.1f}% {n:>6} {sig:>4}")
        if sig_days:
            print(f"  → 有意な曜日効果: {', '.join(sig_days)}")

    # ──────────────────────────────────────────────
    # Section 6: 月次季節性
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  6. 月次季節性（月ごとの傾向）")
    print("=" * 80)
    month_names = {1:'1月',2:'2月',3:'3月',4:'4月',5:'5月',6:'6月',
                   7:'7月',8:'8月',9:'9月',10:'10月',11:'11月',12:'12月'}

    print(f"\n  各ペアの月別平均リターン(%) と勝率")
    for pair in available:
        r = returns[pair].dropna()
        r_idx = r.copy()
        r_idx.index = pd.to_datetime(r_idx.index)

        # 月次リターンを計算
        monthly = r_idx.resample('ME').sum()
        monthly_idx = monthly.copy()
        monthly_idx.index = pd.to_datetime(monthly_idx.index)

        print(f"\n  {pair}:")
        print(f"  {'月':>4} {'平均%':>8} {'勝率':>6} {'N':>4} {'傾向':>6}")
        strong_months = []
        for m in range(1, 13):
            month_data = monthly_idx[monthly_idx.index.month == m]
            if len(month_data) == 0:
                continue
            avg = month_data.mean() * 100
            wr = (month_data > 0).mean() * 100
            n = len(month_data)
            if wr >= 65:
                trend = "↑↑"
                strong_months.append(f"{month_names[m]}↑")
            elif wr <= 35:
                trend = "↓↓"
                strong_months.append(f"{month_names[m]}↓")
            elif wr >= 55:
                trend = "↑"
            elif wr <= 45:
                trend = "↓"
            else:
                trend = "→"
            print(f"  {month_names[m]:>4} {avg:>+8.3f} {wr:>5.1f}% {n:>4} {trend:>6}")
        if strong_months:
            print(f"  → 強い季節性: {', '.join(strong_months)}")

    # ──────────────────────────────────────────────
    # Section 7: 相関構造
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  7. 相関構造（ペア間のリターン相関）")
    print("=" * 80)

    avail_returns = returns[available].dropna()
    corr_matrix = avail_returns.corr()

    # 高相関ペア（Top 20）
    print(f"\n  【高相関ペア Top 20】相関 > 0.5")
    corr_pairs = []
    for i, p1 in enumerate(available):
        for j, p2 in enumerate(available):
            if i < j:
                c = corr_matrix.loc[p1, p2]
                corr_pairs.append((p1, p2, c))
    corr_pairs.sort(key=lambda x: abs(x[2]), reverse=True)

    print(f"  {'Pair 1':<10} {'Pair 2':<10} {'相関':>7} {'方向':>6}")
    print(f"  {'-'*36}")
    for p1, p2, c in corr_pairs[:20]:
        direction = "正" if c > 0 else "逆"
        print(f"  {p1:<10} {p2:<10} {c:>+7.3f} {direction:>6}")

    # 低相関ペア（分散効果が高い）
    print(f"\n  【低相関ペア Top 10】分散投資に有効")
    low_corr = [(p1, p2, c) for p1, p2, c in corr_pairs if abs(c) < 0.3]
    low_corr.sort(key=lambda x: abs(x[2]))
    for p1, p2, c in low_corr[:10]:
        print(f"  {p1:<10} {p2:<10} {c:>+7.3f}")

    # 相関クラスター
    print(f"\n  【相関クラスター】相関 > 0.6 のグループ")
    clusters = {}
    for p1, p2, c in corr_pairs:
        if abs(c) > 0.6:
            found = False
            for cid, members in clusters.items():
                if p1 in members or p2 in members:
                    members.add(p1)
                    members.add(p2)
                    found = True
                    break
            if not found:
                clusters[len(clusters)] = {p1, p2}
    for cid, members in clusters.items():
        print(f"  クラスター{cid+1}: {', '.join(sorted(members))}")

    # ──────────────────────────────────────────────
    # Section 8: 通貨ストレングス分析
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  8. 通貨ストレングス分析（個別通貨の強弱）")
    print("=" * 80)

    currencies = ['EUR', 'USD', 'JPY', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF']

    def parse_pair(pair):
        parts = pair.split('/')
        return parts[0], parts[1]

    # 全期間の平均ストレングス
    print(f"\n  【全期間平均ストレングス】")
    print(f"  通貨が買われる(=ペア上昇のBase側)とプラス")
    ccy_strength = {c: [] for c in currencies}
    for pair in available:
        base, quote = parse_pair(pair)
        r = returns[pair].dropna()
        mean_r = r.mean()
        if base in ccy_strength:
            ccy_strength[base].append(mean_r)
        if quote in ccy_strength:
            ccy_strength[quote].append(-mean_r)

    print(f"\n  {'通貨':>4} {'強弱(bp/日)':>12} {'ランク':>6}")
    print(f"  {'-'*26}")
    avg_strength = {c: np.mean(v) * 10000 if v else 0 for c, v in ccy_strength.items()}
    sorted_strength = sorted(avg_strength.items(), key=lambda x: x[1], reverse=True)
    for rank, (c, s) in enumerate(sorted_strength, 1):
        print(f"  {c:>4} {s:>+12.3f} {rank:>6}")

    # 年別通貨ストレングス
    print(f"\n  【年別通貨ストレングス (bp/日)】")
    year_list = sorted(returns.index.year.unique())
    print(f"  {'年':>6}", end="")
    for c in currencies:
        print(f" {c:>6}", end="")
    print()
    print(f"  {'-'*58}")

    for year in year_list:
        yr_returns = returns[returns.index.year == year]
        yr_strength = {}
        for c in currencies:
            vals = []
            for pair in available:
                base, quote = parse_pair(pair)
                r = yr_returns[pair].dropna()
                if len(r) == 0:
                    continue
                m = r.mean()
                if base == c:
                    vals.append(m)
                if quote == c:
                    vals.append(-m)
            yr_strength[c] = np.mean(vals) * 10000 if vals else 0
        print(f"  {year:>6}", end="")
        for c in currencies:
            v = yr_strength[c]
            print(f" {v:>+6.1f}", end="")
        print()

    # ──────────────────────────────────────────────
    # Section 9: レジーム検出
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  9. レジーム検出（リスクオン/リスクオフ）")
    print("=" * 80)

    jpy_pairs = [p for p in available if p.endswith('/JPY')]
    print(f"  JPYクロスペア: {', '.join(jpy_pairs)}")

    # JPY合成指数: 全X/JPYペアのリターン平均
    jpy_returns = returns[jpy_pairs].dropna(how='all')
    jpy_composite = jpy_returns.mean(axis=1)
    jpy_rolling = jpy_composite.rolling(20).mean()

    # レジーム判定
    risk_on = (jpy_rolling > 0).sum()
    risk_off = (jpy_rolling <= 0).sum()
    total = len(jpy_rolling.dropna())
    print(f"\n  リスクオン日数（JPY弱含み）: {risk_on} ({risk_on/total*100:.1f}%)")
    print(f"  リスクオフ日数（JPY強含み）: {risk_off} ({risk_off/total*100:.1f}%)")

    # レジーム別のペアパフォーマンス
    regime = pd.Series(np.where(jpy_rolling > 0, 1, -1), index=jpy_rolling.index)
    regime = regime.reindex(returns.index).dropna()

    print(f"\n  【レジーム別パフォーマンス (bp/日)】")
    print(f"  {'Pair':<10} {'RiskOn':>8} {'RiskOff':>8} {'差分':>8} {'優位レジーム':>14}")
    print(f"  {'-'*52}")

    for pair in available:
        r = returns[pair].reindex(regime.index).dropna()
        reg = regime.reindex(r.index).dropna()
        r = r.reindex(reg.index)

        on_r = r[reg == 1]
        off_r = r[reg == -1]
        if len(on_r) == 0 or len(off_r) == 0:
            continue
        on_m = on_r.mean() * 10000
        off_m = off_r.mean() * 10000
        diff = on_m - off_m
        better = "リスクオン" if diff > 0.5 else ("リスクオフ" if diff < -0.5 else "同等")
        print(f"  {pair:<10} {on_m:>+8.2f} {off_m:>+8.2f} {diff:>+8.2f} {better:>14}")

    # ──────────────────────────────────────────────
    # 総合プロファイル
    # ──────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  ★ 総合プロファイル（各ペアの動きのクセまとめ）")
    print("=" * 80)

    for pair in available:
        s = stats_data.get(pair, {})
        h = hurst_data.get(pair, {})
        ac = ac_data.get(pair, [0]*5)

        hval = h.get('hurst', 0.5)
        if hval < 0.45:
            type_str = "平均回帰型"
            strategy = "→ Z-score逆張りが有効"
        elif hval > 0.55:
            type_str = "トレンド型"
            strategy = "→ トレンドフォロー/ブレイクアウトが有効"
        else:
            type_str = "ランダム型"
            strategy = "→ ブレイクアウト戦略が有効"

        vol_rank = [p for p, _ in sorted_vol].index(pair) + 1

        print(f"\n  ── {pair} ──")
        print(f"  分類: {type_str} (H={hval:.3f})")
        print(f"  ボラティリティ: {s.get('ann_vol', 0):.2f}% (年率) [ランク: {vol_rank}/{len(available)}]")
        print(f"  自己相関AR(1): {ac[0]:+.4f} {'(有意)' if abs(ac[0]) > sig_threshold else ''}")
        print(f"  歪度: {s.get('skew', 0):+.3f}  尖度: {s.get('kurt', 0):.2f}")
        print(f"  {strategy}")

    print("\n\n[完了]")


if __name__ == '__main__':
    main()
