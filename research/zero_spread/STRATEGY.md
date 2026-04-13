# FXTF ゼロスプレッド・スキャルピング戦略仕様

## 1. 目的

FXTF (FX Trade Financial) のゼロスプレッドキャンペーン時間帯 (USD/JPY, EUR/USD, EUR/JPY 等の主要ペアで spread が 0.0pip 提示される時間) を **構造的優位性** として活用し、通常 spread 下では破綻する「1-3pip を狙う超短期トレード」を **正の期待値** で運用する。

「勘」「マーチンゲール」「無根拠ナンピン」を排し、**統計的エントリー条件 + 明示的リスク管理 + バックテスト検証** で意思決定を完結させる。

---

## 2. なぜゼロスプレッドが Edge になるか

USD/JPY を例に、TP=2.5pip / SL=2.0pip / 想定勝率 58% で:

```
gross EV = 0.58 × 2.5 − 0.42 × 2.0 = +0.61 pip / trade
通常 spread (往復 0.4pip) 込み: +0.21 pip   ← 際どい / スリッページで負け
ゼロスプレッド時:               +0.61 pip   ← 約 3 倍
```

1日 10-20 トレード × 0.4pip × 月20営業日 = **月 80-160pip 純益**。
通常 spread では月 0-40pip となり、運用コストや税控除でほぼ利益が出ない。

→ **「spread 0.0 を前提にしないと EV ≤ 0 となるロジック」を意図的に組む** ことで、
ゼロスプレッドという市場構造的な歪みそのものが収益源となる。これがバックテスト
の **spread 感度分析** で可視化される (spread 0.0pip → +EV、0.4pip → ≤ 0 EV)。

---

## 3. 対象

| 項目 | 値 |
|---|---|
| 通貨ペア | USD/JPY, EUR/USD, EUR/JPY |
| 時間軸 | 1分足 |
| セッション (JST) | 東京寄付 09:00-10:30 / ロンドン寄付 16:00-17:30 / NY寄付 21:30-23:00 |
| トレード回数上限 | ペアあたり 10 / 日 |
| 同時保有上限 | ペアあたり 1、合計 3 |

セッション選定理由: ゼロスプレッドキャンペーンが提供されやすい時間帯と
重なり、同時に流動性が高く再帰性 (オーバーシュート → 平均回帰) が
出やすい時間帯。

---

## 4. エントリー条件 (1分足、すべて AND)

1. 現在時刻が **FXTF ゼロスプレッド時間帯** (config) かつ **対象セッション** 内
2. 直近 20 本の終値で `μ`, `σ` を算出し `|close − μ| > 2.0 × σ`
3. その 1分足の **wick 比率 ≥ 60%**
   - SHORT 候補なら upper wick / range ≥ 0.6
   - LONG 候補なら lower wick / range ≥ 0.6
4. 直近 5 分 ATR が 20 日 5 分 ATR 中央値の `[0.3×, 1.2×]` レンジ内
   (凪すぎ / 暴騰中を除外)
5. ニュースブラックアウト窓 (BOJ / FOMC / NFP の ±3 分) 外
6. 当日同ペアのトレード回数 < `max_trades_day` (=10)
7. 現在ポジション保有なし

**方向**: `close > μ + 2σ` → SHORT、`close < μ − 2σ` → LONG (extension を fade)

---

## 5. エグジット

| 条件 | 動作 |
|---|---|
| 価格が `μ` (中心線) に到達 | 利益確定 |
| 価格が +2.5 pip 達成 (どちらが先でも) | 利益確定 |
| 価格が SL を逆抜け | 損切り |
| 30 本 (=30 分) 経過 | 時間切れ成行決済 |
| キルスイッチ発火 | 即決済 |

**SL 計算**: `SL_pips = clip(1.5 × ATR(1min,14), 2.0, 4.0)`

---

## 6. ポジションサイジング

```
risk_jpy   = equity_jpy × risk_pct        # risk_pct = 0.5%
lot_units  = floor( risk_jpy / (sl_pips × pip_value_jpy_per_1k) / 1000 ) × 1000
```

- USD/JPY: pip = 0.01、1k 通貨あたり pip 価値 ≒ ¥100
- EUR/JPY: pip = 0.01、1k 通貨あたり pip 価値 ≒ ¥100
- EUR/USD: pip = 0.0001、1k 通貨あたり pip 価値 ≒ USD/JPY × 0.10 円

固定割合方式 (Kelly 上限付き)。複利は equity 再計算で表現。

---

## 7. リスク管理 / キルスイッチ

| 条件 | 挙動 |
|---|---|
| 同時保有数 | ペアあたり 1、合計 3 |
| 日次損失 ≤ −2% | 当日全停止 |
| ピーク資産比 ≤ −6% DD | 戦略全停止、手動再アーム |
| 5分 ATR > 3× 20日中央値 | エントリースキップ (フラッシュ/ニュース回避) |
| ライブ spread > 0.1pip | 停止 (キャンペーン終了検知 — 本実装スコープ外) |

---

## 8. バックテスト設計

- データ: Twelve Data 1分足 USD/JPY / EUR/USD / EUR/JPY、2024-01 → 2026-03 (24か月)
- 約定: シグナル発生バーの **次バー始値** + `slippage_pips` (0.2pip / 片側)
- ポジション保有中は同一バー内で SL → TP の順に判定 (保守的)
- 複利モデル: `equity *= (1 + pnl_fraction)` (既存 `research/backtest_zscore_all.py` と同形)

### 受入ゲート (3 ペア合算)

| 指標 | 閾値 |
|---|---|
| 勝率 | ≥ 55% |
| 期待値 (slip 0.2pip 控除済 / spread 0.0pip) | ≥ +0.4 pip / trade |
| MaxDD | ≤ 8% |
| サンプル数 | ≥ 300 trades |
| **spread 0.4pip 想定 EV** | **≤ 0 (キャンペーン依存性の証明)** |

### 感度分析

`spread_assumption_pips ∈ {0.0, 0.2, 0.4, 0.6}` で再実行し EV 曲線を出力。
**0.0 で +EV、0.4 で ≤ 0 EV** という単調減少カーブが描けて初めて
「ゼロスプレッドという構造を logic で活かしている」と立証できる。

---

## 9. 検証手順

```bash
cd /home/user/sokotsudo
python -m pytest research/zero_spread/tests/ -v
python -m research.zero_spread.fetch_1min --pair USD/JPY \
       --from 2024-01-01 --to 2026-03-31 \
       --config research/zero_spread/config.example.json
python -m research.zero_spread.backtest \
       --config research/zero_spread/config.example.json \
       --out research/zero_spread/results/
# → results/summary.md と results/spread_sensitivity.md を確認
```

---

## 10. 本仕様で意識的に「やらないこと」

- マーチンゲール / ナンピン
- 含み損ホールド (時間切れで必ず決済)
- ニュース直撃トレード (3分ブラックアウト)
- spread 0.4pip 以上の通常時間帯運用 (キルスイッチで停止)
- ゼロカット前提のフルレバ (risk_pct 0.5% 固定)
- 過剰最適化を防ぐため walk-forward (train 2024 / test 2025) で再評価
