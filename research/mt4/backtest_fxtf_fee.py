#!/usr/bin/env python3
"""
BB_Reversal_Martin FXTF手数料込みバックテスト
PDF記載の建玉連動手数料体系に基づき、ペア別のRank1無料枠を考慮
"""
import numpy as np
import pandas as pd
import yfinance as yf

# EA パラメータ
RISK_PCT=0.8; RR_RATIO=2.0; BE_TRIGGER_RR=1.0; PARTIAL_RR=1.5; PARTIAL_PCT=0.5
TRAIL_ATR_MULT=0.5; MAX_HOLD_BARS=20; MARTIN=[1.0,1.5,2.0]
SL_MULTS={1:2.0,2:1.8,3:1.5}; ATR_FILTER_MULT=2.5
INITIAL_EQUITY=500000

# FXTF手数料体系（PDF記載）
# (Rank1無料枠通貨数, Rank2手数料円/1万通貨)
FXTF_FEE = {
    "USDJPY":(10000, 40), "EURJPY":(10000, 60), "EURUSD":(10000, 60),
    "AUDJPY":(10000, 60), "GBPJPY":(10000, 80),
    "GBPUSD":( 5000,100), "AUDUSD":( 5000, 70),
    "NZDJPY":( 3000, 70), "CADJPY":( 3000, 60), "USDCAD":( 3000,120),
    "ZARJPY":( 1000, 70), "EURAUD":( 1000,220), "NZDUSD":( 1000,150),
    "EURGBP":( 1000,180), "GBPAUD":( 1000,240), "AUDNZD":( 1000,120),
    "CHFJPY":( 1000,180), "USDCHF":( 1000,100), "EURNZD":( 1000,290),
    "GBPCAD":( 1000,210), "AUDCHF":( 1000,200), "EURCAD":( 1000,170),
    "EURCHF":( 1000,220), "GBPNZD":( 1000,290), "GBPCHF":( 1000,300),
    "AUDCAD":( 1000,180),
}

# プレミアムペア (Rank1=1万通貨): 0.1lot上限
PREMIUM_PAIRS = {"USDJPY","EURJPY","EURUSD","AUDJPY","GBPJPY"}
# ただし EURJPY/EURUSD もランク1=1万通貨だが、スプレッド環境で扱いを揃える
# ここでは "ユーザー指定: USDJPY/GBPJPY/AUDJPY" に限定
USER_PREMIUM = {"USDJPY","EURJPY","EURUSD","AUDJPY","GBPJPY"}

FXTF_PAIRS_TICKERS = {
    "EURUSD":"EURUSD=X","USDJPY":"USDJPY=X","EURJPY":"EURJPY=X","GBPUSD":"GBPUSD=X",
    "GBPJPY":"GBPJPY=X","AUDJPY":"AUDJPY=X","NZDJPY":"NZDJPY=X","ZARJPY":"ZARJPY=X",
    "CHFJPY":"CHFJPY=X","USDCHF":"USDCHF=X","AUDUSD":"AUDUSD=X","EURGBP":"EURGBP=X",
    "NZDUSD":"NZDUSD=X","USDCAD":"USDCAD=X","CADJPY":"CADJPY=X","AUDCHF":"AUDCHF=X",
    "EURAUD":"EURAUD=X","AUDNZD":"AUDNZD=X","EURCAD":"EURCAD=X","EURCHF":"EURCHF=X",
    "GBPAUD":"GBPAUD=X","AUDCAD":"AUDCAD=X","EURNZD":"EURNZD=X","GBPCAD":"GBPCAD=X",
    "GBPCHF":"GBPCHF=X","GBPNZD":"GBPNZD=X",
}

def pcfg(name):
    j=name.endswith("JPY")
    if j:tv=1000
    elif name in("EURUSD","GBPUSD","AUDUSD","NZDUSD"):tv=1500
    else:tv=1200
    return{"pip":0.01 if j else 0.0001,"pip_mult":100 if j else 10000,"tick_value":tv}

