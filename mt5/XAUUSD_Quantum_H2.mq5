//+------------------------------------------------------------------+
//| XAUUSD Quantum H2 - MT5 Stage 1 (sweep-to-value)                 |
//| BUILD M1.1 (2026-11-27)                                          |
//|  M1.1 changes plumbing only; the rule below is M1's, unchanged:  |
//|   * a signal bar that closes during a full recalculation         |
//|     (prev_calculated = 0) still alerts (M1 skipped it);          |
//|   * each signal alerts once, also across re-attach / restart     |
//|     (terminal global variable per symbol and timeframe);         |
//|   * progress is tracked by bar TIME, not index (the chart's      |
//|     max-bars limit shifts indexes);                              |
//|   * H1 history must be synchronised before the trend is read;    |
//|   * panel shows the H1 history start and the 1D bar count;       |
//|   * alert text says display copy, not validated.                 |
//|                                                                  |
//| DISPLAY ONLY. The system of record is the website (A7); this is a|
//| copy of its arm H3 rule (= the TradingView line's H2 block) for  |
//| the operator's own MT5 terminal (Exness, XAUUSDm, Windows).      |
//|                                                                  |
//| The rule, as written in the website's quantum/arm_h3.py:         |
//|  LONG at the close of bar i (SHORT is the exact mirror):         |
//|   trend  >= 2 of the 1H / 4H / 1D scores >= 60 (score = 40       |
//|          [c1 > EMA200] + 40 [EMA20 > EMA100] + 20 [c1 > EMA20],  |
//|          on the last completed bar of that timeframe; none = 50) |
//|   sweep  low < swing low and close > swing low; the swing low is |
//|          the last 5-bar pivot low not yet traded through, as it  |
//|          stood before bar i                                      |
//|   value  close <= POC (100 bars, 40 bins, typical price, 70% VA) |
//|   risk   R = close - (low - 0.15 ATR14), 0.5 ATR <= R <= 5 ATR   |
//|  Plan: entry close; stop entry - R; TP1 = max(POC, entry + R);   |
//|        TP2 = max(VAH, entry + 2R).                               |
//|                                                                  |
//| Bars as the website builds them (quantum/data/market.py):        |
//|  1H = the broker's H1; 4H = 1H grouped on New York wall time from|
//|  17:00 (17, 21, 01, 05, 09, 13); 1D = the NY 17:00 trading day,  |
//|  dated 00:00 UTC like the website's daily bars. Each chart bar   |
//|  reads the last higher bar that OPENED before the chart bar      |
//|  CLOSED, and in it close[1] and the EMAs of close[1] (no         |
//|  look-ahead).                                                    |
//|  EMAs are seeded with the SMA of their first n values (Pine).    |
//|                                                                  |
//| Known differences from the website (by data, not by rule):       |
//|  * prices are Exness's, the website's are Twelve Data XAU/USD;   |
//|  * volume is the broker's TICK volume; the website uses COMEX    |
//|    futures volume, so POC / VAH / VAL (and therefore signals)    |
//|    can differ. Neither is "true" spot gold volume.               |
//+------------------------------------------------------------------+
#property copyright   "Display only - the record is the website (A7)"
#property version     "1.10"
#property description "H2 sweep-to-value: trend 1H/4H/1D, 5-bar swing sweeps, 100-bar volume profile. Display only."
#property indicator_chart_window
#property indicator_buffers 5
#property indicator_plots   5

#property indicator_label1  "H2 BUY"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLime
#property indicator_width1  2
#property indicator_label2  "H2 SELL"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrRed
#property indicator_width2  2
#property indicator_label3  "POC (100 bars)"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrGold
#property indicator_style3  STYLE_SOLID
#property indicator_width3  1
#property indicator_label4  "VAH"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrSlateGray
#property indicator_style4  STYLE_DOT
#property indicator_label5  "VAL"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrSlateGray
#property indicator_style5  STYLE_DOT

//--- inputs (new inputs go at the END: MT5 keeps saved values by name, but keep the habit)
input int    InpServerGmtOffset = -99;   // Broker server GMT offset in hours (-99 = detect automatically)
input bool   InpAlertPopup      = true;  // Pop-up alert on a new H2 signal
input bool   InpAlertPush       = true;  // Push alert to the MT5 phone app (set the MetaQuotes ID first)
input bool   InpShowValueLines  = true;  // Draw POC / VAH / VAL
input bool   InpShowPanel       = true;  // Show the H2 panel
input int    InpPanelCorner     = 0;     // Panel corner: 0 top-left, 1 top-right, 2 bottom-left, 3 bottom-right
input int    InpPanelFontSize   = 9;     // Panel font size
input bool   InpShowPlanLines   = true;  // Draw entry / SL / TP1 / TP2 of the last signal
input int    InpMaxBars         = 20000; // Chart bars to calculate (history)

