#!/usr/bin/env python3
"""
BB_Reversal_Martin vs ZscoreScalper 比較バックテスト
同一の実データ(Yahoo M15 ~3ヶ月)で両EAの成績を比較
"""
import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 500000

# ============= BB_Reversal_Martin パラメータ =============
BB_RISK_PCT=0.8; BB_RR=2.0; BE_TRIGGER_RR=1.0; PARTIAL_RR=1.5; PARTIAL_PCT=0.5
TRAIL_ATR_MULT=0.5; BB_MAX_HOLD=20; MARTIN=[1.0,1.5,2.0]
BB_SL_MULTS={1:2.0,2:1.8,3:1.5}; ATR_FILTER_MULT=2.5

# ============= ZscoreScalper パラメータ =============
Z_WINDOW=30; Z_ENTRY=0.51; Z_EXIT=0.5; Z_STOP=6.0
Z_TIMEOUT_BARS=8  # 2h / 15min = 8 bars
Z_TP_PIPS=15; Z_SL_PIPS=15; Z_LOT=0.1
Z_SPREAD_PIPS=0.0  # FXTFは1万通貨(0.1lot)まで スプレッド 0

FXTF_PAIRS = {
    "EURUSD":{"t":"EURUSD=X","sp":0.3},"USDJPY":{"t":"USDJPY=X","sp":0.3},
    "EURJPY":{"t":"EURJPY=X","sp":0.5},"GBPUSD":{"t":"GBPUSD=X","sp":0.7},
    "GBPJPY":{"t":"GBPJPY=X","sp":0.7},"AUDJPY":{"t":"AUDJPY=X","sp":0.5},
    "NZDJPY":{"t":"NZDJPY=X","sp":0.8},"ZARJPY":{"t":"ZARJPY=X","sp":1.5},
    "CHFJPY":{"t":"CHFJPY=X","sp":1.5},"USDCHF":{"t":"USDCHF=X","sp":1.5},
    "AUDUSD":{"t":"AUDUSD=X","sp":0.5},"EURGBP":{"t":"EURGBP=X","sp":1.0},
    "NZDUSD":{"t":"NZDUSD=X","sp":1.0},"USDCAD":{"t":"USDCAD=X","sp":1.5},
    "CADJPY":{"t":"CADJPY=X","sp":1.5},"AUDCHF":{"t":"AUDCHF=X","sp":2.0},
    "EURAUD":{"t":"EURAUD=X","sp":1.5},"AUDNZD":{"t":"AUDNZD=X","sp":2.0},
    "EURCAD":{"t":"EURCAD=X","sp":2.0},"EURCHF":{"t":"EURCHF=X","sp":1.5},
    "GBPAUD":{"t":"GBPAUD=X","sp":2.0},"AUDCAD":{"t":"AUDCAD=X","sp":2.0},
    "EURNZD":{"t":"EURNZD=X","sp":2.5},"GBPCAD":{"t":"GBPCAD=X","sp":2.5},
    "GBPCHF":{"t":"GBPCHF=X","sp":2.0},"GBPNZD":{"t":"GBPNZD=X","sp":3.0},
}

def pcfg(name,sp):
    # tick_value: 1.0lot (100,000通貨)あたりの1pip=JPY
    # JPYペア: 100,000×0.01=1000円/pip
    # USD系: 100,000×0.0001×USDJPY(~150)=1500円/pip
    # その他: 100,000×0.0001×quote_rate≈1000-1500円/pip → 1200で近似
    j=name.endswith("JPY")
    if j:
        tv=1000
    elif name in("EURUSD","GBPUSD","AUDUSD","NZDUSD"):
        tv=1500  # USD quote
    else:
        tv=1200  # 他のクロス（概算）
    return{"pip":0.01 if j else 0.0001,"pip_mult":100 if j else 10000,
            "spread":sp,"tick_value":tv}

def fetch(ticker):
    df=yf.download(ticker,period="60d",interval="15m",progress=False)
    if df.empty:return None
    df=df.droplevel("Ticker",axis=1) if isinstance(df.columns,pd.MultiIndex) else df
    df=df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"})
    df=df[["open","high","low","close"]].dropna()
    df["time"]=df.index;df=df.reset_index(drop=True)
    return df