def fetch(ticker):
    df=yf.download(ticker,period="60d",interval="15m",progress=False)
    if df.empty:return None
    df=df.droplevel("Ticker",axis=1) if isinstance(df.columns,pd.MultiIndex) else df
    df=df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"})
    df=df[["open","high","low","close"]].dropna()
    df["time"]=df.index;df=df.reset_index(drop=True)
    return df

def calc_ind(df):
    c=df["close"]
    df["sma200"]=c.rolling(200).mean();df["sma50"]=c.rolling(50).mean();df["sma20"]=c.rolling(20).mean()
    df["sma200_up"]=df["sma200"]>df["sma200"].shift(5);df["sma50_up"]=df["sma50"]>df["sma50"].shift(5)
    d=c.diff();g=d.clip(lower=0).ewm(span=10,adjust=False).mean()
    l=(-d.clip(upper=0)).ewm(span=10,adjust=False).mean()
    df["rsi"]=100-(100/(1+g/l.replace(0,np.nan)))
    tr=pd.concat([df["high"]-df["low"],(df["high"]-c.shift(1)).abs(),(df["low"]-c.shift(1)).abs()],axis=1).max(axis=1)
    df["atr14"]=tr.rolling(14).mean();df["atr14_ma100"]=df["atr14"].rolling(100).mean()
    bm=c.rolling(20).mean();bs=c.rolling(20).std()
    df["bb_upper"]=bm+2.5*bs;df["bb_lower"]=bm-2.5*bs
    fm=c.rolling(10).mean();fs=c.rolling(10).std()
    df["fbb_upper"]=fm+2.0*fs;df["fbb_lower"]=fm-2.0*fs
    return df.dropna().reset_index(drop=True)

def check_sig(row,prev):
    if row["atr14"]>=row["atr14_ma100"]*ATR_FILTER_MULT:return 0
    c1,c2,o1,rsi=row["close"],prev["close"],row["open"],row["rsi"]
    u2,u5=row["sma200_up"],row["sma50_up"]
    if u2 and c2<=prev["bb_lower"] and c1>row["bb_lower"] and c1>o1 and rsi<42:return 1
    if not u2 and c2>=prev["bb_upper"] and c1<row["bb_upper"] and c1<o1 and rsi>58:return -1
    if u2 and u5 and c1<=row["fbb_lower"] and rsi<48:return 2
    if not u2 and not u5 and c1>=row["fbb_upper"] and rsi>52:return -2
    gap=abs(row["sma20"]-row["sma50"])
    if gap>=row["atr14"]*2:
        lo,hi=min(row["sma20"],row["sma50"]),max(row["sma20"],row["sma50"])
        if u2 and lo<=c1<=hi and 30<=rsi<=50:return 3
        if not u2 and lo<=c1<=hi and 50<=rsi<=70:return -3
    return 0

def calc_fee(pair,lots):
    """FXTF建玉連動手数料: lots → 円
    ランクに入った瞬間に全体にレート適用（階段式ではなく定額レート）
    例 EURGBP Rank2=180円/1万通貨:
      1,000通貨  → 0円 (rank1)
      2,000通貨  → 36円 (rank2: 2000/10000*180)
      10,000通貨 → 180円 (rank2: 10000/10000*180)
    """
    if pair not in FXTF_FEE:return 0
    rank1,r2=FXTF_FEE[pair]
    units=lots*100000  # 1.0lot=100,000通貨
    if units<=rank1:return 0  # rank1 無料
    return units/10000*r2     # rank2: 全体にレート適用

