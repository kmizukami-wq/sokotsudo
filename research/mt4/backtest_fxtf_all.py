#!/usr/bin/env python3
"""BB_Reversal_Martin: FXTF全26通貨ペア バックテスト"""
import numpy as np
import pandas as pd
import yfinance as yf

RISK_PCT=0.8; RR_RATIO=2.0; BE_TRIGGER_RR=1.0; PARTIAL_RR=1.5; PARTIAL_PCT=0.5
TRAIL_ATR_MULT=0.5; MAX_HOLD_BARS=20; MARTIN=[1.0,1.5,2.0]
SL_MULTS={1:2.0,2:1.8,3:1.5}; ATR_FILTER_MULT=2.5; INITIAL_EQUITY=500000

# pip/tick_value設定: JPYペア=pip0.01,mult100,tv100 / その他=pip0.0001,mult10000,tv150
FXTF_PAIRS = {
    "EURUSD":  {"t":"EURUSD=X","sp":0.3}, "USDJPY":  {"t":"USDJPY=X","sp":0.3},
    "EURJPY":  {"t":"EURJPY=X","sp":0.5}, "GBPUSD":  {"t":"GBPUSD=X","sp":0.7},
    "GBPJPY":  {"t":"GBPJPY=X","sp":0.7}, "AUDJPY":  {"t":"AUDJPY=X","sp":0.5},
    "NZDJPY":  {"t":"NZDJPY=X","sp":0.8}, "ZARJPY":  {"t":"ZARJPY=X","sp":1.5},
    "CHFJPY":  {"t":"CHFJPY=X","sp":1.5}, "USDCHF":  {"t":"USDCHF=X","sp":1.5},
    "AUDUSD":  {"t":"AUDUSD=X","sp":0.5}, "EURGBP":  {"t":"EURGBP=X","sp":1.0},
    "NZDUSD":  {"t":"NZDUSD=X","sp":1.0}, "USDCAD":  {"t":"USDCAD=X","sp":1.5},
    "CADJPY":  {"t":"CADJPY=X","sp":1.5}, "AUDCHF":  {"t":"AUDCHF=X","sp":2.0},
    "EURAUD":  {"t":"EURAUD=X","sp":1.5}, "AUDNZD":  {"t":"AUDNZD=X","sp":2.0},
    "EURCAD":  {"t":"EURCAD=X","sp":2.0}, "EURCHF":  {"t":"EURCHF=X","sp":1.5},
    "GBPAUD":  {"t":"GBPAUD=X","sp":2.0}, "AUDCAD":  {"t":"AUDCAD=X","sp":2.0},
    "EURNZD":  {"t":"EURNZD=X","sp":2.5}, "GBPCAD":  {"t":"GBPCAD=X","sp":2.5},
    "GBPCHF":  {"t":"GBPCHF=X","sp":2.0}, "GBPNZD":  {"t":"GBPNZD=X","sp":3.0},
}

def pair_cfg(name, sp):
    is_jpy = name.endswith("JPY")
    return {"pip":0.01 if is_jpy else 0.0001, "pip_mult":100 if is_jpy else 10000,
            "spread":sp, "tick_value":100 if is_jpy else 150}

def fetch(ticker):
    df = yf.download(ticker, period="60d", interval="15m", progress=False)
    if df.empty: return None
    df = df.droplevel("Ticker",axis=1) if isinstance(df.columns,pd.MultiIndex) else df
    df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"})
    df = df[["open","high","low","close"]].dropna()
    df["time"] = df.index; df = df.reset_index(drop=True)
    return df

