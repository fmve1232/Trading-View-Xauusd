# MT5 line (operator, 2026-11-27): free, no calculation limit

TradingView's free plan stops a script after 20 seconds (F-A94). MetaTrader 5 runs indicators on the operator's own
Windows PC, so there is no such limit, and it shows the broker's own prices (Exness `XAUUSDm`), the ones traded.

**Display only (A7):** the system of record is the website. These files copy its rules; they never count as evidence.

| Build | File | What |
|---|---|---|
| M1 (2026-11-27) | `XAUUSD_Quantum_H2.mq5` | Stage 1: the H2 / arm H3 sweep-to-value signal (trend 1H / 4H / 1D, 5-bar swing sweeps, 100-bar volume profile), BUY / SELL arrows, POC / VAH / VAL, the last signal's entry / SL / TP1 / TP2, a checklist panel, pop-up and phone alerts |

Planned: Stage 2, the Master's engine and dashboard, then Visuals' strip. Each stage is checked against the website's
own code before it is sent.

## Install (Windows, once per build)
1. MT5 desktop -> **F4** (MetaEditor) -> **File -> New -> Custom Indicator** -> any name -> Finish.
2. Select everything in the new file, paste the `.mq5` text over it, press **F7** (Compile). Expect `0 errors`.
   (Or copy the `.mq5` into `File -> Open Data Folder -> MQL5\Indicators` and compile it there.)
3. MT5 -> **Navigator -> Indicators** -> drag it onto an `XAUUSDm` M15 chart (15m is the decision timeframe).
4. If the panel is empty at first: MT5 is still downloading H1 history. Switch the chart to H1 and back once.

## Phone alerts (free)
1. Phone MT5 app -> Settings -> Messages: copy the **MetaQuotes ID**.
2. Desktop: Tools -> Options -> Notifications: tick *Enable Push Notifications*, paste the ID, *Test*.
Alerts fire only while the desktop MT5 is running (the PC on). A signal is announced once, when its bar closes.

## What it shows
- Lime arrow under a bar = H2 BUY at that bar's close; red arrow above = H2 SELL. The forming bar never signals.
- Gold line = POC of the last 100 bars; grey dotted = VAH / VAL.
- Dashed lines from the last signal: entry (white), SL (red), TP1 / TP2 (green).
- Panel: trend scores 1H / 4H / 1D, current swing low / high, value position, the BUY and SELL checklists
  (trend, swing, sweep, value, risk), the last signal and its plan.

## How it was checked (`tools/h2_mt5_check.py`)
- The website (read-only, its own store) gives the reference arm H3 signals on 15m; a statement-for-statement Python
  copy of the `.mq5` runs on the same bars: **53 of 53 signals, same direction, SL, TP1, TP2 and swept level**.
- 4H bars are built on the New York 17:00 grid exactly as the website builds them; MT5's own H4 (UTC grid) is detected
  as different (control).
- 1D bars: the website's daily bars (Twelve Data's own feed) close with the New York 17:00 session (median gap $0.66 on
  192 days), not on UTC days ($4.71), so the `.mq5` builds 1D from H1 on the NY trading day.
- NOT checked here: the MQL5 compile (no MetaTrader in this environment; the operator's F7 is that test) and the
  operator's data: Exness prices and TICK volume differ from the website's Twelve Data prices and COMEX volume, so POC
  and therefore some signals can differ on the terminal. That is a data difference, not a rule difference.