def run_bt(df,cfg,pair,mode):
    """
    mode:
      'all_0.1_cap'      : 全ペア0.1lot上限
      'premium_only_cap' : USDJPY/GBPJPY/AUDJPYのみ0.1cap、他は無制限
      'no_cap'           : 全ペア上限なし（リスク%そのまま）
    """
    pm=cfg["pip_mult"];tv=cfg["tick_value"];pu=cfg["pip"]
    eq=float(INITIAL_EQUITY);ep=eq;mdd=0.0;mseq=eq
    ms=0;cl=0;trades=[];monthly=[];cm=None
    i=1

    # 上限決定
    if mode=="all_0.1_cap":
        max_lot=0.1
    elif mode=="premium_only_cap":
        max_lot=0.1 if pair in USER_PREMIUM else 100.0
    else:  # no_cap
        max_lot=100.0

    while i<len(df)-MAX_HOLD_BARS-1:
        row=df.iloc[i];prev=df.iloc[i-1]
        rm=pd.to_datetime(row["time"]).month
        if cm is None:cm=rm;mseq=eq
        elif rm!=cm:monthly.append({"m":cm,"p":(eq-mseq)/mseq*100});cm=rm;mseq=eq
        sig=check_sig(row,prev)
        if sig==0:i+=1;continue
        d=1 if sig>0 else -1;st=abs(sig);atr=row["atr14"]
        sld=atr*SL_MULTS.get(st,1.5);tpd=sld*RR_RATIO
        ep_=row["close"];mm=MARTIN[min(ms,2)]

        # リスク%ベースのロット計算（上限でcap）
        ra=eq*RISK_PCT/100.0
        sp_pips=sld*pm
        if sp_pips<=0:i+=1;continue
        raw=(ra*mm)/(sp_pips*tv)
        lots=max(0.01,int(raw/0.01)*0.01)
        lots=min(lots,max_lot)

        # エントリー時のスプレッド = 手数料から概算（双方向なので×2）
        fee=calc_fee(pair,lots)  # エントリー手数料 (片道)

        slp=ep_-d*sld;tpp=ep_+d*tpd
        be=False;pc=False;rl=lots;rp=0.0;res="timeout";eb=i;pnl=0.0;to=False
        for j in range(1,MAX_HOLD_BARS+1):
            if i+j>=len(df):break
            b=df.iloc[i+j];ba=b["atr14"] if not np.isnan(b["atr14"]) else atr
            if d==1:
                if not be and(b["high"]-ep_)>=sld*BE_TRIGGER_RR:slp=ep_;be=True  # 完全BE (手数料別計算)
                if not pc and(b["high"]-ep_)>=sld*PARTIAL_RR:
                    cl_=round(rl*PARTIAL_PCT,2)
                    if cl_>=0.01 and(rl-cl_)>=0.01:
                        rp+=(sld*PARTIAL_RR)*pm*cl_*tv;rl=round(rl-cl_,2);pc=True
                        ts=ep_+sld*PARTIAL_RR-ba*TRAIL_ATR_MULT
                        if ts>slp:slp=ts
                if pc:
                    ts=b["high"]-ba*TRAIL_ATR_MULT
                    if ts>slp:slp=ts
                if b["low"]<=slp:pnl=(slp-ep_)*pm*rl*tv+rp;res="BE" if be else "SL";eb=i+j;break
                if b["high"]>=tpp:pnl=tpd*pm*rl*tv+rp;res="TP";eb=i+j;break
            else:
                if not be and(ep_-b["low"])>=sld*BE_TRIGGER_RR:slp=ep_;be=True
                if not pc and(ep_-b["low"])>=sld*PARTIAL_RR:
                    cl_=round(rl*PARTIAL_PCT,2)
                    if cl_>=0.01 and(rl-cl_)>=0.01:
                        rp+=(sld*PARTIAL_RR)*pm*cl_*tv;rl=round(rl-cl_,2);pc=True
                        ts=ep_-sld*PARTIAL_RR+ba*TRAIL_ATR_MULT
                        if ts<slp:slp=ts
                if pc:
                    ts=b["low"]+ba*TRAIL_ATR_MULT
                    if ts<slp:slp=ts
                if b["high"]>=slp:pnl=(ep_-slp)*pm*rl*tv+rp;res="BE" if be else "SL";eb=i+j;break
                if b["low"]<=tpp:pnl=tpd*pm*rl*tv+rp;res="TP";eb=i+j;break
        else:
            ex=df.iloc[min(i+MAX_HOLD_BARS,len(df)-1)]["close"]
            pnl=d*(ex-ep_)*pm*rl*tv+rp;to=True

        # 手数料控除（エントリー + 決済の往復）
        total_fee=calc_fee(pair,lots)+calc_fee(pair,lots+(lots-rl))  # 部分利確分も考慮した往復
        # 簡易: 片道手数料 × 2 × (部分利確なら1.5倍)
        fee_round=fee*2 if not pc else fee*2 + calc_fee(pair,lots*PARTIAL_PCT)
        pnl-=fee_round

        if to or res=="BE":cl=0;ms=0
        elif pnl<0:
            cl+=1
            if cl>=3:ms=0;cl=0
            else:ms=min(cl,2)
        else:cl=0;ms=0
        eq+=pnl;ep=max(ep,eq);dd=(ep-eq)/ep*100 if ep>0 else 0;mdd=max(mdd,dd)
        trades.append({"result":res,"pnl":pnl,"lots":lots,"fee":fee_round})
        i=eb+1
    if mseq>0 and cm is not None:monthly.append({"m":cm,"p":(eq-mseq)/mseq*100})
    return trades,mdd,monthly,eq

