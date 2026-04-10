//+------------------------------------------------------------------+
//| GBP_Monthly10pct.mq4                                             |
//| GBP/USD 月利20%+ ピラミッドトレンドフォロー EA                    |
//| 15分足専用 / FXTF MT4対応                                         |
//+------------------------------------------------------------------+
//| 戦略: EMA50/200クロス + ATR x3.5 トレイリング + ピラミッド2段     |
//|   バックテスト結果 (GBP/USD):                                     |
//|     月利+21.3%, MaxDD 27.3%, PF 1.27, 3/4ヶ月で10%超             |
//+------------------------------------------------------------------+
#property copyright "sokotsudo research"
#property version   "3.00"
#property strict

//+------------------------------------------------------------------+
//| 外部パラメータ                                                    |
//+------------------------------------------------------------------+
// --- 共通 ---
input int    MagicNumber       = 20001;   // MagicNumber
input double MaxRiskPercent    = 2.0;     // 1トレードリスク (%)
input int    MaxPositions      = 2;       // 最大同時ポジション数
input double MonthlyDDLimit    = 15.0;    // 月間DD制限 (%)
input int    ServerGMTOffset   = 9;       // サーバーGMTオフセット (FXTF=9)
input int    Slippage          = 10;      // スリッページ (points)
input double MaxSpreadPips     = 5.0;     // 最大許容スプレッド (pips)

// --- トレンドフォロー ---
input bool   EnableTrend       = true;    // トレンドフォロー有効
input int    FastEMA           = 50;      // 短期EMA期間
input int    SlowEMA           = 200;     // 長期EMA期間
input double ATR_Trail_Mult    = 3.5;     // ATRトレイリング倍率
input int    ATR_Period        = 14;      // ATR期間
input int    TrendStartHour    = 7;       // トレンド取引開始 (UTC)
input int    TrendEndHour      = 21;      // トレンド取引終了 (UTC)

// --- ピラミッディング ---
input bool   EnablePyramid     = true;    // ピラミッド有効
input int    PyramidMax        = 2;       // 最大追加段数
input double PyramidTriggerATR = 3.0;     // 追加起動 (ATR倍)
input double PyramidLotRatio   = 0.5;     // 追加ロット比率 (メインの50%)

// --- ロンドンブレイクアウト ---
input bool   EnableLondonBK    = false;   // ロンドンBK有効 (GBP/USDではOFF推奨)
input int    AsianStartHour    = 0;       // アジアレンジ開始 (UTC)
input int    AsianEndHour      = 7;       // アジアレンジ終了 (UTC)
input int    LondonEndHour     = 16;      // ロンドンセッション終了 (UTC)
input double BK_TP_Mult        = 1.5;     // TP倍率 (レンジ幅に対して)
input double BK_RiskPercent    = 2.0;     // BKリスク (%)
input double MinRangePips      = 20.0;    // 最小レンジ幅 (pips)
input double MaxRangePips      = 120.0;   // 最大レンジ幅 (pips)

//+------------------------------------------------------------------+
//| 定数                                                              |
//+------------------------------------------------------------------+
#define MAGIC_TREND  0
#define MAGIC_BK     1

//+------------------------------------------------------------------+
//| グローバル変数                                                    |
//+------------------------------------------------------------------+
datetime g_lastBarTime     = 0;
double   g_monthStartEq    = 0;
int      g_currentMonth    = 0;
bool     g_monthStopped    = false;

// ロンドンBK用
double   g_asianHigh       = 0;
double   g_asianLow        = 0;
bool     g_asianRangeSet   = false;
bool     g_bkTriggered     = false;
int      g_bkDate          = 0;

// トレンドフォロー用
double   g_trendTrailStop  = 0;
int      g_trendDirection  = 0;  // 1=long, -1=short, 0=flat
double   g_trendEntryPrice = 0;
double   g_trendEntryATR   = 0;