//--- frozen constants (the website's rule; do not tune)
#define PIVOT      5
#define STOP_ATR   0.15
#define R_MIN_ATR  0.5
#define R_MAX_ATR  5.0
#define VP_BARS    100
#define VP_BINS    40
#define VA_SHARE   0.70
#define ATR_LEN    14
#define NA         (-1.0e300)

double BufBuy[], BufSell[], BufPoc[], BufVah[], BufVal[];

//--- higher-timeframe series: open time (server) and the trend score on that bar (0 = 1H, 1 = 4H, 2 = 1D)
struct HtfSeries
{
   datetime open[];
   double   score[];
   int      n;
};
HtfSeries g_ht[3];

//--- chart-timeframe state
double   g_atr[];             // ATR14 per chart bar
double   g_swH = NA, g_swL = NA;
datetime g_doneTime = 0;      // open time of the last chart bar fully processed (0 = none)
int      g_offSec = 0;        // server - UTC, seconds
datetime g_lastAlertBar = 0;  // open time of the last bar alerted (kept in a terminal global variable)
datetime g_h1Start = 0;       // first H1 bar loaded (server time)
int      g_syncTries = 0;     // calls that found H1 not yet synchronised

//--- last signal (for the panel and the plan lines)
int      g_sigDir = 0; datetime g_sigTime = 0; double g_sigEntry = NA, g_sigSl = NA, g_sigTp1 = NA, g_sigTp2 = NA, g_sigSwept = NA;
//--- last bar checklist
bool     g_ckL[5], g_ckS[5];
double   g_sc[3];
double   g_poc = NA, g_vah = NA, g_val = NA;

string   PFX = "QH2_";

bool IsNA(const double x) { return x <= -1.0e299; }
int  IMax(const int a, const int b) { return a > b ? a : b; }
int  IMin(const int a, const int b) { return a < b ? a : b; }

//+------------------------------------------------------------------+
//| New York UTC offset (seconds) at a UTC time: -4h in US DST, else -5h |
//+------------------------------------------------------------------+
datetime NthSunday(const int year, const int mon, const int nth)
{
   MqlDateTime d; d.year = year; d.mon = mon; d.day = 1; d.hour = 0; d.min = 0; d.sec = 0;
   datetime first = StructToTime(d);
   MqlDateTime f; TimeToStruct(first, f);
   int firstSun = 1 + (7 - f.day_of_week) % 7;
   d.day = firstSun + 7 * (nth - 1);
   return StructToTime(d);
}

int NyOffset(const datetime utc)
{
   MqlDateTime t; TimeToStruct(utc, t);
   datetime start = NthSunday(t.year, 3, 2) + 7 * 3600;   // 02:00 EST = 07:00 UTC
   datetime end   = NthSunday(t.year, 11, 1) + 6 * 3600;  // 02:00 EDT = 06:00 UTC
   return (utc >= start && utc < end) ? -4 * 3600 : -5 * 3600;
}

//+------------------------------------------------------------------+
//| EMA seeded by the SMA of its first n values (Pine / website)     |
//+------------------------------------------------------------------+
void EmaSeeded(const double &x[], const int n, const int len, double &out[])
{
   ArrayResize(out, n);
   double alpha = 2.0 / (len + 1.0);
   double prev = NA;
   int run = 0; double sum = 0.0;
   for(int i = 0; i < n; i++)
   {
      if(IsNA(prev))
      {
         // seed = sma(x, len) at i: needs len valid values ending at i
         if(IsNA(x[i])) { run = 0; sum = 0.0; out[i] = NA; continue; }
         run++; sum += x[i];
         if(run > len) sum -= x[i - len];
         out[i] = (run >= len) ? sum / len : NA;
         prev = out[i];
      }
      else
      {
         out[i] = IsNA(x[i]) ? NA : alpha * x[i] + (1.0 - alpha) * prev;
         prev = out[i];
      }
   }
}

