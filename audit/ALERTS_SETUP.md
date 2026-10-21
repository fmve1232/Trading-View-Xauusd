# Alerts: what fires, and how to set it up in TradingView (v85)

## What the Master sends: ONE alert covers everything

Every Master `alert()` call is `alert.freq_once_per_bar_close`. It fires once, when the bar closes, on the confirmed
value, and it never fires intrabar on a signal that disappears by the close. Prices are MT5 prices.

| Event | Message (example) |
|---|---|
| **Confirmed BUY / SELL** | `XAUUSD 15 BUY \| MT5 entry … SL … TP1 … TP2 … TP3 … (RR) P..% EV.. \| bias \| TQ.. \| session` |
| **DECISION change** | `XAUUSD 15 DECISION WAIT -> SELL \| MT5 plan …` (also BUY → NO TRADE when a veto engages) |
| **CHoCH / BOS / MSS** (first bar) | `XAUUSD 15 CHoCH▼ \| info, not a DECISION` (BOS▲ / BOS▼, MSS▲ / MSS▼ alike) |
| **Pool sweep** (PDH / PDL, PWH / PWL, PMH / PML: wick through, close back) | `… SWEEP-HIGH \| info, not a DECISION` |
| **H2 SETUP** | `… \| H2 SETUP SELL entry … SL … TP1 … (MT5)` (rides in the event alert) |
| Risk lock / tracked outcome | `… RISK LOCK engaged …`, `… tracked SELL reached TP1 …` |

**Visuals** (needs a second alert, "Any alert() function call" on Visuals):
- **H2 swing sweeps**: `XAUUSD 15 H2-SWEEP-LOW 4118.74 (MT5) | trend DOWN | info, not a DECISION`. Since v85 it lives
  here, because the Master is at its token limit (F-A72).
- ✕ pivot sweeps.
- The 4H / PDH / PDL **touches**: these fire intrabar, the moment price touches, by design.
- The H2 BUY / SELL signals.

## Setup (do this AFTER pasting the new Master)

1. On the chart, open the Master's "…" menu → **Add alert** (or Alerts → +).
2. Condition: **XAUUSD Quantum 5.0** → **Any alert() function call**. Do not pick an alertcondition such as "Nexus Buy
   Signal": that carries less text.
3. Notifications: tick **Notify in app** (phone push via the TradingView app), and optionally email / pop-up.
4. Expiration: as long as your plan allows. Free-plan alerts can expire; renew them.
5. Create it on the **timeframe you trade** (15M is the registered one). The alert keeps the timeframe and settings it
   was created with.

## Things that silently break alerts

- **After every paste of a new Master, delete the old alert and create it again.** An alert keeps running the script
  version, inputs and timeframe it was created with.
- Changing an input (e.g. the MT5 offset) also needs the alert recreated.
- `Institutional Performance Mode` ON suppresses the alerts (it is OFF by default).
- **Plan limits:** the free plan allows very few technical (indicator) alerts. Sources disagree: one active technical
  alert per a TradingView post, while some guides say none on Basic. Check tradingview.com/pricing. With one alert,
  put it on the **Master**: it carries the confirmed signals, CHoCH and the engine's and H2's sweeps.
- Alerts fire on live bars only; nothing is sent for history.