def calc_ind_bb(df):
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
    # Z-score
    zm=c.rolling(Z_WINDOW).mean();zs=c.rolling(Z_WINDOW).std()
    df["zscore"]=(c-zm)/zs.replace(0,np.nan)
    return df.dropna().reset_index(drop=True)

# ============= BB_Reversal_Martin バックテスト =============
def check_bb_sig(row,prev):
    if row["atr14"]>=row["atr14_ma100"]*ATR_FILTER_MULT:return 0
    c1,c2,rsi=row["close"],prev["close"],row["rsi"]
    u2,u5=row["sma200_up"],row["sma50_up"]
    if u2 and c2<=prev["bb_lower"] and c1>row["bb_lower"] and rsi<42:return 1
    if not u2 and c2>=prev["bb_upper"] and c1<row["bb_upper"] and rsi>58:return -1
    if u2 and u5 and c1<=row["fbb_lower"] and rsi<48:return 2
    if not u2 and not u5 and c1>=row["fbb_upper"] and rsi>52:return -2
    gap=abs(row["sma20"]-row["sma50"])
    if gap>=row["atr14"]*2:
        lo,hi=min(row["sma20"],row["sma50"]),max(row["sma20"],row["sma50"])
        if u2 and lo<=c1<=hi and 30<=rsi<=50:return 3
        if not u2 and lo<=c1<=hi and 50<=rsi<=70:return -3
    return 0

def run_bb(df,cfg):
    pm=cfg["pip_mult"];tv=cfg["tick_value"];pu=cfg["pip"]
    eq=float(INITIAL_EQUITY);ep=eq;mdd=0.0;mseq=eq
    ms=0;cl=0;trades=[];monthly=[];cm=None
    i=1
    while i<len(df)-BB_MAX_HOLD-1:
        row=df.iloc[i];prev=df.iloc[i-1]
        rm=pd.to_datetime(row["time"]).month
        if cm is None:cm=rm;mseq=eq
        elif rm!=cm:monthly.append({"m":cm,"p":(eq-mseq)/mseq*100});cm=rm;mseq=eq
        sig=check_bb_sig(row,prev)
        if sig==0:i+=1;continue
        d=1 if sig>0 else -1;st=abs(sig);atr=row["atr14"]
        sld=atr*BB_SL_MULTS.get(st,1.5);tpd=sld*BB_RR;spd=cfg["spread"]*pu
        ep_=row["close"];ra=eq*BB_RISK_PCT/100.0;mm=MARTIN[min(ms,2)]
        sp=sld*pm
        if sp<=0:i+=1;continue
        lots=max(0.01,int((ra*mm)/(sp*tv)/0.01)*0.01)
        slp=ep_-d*sld;tpp=ep_+d*tpd
        be=False;pc=False;rl=lots;rp=0.0;res="timeout";eb=i;pnl=0.0;to=False
        for j in range(1,BB_MAX_HOLD+1):
            if i+j>=len(df):break
            b=df.iloc[i+j];ba=b["atr14"] if not np.isnan(b["atr14"]) else atr
            if d==1:
                if not be and(b["high"]-ep_)>=sld*BE_TRIGGER_RR:slp=ep_+spd;be=True
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
                if not be and(ep_-b["low"])>=sld*BE_TRIGGER_RR:slp=ep_-spd;be=True
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
            ex=df.iloc[min(i+BB_MAX_HOLD,len(df)-1)]["close"]
            pnl=d*(ex-ep_)*pm*rl*tv+rp;to=True
        pnl-=cfg["spread"]*tv*lots
        if to or res=="BE":cl=0;ms=0
        elif pnl<0:
            cl+=1
            if cl>=3:ms=0;cl=0
            else:ms=min(cl,2)
        else:cl=0;ms=0
        eq+=pnl;ep=max(ep,eq);dd=(ep-eq)/ep*100 if ep>0 else 0;mdd=max(mdd,dd)
        trades.append({"result":res,"pnl":pnl})
        i=eb+1
    if mseq>0 and cm is not None:monthly.append({"m":cm,"p":(eq-mseq)/mseq*100})
    return trades,mdd,monthly,eq