def calc_ind(df):
    c=df["close"]
    df["sma200"]=c.rolling(200).mean(); df["sma50"]=c.rolling(50).mean(); df["sma20"]=c.rolling(20).mean()
    df["sma200_up"]=df["sma200"]>df["sma200"].shift(5); df["sma50_up"]=df["sma50"]>df["sma50"].shift(5)
    d=c.diff(); g=d.clip(lower=0).ewm(span=10,adjust=False).mean(); l=(-d.clip(upper=0)).ewm(span=10,adjust=False).mean()
    df["rsi"]=100-(100/(1+g/l.replace(0,np.nan)))
    tr=pd.concat([df["high"]-df["low"],(df["high"]-c.shift(1)).abs(),(df["low"]-c.shift(1)).abs()],axis=1).max(axis=1)
    df["atr14"]=tr.rolling(14).mean(); df["atr14_ma100"]=df["atr14"].rolling(100).mean()
    bm=c.rolling(20).mean(); bs=c.rolling(20).std()
    df["bb_upper"]=bm+2.5*bs; df["bb_lower"]=bm-2.5*bs
    fm=c.rolling(10).mean(); fs=c.rolling(10).std()
    df["fbb_upper"]=fm+2.0*fs; df["fbb_lower"]=fm-2.0*fs
    return df.dropna().reset_index(drop=True)

def check_sig(row,prev,enabled=(1,2,3)):
    if row["atr14"]>=row["atr14_ma100"]*ATR_FILTER_MULT: return 0
    c1,c2,rsi=row["close"],prev["close"],row["rsi"]
    u2,u5=row["sma200_up"],row["sma50_up"]
    if 1 in enabled:
        if u2 and c2<=prev["bb_lower"] and c1>row["bb_lower"] and rsi<42: return 1
        if not u2 and c2>=prev["bb_upper"] and c1<row["bb_upper"] and rsi>58: return -1
    if 2 in enabled:
        if u2 and u5 and c1<=row["fbb_lower"] and rsi<48: return 2
        if not u2 and not u5 and c1>=row["fbb_upper"] and rsi>52: return -2
    if 3 in enabled:
        gap=abs(row["sma20"]-row["sma50"])
        if gap>=row["atr14"]*2:
            lo,hi=min(row["sma20"],row["sma50"]),max(row["sma20"],row["sma50"])
            if u2 and lo<=c1<=hi and 30<=rsi<=50: return 3
            if not u2 and lo<=c1<=hi and 50<=rsi<=70: return -3
    return 0

