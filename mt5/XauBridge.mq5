//+------------------------------------------------------------------+
//| XauBridge.mq5                                                     |
//| Sends this chart's broker ticks to your XAU relay, so the website |
//| shows your MT5 price, tick volume and a tick footprint.           |
//|                                                                   |
//| READ-ONLY: this Expert Advisor never opens, changes or closes a   |
//| trade. It only reads ticks and posts them to RelayUrl.            |
//|                                                                   |
//| Setup (once):                                                     |
//|  1. Tools > Options > Expert Advisors: tick "Allow WebRequest for |
//|     listed URL" and add https://xau-stream.fm-ve1232.workers.dev  |
//|  2. Attach to an XAUUSDm chart and set PushKey to the same value  |
//|     as the GitHub secret MT5_PUSH_KEY (Algo Trading may stay off).|
//+------------------------------------------------------------------+
#property copyright "XAUUSD Quantum"
#property version   "1.00"
#property description "Read-only: posts this chart's ticks to your XAU relay. Never trades."

input string RelayUrl    = "https://xau-stream.fm-ve1232.workers.dev/mt5"; // relay address (must be allowed in Options)
input string PushKey     = "";                                             // same value as the MT5_PUSH_KEY secret
input int    PushEveryMs = 2000;                                           // 2000 keeps Cloudflare's free plan under its daily limit

long   g_last_msc = 0;     // time of the last tick the relay accepted
int    g_digits   = 2;
int    g_fail     = 0;

int OnInit()
  {
   if(StringLen(PushKey) < 16)
     {
      Print("XauBridge: set PushKey to the MT5_PUSH_KEY secret (16+ characters).");
      return(INIT_PARAMETERS_INCORRECT);
     }
   g_digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   int ms = PushEveryMs < 1000 ? 1000 : PushEveryMs;
   if(!EventSetMillisecondTimer(ms))
     {
      Print("XauBridge: could not start the timer.");
      return(INIT_FAILED);
     }
   Print("XauBridge: sending ", _Symbol, " ticks to ", RelayUrl, " every ", ms, " ms (read-only).");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

// Ticks are collected with CopyTicks in OnTimer, so none are lost between pushes.
void OnTick()
  {
  }

void OnTimer()
  {
   MqlTick ticks[];
   int n;
   if(g_last_msc == 0)
      n = CopyTicks(_Symbol, ticks, COPY_TICKS_ALL, 0, 500);                      // first push: the latest 500 ticks
   else
      n = CopyTicks(_Symbol, ticks, COPY_TICKS_ALL, (ulong)(g_last_msc + 1), 2000); // then only new ticks
   if(n <= 0)
      return;                                                                        // market closed or no new tick

   string body = "{\"sym\":\"" + _Symbol + "\",\"server\":\"" + AccountInfoString(ACCOUNT_SERVER) +
                 "\",\"digits\":" + IntegerToString(g_digits) + ",\"ticks\":[";
   for(int i = 0; i < n; i++)
     {
      if(i > 0)
         body += ",";
      body += "[" + IntegerToString(ticks[i].time_msc) + "," +
              DoubleToString(ticks[i].bid, g_digits) + "," +
              DoubleToString(ticks[i].ask, g_digits) + "," +
              DoubleToString(ticks[i].last, g_digits) + "," +
              IntegerToString((long)ticks[i].volume) + "," +
              IntegerToString((long)ticks[i].flags) + "]";
     }
   body += "]}";

   char data[];
   char result[];
   string result_headers;
   int len = StringToCharArray(body, data, 0, StringLen(body), CP_UTF8);
   ArrayResize(data, len);
   string headers = "Content-Type: application/json\r\nX-Push-Key: " + PushKey + "\r\n";

   ResetLastError();
   int code = WebRequest("POST", RelayUrl, headers, 5000, data, result, result_headers);
   if(code == 200)
     {
      g_last_msc = ticks[n - 1].time_msc;
      g_fail = 0;
     }
   else
     {
      g_fail++;
      if(g_fail == 1 || g_fail % 30 == 0)   // do not flood the Experts log
        {
         if(code == -1)
            Print("XauBridge: WebRequest failed (error ", GetLastError(), "). Add https://xau-stream.fm-ve1232.workers.dev in Tools > Options > Expert Advisors > Allow WebRequest.");
         else
            if(code == 403)
               Print("XauBridge: relay refused the PushKey (HTTP 403). It must equal the MT5_PUSH_KEY secret.");
            else
               Print("XauBridge: relay answered HTTP ", code, ": ", CharArrayToString(result));
        }
     }
  }
//+------------------------------------------------------------------+