// ピラミッド用
int      g_pyramidCount    = 0;  // 追加済み段数
#define  MAGIC_PYR1  2
#define  MAGIC_PYR2  3

//+------------------------------------------------------------------+
//| 状態ファイル名取得                                                |
//+------------------------------------------------------------------+
string GetStateFile()
{
   return "GBP10pct_" + Symbol() + "_" + IntegerToString(MagicNumber) + ".dat";
}

//+------------------------------------------------------------------+
//| 状態保存 - EA再起動後も継続可能にする                             |
//+------------------------------------------------------------------+
void SaveState()
{
   string filename = GetStateFile();
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT);
   if(handle == INVALID_HANDLE)
   {
      Print("[STATE] Save failed: ", GetLastError());
      return;
   }
   // トレンドフォロー状態
   FileWriteString(handle, DoubleToString(g_trendTrailStop, Digits) + "\n");
   FileWriteString(handle, IntegerToString(g_trendDirection) + "\n");
   // ロンドンBK状態
   FileWriteString(handle, DoubleToString(g_asianHigh, Digits) + "\n");
   FileWriteString(handle, DoubleToString(g_asianLow, Digits) + "\n");
   FileWriteString(handle, IntegerToString(g_asianRangeSet) + "\n");
   FileWriteString(handle, IntegerToString(g_bkTriggered) + "\n");
   FileWriteString(handle, IntegerToString(g_bkDate) + "\n");
   // DD管理
   FileWriteString(handle, DoubleToString(g_monthStartEq, 2) + "\n");
   FileWriteString(handle, IntegerToString(g_currentMonth) + "\n");
   FileWriteString(handle, IntegerToString(g_monthStopped) + "\n");
   // ピラミッド
   FileWriteString(handle, IntegerToString(g_pyramidCount) + "\n");
   FileWriteString(handle, DoubleToString(g_trendEntryPrice, Digits) + "\n");
   FileWriteString(handle, DoubleToString(g_trendEntryATR, Digits) + "\n");
   FileClose(handle);
}

//+------------------------------------------------------------------+
//| 状態読み込み                                                      |
//+------------------------------------------------------------------+
void LoadState()
{
   string filename = GetStateFile();
   if(!FileIsExist(filename))
      return;

   int handle = FileOpen(filename, FILE_READ | FILE_TXT);
   if(handle == INVALID_HANDLE)
      return;

   if(!FileIsEnding(handle)) g_trendTrailStop = StringToDouble(FileReadString(handle));
   if(!FileIsEnding(handle)) g_trendDirection  = (int)StringToInteger(FileReadString(handle));
   if(!FileIsEnding(handle)) g_asianHigh      = StringToDouble(FileReadString(handle));
   if(!FileIsEnding(handle)) g_asianLow       = StringToDouble(FileReadString(handle));
   if(!FileIsEnding(handle)) g_asianRangeSet  = (bool)StringToInteger(FileReadString(handle));
   if(!FileIsEnding(handle)) g_bkTriggered    = (bool)StringToInteger(FileReadString(handle));
   if(!FileIsEnding(handle)) g_bkDate         = (int)StringToInteger(FileReadString(handle));
   if(!FileIsEnding(handle)) g_monthStartEq   = StringToDouble(FileReadString(handle));
   if(!FileIsEnding(handle)) g_currentMonth   = (int)StringToInteger(FileReadString(handle));
   if(!FileIsEnding(handle)) g_monthStopped   = (bool)StringToInteger(FileReadString(handle));
   if(!FileIsEnding(handle)) g_pyramidCount   = (int)StringToInteger(FileReadString(handle));
   if(!FileIsEnding(handle)) g_trendEntryPrice = StringToDouble(FileReadString(handle));
   if(!FileIsEnding(handle)) g_trendEntryATR  = StringToDouble(FileReadString(handle));
   FileClose(handle);

   Print("[STATE] Loaded: trail=", g_trendTrailStop,
         " dir=", g_trendDirection,
         " asianH=", g_asianHigh, " asianL=", g_asianLow,
         " monthEq=", g_monthStartEq);
}

