# Data integrity audit (2026-11-01)

Executed on `market-data` @ `0bb2c8a96` and `research-data` @ `d15e2b800`. The checks are: duplicates, ordering,
NaN, OHLC consistency, non-positive prices, grid alignment, gaps, returns beyond 8σ, flat bars and market-shut bars.
`audit/INSTITUTIONAL_AUDIT_2026-10-31.md` §4 has the per-series table.

| Area | Finding | Status |
|---|---|---|
| Gold, Twelve Data XAU/USD (5m / 15m / 60m / 1d) | 0 duplicates, 0 NaN, 0 inconsistent OHLC | OK |
| Weekend / closure quote bars | The free feed prints quotes 24/7: 1,682 shut-window bars on 60m, median range $0.27 (weekdays $14.90) | **Removed before the engine** (`sources.trading_week_only`), verified |
| Reopen bar | The first print after a closure is the stale quote | Repaired from 5-minute bars (D-09) |
| Yahoo off-grid snapshots | Latest-quote rows stored as bars | Dropped (`drop_offgrid`, D-10) |
| Cross-assets (DXY, EURUSD, GC, SI, SPX, TNX, VIX) | Clean. SPX / TNX hourly bars sit on :30 / :20 (Yahoo's grid) | `align` is as-of, so this is safe |
| Research history 2020-01-24 → 2026-10-22 (1h 42,835; 15min 170,863 bars) | 3,117 / 12,242 shut-window bars in 2025–26 only (a feed-format change) | **Fixed:** `research.history.load()` filters them |
| Large moves | 2026-01-29 −5.96% (1h), 2021-08-08 flash crash, 2020-03-16 | Plausible real events. Not cross-checked against a second source in this session (the `xcheck-dukascopy` workflow does it on GitHub) |
| Volume | Spot has no centralised volume. The engine uses COMEX GC futures volume bar for bar (D-07); missing = 0, counted | Labelled; **no true order flow exists in this data** |
| Bid / ask | Not stored; prices are single quotes | Spread is modelled (0.30 / 0.50), not observed. The MT5 evidence (`audit/COST_PROFILES.md` §4) would measure it |
| Ticks | None | Intrabar order unknown. A 5-minute re-walk is the finest check available |
| Fallback source | Yahoo `GC=F` if Twelve Data fails | Recorded per trade; not counted (§7) |
| Price cross-check | Twelve Data against OANDA (TradingView) on 2 Oct NFP: PDH within $0.57 | One spot check; the `xcheck-prices` / `xcheck-dukascopy` workflows run weekly |

**Point-in-time.**

- Every engine input is as-of its own bar's close.
- HTF and cross-asset values use the last bar opened before the chart bar's close (D-01).
- COT is keyed on its Friday release (D-05).
- FRED daily series in the macro panel are display only.

**Gaps for the research programme.**

1. **No tick or bid/ask history:** TP/SL ordering cannot be proven inside a bar, so such bars must be labelled
   AMBIGUOUS in research.
2. **No true order-flow data** (OTC spot). COMEX GC volume is a proxy only.
3. **Twelve Data intraday history starts 2020-01-24.**
4. **No point-in-time news archive** beyond the dated calendar list. Event studies need a verified historical
   calendar (BLS / Fed archives).
