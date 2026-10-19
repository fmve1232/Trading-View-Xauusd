# TradingView line at build v73 — display-only reference

The operator's TradingView scripts as of 2026-10-17 (branch `claude/xauusd-developed-files-tmnk9g` @ `853a232c`),
kept so the website can be checked against them. **They are not the counted system** (`audit/PREREGISTRATION.md`
Amendment 6). Amendment 9 ports the two engine fixes of v51–v73 that also applied to the website. The previous
reference (v50) stays in `reference/pine-v50/` because Amendment 7 cites its hashes.

Hashes are in `SHA256SUMS` (`sha256sum -c SHA256SUMS` from this folder). Each file's BUILD STAMP gives the build that last
changed it:

| File | Last changed | Role on TradingView |
|---|---|---|
| `XAUUSD_Quantum_5_0_Master.pine` | v69 (the v72 set) | the live indicator; compiled (operator, 18 Oct) |
| `XAUUSD_Quantum_5_5_Visuals.pine` | v73 | chart visuals, terminal panel, H2 card, gold drivers |
| `XAUUSD_Quantum_5_0_Brief.pine` | v70 | Market Brief + GOLD ARROWS grid (companion, same engine) |
| `XAUUSD_Quantum_5_0_Diagnostics.pine` | v68 | diagnostics companion |
| `XAUUSD_Quantum_5_0_Strategy.pine` | v68 | Treatment arm |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` | v68 | Control arm |
| `XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine` | v68 | Challenger (H1) |
| `XAUUSD_Quantum_5_0_Strategy_H2.pine` | v51 | the Pine line's H2 = **H3 on the website** |
| `XAUUSD_Quantum_5_0_EdgeCases.pine` | v54 | run-once assertion table |

## Parity map, builds v51–v73, against the website

| Pine | What | Website |
|---|---|---|
| **F-A64 (v64)** | macro correlations paired gold *now* with each asset *one bar earlier* | **ported, Amendment 9** (`features.py`): same-period pairing. Measured on the website's store: silver read r 0.09 instead of 0.83 |
| **F-A65 (v65)** | the dollar (DXY + EURUSD) and the 10Y (US10Y + TIPS on the same feed) each counted twice | **ported, Amendment 9**: EURUSD only without DXY; TIPS off on the 10Y feed; majority over the independent factors |
| F-A62 (v63) | London DST computed wrongly on up to 5 days a year | **already equal**: the website uses the IANA database (D-02) |
| F-A60 (v62) | the Master's H2 read availability-gated HTF scores (50) above 30M | **already equal**: the website's H3 reads the raw 1H / 4H / 1D scores on every timeframe |
| F-A61 (v63) | lengths of 0 stop the script | not applicable (config defaults are fixed and tested) |
| F-A63 (v63) | MTF layers that cannot vote shown as a score | **already equal**: the Overview shows only layers above the chart; the new grid says "no data on this TF" |
| F-A54 (v53) | arrows coloured by what they mean for gold; ≈ when flat or \|r\| ≤ 0.25; ▲▲ when \|r\| > 0.5 | **ported** (display): Macro tab and Overview arrows; the GOLD ARROWS grid (`report.gold_arrows`, 23 cells + CLIMAX) |
| v65–v66 | five more gold drivers: USDJPY, oil, real 10Y yield, 10Y breakeven, US 2Y | **ported** (display): JPY/USD and oil were on the site; real yield (FRED DFII10), breakeven (T10YIE) and US 2Y (DGS2) added as daily boxes, direction by trend vs EMA10 / EMA20 |
| F-A55 (v54) | DO NOW must follow the DECISION; a vetoed bar names its block | DO NOW already did; **ported**: "What to do now" names the veto (or the risk lock) |
| v57 | LIQ DRAW: the engine's liquidity destination, distinct from the nearest-level TARGET | **ported**: "Liquidity draw" in the Overview, the strip and the brief's target tile |
| v61 | "!FIT" when in-sample win rate > rolling + 15 | the site had it; **aligned** to Pine's in-sample n ≥ 10 |
| v61 | a crossed playbook trigger: "price through it: fires if this bar closes here" | **ported** (brief and plan card) |
| v67 | ADX with DI+ / DI− | **ported** (Overview, Regime card) |
| v52 | Market Brief | the site's own (v52 ported it from the site to Pine) |
| v55–v60, v73 | phone card, strip, terminal panel layouts | Pine table layout; the site has its own responsive layout |
| v58–v72 | compiler-limit work (token model, helper write-outs, UDT failure) | Pine only |

## Notes found while comparing

1. **RSI divergence cell (Pine Brief, GOLD ARROWS).** With the engine's divergence filter off (the default, `useRsiDivFilter = false`), both
   divergence flags are `true`, and `f_brS(bullRsiDiv, bearRsiDiv)` prints a green ▲ on every bar. The website's grid shows
   "filter off (engine default)" instead. Pine-side display defect; not ported.
2. **One verdict per instrument.** Pine's grid scores USDJPY and oil by the engine's same-bar correlation (≈ when \|r\| ≤ 0.25).
   The website's grid uses the macro panel's own verdict for those two, so one instrument never shows two colours on the page.
3. **MTF confluence denominator (shared, not changed).** After F-A65 the macro vote pool is 4–6, but both Pine v73
   (`mtfConfluenceScore … / (mtfAvail + 6.0)`) and the website still divide the MTF confluence score by
   available MTF layers + 6. The two stay identical; changing it would be a further engine amendment.

## Later builds (not copied here)

| Pine | What | Website |
|---|---|---|
| v74, v75 | Visuals docks the gold drivers, the H2 card and liquidity / sweeps under the Master's columns | TradingView table layout; the site shows the same values in its own cards |
| v76 | H2 card: the last signal's age, outcome and LIVE / STALE | **ported** to the H2 and H3 cards (`report.signal_status`, display only) |