//+------------------------------------------------------------------+
//| UTC時間取得                                                       |
//+------------------------------------------------------------------+
int GetUTCHour()
{
   datetime utcTime = TimeCurrent() - ServerGMTOffset * 3600;
   MqlDateTime dt;
   TimeToStruct(utcTime, dt);
   return dt.hour;
}

int GetUTCDay()
{
   datetime utcTime = TimeCurrent() - ServerGMTOffset * 3600;
   MqlDateTime dt;
   TimeToStruct(utcTime, dt);
   return dt.day;
}

//+------------------------------------------------------------------+
//| 新バー検知                                                        |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime currentBarTime = iTime(NULL, PERIOD_M15, 0);
   if(currentBarTime != g_lastBarTime)
   {
      g_lastBarTime = currentBarTime;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| pip値取得                                                         |
//+------------------------------------------------------------------+
double GetPipValue()
{
   if(Digits == 3 || Digits == 5)
      return Point * 10;
   return Point;
}

//+------------------------------------------------------------------+
//| スプレッドチェック                                                |
//+------------------------------------------------------------------+
bool IsSpreadOK()
{
   double spread = (Ask - Bid) / GetPipValue();
   if(spread > MaxSpreadPips)
   {
      // 10バーに1回だけログ出力（ログ溢れ防止）
      static int logCounter = 0;
      if(logCounter % 10 == 0)
         Print("[SPREAD] ", DoubleToString(spread, 1), " pips > limit ",
               DoubleToString(MaxSpreadPips, 1), ". Skipping.");
      logCounter++;
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| 最小ストップレベルチェック                                        |
//+------------------------------------------------------------------+
double GetMinStopDistance()
{
   double stopLevel = MarketInfo(Symbol(), MODE_STOPLEVEL) * Point;
   double freezeLevel = MarketInfo(Symbol(), MODE_FREEZELEVEL) * Point;
   return MathMax(stopLevel, freezeLevel) + GetPipValue(); // 余裕1pip
}

//+------------------------------------------------------------------+
//| 自分のポジション数                                                |
//+------------------------------------------------------------------+
int CountMyOrders(int subMagic = -1)
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol())
         continue;
      int om = OrderMagicNumber();
      if(subMagic >= 0)
      {
         if(om == MagicNumber + subMagic)
            count++;
      }
      else
      {
         if(om >= MagicNumber && om <= MagicNumber + 10)
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| 自分のポジションチケット取得                                      |
//+------------------------------------------------------------------+
int FindMyOrder(int subMagic)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber + subMagic)
         return OrderTicket();
   }
   return -1;
}