# ============= ZscoreScalper バックテスト =============
def run_zscore(df,cfg):
    pm=cfg["pip_mult"];tv=cfg["tick_value"];pu=cfg["pip"]
    tp_dist=Z_TP_PIPS*pu;sl_dist=Z_SL_PIPS*pu
    eq=float(INITIAL_EQUITY);ep=eq;mdd=0.0;mseq=eq
    trades=[];monthly=[];cm=None
    i=Z_WINDOW
    while i<len(df)-Z_TIMEOUT_BARS-1:
        row=df.iloc[i]
        rm=pd.to_datetime(row["time"]).month
        if cm is None:cm=rm;mseq=eq
        elif rm!=cm:monthly.append({"m":cm,"p":(eq-mseq)/mseq*100});cm=rm;mseq=eq
        z=row["zscore"]
        if np.isnan(z) or z==0:i+=1;continue
        # Entry
        if abs(z)<=Z_ENTRY:i+=1;continue
        d=-1 if z>Z_ENTRY else 1  # z>0.51→SHORT, z<-0.51→LONG
        ep_=row["close"]
        sl_price=ep_-d*sl_dist
        tp_price=ep_+d*tp_dist
        lots=Z_LOT
        res="timeout";eb=i;pnl=0.0
        # Exit loop
        for j in range(1,Z_TIMEOUT_BARS+1):
            if i+j>=len(df):break
            b=df.iloc[i+j]
            if d==1:  # LONG
                if b["low"]<=sl_price:pnl=-sl_dist*pm*lots*tv;res="SL";eb=i+j;break
                if b["high"]>=tp_price:pnl=tp_dist*pm*lots*tv;res="TP";eb=i+j;break
                # Zscore exit
                z2=b["zscore"]
                if not np.isnan(z2):
                    if z2>-Z_EXIT or z2<-Z_STOP:
                        pnl=(b["close"]-ep_)*pm*lots*tv;res="Zexit";eb=i+j;break
            else:  # SHORT
                if b["high"]>=sl_price:pnl=-sl_dist*pm*lots*tv;res="SL";eb=i+j;break
                if b["low"]<=tp_price:pnl=tp_dist*pm*lots*tv;res="TP";eb=i+j;break
                z2=b["zscore"]
                if not np.isnan(z2):
                    if z2<Z_EXIT or z2>Z_STOP:
                        pnl=(ep_-b["close"])*pm*lots*tv;res="Zexit";eb=i+j;break
        else:
            ex=df.iloc[min(i+Z_TIMEOUT_BARS,len(df)-1)]["close"]
            pnl=d*(ex-ep_)*pm*lots*tv
        pnl-=Z_SPREAD_PIPS*tv*lots  # FXTF 1万通貨まで spread=0
        eq+=pnl;ep=max(ep,eq);dd=(ep-eq)/ep*100 if ep>0 else 0;mdd=max(mdd,dd)
        trades.append({"result":res,"pnl":pnl})
        i=eb+1
    if mseq>0 and cm is not None:monthly.append({"m":cm,"p":(eq-mseq)/mseq*100})
    return trades,mdd,monthly,eq

def summarize(trades,mdd,monthly,final_eq):
    if not trades:return None
    dt=pd.DataFrame(trades);n=len(dt)
    w=dt[dt["pnl"]>0];l=dt[dt["pnl"]<=0]
    wr=len(w)/n*100;tp=dt["pnl"].sum()
    gw=w["pnl"].sum() if len(w)>0 else 0;gl=abs(l["pnl"].sum()) if len(l)>0 else 0
    pf=gw/gl if gl>0 else float("inf")
    mm=pd.DataFrame(monthly)["p"].median() if monthly else 0
    return{"n":n,"wr":wr,"pnl":tp,"pf":pf,"dd":mdd,"mm":mm,"final":final_eq}