//+------------------------------------------------------------------+
//| Build one HTF series from H1 bars and score each bar             |
//| kind: 0 = 1H, 1 = 4H (NY 17:00 grid), 2 = 1D (NY trading day)    |
//+------------------------------------------------------------------+
void BuildHtf(const int kind, const MqlRates &h1[], const int n1)
{
   datetime op[]; double cl[]; int n = 0;
   ArrayResize(op, n1); ArrayResize(cl, n1);
   long curKey = LONG_MIN;
   for(int i = 0; i < n1; i++)
   {
      datetime utc = h1[i].time - g_offSec;
      long key; datetime label;
      if(kind == 0) { key = (long)utc; label = h1[i].time; }
      else if(kind == 1)
      {
         int ny = NyOffset(utc);
         long w7 = (long)utc + ny + 7 * 3600;              // NY wall clock + 7h: the session starts at 00:00
         long b  = w7 - (w7 % (4 * 3600));
         key = b;
         label = (datetime)(b - 7 * 3600 - ny + g_offSec);
      }
      else
      {
         // the New York trading day (17:00 to 17:00), dated like the website's daily bars: 00:00 UTC of its date.
         // Measured on the website's store (mt5/tools/h2_mt5_check.py 2): its Twelve Data daily closes are this
         // session's closes (median gap $0.66), not UTC calendar days ($5.84).
         long w7 = (long)utc + NyOffset(utc) + 7 * 3600;
         long d = (w7 / 86400) * 86400;
         key = d;
         label = (datetime)(d + g_offSec);
      }
      if(key != curKey) { op[n] = label; cl[n] = h1[i].close; n++; curKey = key; }
      else cl[n - 1] = h1[i].close;                    // close = last H1 close of the bucket
   }
   ArrayResize(op, n); ArrayResize(cl, n);
   double c1[]; ArrayResize(c1, n);
   for(int i = 0; i < n; i++) c1[i] = (i == 0) ? NA : cl[i - 1];
   double e20[], e100[], e200[];
   EmaSeeded(c1, n, 20, e20); EmaSeeded(c1, n, 100, e100); EmaSeeded(c1, n, 200, e200);
   ArrayResize(g_ht[kind].open, n); ArrayResize(g_ht[kind].score, n);
   for(int i = 0; i < n; i++)
   {
      g_ht[kind].open[i] = op[i];
      double c = c1[i];
      if(IsNA(c)) { g_ht[kind].score[i] = 50.0; continue; }
      double s = 0.0;
      if(!IsNA(e200[i]) && c > e200[i]) s += 40.0;
      if(!IsNA(e20[i]) && !IsNA(e100[i]) && e20[i] > e100[i]) s += 40.0;
      if(!IsNA(e20[i]) && c > e20[i]) s += 20.0;
      g_ht[kind].score[i] = s;
   }
   g_ht[kind].n = n;
}

//--- the last HTF bar that opened strictly before t (server time); -1 if none
int HtfIndexBefore(const int kind, const datetime t)
{
   int lo = 0, hi = g_ht[kind].n - 1, ans = -1;
   while(lo <= hi)
   {
      int mid = (lo + hi) / 2;
      if(g_ht[kind].open[mid] < t) { ans = mid; lo = mid + 1; }
      else hi = mid - 1;
   }
   return ans;
}

bool LoadHtf()
{
   MqlRates h1[];
   int want = IMin(Bars(_Symbol, PERIOD_H1), 40000);       // Bars() also starts the H1 download if needed
   if(want < 300) return false;
   int got = CopyRates(_Symbol, PERIOD_H1, 0, want, h1);   // oldest first
   if(got < 300) return false;
   //--- wait (a few calls) until the terminal says the H1 series is complete, so the trend is not read from a
   //--- partial download; after 50 calls proceed anyway (the panel then shows "H1 not synchronised")
   if(!(bool)SeriesInfoInteger(_Symbol, PERIOD_H1, SERIES_SYNCHRONIZED) && g_syncTries < 50) { g_syncTries++; return false; }
   g_h1Start = h1[0].time;
   for(int k = 0; k < 3; k++) BuildHtf(k, h1, got);
   return true;
}

string GvName() { return PFX + _Symbol + "_" + IntegerToString(PeriodSeconds(_Period)); }

