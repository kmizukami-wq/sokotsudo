//+------------------------------------------------------------------+
//| FXTF_TickScalper.mq4                                             |
//| 手法A: ティック・スキャルピング (最適化版)                       |
//| FX TF ランク1 無料枠（USD/JPY 10,000通貨）内での運用想定         |
//|                                                                  |
//| 戦略:                                                            |
//|   1. M1 EMA(20) vs EMA(60) で方向を固定 (BUY only or SELL only)  |
//|   2. 直近5tickのうち3tick以上が順方向ならエントリ                |
//|   3. 退出:                                                       |
//|      - -2.5pip到達で損切                                         |
//|      - peak >= 1.8pip 到達後、peak-1.2pipまで下落で利確(TRAIL)   |
//|      - 60秒タイムアウト                                          |
//|                                                                  |
//| OOS検証: 勝率78%, 期待値+1.30p/回 (シミュレータ内理論値)         |
//+------------------------------------------------------------------+
#property copyright   "FXTF TickScalper"
#property link        ""
#property version     "1.00"
#property strict
#property description "FXTF Rank1 no-commission tick scalper (optimized)"

//--- Input parameters (ASCII-only to avoid MT4 encoding issues)
input double InpLots           = 0.01;   // Lot size (FXTF: 0.01=100units / 0.1=1,000units / 1.0=10,000units)
input int    InpMagicNumber    = 0;      // Magic number (0 = auto-generate from Symbol)
input int    InpSlippage       = 3;      // Max slippage (points)

input string _sep1_            = "===== Exit Params =====";
input double InpStopPip        = 2.5;    // Stop loss (pip)
input double InpPeakActivate   = 1.8;    // Trail activation peak (pip)
input double InpTrailGap       = 1.2;    // Trail retrace gap (pip)
input int    InpTimeoutSec     = 60;     // Max hold time (sec)

input string _sep2_            = "===== Entry Params =====";
input int    InpTriggerWindow  = 5;      // Tick window size
input int    InpTriggerHits    = 3;      // Required same-direction ticks
input int    InpEMAFast        = 20;     // EMA fast period (M1)
input int    InpEMASlow        = 60;     // EMA slow period (M1)

input string _sep3_            = "===== Risk Guard =====";
input double InpMaxUnits       = 10000;  // Rank-1 unit cap (0-fee tier)
input double InpMaxSpreadPoints= 2;      // Max allowed spread (points); skip entry if wider
input bool   InpSkipTokyoMorn  = false;  // Skip JST 06-09 (Tokyo wide-spread hours)
input bool   InpSkipNYNewsHrs  = false;  // Skip JST 21-24 (NY open + US news hours)
input int    InpJSTFromBroker  = 7;      // Hours to add to broker time for JST (winter=7 / summer=6)
input bool   InpTradeOnlyEAHrs = true;   // Enable custom trading hours (overrides other flags)
input int    InpStartHour      = 9;      // Custom start hour JST (inclusive)
input int    InpEndHour        = 3;      // Custom end hour JST (exclusive); wraps past midnight
input bool   InpVerbose        = false;  // Verbose log output

//--- グローバル状態
double   g_recentMids[];       // 直近tickのmid
int      g_recentCount = 0;
double   g_point;              // = Point (0.001 on 3/5-digit)
double   g_pipSize;            // 1pip価格幅
int      g_direction = 0;      // +1=BUY / -1=SELL / 0=FLAT
datetime g_lastM1Time = 0;
double   g_peakPip = 0;        // 現ポジションのピーク利益(pip)
datetime g_entryTime = 0;
int      g_effectiveMagic = 0; // Magic number (auto-generated if InpMagicNumber=0)

//+------------------------------------------------------------------+
//| Symbol からマジックナンバーを自動生成 (77000-85999 の範囲)         |
//+------------------------------------------------------------------+
int AutoMagicFromSymbol()
{
   string s = Symbol();
   int hash = 0;
   int len = StringLen(s);
   for(int i = 0; i < len; i++)
   {
      int c = StringGetChar(s, i);
      hash = (hash * 31 + c) & 0x7FFFFFFF;  // 正の整数に丸め
   }
   return 77000 + (hash % 9000);  // 77000〜85999
}