def summarize(trades,mdd,monthly):
    if not trades:return None
    dt=pd.DataFrame(trades);n=len(dt)
    w=dt[dt["pnl"]>0];l=dt[dt["pnl"]<=0]
    wr=len(w)/n*100;tp=dt["pnl"].sum()
    gw=w["pnl"].sum() if len(w)>0 else 0;gl=abs(l["pnl"].sum()) if len(l)>0 else 0
    pf=gw/gl if gl>0 else float("inf")
    mm=pd.DataFrame(monthly)["p"].median() if monthly else 0
    avg_lot=dt["lots"].mean()
    total_fee=dt["fee"].sum()
    return{"n":n,"wr":wr,"pnl":tp,"pf":pf,"dd":mdd,"mm":mm,"lot":avg_lot,"fee":total_fee}

def main():
    print("="*110)
    print("BB_Reversal_Martin FXTF手数料込みバックテスト")
    print(f"初期: ¥{INITIAL_EQUITY:,} | リスク: {RISK_PCT}% | 手数料モデル: PDF2026年3月2日")
    print(f"プレミアムペア(0.1cap適用): {', '.join(USER_PREMIUM)}")
    print("="*110)

    all_data={}
    for pn,ticker in FXTF_PAIRS_TICKERS.items():
        print(f"  {pn:>8s}... ",end="",flush=True)
        df=fetch(ticker)
        if df is None or len(df)<300:print("SKIP");continue
        df=calc_ind(df)
        all_data[pn]=df
        print(f"{len(df)} bars")

    modes=[
        ("全ペア 0.1cap",       "all_0.1_cap"),
        ("Rank1=1万ペア5つのみ 0.1cap", "premium_only_cap"),
        ("全ペア 無制限",       "no_cap"),
    ]

    results={}
    for mode_name,mode_key in modes:
        print(f"\n[モード: {mode_name}]")
        for pn,df in all_data.items():
            cfg=pcfg(pn)
            tr,dd,mo,eq=run_bt(df,cfg,pn,mode_key)
            s=summarize(tr,dd,mo)
            results.setdefault(pn,{})[mode_name]=s

    # 3モード比較テーブル
    mode_keys=[m[0] for m in modes]
    print(f"\n{'='*110}")
    print(f"  【3モード比較: 純損益 (手数料込み, 3ヶ月)】")
    print(f"{'='*110}")
    header=f"  {'ペア':>7s}  {'Rank1':>7s}"+"".join(f"  {k:>26s}" for k in mode_keys)
    print(header)
    print(f"  {'-'*(17+28*len(mode_keys))}")
    totals={k:0 for k in mode_keys}
    for pn in all_data:
        rank1=FXTF_FEE.get(pn,(0,0))[0]
        row=f"  {pn:>7s}  {rank1:>6,}通"
        for k in mode_keys:
            s=results[pn][k]
            if s:
                row+=f"   PF{s['pf']:>4.2f} {s['pnl']:>+9,.0f} Lot{s['lot']:.2f}"
                totals[k]+=s["pnl"]
            else:
                row+=f"   {'---':>26s}"
        print(row)
    print(f"  {'-'*(17+28*len(mode_keys))}")
    tr=f"  {'合計':>7s}         "
    for k in mode_keys:tr+=f"   {'':>9s}{totals[k]:>+9,.0f}         "
    print(tr)

    # サマリー
    print(f"\n{'='*110}")
    print(f"  【全体サマリー】")
    print(f"{'='*110}")
    print(f"  {'モード':>32s}  {'合計損益(¥)':>13s}  {'月利中央値合計':>14s}  {'+ペア数':>8s}  {'平均lot':>7s}  {'総手数料':>11s}")
    print(f"  {'-'*95}")
    for mn,_ in modes:
        vals=[results[pn][mn] for pn in all_data if results[pn][mn]]
        if not vals:continue
        tot=sum(v["pnl"] for v in vals)
        mm=sum(v["mm"] for v in vals)
        plus=sum(1 for v in vals if v["pnl"]>0)
        avg_lot=sum(v["lot"] for v in vals)/len(vals)
        tot_fee=sum(v["fee"] for v in vals)
        print(f"  {mn:>32s}  {tot:>+12,.0f}  {mm:>+13.1f}%  {plus:>6d}/26  {avg_lot:>6.3f}  {tot_fee:>+10,.0f}")

    # プラス収支ペアのみ合算で月利試算
    print(f"\n{'='*110}")
    print(f"  【プラス収支ペアのみ採用した場合の想定月利】")
    print(f"{'='*110}")
    print(f"  {'モード':>32s}  {'採用ペア数':>10s}  {'3ヶ月損益':>14s}  {'月利合算':>10s}  {'月次絶対額':>14s}")
    print(f"  {'-'*90}")
    for mn,_ in modes:
        plus=[results[pn][mn] for pn in all_data if results[pn][mn] and results[pn][mn]["pnl"]>0]
        if not plus:continue
        n=len(plus);pnl=sum(v["pnl"] for v in plus);mm=sum(v["mm"] for v in plus)
        abs_m=INITIAL_EQUITY*mm/100
        print(f"  {mn:>32s}  {n:>8d}/26  {pnl:>+13,.0f}  {mm:>+9.1f}%  {abs_m:>+13,.0f}")

    # 推奨モードの提示
    print(f"\n{'='*110}")
    print(f"  【プレミアム3ペアのみ 0.1cap モードの詳細】")
    print(f"{'='*110}")
    print(f"  {'ペア':>7s}  {'タイプ':>6s}  {'平均lot':>7s}  {'PF':>5s}  {'勝率':>6s}  {'純損益':>11s}  {'月利中央':>7s}  {'手数料':>10s}")
    print(f"  {'-'*80}")
    key="Rank1=1万ペア5つのみ 0.1cap"
    for pn in all_data:
        s=results[pn][key]
        if not s:continue
        ptype="★無料" if pn in USER_PREMIUM else "▼有料"
        print(f"  {pn:>7s}  {ptype:>6s}  {s['lot']:>6.3f}  {s['pf']:>5.2f}  {s['wr']:>5.1f}%  {s['pnl']:>+10,.0f}  {s['mm']:>+6.1f}%  {s['fee']:>+9,.0f}")

main()