//+------------------------------------------------------------------+
//| Strict pivots (Pine ta.pivothigh / pivotlow, 5 / 5), reported on  |
//| bar i for the pivot at i - 5                                     |
//+------------------------------------------------------------------+
double PivotHigh(const double &h[], const int i)
{
   if(i < 2 * PIVOT) return NA;
   int c = i - PIVOT;
   for(int k = c - PIVOT; k <= i; k++) if(k != c && !(h[c] > h[k])) return NA;
   return h[c];
}
double PivotLow(const double &l[], const int i)
{
   if(i < 2 * PIVOT) return NA;
   int c = i - PIVOT;
   for(int k = c - PIVOT; k <= i; k++) if(k != c && !(l[c] < l[k])) return NA;
   return l[c];
}

//--- the 100-bar volume profile at bar i (the website's construction); false if not available
bool VolumeProfile(const int i, const double &h[], const double &l[], const double &c[], const long &v[],
                   double &poc, double &vah, double &val)
{
   if(i < VP_BARS - 1) return false;
   double hi = h[i], lo = l[i];
   for(int k = i - VP_BARS + 1; k <= i; k++) { if(h[k] > hi) hi = h[k]; if(l[k] < lo) lo = l[k]; }
   double bs = (hi - lo) / VP_BINS;
   if(!(bs > 0.0)) return false;
   double vols[VP_BINS]; ArrayInitialize(vols, 0.0);
   for(int k = i - VP_BARS + 1; k <= i; k++)
   {
      int b = (int)(((h[k] + l[k] + c[k]) / 3.0 - lo) / bs);
      b = IMax(0, IMin(b, VP_BINS - 1));
      vols[b] += (double)v[k];
   }
   int pk = 0; double mx = 0.0, tot = 0.0;
   for(int b = 0; b < VP_BINS; b++) { tot += vols[b]; if(vols[b] > mx) { mx = vols[b]; pk = b; } }
   double cum = mx, tgt = tot * VA_SHARE;
   int blo = pk, bhi = pk;
   while(cum < tgt && (blo > 0 || bhi < VP_BINS - 1))
   {
      double vb = blo > 0 ? vols[blo - 1] : -1.0;
      double va = bhi < VP_BINS - 1 ? vols[bhi + 1] : -1.0;
      if(va >= vb && bhi < VP_BINS - 1) { bhi++; cum += va; }
      else if(blo > 0) { blo--; cum += vb; }
      else break;
   }
   poc = lo + bs * (pk + 0.5);
   vah = lo + bs * (bhi + 0.5);
   val = lo + bs * (blo + 0.5);
   return true;
}

