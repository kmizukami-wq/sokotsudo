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
input int    InpSlippage       = 0;      // Max slippage (points); 0 = strict price; raise to 3-5 if rejected often

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
input int    InpJSTFromBroker  = 6;      // Hours to add to broker time for JST (summer=6 / winter=7)
input bool   InpTradeOnlyEAHrs = true;   // Enable custom trading hours (overrides other flags)
input int    InpStartHour      = 9;      // Custom start hour JST (inclusive)
input int    InpEndHour        = 3;      // Custom end hour JST (exclusive); wraps past midnight
input bool   InpVerbose        = false;  // Verbose log output
input bool   InpLogCSV         = false;  // Append diagnostics to MQL4/Files/TickScalp_<Symbol>.csv

//--- グローバル状態
double   g_recentMids[];       // 直近tickのmid
int      g_recentCount = 0;
double   g_point;              // = Point (0.001 on 3/5-digit)
double   g_pipSize;            // 1pip価格幅
int      g_direction = 0;      // +1=BUY / -1=SELL / 0=FLAT
int      g_prevDirection = 0;  // DIR変化検出用 (UpdateDirection が比較)
double   g_lastEmaFast = 0;    // 直近 UpdateDirection で読んだ emaF (ログ用)
double   g_lastEmaSlow = 0;
double   g_lastEmaSlopePip = 0;// emaF(bar1)-emaF(bar3) を pip 換算
datetime g_lastM1Time = 0;
double   g_peakPip = 0;        // 現ポジションのピーク利益(pip)
datetime g_entryTime = 0;
int      g_effectiveMagic = 0; // Magic number (auto-generated if InpMagicNumber=0)

// エントリ時点の診断値 (EXITログで再利用 / CSV)
int      g_entrySide     = 0;
double   g_entryPrice    = 0;
double   g_entryEmaGap   = 0;
double   g_entryEmaSlope = 0;
int      g_entryHits     = 0;
double   g_entryTickMove = 0;
double   g_entrySpread   = 0;

string   g_csvFile = "";        // OnInit で確定
int      g_csvHeaderWritten = 0;

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
   // JST time diagnostics - verify InpJSTFromBroker (summer=6 / winter=7)
   datetime brokerT = TimeCurrent();
   int jstHour = (TimeHour(brokerT) + InpJSTFromBroker) % 24;
   int jstMin = TimeMinute(brokerT);
   PrintFormat("Time: broker=%s JST=%02d:%02d (offset=%d)",
               TimeToStr(brokerT, TIME_DATE|TIME_MINUTES),
               jstHour, jstMin, InpJSTFromBroker);
   PrintFormat("Trade hours (JST): %02d:00 to %02d:00 (TradeOnly=%s / SkipTokyo=%s / SkipNY=%s)",
               InpStartHour, InpEndHour,
               (InpTradeOnlyEAHrs ? "true" : "false"),
               (InpSkipTokyoMorn ? "true" : "false"),
               (InpSkipNYNewsHrs ? "true" : "false"));
   PrintFormat("Exit: stop=-%.1fp peak>=%.1fp trailGap=%.1fp timeout=%ds",
               InpStopPip, InpPeakActivate, InpTrailGap, InpTimeoutSec);
   PrintFormat("Entry: %d/%d ticks same-direction + EMA(%d)vs EMA(%d) on M1",
               InpTriggerHits, InpTriggerWindow, InpEMAFast, InpEMASlow);
   PrintFormat("Execution: lots=%.2f slippage=%d maxSpread=%.1fp",
               InpLots, InpSlippage, InpMaxSpreadPoints);

   // CSV 診断ログ準備
   g_csvFile = StringConcatenate("TickScalp_", Symbol(), ".csv");
   if(InpLogCSV)
   {
      int h = FileOpen(g_csvFile, FILE_CSV|FILE_READ|FILE_ANSI, ';');
      bool needHeader = (h == INVALID_HANDLE);
      if(h != INVALID_HANDLE) FileClose(h);
      if(needHeader)
      {
         int hw = FileOpen(g_csvFile, FILE_CSV|FILE_WRITE|FILE_ANSI, ';');
         if(hw != INVALID_HANDLE)
         {
            FileWriteString(hw, "timestamp;symbol;event;side;pip;holdSec;emaGap;emaSlope;hits;tickMove;spread\r\n");
            FileClose(hw);
         }
      }
      PrintFormat("CSV log -> MQL4/Files/%s", g_csvFile);
   }
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
//| 診断ヘルパ                                                       |
//+------------------------------------------------------------------+
double ComputeEmaGapPip()
{
   return (g_lastEmaFast - g_lastEmaSlow) / g_pipSize;
}