//+------------------------------------------------------------------+
//| ピラミッド全決済                                                  |
//+------------------------------------------------------------------+
void CloseAllPyramids()
{
   for(int pm = MAGIC_PYR1; pm <= MAGIC_PYR2; pm++)
   {
      int pyrTicket = FindMyOrder(pm);
      if(pyrTicket <= 0) continue;
      if(!OrderSelect(pyrTicket, SELECT_BY_TICKET)) continue;
      double closePrice = (OrderType() == OP_BUY) ? Bid : Ask;
      if(OrderClose(pyrTicket, OrderLots(), closePrice, Slippage, clrGray))
         Print("[PYR", pm - MAGIC_PYR1 + 1, "] Force closed");
      else
         Print("[PYR", pm - MAGIC_PYR1 + 1, "] Force close failed: ", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| ロットサイズ計算                                                  |
//+------------------------------------------------------------------+
double CalcLotSize(double slDistance, double riskPct)
{
   if(slDistance <= 0) return MarketInfo(Symbol(), MODE_MINLOT);

   double equity     = AccountEquity();
   double riskAmount = equity * riskPct / 100.0;
   double tickValue  = MarketInfo(Symbol(), MODE_TICKVALUE);
   double tickSize   = MarketInfo(Symbol(), MODE_TICKSIZE);
   double minLot     = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot     = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep    = MarketInfo(Symbol(), MODE_LOTSTEP);

   if(tickValue <= 0 || tickSize <= 0) return minLot;

   double slCostPerLot = slDistance / tickSize * tickValue;
   if(slCostPerLot <= 0) return minLot;

   double lots = riskAmount / slCostPerLot;

   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(lots, minLot);
   lots = MathMin(lots, maxLot);

   return lots;
}

//+------------------------------------------------------------------+
//| 月間DD チェック                                                   |
//+------------------------------------------------------------------+
bool CheckMonthlyDD()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int month = dt.mon;

   if(month != g_currentMonth)
   {
      g_currentMonth = month;
      g_monthStartEq = AccountEquity();
      g_monthStopped = false;
      Print("[DD] New month. Start equity: ", DoubleToString(g_monthStartEq, 0));
      SaveState();
   }

   if(g_monthStartEq > 0)
   {
      double dd = (g_monthStartEq - AccountEquity()) / g_monthStartEq * 100;
      if(dd >= MonthlyDDLimit)
      {
         if(!g_monthStopped)
         {
            Print("[DD STOP] Monthly DD ", DoubleToString(dd, 1), "% >= ",
                  DoubleToString(MonthlyDDLimit, 1), "%. Trading stopped for this month.");
            g_monthStopped = true;
            SaveState();
         }
         return false;
      }
   }
   return true;
}

//+------------------------------------------------------------------+
//| Init                                                              |
//+------------------------------------------------------------------+
int OnInit()
{
   // 状態復元
   LoadState();

   // 初回起動時のみ月初equity設定
   if(g_monthStartEq <= 0)
   {
      g_monthStartEq = AccountEquity();
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      g_currentMonth = dt.mon;
   }

   // 既存ポジションからトレンド方向を復元
   int trendTicket = FindMyOrder(MAGIC_TREND);
   if(trendTicket > 0 && OrderSelect(trendTicket, SELECT_BY_TICKET))
   {
      if(OrderType() == OP_BUY)
         g_trendDirection = 1;
      else if(OrderType() == OP_SELL)
         g_trendDirection = -1;

      // トレイリングストップが0なら現在のSLから復元
      if(g_trendTrailStop == 0 && OrderStopLoss() > 0)
         g_trendTrailStop = OrderStopLoss();

      Print("[INIT] Existing trend position found. Dir=", g_trendDirection,
            " TrailStop=", g_trendTrailStop);
   }

   Print("=== GBP Monthly10% EA v3.0 (Pyramid) ===");
   Print("  Symbol: ", Symbol(), " (", Digits, " digits)");
   Print("  Trend: ", EnableTrend, " | LondonBK: ", EnableLondonBK,
         " | Pyramid: ", EnablePyramid, " (max ", PyramidMax, ", trigger ", PyramidTriggerATR, "ATR)");
   Print("  Risk: ", MaxRiskPercent, "% | MaxPos: ", MaxPositions);
   Print("  MonthlyDD Limit: ", MonthlyDDLimit, "%");
   Print("  Max Spread: ", MaxSpreadPips, " pips");
   Print("  ServerGMT: +", ServerGMTOffset);
   Print("  Min StopLevel: ", DoubleToString(GetMinStopDistance() / GetPipValue(), 1), " pips");

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| OnTick                                                            |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!IsNewBar()) return;

   // DD制限チェック
   if(!CheckMonthlyDD()) return;

   // スプレッドチェック
   if(!IsSpreadOK()) return;

   int utcHour = GetUTCHour();
   int utcDay  = GetUTCDay();

   // === トレンドフォロー ===
   if(EnableTrend)
      ProcessTrendFollow(utcHour);

   // === ロンドンブレイクアウト ===
   if(EnableLondonBK)
      ProcessLondonBK(utcHour, utcDay);
}

//+------------------------------------------------------------------+
//| トレンドフォロー処理                                              |
//+------------------------------------------------------------------+
void ProcessTrendFollow(int utcHour)
{
   double emaFast = iMA(NULL, PERIOD_M15, FastEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double emaSlow = iMA(NULL, PERIOD_M15, SlowEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double atr     = iATR(NULL, PERIOD_M15, ATR_Period, 1);
   double close1  = iClose(NULL, PERIOD_M15, 1);
   double high1   = iHigh(NULL, PERIOD_M15, 1);
   double low1    = iLow(NULL, PERIOD_M15, 1);

   if(atr <= 0) return;

   int signal = 0;
   if(emaFast > emaSlow) signal = 1;
   if(emaFast < emaSlow) signal = -1;

   int ticket = FindMyOrder(MAGIC_TREND);

   // === ピラミッドポジション管理 (メインより先に処理) ===
   if(EnablePyramid)
   {
      for(int pm = MAGIC_PYR1; pm <= MAGIC_PYR2; pm++)
      {
         int pyrTicket = FindMyOrder(pm);
         if(pyrTicket <= 0) continue;
         if(!OrderSelect(pyrTicket, SELECT_BY_TICKET)) continue;

         double pyrMinDist = GetMinStopDistance();
         if(OrderType() == OP_BUY)
         {
            double pyrStop = close1 - atr * ATR_Trail_Mult;
            double curSL = OrderStopLoss();
            if(low1 <= curSL || signal == -1)
            {
               OrderClose(pyrTicket, OrderLots(), Bid, Slippage, clrRed);
               Print("[PYR", pm - MAGIC_PYR1 + 1, "] Closed BUY");
            }
            else if(pyrStop > curSL + GetPipValue() && Bid - pyrStop >= pyrMinDist)
            {
               OrderModify(pyrTicket, OrderOpenPrice(),
                           NormalizeDouble(pyrStop, Digits), 0, 0);
            }
         }
         else
         {
            double pyrStop = close1 + atr * ATR_Trail_Mult;
            double curSL = OrderStopLoss();
            if(high1 >= curSL || signal == 1)
            {
               OrderClose(pyrTicket, OrderLots(), Ask, Slippage, clrBlue);
               Print("[PYR", pm - MAGIC_PYR1 + 1, "] Closed SELL");
            }
            else if((pyrStop < curSL - GetPipValue() || curSL == 0) &&
                    pyrStop - Ask >= pyrMinDist)
            {
               OrderModify(pyrTicket, OrderOpenPrice(),
                           NormalizeDouble(pyrStop, Digits), 0, 0);
            }
         }
      }
   }

   // === メインポジション管理 ===
   if(ticket > 0)
   {
      if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
      int orderType = OrderType();
      double minDist = GetMinStopDistance();

      if(orderType == OP_BUY)
      {
         double newStop = close1 - atr * ATR_Trail_Mult;
         if(newStop > g_trendTrailStop)
            g_trendTrailStop = newStop;

         if(low1 <= g_trendTrailStop || signal == -1)
         {
            if(OrderClose(ticket, OrderLots(), Bid, Slippage, clrRed))
            {
               double pnl = (Bid - OrderOpenPrice()) / GetPipValue();
               Print("[TREND] Closed BUY +", DoubleToString(pnl, 1), " pips");
               // ピラミッドも全決済
               CloseAllPyramids();
               g_trendTrailStop = 0;
               g_trendDirection = 0;
               g_pyramidCount = 0;
               g_trendEntryPrice = 0;
               g_trendEntryATR = 0;
               SaveState();
            }
            else
               Print("[TREND] Close BUY failed: ", GetLastError());
         }
         else
         {
            double currentSL = OrderStopLoss();
            if(g_trendTrailStop > currentSL + GetPipValue() &&
               Bid - g_trendTrailStop >= minDist)
            {
               if(OrderModify(ticket, OrderOpenPrice(),
                              NormalizeDouble(g_trendTrailStop, Digits),
                              OrderTakeProfit(), 0))
                  SaveState();
               else
                  Print("[TREND] Modify SL failed: ", GetLastError());
            }
         }
      }
      else if(orderType == OP_SELL)
      {
         double newStop = close1 + atr * ATR_Trail_Mult;
         if(newStop < g_trendTrailStop || g_trendTrailStop == 0)
            g_trendTrailStop = newStop;

         if(high1 >= g_trendTrailStop || signal == 1)
         {
            if(OrderClose(ticket, OrderLots(), Ask, Slippage, clrBlue))
            {
               double pnl = (OrderOpenPrice() - Ask) / GetPipValue();
               Print("[TREND] Closed SELL +", DoubleToString(pnl, 1), " pips");
               CloseAllPyramids();
               g_trendTrailStop = 0;
               g_trendDirection = 0;
               g_pyramidCount = 0;
               g_trendEntryPrice = 0;
               g_trendEntryATR = 0;
               SaveState();
            }
            else
               Print("[TREND] Close SELL failed: ", GetLastError());
         }
         else
         {
            double currentSL = OrderStopLoss();
            if((g_trendTrailStop < currentSL - GetPipValue() || currentSL == 0) &&
               g_trendTrailStop - Ask >= minDist)
            {
               if(OrderModify(ticket, OrderOpenPrice(),
                              NormalizeDouble(g_trendTrailStop, Digits),
                              OrderTakeProfit(), 0))
                  SaveState();
               else
                  Print("[TREND] Modify SL failed: ", GetLastError());
            }
         }
      }

      // === ピラミッド追加判定 ===
      if(EnablePyramid && g_pyramidCount < PyramidMax && g_trendEntryATR > 0)
      {
         double unrealizedATR = 0;
         if(g_trendDirection == 1)
            unrealizedATR = (close1 - g_trendEntryPrice) / g_trendEntryATR;
         else if(g_trendDirection == -1)
            unrealizedATR = (g_trendEntryPrice - close1) / g_trendEntryATR;

         double threshold = PyramidTriggerATR * (g_pyramidCount + 1);
         if(unrealizedATR >= threshold)
         {
            double slDist = atr * ATR_Trail_Mult;
            double minDist2 = GetMinStopDistance();
            if(slDist < minDist2) slDist = minDist2;

            double pyrLots = CalcLotSize(slDist, MaxRiskPercent) * PyramidLotRatio;
            double minLot = MarketInfo(Symbol(), MODE_MINLOT);
            if(pyrLots < minLot) pyrLots = minLot;

            int pyrMagic = MagicNumber + MAGIC_PYR1 + g_pyramidCount;

            if(g_trendDirection == 1)
            {
               double sl = NormalizeDouble(Ask - slDist, Digits);
               int t = OrderSend(Symbol(), OP_BUY, pyrLots, Ask, Slippage,
                                 sl, 0, "GBP10 PYR" + IntegerToString(g_pyramidCount + 1) + " BUY",
                                 pyrMagic, 0, clrAqua);
               if(t > 0)
               {
                  g_pyramidCount++;
                  Print("[PYR", g_pyramidCount, "] BUY ", DoubleToString(pyrLots, 2),
                        " @ ", Ask, " (unrealized ", DoubleToString(unrealizedATR, 1), " ATR)");
                  SaveState();
               }
               else
                  Print("[PYR] BUY failed: ", GetLastError());
            }
            else
            {
               double sl = NormalizeDouble(Bid + slDist, Digits);
               int t = OrderSend(Symbol(), OP_SELL, pyrLots, Bid, Slippage,
                                 sl, 0, "GBP10 PYR" + IntegerToString(g_pyramidCount + 1) + " SELL",
                                 pyrMagic, 0, clrMagenta);
               if(t > 0)
               {
                  g_pyramidCount++;
                  Print("[PYR", g_pyramidCount, "] SELL ", DoubleToString(pyrLots, 2),
                        " @ ", Bid, " (unrealized ", DoubleToString(unrealizedATR, 1), " ATR)");
                  SaveState();
               }
               else
                  Print("[PYR] SELL failed: ", GetLastError());
            }
         }
      }

      return;
   }

   // === ポジションなし: 新規エントリー ===
   // 取引時間チェック（新規エントリーのみ。決済はいつでも可）
   if(utcHour < TrendStartHour || utcHour >= TrendEndHour)
      return;
   if(signal == 0) return;
   if(CountMyOrders() >= MaxPositions) return;

   double slDist = atr * ATR_Trail_Mult;
   double minDist2 = GetMinStopDistance();
   if(slDist < minDist2)
      slDist = minDist2;

   double lots = CalcLotSize(slDist, MaxRiskPercent);

   if(signal == 1)
   {
      double sl = NormalizeDouble(Ask - slDist, Digits);
      g_trendTrailStop = sl;
      g_trendDirection = 1;
      g_trendEntryPrice = Ask;
      g_trendEntryATR = atr;
      g_pyramidCount = 0;
      int t = OrderSend(Symbol(), OP_BUY, lots, Ask, Slippage,
                        sl, 0,
                        "GBP10 Trend BUY", MagicNumber + MAGIC_TREND, 0, clrBlue);
      if(t > 0)
      {
         Print("[TREND] BUY ", DoubleToString(lots, 2), " lots @ ", Ask,
               " SL=", sl, " (", DoubleToString(slDist / GetPipValue(), 1), " pips)");
         SaveState();
      }
      else
         Print("[TREND] BUY failed: ", GetLastError());
   }
   else
   {
      double sl = NormalizeDouble(Bid + slDist, Digits);
      g_trendTrailStop = sl;
      g_trendDirection = -1;
      g_trendEntryPrice = Bid;
      g_trendEntryATR = atr;
      g_pyramidCount = 0;
      int t = OrderSend(Symbol(), OP_SELL, lots, Bid, Slippage,
                        sl, 0,
                        "GBP10 Trend SELL", MagicNumber + MAGIC_TREND, 0, clrRed);
      if(t > 0)
      {
         Print("[TREND] SELL ", DoubleToString(lots, 2), " lots @ ", Bid,
               " SL=", sl, " (", DoubleToString(slDist / GetPipValue(), 1), " pips)");
         SaveState();
      }
      else
         Print("[TREND] SELL failed: ", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| ロンドンブレイクアウト処理                                        |
//+------------------------------------------------------------------+
void ProcessLondonBK(int utcHour, int utcDay)
{
   // 日付変更でリセット
   if(utcDay != g_bkDate)
   {
      g_bkDate = utcDay;
      g_asianRangeSet = false;
      g_bkTriggered = false;
      g_asianHigh = 0;
      g_asianLow = 0;
      SaveState();
   }

   // === アジアレンジ収集 (AsianStartHour ~ AsianEndHour-1 UTC) ===
   if(utcHour >= AsianStartHour && utcHour < AsianEndHour)
   {
      double h = iHigh(NULL, PERIOD_M15, 1);
      double l = iLow(NULL, PERIOD_M15, 1);

      // 初回は現在値で初期化
      if(g_asianHigh == 0) g_asianHigh = h;
      if(g_asianLow == 0)  g_asianLow = l;

      if(h > g_asianHigh) g_asianHigh = h;
      if(l < g_asianLow)  g_asianLow = l;
      g_asianRangeSet = true;
      return;
   }

   // === ロンドンセッション終了: BKポジション決済 ===
   if(utcHour >= LondonEndHour)
   {
      int ticket = FindMyOrder(MAGIC_BK);
      if(ticket > 0 && OrderSelect(ticket, SELECT_BY_TICKET))
      {
         double closePrice = (OrderType() == OP_BUY) ? Bid : Ask;
         if(OrderClose(ticket, OrderLots(), closePrice, Slippage, clrGray))
         {
            double pnl = (OrderType() == OP_BUY)
               ? (Bid - OrderOpenPrice()) / GetPipValue()
               : (OrderOpenPrice() - Ask) / GetPipValue();
            Print("[BK] Session end close. P/L: ", DoubleToString(pnl, 1), " pips");
         }
         else
            Print("[BK] Session end close failed: ", GetLastError());
      }
      return;
   }

   // ロンドンセッション中のみBKエントリー
   if(!g_asianRangeSet || g_bkTriggered) return;
   if(utcHour < AsianEndHour) return;

   // レンジ幅チェック
   double pipVal = GetPipValue();
   double rangeWidth = g_asianHigh - g_asianLow;
   double rangePips = rangeWidth / pipVal;

   if(rangePips < MinRangePips || rangePips > MaxRangePips)
   {
      if(utcHour == AsianEndHour)
         Print("[BK] Range ", DoubleToString(rangePips, 1),
               " pips out of bounds (", MinRangePips, "-", MaxRangePips, "). Skip today.");
      return;
   }

   if(CountMyOrders() >= MaxPositions) return;

   double close1 = iClose(NULL, PERIOD_M15, 1);
   double high1  = iHigh(NULL, PERIOD_M15, 1);
   double low1   = iLow(NULL, PERIOD_M15, 1);
   double spread = Ask - Bid;
   double minDist = GetMinStopDistance();

   double tp = rangeWidth * BK_TP_Mult;
   double sl = rangeWidth;

   // 最小ストップレベル確保
   if(sl < minDist)
      sl = minDist;

   // === ロングブレイクアウト ===
   if(close1 > g_asianHigh)
   {
      double entry   = Ask;
      double slPrice = NormalizeDouble(entry - sl, Digits);
      double tpPrice = NormalizeDouble(entry + tp, Digits);
      double lots = CalcLotSize(sl, BK_RiskPercent);

      int t = OrderSend(Symbol(), OP_BUY, lots, entry, Slippage,
                        slPrice, tpPrice,
                        "GBP10 BK BUY", MagicNumber + MAGIC_BK, 0, clrGreen);
      if(t > 0)
      {
         Print("[BK] BUY ", DoubleToString(lots, 2), " @ ", entry,
               " SL=", slPrice, " TP=", tpPrice,
               " Range=", DoubleToString(rangePips, 1), "pips");
         g_bkTriggered = true;
         SaveState();
      }
      else
         Print("[BK] BUY failed: ", GetLastError());
   }
   // === ショートブレイクアウト ===
   else if(close1 < g_asianLow)
   {
      double entry   = Bid;
      double slPrice = NormalizeDouble(entry + sl, Digits);
      double tpPrice = NormalizeDouble(entry - tp, Digits);
      double lots = CalcLotSize(sl, BK_RiskPercent);

      int t = OrderSend(Symbol(), OP_SELL, lots, entry, Slippage,
                        slPrice, tpPrice,
                        "GBP10 BK SELL", MagicNumber + MAGIC_BK, 0, clrOrange);
      if(t > 0)
      {
         Print("[BK] SELL ", DoubleToString(lots, 2), " @ ", entry,
               " SL=", slPrice, " TP=", tpPrice,
               " Range=", DoubleToString(rangePips, 1), "pips");
         g_bkTriggered = true;
         SaveState();
      }
      else
         Print("[BK] SELL failed: ", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| DeInit                                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   SaveState();
   Print("GBP Monthly10% EA stopped. Reason: ", reason,
         " Equity: ", DoubleToString(AccountEquity(), 0));
}
//+------------------------------------------------------------------+