def run_bt(df,cfg,enabled=(1,2,3)):
    pm=cfg["pip_mult"];tv=cfg["tick_value"];pu=cfg["pip"]
    eq=float(INITIAL_EQUITY);ep=eq;mdd=0.0;mseq=eq
    ms=0;cl=0;trades=[];monthly=[];cm=None
    i=1
    while i<len(df)-MAX_HOLD_BARS-1:
        row=df.iloc[i];prev=df.iloc[i-1]
        rm=pd.to_datetime(row["time"]).month
        if cm is None: cm=rm;mseq=eq
        elif rm!=cm:
            monthly.append({"month":cm,"pnl_pct":(eq-mseq)/mseq*100});cm=rm;mseq=eq
        sig=check_sig(row,prev,enabled=enabled)
        if sig==0: i+=1;continue
        d=1 if sig>0 else -1;st=abs(sig);atr=row["atr14"]
        slm=SL_MULTS.get(st,1.5);sld=atr*slm;tpd=sld*RR_RATIO;spd=cfg["spread"]*pu
        ep_=row["close"];ra=eq*RISK_PCT/100.0;mm=MARTIN[min(ms,2)]
        sp=sld*pm
        if sp<=0: i+=1;continue
        lots=max(0.01,int((ra*mm)/(sp*tv)/0.01)*0.01)
        slp=ep_-d*sld;tpp=ep_+d*tpd
        be=False;pc=False;rl=lots;rp=0.0;res="timeout";eb=i;pnl=0.0;to=False
        for j in range(1,MAX_HOLD_BARS+1):
            if i+j>=len(df):break
            b=df.iloc[i+j];ba=b["atr14"] if not np.isnan(b["atr14"]) else atr
            if d==1:
                if not be and (b["high"]-ep_)>=sld*BE_TRIGGER_RR: slp=ep_+spd;be=True
                if not pc and (b["high"]-ep_)>=sld*PARTIAL_RR:
                    cl_=round(rl*PARTIAL_PCT,2)
                    if cl_>=0.01 and(rl-cl_)>=0.01:
                        rp+=(ep_+sld*PARTIAL_RR-ep_)*pm*cl_*tv;rl=round(rl-cl_,2);pc=True
                        ts=ep_+sld*PARTIAL_RR-ba*TRAIL_ATR_MULT
                        if ts>slp:slp=ts
                if pc:
                    ts=b["high"]-ba*TRAIL_ATR_MULT
                    if ts>slp:slp=ts
                if b["low"]<=slp: pnl=(slp-ep_)*pm*rl*tv+rp;res="BE" if be else "SL";eb=i+j;break
                if b["high"]>=tpp: pnl=tpd*pm*rl*tv+rp;res="TP";eb=i+j;break
            else:
                if not be and (ep_-b["low"])>=sld*BE_TRIGGER_RR: slp=ep_-spd;be=True
                if not pc and (ep_-b["low"])>=sld*PARTIAL_RR:
                    cl_=round(rl*PARTIAL_PCT,2)
                    if cl_>=0.01 and(rl-cl_)>=0.01:
                        rp+=(ep_-(ep_-sld*PARTIAL_RR))*pm*cl_*tv;rl=round(rl-cl_,2);pc=True
                        ts=ep_-sld*PARTIAL_RR+ba*TRAIL_ATR_MULT
                        if ts<slp:slp=ts
                if pc:
                    ts=b["low"]+ba*TRAIL_ATR_MULT
                    if ts<slp:slp=ts
                if b["high"]>=slp: pnl=(ep_-slp)*pm*rl*tv+rp;res="BE" if be else "SL";eb=i+j;break
                if b["low"]<=tpp: pnl=tpd*pm*rl*tv+rp;res="TP";eb=i+j;break
        else:
            ex=df.iloc[min(i+MAX_HOLD_BARS,len(df)-1)]["close"]
            pnl=d*(ex-ep_)*pm*rl*tv+rp;to=True
        pnl-=cfg["spread"]*tv*lots
        if to or res=="BE": cl=0;ms=0
        elif pnl<0:
            cl+=1
            if cl>=3:ms=0;cl=0
            else:ms=min(cl,2)
        else:cl=0;ms=0
        eq+=pnl;ep=max(ep,eq);dd=(ep-eq)/ep*100 if ep>0 else 0;mdd=max(mdd,dd)
        trades.append({"result":res,"pnl":pnl,"be":be,"partial":pc})
        i=eb+1
    if mseq>0 and cm is not None:
        monthly.append({"month":cm,"pnl_pct":(eq-mseq)/mseq*100})
    return trades,mdd,monthly

def summarize(trades,mdd,monthly):
    if not trades:return None
    dt=pd.DataFrame(trades);n=len(dt)
    w=dt[dt["pnl"]>0];l=dt[dt["pnl"]<=0]
    wr=len(w)/n*100;tp=dt["pnl"].sum()
    gw=w["pnl"].sum() if len(w)>0 else 0;gl=abs(l["pnl"].sum()) if len(l)>0 else 0
    pf=gw/gl if gl>0 else float("inf")
    mm=pd.DataFrame(monthly)["pnl_pct"].median() if monthly else 0
    r=dt["result"].value_counts().to_dict()
    return{"n":n,"wr":wr,"pnl":tp,"pf":pf,"dd":mdd,"mm":mm,"r":r,"monthly":monthly}