//+------------------------------------------------------------------+
//| Init                                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   ArrayResize(g_recentMids, InpTriggerWindow);
   ArrayInitialize(g_recentMids, 0.0);
   g_recentCount = 0;

   g_point = Point;
   // 1pip判定: 3桁(JPY)なら0.01, 5桁(その他)なら0.0001
   if(Digits == 3 || Digits == 5)
      g_pipSize = g_point * 10;
   else
      g_pipSize = g_point;

   // マジックナンバー: 0なら自動生成
   if(InpMagicNumber <= 0)
      g_effectiveMagic = AutoMagicFromSymbol();
   else
      g_effectiveMagic = InpMagicNumber;

   Print("=== FXTF TickScalper initialized ===");
   PrintFormat("Symbol=%s Digits=%d Point=%.5f pipSize=%.5f Magic=%d%s",
               Symbol(), Digits, g_point, g_pipSize,
               g_effectiveMagic, (InpMagicNumber<=0 ? " (auto)" : ""));
   PrintFormat("Exit: stop=-%.1fp peak>=%.1fp trailGap=%.1fp timeout=%ds",
               InpStopPip, InpPeakActivate, InpTrailGap, InpTimeoutSec);
   PrintFormat("Entry: %d/%d ticks same-direction + EMA(%d)vs EMA(%d) on M1",
               InpTriggerHits, InpTriggerWindow, InpEMAFast, InpEMASlow);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {}

//+------------------------------------------------------------------+
//| JST時刻を取得 (brokerTime + InpJSTFromBroker)                    |
//+------------------------------------------------------------------+
int GetJSTHour()
{
   int h = TimeHour(TimeCurrent()) + InpJSTFromBroker;
   h = (h % 24 + 24) % 24;
   return h;
}

//+------------------------------------------------------------------+
//| 時間帯フィルタ                                                   |
//+------------------------------------------------------------------+
bool IsTradeHour()
{
   int jstH = GetJSTHour();

   // 6-9 JST 除外 (Tokyo fix前後の広スプレッド帯)
   if(InpSkipTokyoMorn && jstH >= 6 && jstH < 9) return false;

   // 21-24 JST 除外 (NY開場+米指標多発帯)
   if(InpSkipNYNewsHrs && jstH >= 21 && jstH < 24) return false;

   // 追加の取引許可時間帯
   if(InpTradeOnlyEAHrs)
   {
      if(InpStartHour <= InpEndHour)
         return (jstH >= InpStartHour && jstH < InpEndHour);
      return (jstH >= InpStartHour || jstH < InpEndHour);
   }
   return true;
}