//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, BufBuy, INDICATOR_DATA);
   SetIndexBuffer(1, BufSell, INDICATOR_DATA);
   SetIndexBuffer(2, BufPoc, INDICATOR_DATA);
   SetIndexBuffer(3, BufVah, INDICATOR_DATA);
   SetIndexBuffer(4, BufVal, INDICATOR_DATA);
   PlotIndexSetInteger(0, PLOT_ARROW, 233);
   PlotIndexSetInteger(1, PLOT_ARROW, 234);
   PlotIndexSetInteger(0, PLOT_ARROW_SHIFT, 12);
   PlotIndexSetInteger(1, PLOT_ARROW_SHIFT, -12);
   for(int p = 0; p < 5; p++) PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   if(!InpShowValueLines) for(int p = 2; p < 5; p++) PlotIndexSetInteger(p, PLOT_DRAW_TYPE, DRAW_NONE);
   IndicatorSetString(INDICATOR_SHORTNAME, "Quantum H2 MT5");
   g_offSec = (InpServerGmtOffset == -99) ? (int)MathRound((double)(TimeTradeServer() - TimeGMT()) / 3600.0) * 3600
                                           : InpServerGmtOffset * 3600;
   g_lastAlertBar = GlobalVariableCheck(GvName()) ? (datetime)GlobalVariableGet(GvName()) : 0;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { ObjectsDeleteAll(0, PFX); Comment(""); }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   if(rates_total < VP_BARS + 2 * PIVOT + 2) return 0;
   int last = rates_total - 2;                        // the last CLOSED bar; the forming bar never signals
   bool fresh = (prev_calculated == 0 || g_doneTime == 0 || time[last] < g_doneTime);
   if(!fresh && time[last] == g_doneTime) { UpdatePanel(time, close, last, rates_total); return rates_total; }

   if(!LoadHtf()) return 0;                           // H1 history not loaded yet: try again on the next tick

   int first = IMax(0, rates_total - 1 - InpMaxBars);
   //--- continue after the last processed bar, found by its TIME (indexes shift when the chart drops old bars);
   //--- if it is not found, the history changed: recalculate everything
   int startBar = first;
   if(!fresh)
   {
      int k = last;
      while(k > first && time[k - 1] > g_doneTime) k--;
      if(k > first && time[k - 1] == g_doneTime) startBar = k; else fresh = true;
   }
   if(fresh)
   {
      ArrayInitialize(BufBuy, EMPTY_VALUE); ArrayInitialize(BufSell, EMPTY_VALUE);
      ArrayInitialize(BufPoc, EMPTY_VALUE); ArrayInitialize(BufVah, EMPTY_VALUE); ArrayInitialize(BufVal, EMPTY_VALUE);
      g_swH = NA; g_swL = NA; g_sigDir = 0; g_doneTime = 0; startBar = first;
   }
   BufBuy[rates_total - 1] = EMPTY_VALUE; BufSell[rates_total - 1] = EMPTY_VALUE;
   BufPoc[rates_total - 1] = EMPTY_VALUE; BufVah[rates_total - 1] = EMPTY_VALUE; BufVal[rates_total - 1] = EMPTY_VALUE;

   //--- ATR14 = RMA of the true range, seeded by the SMA of the first 14 (Pine ta.atr; TR of bar 0 = high - low)
   ArrayResize(g_atr, rates_total);
   double sumTr = 0.0;
   for(int i = 0; i < rates_total; i++)
   {
      double tr = (i == 0) ? high[i] - low[i]
                           : MathMax(high[i] - low[i], MathMax(MathAbs(high[i] - close[i - 1]), MathAbs(low[i] - close[i - 1])));
      if(i < ATR_LEN - 1) { sumTr += tr; g_atr[i] = NA; }
      else if(i == ATR_LEN - 1) { sumTr += tr; g_atr[i] = sumTr / ATR_LEN; }
      else g_atr[i] = (g_atr[i - 1] * (ATR_LEN - 1) + tr) / ATR_LEN;
   }

   for(int i = startBar; i <= last; i++)
   {
      double a = g_atr[i];
      //--- sweep against the swing as it stood before this bar
      bool sweepL = !IsNA(g_swL) && low[i] < g_swL && close[i] > g_swL;
      bool sweepH = !IsNA(g_swH) && high[i] > g_swH && close[i] < g_swH;
      double lvlL = g_swL, lvlH = g_swH;
      if(!IsNA(g_swL) && low[i] < g_swL) g_swL = NA;
      if(!IsNA(g_swH) && high[i] > g_swH) g_swH = NA;
      double pl = PivotLow(low, i), ph = PivotHigh(high, i);
      if(!IsNA(pl)) g_swL = pl;
      if(!IsNA(ph)) g_swH = ph;

      //--- trend: 1H / 4H / 1D scores on the last higher bar that opened before this bar closed
      datetime closeT = time[i] + PeriodSeconds(_Period);
      int upN = 0, dnN = 0; double sc[3];
      for(int k = 0; k < 3; k++)
      {
         int j = HtfIndexBefore(k, closeT);
         sc[k] = (j < 0) ? 50.0 : g_ht[k].score[j];
         if(sc[k] >= 60.0) upN++;
         if(sc[k] <= 40.0) dnN++;
      }
      bool trendUp = upN >= 2, trendDn = dnN >= 2;

      double poc = NA, vah = NA, val = NA;
      bool vp = VolumeProfile(i, high, low, close, tick_volume, poc, vah, val);
      BufPoc[i] = vp ? poc : EMPTY_VALUE; BufVah[i] = vp ? vah : EMPTY_VALUE; BufVal[i] = vp ? val : EMPTY_VALUE;

      bool aOk = !IsNA(a);
      double rl = (sweepL && aOk) ? close[i] - (low[i] - STOP_ATR * a) : NA;
      double rs = (sweepH && aOk) ? (high[i] + STOP_ATR * a) - close[i] : NA;
      bool riskL = !IsNA(rl) && rl >= R_MIN_ATR * a && rl <= R_MAX_ATR * a;
      bool riskS = !IsNA(rs) && rs >= R_MIN_ATR * a && rs <= R_MAX_ATR * a;
      bool isLong  = sweepL && trendUp && vp && close[i] <= poc && riskL;
      bool isShort = sweepH && trendDn && vp && close[i] >= poc && riskS;

      BufBuy[i] = EMPTY_VALUE; BufSell[i] = EMPTY_VALUE;
      if(isLong)
      {
         BufBuy[i] = low[i];
         g_sigDir = 1; g_sigTime = time[i]; g_sigEntry = close[i]; g_sigSl = close[i] - rl;
         g_sigTp1 = MathMax(poc, close[i] + rl); g_sigTp2 = MathMax(vah, close[i] + 2.0 * rl); g_sigSwept = lvlL;
      }
      else if(isShort)
      {
         BufSell[i] = high[i];
         g_sigDir = -1; g_sigTime = time[i]; g_sigEntry = close[i]; g_sigSl = close[i] + rs;
         g_sigTp1 = MathMin(poc, close[i] - rs); g_sigTp2 = MathMin(val, close[i] - 2.0 * rs); g_sigSwept = lvlH;
      }

      if(i == last)
      {
         g_ckL[0] = trendUp; g_ckL[1] = !IsNA(lvlL); g_ckL[2] = sweepL; g_ckL[3] = vp && close[i] <= poc; g_ckL[4] = riskL;
         g_ckS[0] = trendDn; g_ckS[1] = !IsNA(lvlH); g_ckS[2] = sweepH; g_ckS[3] = vp && close[i] >= poc; g_ckS[4] = riskS;
         for(int k = 0; k < 3; k++) g_sc[k] = sc[k];
         g_poc = vp ? poc : NA; g_vah = vp ? vah : NA; g_val = vp ? val : NA;
         //--- alert once per signal bar, and only if that bar closed within the last bar period (never for history,
         //--- also after a full recalculation); the last alerted bar is kept in a terminal global variable
         int per = PeriodSeconds(_Period);
         bool recent = (long)TimeCurrent() - ((long)time[i] + per) < (long)per;
         if((isLong || isShort) && recent && time[i] > g_lastAlertBar)
         {
            g_lastAlertBar = time[i];
            GlobalVariableSet(GvName(), (double)time[i]);
            string msg = StringFormat("%s %s H2 %s @ %s SL %s TP1 %s TP2 %s | bar %s | display copy, not validated",
                                      _Symbol, StringSubstr(EnumToString(_Period), 7),
                                      isLong ? "BUY" : "SELL", DoubleToString(g_sigEntry, _Digits), DoubleToString(g_sigSl, _Digits),
                                      DoubleToString(g_sigTp1, _Digits), DoubleToString(g_sigTp2, _Digits),
                                      TimeToString(time[i], TIME_DATE | TIME_MINUTES));
            if(InpAlertPopup) Alert(msg);
            if(InpAlertPush && !SendNotification(msg)) Print("QH2 push failed, error ", GetLastError(), " (check Tools -> Options -> Notifications)");
         }
      }
      g_doneTime = time[i];
   }
   UpdatePanel(time, close, last, rates_total);
   return rates_total;
}