def main():
    print("="*110)
    print("EA比較バックテスト: BB_Reversal_Martin vs ZscoreScalper")
    print(f"初期資金: ¥{INITIAL_EQUITY:,} | M15実データ約3ヶ月 (Yahoo Finance)")
    print("="*110)

    results={}
    for pn,info in FXTF_PAIRS.items():
        cfg=pcfg(pn,info["sp"])
        print(f"  {pn}...",end=" ",flush=True)
        df=fetch(info["t"])
        if df is None or len(df)<300:print("SKIP");continue
        df=calc_ind_bb(df)
        # BB_Reversal_Martin
        tr1,dd1,mo1,eq1=run_bb(df,cfg)
        s1=summarize(tr1,dd1,mo1,eq1)
        # ZscoreScalper
        tr2,dd2,mo2,eq2=run_zscore(df,cfg)
        s2=summarize(tr2,dd2,mo2,eq2)
        results[pn]={"bb":s1,"z":s2,"sp":info["sp"]}
        b1=f"PF={s1['pf']:.2f}" if s1 else "無"
        b2=f"PF={s2['pf']:.2f}" if s2 else "無"
        print(f"BB:{b1} Z:{b2}")

    # 結果テーブル
    print(f"\n{'='*110}")
    print(f"  【通貨ペア別 EA成績比較】")
    print(f"{'='*110}")
    print(f"  {'ペア':>7s} {'SP':>4s} │ {'BB_PF':>5s} {'BB勝率':>6s} {'BB_DD':>6s} {'BB損益':>11s} {'BB月利':>6s} {'BB_N':>4s} │ {'Z_PF':>5s} {'Z勝率':>6s} {'Z_DD':>5s} {'Z損益':>11s} {'Z月利':>6s} {'Z_N':>5s} │ {'勝者'}")
    print(f"  {'-'*108}")

    bb_wins=0;z_wins=0;tie=0
    bb_total=0;z_total=0
    for pn,r in results.items():
        sp=r["sp"];s1=r["bb"];s2=r["z"]
        if s1 and s2:
            pf1=f"{s1['pf']:.2f}" if s1['pf']<100 else "∞"
            pf2=f"{s2['pf']:.2f}" if s2['pf']<100 else "∞"
            pnl1=f"+¥{s1['pnl']:,.0f}" if s1['pnl']>=0 else f"-¥{abs(s1['pnl']):,.0f}"
            pnl2=f"+¥{s2['pnl']:,.0f}" if s2['pnl']>=0 else f"-¥{abs(s2['pnl']):,.0f}"
            bb_total+=s1['pnl'];z_total+=s2['pnl']
            if s1['pnl']>s2['pnl']:winner="BB";bb_wins+=1
            elif s2['pnl']>s1['pnl']:winner="Zscore";z_wins+=1
            else:winner="-";tie+=1
            print(f"  {pn:>7s} {sp:>4.1f} │ {pf1:>5s} {s1['wr']:>5.1f}% {s1['dd']:>5.1f}% {pnl1:>11s} {s1['mm']:>+5.1f}% {s1['n']:>4d} │ {pf2:>5s} {s2['wr']:>5.1f}% {s2['dd']:>4.1f}% {pnl2:>11s} {s2['mm']:>+5.1f}% {s2['n']:>5d} │ {winner}")

    print(f"  {'-'*108}")
    print(f"  合計損益:  BB=¥{bb_total:+,.0f}   Zscore=¥{z_total:+,.0f}")
    print(f"  勝敗:      BB={bb_wins}勝  Zscore={z_wins}勝  引分={tie}")

    # 推奨ペア（両EA）
    print(f"\n{'='*110}")
    print(f"  【EA別 推奨ペア（PF≥1.1 & DD<15%）】")
    print(f"{'='*110}")
    bb_ok=[pn for pn,r in results.items() if r["bb"] and r["bb"]["pf"]>=1.1 and r["bb"]["dd"]<15]
    z_ok=[pn for pn,r in results.items() if r["z"] and r["z"]["pf"]>=1.1 and r["z"]["dd"]<15]
    print(f"  BB_Reversal_Martin: {', '.join(bb_ok) if bb_ok else 'なし'}")
    print(f"  ZscoreScalper:      {', '.join(z_ok) if z_ok else 'なし'}")
    print(f"\n  BB 合計ペア: {len(bb_ok)} / Zscore合計: {len(z_ok)}")

main()