def main():
    print("="*95)
    print("BB_Reversal_Martin: FXTF全26通貨ペア 実データバックテスト (M15, ~3ヶ月)")
    print(f"初期資金: ¥{INITIAL_EQUITY:,} | リスク: {RISK_PCT}% | RR: {RR_RATIO}")
    print("="*95)

    results=[]
    for pn,info in FXTF_PAIRS.items():
        cfg=pair_cfg(pn,info["sp"])
        print(f"  {pn:>8s}...",end=" ",flush=True)
        df=fetch(info["t"])
        if df is None or len(df)<300:print("SKIP");continue
        df=calc_ind(df)
        tr,dd,mo=run_bt(df,cfg)
        s=summarize(tr,dd,mo)
        if s:
            results.append({"pair":pn,"sp":info["sp"],**s})
            pf_s=f"{s['pf']:.2f}" if s['pf']<100 else "∞"
            print(f"N={s['n']:>3d} PF={pf_s:>5s} WR={s['wr']:.1f}% DD={s['dd']:.1f}% PnL={s['pnl']:+,.0f}")
        else:print("NO SIGNAL")

    if not results:print("No results");return
    df_r=pd.DataFrame(results).sort_values("pf",ascending=False)

    # メイン結果テーブル
    print(f"\n{'='*95}")
    print(f"  【全26通貨ペア 成績一覧】（PF降順）")
    print(f"{'='*95}")
    print(f"  {'ペア':>8s}  {'SP':>4s}  {'PF':>5s}  {'勝率':>6s}  {'最大DD':>7s}  {'純損益':>12s}  {'月利中央':>7s}  {'トレード':>6s}  {'決済内訳':>20s}  {'判定'}")
    print(f"  {'-'*95}")
    for _,r in df_r.iterrows():
        pf_s=f"{r['pf']:.2f}" if r['pf']<100 else "∞"
        pnl_s=f"+¥{r['pnl']:,.0f}" if r['pnl']>=0 else f"-¥{abs(r['pnl']):,.0f}"
        res=" ".join(f"{k}:{v}" for k,v in sorted(r['r'].items()))
        if r['pf']>=1.3 and r['dd']<10: v="★稼働推奨"
        elif r['pf']>=1.2 and r['dd']<15: v="◎有望"
        elif r['pf']>=1.1: v="○条件付き"
        elif r['pf']>=1.0: v="△様子見"
        else: v="×見送り"
        print(f"  {r['pair']:>8s}  {r['sp']:>4.1f}  {pf_s:>5s}  {r['wr']:>5.1f}%  {r['dd']:>6.1f}%  {pnl_s:>12s}  {r['mm']:>+6.1f}%  {r['n']:>6d}  {res:>20s}  {v}")

    # 月利テーブル
    month_names={1:"1月",2:"2月",3:"3月",4:"4月"}
    print(f"\n{'='*95}")
    print(f"  【月利(%) 上位10ペア】")
    print(f"{'='*95}")
    top10=df_r.head(10)
    hdr=f"  {'月':>4s}"+"".join(f" {r['pair']:>8s}" for _,r in top10.iterrows())
    print(hdr)
    print(f"  {'-'*(4+9*len(top10))}")

    pair_mo={}
    for _,r in top10.iterrows():
        pair_mo[r["pair"]]={m["month"]:m["pnl_pct"] for m in r["monthly"]} if r.get("monthly") else {}
    ams=sorted(set(m for pm in pair_mo.values() for m in pm))
    for mo in ams:
        row=f"  {month_names.get(mo,str(mo)):>4s}"
        for _,r in top10.iterrows():
            v=pair_mo[r["pair"]].get(mo)
            row+=f" {v:>+7.1f}%" if v is not None else f" {'---':>8s}"
        print(row)

    # サマリー統計
    profitable=df_r[df_r["pnl"]>0]
    print(f"\n{'='*95}")
    print(f"  【サマリー】")
    print(f"{'='*95}")
    print(f"  全ペア数:        {len(df_r)}")
    print(f"  プラス収支:      {len(profitable)} ペア")
    print(f"  PF≥1.3 & DD<10%: {len(df_r[(df_r['pf']>=1.3)&(df_r['dd']<10)])} ペア (稼働推奨)")
    print(f"  PF≥1.2 & DD<15%: {len(df_r[(df_r['pf']>=1.2)&(df_r['dd']<15)])} ペア (有望以上)")
    print(f"  合計損益:        ¥{df_r['pnl'].sum():+,.0f}")

main()
