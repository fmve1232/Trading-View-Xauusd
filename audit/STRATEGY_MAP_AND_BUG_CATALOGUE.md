# XAUUSD strategy map and bug catalogue (v83, 2026-10-21)

Operator: "list all possible strategies used in XAUUSD and all possible bugs, then test all files and validate". Each
"implemented" claim below was checked by grepping the files. Each validation names the tool that executes it.

## 1. Strategies used on XAUUSD, and where they are in these files

| # | Strategy family (what traders do on gold) | In our files | Validated by |
|---|---|---|---|
| 1 | **Trend following**: EMA stacks, higher-timeframe alignment | Master engine trend score (EMA20/100/200), 5M-1D MTF confluence; Challenger arm H1 = fast-trend gate | `decision_check` (trend exclusivity), `formula_trace` (MTF normalisation), A/B arms |
| 2 | **Market structure / breakout**: BOS, CHoCH, MSS | Master structure engine (internal + swing); Visuals labels (a simplified detector, marked "~") | `decision_check`, `sequence` triage (breakout state), alerts gated on confirmed bars |
| 3 | **Liquidity sweep / stop hunt** (ICT / SMC) | Master liquidity pools (PDH/PDL, PWH/PWL, PMH/PML, EQH/EQL), reach scores; H2 sweep-to-value; Visuals ✕ markers | `h2_trace` (200 × 300-bar sweep paths), `panel_check` (levels, nearest-level search) |
| 4 | **Mean reversion to value**: VWAP, volume-profile POC / value area | Master VWAP + value area; H2 (long only at / below POC, short only at / above) | `h2_trace` (VP vs the engine's VP code), `panel_check` |
| 5 | **Fair value gaps / order blocks** (SMC) | Master engine FVG / OB (feed trade quality, SL / TP candidates); Visuals boxes (off by default) | engine parity `diag_parity`; inputs KNOWN (draw vs engine switch) |
| 6 | **Session trading**: Asian range, London / NY open, kill zones | Master session engine, session quality gate, kill zones; manipulation / continuation history | `tf_check` (sessions vs the IANA DST rules), `h2_parity` (SESSIntel = engine) |
| 7 | **Key levels**: previous day / week / month high-low, round numbers | Pools above; round-number grid (`rnGrid`) for SL / TP magnets | `inputs_check` (rnGrid ≥ 1), plan rows `refactor_check` |
| 8 | **Intermarket / macro**: DXY, US10Y, real yield, breakeven, USDJPY, oil, silver, SPX, US2Y | Master macro engine (DXY, yields, XAG, SPX, EUR); five display-only drivers (Visuals / Brief) | `macro_check` (same-bar pairing, each factor once, known-r model) |
| 9 | **News avoidance**: NFP, CPI, FOMC | `newsSession` window suppresses signals (off by default) | **F-A71 fixed in v83**: label corrected (exchange time = New York, not UTC) |
| 10 | **Volatility regime / ATR stops** | Regime engine (compress / range / trend / expansion / abnormal), adaptive ATR, SL multiples, size haircut | `regime_check` (all percentiles, ATR floor) |
| 11 | **Momentum / oscillators**: RSI, divergence, ADX | RSI and RSI divergence (engine, Brief grid), ADX gate, DI+ / DI- | `decision_check` (gates), `deadcode` (wired) |
| 12 | **Order flow / volume**: CVD, delta, footprint | CVD and delta on TICK volume (spot gold has no exchange volume), footprint approximation (Visuals, off by default) | labelled as a proxy in the code; Diagnostics reports its correlation with COMEX volume |
| 13 | **Positioning / sentiment**: COT | COT state (crowded long / short) as context | `deadcode` (wired to the macro line) |
| 14 | **Seasonality**: day of week | Day-of-week tracker | `deadcode` |
| 15 | **Probability / statistics-driven entries** | Calibrated probabilities (Platt / WLS), Brier / Murphy, analog evidence, race expectancy, Wilson-low + Kelly sizing, trade-quality score | `formula_trace` 61 / 61 in all 6 engine copies, `formula_check`, `race_model_check`, `expectancy_check` |
| 16 | **Risk controls**: daily loss / trade caps / loss streak lockout, costs | Risk lock, spread + slippage + commission model in R | `decision_check` (veto / lock precedence), `sequence` triage (tqVeto) |
| — | **Not implemented**: MACD, Fibonacci / harmonics, grid / martingale | none (the "grid" in the code is the race-probability interpolation grid) | — (martingale / grid is a ruin-risk method; deliberately absent) |

**No strategy here has a demonstrated edge yet.** The engine's own statistics on the operator's charts read WR
22-23 % and PF 0.8-0.92. The website's frozen forward test (A7) decides, and nothing may be tuned on this history.

## 2. Bug catalogue: every class, how it is tested, and the result on v83

| Class | What goes wrong | Tool | Result on all 9 files |
|---|---|---|---|
| Look-ahead (future leak) | `request.security(..., lookahead_on)` without `[1]` shows tomorrow's value on historical bars | `bug_scan` R1 | **0**; positive control caught |
| Higher-TF repaint | HTF value without offset changes until the HTF bar closes | `bug_scan` R2, `pinelimits` G10 | 1: Visuals' "forming 4H" lines, labelled REPAINTS, off by default (by design) |
| Intrabar state | `varip`, `timenow` | `bug_scan` R3 / R4 | **0** |
| Unconfirmed alerts | alerts firing intrabar and vanishing | `bug_scan` A1 | Master: all gated by `barstate.isconfirmed`. Visuals: the level-TOUCH alerts are intrabar by design; H2 alerts fire on confirmed bars only (`h2_trace`) |
| Time zone | session / hour logic in the exchange zone while the user thinks UTC | `bug_scan` T1, `tf_check` | **F-A71**: the news window was labelled UTC but runs in New York time. Fixed (label + tooltip) in v83. Sessions and DST: `tf_check` PASS |
| Same-position tables | TradingView shows one table per position per script | `bug_scan` P1, `panel_check` 5 / 8 | Defaults collision-free. Possible only through user choices (Diagnostics panel at a bottom corner; the Master's Mobile card; Visuals' separate-card positions). Documented. F-A69 (fixed v77) was this class |
| Divide by zero / na | x / 0 = na in Pine: spreads into decisions or shows "NaN" | `bug_scan` D1 + hand triage | All ~80 engine sites guarded (sample-size gates ≥ 20 / ≥ 30, `math.max(…, ε)`, ATR floor, validity flags, input minvals). **0 real** |
| "NaN" on screen | na number printed in text | `panel_check` 9 (executed) | **F-A70** fixed in v82; 0 NaN in 33,000 evaluations |
| Backtest flattery | fills on close, no costs | `bug_scan` S1 | Arms use `process_orders_on_close=true` (fill at the signal bar's close: mildly optimistic). Part of the frozen pre-registered arms, so documented, not changed. Commission and slippage are set |
| Dead / unwired values | computed, never shown | `deadcode`, `trace` | 0 dead; every unread value in the arms / Brief is shown by a companion (cross-checked) |
| Read-before-write order | a value used before it is updated on the bar | `sequence` | All hits are the triaged previous-bar-state patterns; v81-v83 added none |
| Timeframe edge cases | lengths, offsets, max_bars_back, every TF | `tf_check`, `inputs_check` | PASS 1m … 1M |
| Engine drift between copies | Diagnostics / Brief / arms diverge from the Master | `diag_parity`, `h2_parity`, `macro_check` E, `refactor_check` | PASS (byte-for-byte derivations) |
| Wrong maths | formula slips | `formula_trace`, `formula_check`, `race_model_check`, `expectancy_check` | PASS |
| Compile limits | tokens, main body, call arity, shadowing | `compile_est`, `pinelimits` | PASS (Master / Brief / Diagnostics at their compiled sizes) |
| Rendering rules | layout, visual order | — (not testable here) | screenshot only |

Run `python3 audit/tools/bug_scan.py` (add `--all` for every hit). Each hit is a question; the triage is above.