//+------------------------------------------------------------------+
//| Panel and plan lines                                             |
//+------------------------------------------------------------------+
string P(const double x) { return IsNA(x) ? "-" : DoubleToString(x, _Digits); }
string Ck(const bool b) { return b ? "OK" : "no"; }

void Row(const int r, const string txt, const color clr)
{
   string name = PFX + "row" + IntegerToString(r);
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   }
   ENUM_BASE_CORNER cn = InpPanelCorner == 1 ? CORNER_RIGHT_UPPER : InpPanelCorner == 2 ? CORNER_LEFT_LOWER
                       : InpPanelCorner == 3 ? CORNER_RIGHT_LOWER : CORNER_LEFT_UPPER;
   bool right = (InpPanelCorner == 1 || InpPanelCorner == 3), lower = (InpPanelCorner >= 2);
   ObjectSetInteger(0, name, OBJPROP_CORNER, cn);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, right ? (lower ? ANCHOR_RIGHT_LOWER : ANCHOR_RIGHT_UPPER) : (lower ? ANCHOR_LEFT_LOWER : ANCHOR_LEFT_UPPER));
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 10);
   int step = (int)MathRound(InpPanelFontSize * 1.9);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 20 + (lower ? (10 - r) : r) * step);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpPanelFontSize);
   ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