//+------------------------------------------------------------------+
//| 現在スプレッドチェック (point単位)                               |
//+------------------------------------------------------------------+
bool IsSpreadAcceptable()
{
   double spreadPoints = (Ask - Bid) / g_point;
   if(spreadPoints > InpMaxSpreadPoints)
   {
      if(InpVerbose)
         PrintFormat("Spread %.1fp > max %.1fp, skip entry", spreadPoints, InpMaxSpreadPoints);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| 方向更新 (M1足確定時に評価)                                      |
//+------------------------------------------------------------------+
void UpdateDirection()
{
   datetime m1 = iTime(Symbol(), PERIOD_M1, 0);
   if(m1 == g_lastM1Time) return;
   g_lastM1Time = m1;

   if(iBars(Symbol(), PERIOD_M1) < InpEMASlow + 2) return;

   double emaF = iMA(Symbol(), PERIOD_M1, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE, 1);
   double emaS = iMA(Symbol(), PERIOD_M1, InpEMASlow, 0, MODE_EMA, PRICE_CLOSE, 1);
   if(emaF > emaS)      g_direction =  1;
   else if(emaF < emaS) g_direction = -1;
   else                 g_direction =  0;

   if(InpVerbose)
      PrintFormat("[%s] Dir=%s emaF=%.5f emaS=%.5f",
                  TimeToStr(m1, TIME_DATE|TIME_MINUTES),
                  g_direction>0?"BUY":g_direction<0?"SELL":"FLAT", emaF, emaS);
}

//+------------------------------------------------------------------+
//| 直近tickリングバッファ更新                                       |
//+------------------------------------------------------------------+
void PushTick(double mid)
{
   int n = InpTriggerWindow;
   // シフト
   for(int i = 0; i < n-1; i++) g_recentMids[i] = g_recentMids[i+1];
   g_recentMids[n-1] = mid;
   if(g_recentCount < n) g_recentCount++;
}

//+------------------------------------------------------------------+
//| エントリトリガ評価                                               |
//+------------------------------------------------------------------+
bool ShouldEnter(int &outSide)
{
   outSide = 0;
   if(g_direction == 0) return false;
   if(g_recentCount < InpTriggerWindow) return false;

   int hits = 0;
   for(int i = 1; i < InpTriggerWindow; i++)
   {
      double diff = g_recentMids[i] - g_recentMids[i-1];
      int sgn = (diff > 0) ? 1 : (diff < 0 ? -1 : 0);
      if(sgn == g_direction) hits++;
   }
   if(hits >= InpTriggerHits)
   {
      outSide = g_direction;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| 自EAの保有ポジションを取得 (なければticket=-1)                   |
//+------------------------------------------------------------------+
int FindMyPosition()
{
   for(int i = OrdersTotal()-1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol()) continue;
      if(OrderMagicNumber() != g_effectiveMagic) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      return OrderTicket();
   }
   return -1;
}

//+------------------------------------------------------------------+
//| 同方向建玉+未約定発注の通貨数量チェック (ランク1ガード)          |
//+------------------------------------------------------------------+
double SumSameDirectionUnits(int side)
{
   double total = 0;
   double contractSize = MarketInfo(Symbol(), MODE_LOTSIZE); // 1ロットあたりの通貨数
   for(int i = OrdersTotal()-1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol()) continue;
      int t = OrderType();
      bool isBuy  = (t == OP_BUY  || t == OP_BUYLIMIT  || t == OP_BUYSTOP);
      bool isSell = (t == OP_SELL || t == OP_SELLLIMIT || t == OP_SELLSTOP);
      if(side > 0 && isBuy)  total += OrderLots() * contractSize;
      if(side < 0 && isSell) total += OrderLots() * contractSize;
   }
   return total;
}

//+------------------------------------------------------------------+
//| エントリ発注                                                     |
//+------------------------------------------------------------------+
void OpenPosition(int side)
{
   double contractSize = MarketInfo(Symbol(), MODE_LOTSIZE);
   double newUnits = InpLots * contractSize;
   double existing = SumSameDirectionUnits(side);
   if(existing + newUnits > InpMaxUnits)
   {
      if(InpVerbose)
         PrintFormat("Guard: existing=%.0f + new=%.0f > max=%.0f, skip entry",
                     existing, newUnits, InpMaxUnits);
      return;
   }

   int type = (side > 0) ? OP_BUY : OP_SELL;
   double price = (side > 0) ? Ask : Bid;
   string comment = "TickScalp";
   int ticket = OrderSend(Symbol(), type, InpLots, price, InpSlippage,
                          0, 0, comment, g_effectiveMagic, 0, clrNONE);
   if(ticket < 0)
   {
      int err = GetLastError();
      PrintFormat("OrderSend failed err=%d", err);
      return;
   }
   g_peakPip  = 0;
   g_entryTime = TimeCurrent();
   if(InpVerbose)
      PrintFormat("ENTRY %s @%.5f ticket=%d",
                  side>0?"BUY":"SELL", price, ticket);
}

//+------------------------------------------------------------------+
//| 現ポジションの含み損益を pip で返す                              |
//+------------------------------------------------------------------+
double CurrentPipPnL(int ticket)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return 0;
   double entry = OrderOpenPrice();
   double cur   = (OrderType() == OP_BUY) ? Bid : Ask;
   int side     = (OrderType() == OP_BUY) ? 1 : -1;
   return (cur - entry) * side / g_pipSize;
}

//+------------------------------------------------------------------+
//| クローズ                                                         |
//+------------------------------------------------------------------+
void ClosePosition(int ticket, string reason)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
   double price = (OrderType() == OP_BUY) ? Bid : Ask;
   double pip   = CurrentPipPnL(ticket);
   bool ok = OrderClose(ticket, OrderLots(), price, InpSlippage, clrNONE);
   if(!ok)
   {
      PrintFormat("OrderClose failed err=%d", GetLastError());
      return;
   }
   PrintFormat("EXIT[%s] pip=%s%.2f peak=%.2f ticket=%d",
               reason, pip>=0?"+":"", pip, g_peakPip, ticket);
   g_peakPip = 0;
}

//+------------------------------------------------------------------+
//| 退出判定                                                         |
//+------------------------------------------------------------------+
void ManagePosition(int ticket)
{
   double pip = CurrentPipPnL(ticket);
   if(pip > g_peakPip) g_peakPip = pip;

   // タイムアウト
   if(TimeCurrent() - g_entryTime >= InpTimeoutSec)
   {
      ClosePosition(ticket, "TIMEOUT");
      return;
   }
   // 損切
   if(pip <= -InpStopPip)
   {
      ClosePosition(ticket, "STOP");
      return;
   }
   // トレール利確
   if(g_peakPip >= InpPeakActivate && pip < g_peakPip - InpTrailGap)
   {
      ClosePosition(ticket, "TRAIL");
      return;
   }
}

//+------------------------------------------------------------------+
//| OnTick                                                           |
//+------------------------------------------------------------------+
void OnTick()
{
   double mid = (Bid + Ask) / 2.0;
   PushTick(mid);

   UpdateDirection();

   int ticket = FindMyPosition();
   if(ticket >= 0)
   {
      ManagePosition(ticket);
      return;
   }

   if(!IsTradeHour()) return;
   if(!IsSpreadAcceptable()) return;

   int side = 0;
   if(ShouldEnter(side))
      OpenPosition(side);
}

//+------------------------------------------------------------------+