double ComputeTickMovePip()
{
   int n = InpTriggerWindow;
   if(g_recentCount < n) return 0;
   return (g_recentMids[n-1] - g_recentMids[0]) / g_pipSize;
}

int ComputeHits(int dir)
{
   int hits = 0;
   if(g_recentCount < InpTriggerWindow || dir == 0) return 0;
   for(int i = 1; i < InpTriggerWindow; i++)
   {
      double diff = g_recentMids[i] - g_recentMids[i-1];
      int sgn = (diff > 0) ? 1 : (diff < 0 ? -1 : 0);
      if(sgn == dir) hits++;
   }
   return hits;
}

string SideStr(int s)
{
   if(s > 0) return "BUY";
   if(s < 0) return "SELL";
   return "FLAT";
}

void LogCSV(string line)
{
   if(!InpLogCSV) return;
   int h = FileOpen(g_csvFile, FILE_CSV|FILE_READ|FILE_WRITE|FILE_ANSI, ';');
   if(h == INVALID_HANDLE)
   {
      h = FileOpen(g_csvFile, FILE_CSV|FILE_WRITE|FILE_ANSI, ';');
      if(h == INVALID_HANDLE) return;
   }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, line + "\r\n");
   FileClose(h);
}

//+------------------------------------------------------------------+
//| 方向更新 (M1足確定時に評価)                                      |
//+------------------------------------------------------------------+
void UpdateDirection()
{
   datetime m1 = iTime(Symbol(), PERIOD_M1, 0);
   if(m1 == g_lastM1Time) return;
   g_lastM1Time = m1;

   if(iBars(Symbol(), PERIOD_M1) < InpEMASlow + 4) return;

   double emaF1 = iMA(Symbol(), PERIOD_M1, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE, 1);
   double emaF3 = iMA(Symbol(), PERIOD_M1, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE, 3);
   double emaS  = iMA(Symbol(), PERIOD_M1, InpEMASlow, 0, MODE_EMA, PRICE_CLOSE, 1);
   g_lastEmaFast     = emaF1;
   g_lastEmaSlow     = emaS;
   g_lastEmaSlopePip = (emaF1 - emaF3) / 2.0 / g_pipSize;  // bar あたりの pip 傾き

   g_prevDirection = g_direction;
   if(emaF1 > emaS)      g_direction =  1;
   else if(emaF1 < emaS) g_direction = -1;
   else                  g_direction =  0;

   double gap = ComputeEmaGapPip();

   // 方向が変わった時は常時ログ
   if(g_direction != g_prevDirection)
   {
      PrintFormat("DIR %s->%s [%s] emaF=%.5f emaS=%.5f gap=%+.2fp slope=%+.2fp/bar",
                  SideStr(g_prevDirection), SideStr(g_direction),
                  TimeToStr(m1, TIME_DATE|TIME_MINUTES),
                  emaF1, emaS, gap, g_lastEmaSlopePip);
      if(InpLogCSV)
      {
         string line = StringFormat("%s;%s;DIR;%s;;;%+0.2f;%+0.2f;;;",
                                    TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS),
                                    Symbol(), SideStr(g_direction),
                                    gap, g_lastEmaSlopePip);
         LogCSV(line);
      }
   }
   else if(InpVerbose)
   {
      PrintFormat("[%s] Dir=%s emaF=%.5f emaS=%.5f gap=%+.2fp slope=%+.2fp/bar",
                  TimeToStr(m1, TIME_DATE|TIME_MINUTES), SideStr(g_direction),
                  emaF1, emaS, gap, g_lastEmaSlopePip);
   }
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

   int hits = ComputeHits(g_direction);
   if(hits >= InpTriggerHits)
   {
      outSide = g_direction;
      return true;
   }
   if(InpVerbose)
   {
      double move = ComputeTickMovePip();
      PrintFormat("Gate[HITS] hits=%d/%d tickMove=%+.2fp (need %d+ in dir=%s)",
                  hits, InpTriggerWindow-1, move,
                  InpTriggerHits, SideStr(g_direction));
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
      string hint = "";
      switch(err)
      {
         case 129: hint = "invalid price - stale quote"; break;
         case 130: hint = "invalid stops (not expected, SL/TP=0)"; break;
         case 131: hint = "invalid lot step - check MODE_LOTSTEP"; break;
         case 132: hint = "market closed"; break;
         case 133: hint = "trade disabled on this symbol"; break;
         case 134: hint = "not enough money - reduce InpLots or add funds"; break;
         case 135: hint = "price changed - will retry next tick"; break;
         case 136: hint = "off quotes - market moved; retry next tick"; break;
         case 137: hint = "broker busy - retry next tick"; break;
         case 138: hint = "requote - consider raising InpSlippage (0->3)"; break;
         case 139: hint = "order locked for processing"; break;
         case 141: hint = "too many requests - slow down"; break;
         case 145: hint = "too close to market - modification blocked"; break;
         case 146: hint = "trade context busy"; break;
         case 148: hint = "too many orders - check open positions"; break;
         case 149: hint = "hedging prohibited - do not open opposite side"; break;
         default:  hint = "see MT4 error code reference"; break;
      }
      PrintFormat("OrderSend failed err=%d (%s)", err, hint);
      return;
   }
   g_peakPip  = 0;
   g_entryTime = TimeCurrent();

   // 診断値のスナップショット (EXIT ログで再利用)
   g_entrySide     = side;
   g_entryPrice    = price;
   g_entryEmaGap   = ComputeEmaGapPip();
   g_entryEmaSlope = g_lastEmaSlopePip;
   g_entryHits     = ComputeHits(side);
   g_entryTickMove = ComputeTickMovePip();
   g_entrySpread   = (Ask - Bid) / g_point;

   PrintFormat("ENTRY %s @%.5f ticket=%d emaGap=%+.2fp slope=%+.2fp/bar hits=%d/%d tickMove=%+.2fp spread=%.1fp",
               SideStr(side), price, ticket,
               g_entryEmaGap, g_entryEmaSlope,
               g_entryHits, InpTriggerWindow-1,
               g_entryTickMove, g_entrySpread);

   if(InpLogCSV)
   {
      string line = StringFormat("%s;%s;ENTRY;%s;;;%+0.2f;%+0.2f;%d;%+0.2f;%.1f",
                                 TimeToStr(g_entryTime, TIME_DATE|TIME_SECONDS),
                                 Symbol(), SideStr(side),
                                 g_entryEmaGap, g_entryEmaSlope,
                                 g_entryHits, g_entryTickMove, g_entrySpread);
      LogCSV(line);
   }
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
   int side     = (OrderType() == OP_BUY) ? 1 : -1;
   int holdSec  = (int)(TimeCurrent() - g_entryTime);

   bool ok = OrderClose(ticket, OrderLots(), price, InpSlippage, clrNONE);
   if(!ok)
   {
      PrintFormat("OrderClose failed err=%d", GetLastError());
      return;
   }
   PrintFormat("EXIT[%s] side=%s pip=%+.2f peak=%+.2f holdSec=%d ticket=%d (entry: gap=%+.2fp slope=%+.2fp/bar hits=%d move=%+.2fp)",
               reason, SideStr(side), pip, g_peakPip, holdSec, ticket,
               g_entryEmaGap, g_entryEmaSlope, g_entryHits, g_entryTickMove);

   if(InpLogCSV)
   {
      string evt = "EXIT_" + reason;
      string line = StringFormat("%s;%s;%s;%s;%+0.2f;%d;%+0.2f;%+0.2f;%d;%+0.2f;%.1f",
                                 TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS),
                                 Symbol(), evt, SideStr(side),
                                 pip, holdSec,
                                 g_entryEmaGap, g_entryEmaSlope,
                                 g_entryHits, g_entryTickMove, g_entrySpread);
      LogCSV(line);
   }
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