void PlanLine(const string id, const double price, const datetime t0, const color clr, const string lbl)
{
   string name = PFX + "plan_" + id;
   if(!InpShowPlanLines || g_sigDir == 0 || IsNA(price)) { ObjectDelete(0, name); return; }
   datetime t1 = t0 + 20 * PeriodSeconds(_Period);
   if(ObjectFind(0, name) < 0) ObjectCreate(0, name, OBJ_TREND, 0, t0, price, t1, price);
   ObjectMove(0, name, 0, t0, price); ObjectMove(0, name, 1, t1, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, lbl + " " + P(price));
}

void UpdatePanel(const datetime &time[], const double &close[], const int last, const int rates_total)
{
   PlanLine("entry", g_sigEntry, g_sigTime, clrWhite, "entry");
   PlanLine("sl", g_sigSl, g_sigTime, clrRed, "SL");
   PlanLine("tp1", g_sigTp1, g_sigTime, clrLime, "TP1");
   PlanLine("tp2", g_sigTp2, g_sigTime, clrSpringGreen, "TP2");
   if(!InpShowPanel) { for(int r = 0; r < 11; r++) ObjectDelete(0, PFX + "row" + IntegerToString(r)); ChartRedraw(); return; }
   int upN = 0, dnN = 0;
   for(int k = 0; k < 3; k++) { if(g_sc[k] >= 60.0) upN++; if(g_sc[k] <= 40.0) dnN++; }
   string trend = upN >= 2 ? "UP" : dnN >= 2 ? "DOWN" : "MIXED";
   color cT = upN >= 2 ? clrLime : dnN >= 2 ? clrTomato : clrSilver;
   Row(0, "QUANTUM H2 | MT5 | display only (record = website)", clrSilver);
   Row(1, StringFormat("Trend %s   1H %.0f | 4H %.0f | 1D %.0f", trend, g_sc[0], g_sc[1], g_sc[2]), cT);
   Row(2, "Swing low " + P(g_swL) + "   swing high " + P(g_swH), clrWhite);
   string pos = IsNA(g_poc) ? "building" : close[last] > g_vah ? "above value" : close[last] < g_val ? "below value"
              : close[last] >= g_poc ? "over POC" : "under POC";
   Row(3, "Value " + pos + "   POC " + P(g_poc) + "  VAH " + P(g_vah) + "  VAL " + P(g_val), clrGold);
   Row(4, StringFormat("BUY  check  trend %s swing %s sweep %s value %s risk %s", Ck(g_ckL[0]), Ck(g_ckL[1]), Ck(g_ckL[2]), Ck(g_ckL[3]), Ck(g_ckL[4])), clrSilver);
   Row(5, StringFormat("SELL check  trend %s swing %s sweep %s value %s risk %s", Ck(g_ckS[0]), Ck(g_ckS[1]), Ck(g_ckS[2]), Ck(g_ckS[3]), Ck(g_ckS[4])), clrSilver);
   if(g_sigDir == 0) Row(6, "Last signal: none in the loaded history", clrSilver);
   else
   {
      int ago = (int)((time[last] - g_sigTime) / PeriodSeconds(_Period));
      Row(6, StringFormat("Last %s %s (%d bars ago)  swept %s", g_sigDir > 0 ? "BUY" : "SELL",
                          TimeToString(g_sigTime, TIME_DATE | TIME_MINUTES), ago, P(g_sigSwept)), g_sigDir > 0 ? clrLime : clrTomato);
   }
   Row(7, g_sigDir == 0 ? " " : "Entry " + P(g_sigEntry) + "  SL " + P(g_sigSl) + "  TP1 " + P(g_sigTp1) + "  TP2 " + P(g_sigTp2), clrWhite);
   Row(8, StringFormat("Server GMT%+d | 4H and 1D on the NY 17:00 grid", g_offSec / 3600), clrDimGray);
   Row(9, "Volume = broker tick volume (website: COMEX); POC can differ", clrDimGray);
   bool synced = (bool)SeriesInfoInteger(_Symbol, PERIOD_H1, SERIES_SYNCHRONIZED);
   int nD = g_ht[2].n;
   Row(10, StringFormat("H1 from %s%s | 1D bars %d%s", TimeToString(g_h1Start, TIME_DATE), synced ? "" : " (H1 not synchronised)",
                        nD, nD < 201 ? " (EMA200 not seeded)" : ""), (synced && nD >= 201) ? clrDimGray : clrOrange);
   ChartRedraw();
}
//+------------------------------------------------------------------+
