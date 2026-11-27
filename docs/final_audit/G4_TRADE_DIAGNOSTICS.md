# G4: per-trade diagnostics of the forward record

**Authority.** Operator mandate of 27 Nov 2026 ("QUANTUM XAUUSD – NEXT PHASE EXECUTION & VALIDATION MANDATE"), G4
APPROVED: record per-trade diagnostics without changing the frozen engine. This is a **records-only** change.

- The engine, the arms, the alerts and the forward ledgers do not read these records.
- `quantum/trade_diag.py` is outside `holdout.ENGINE_SOURCES`, so the freeze key is unchanged.

## What is recorded, per closed forward trade

| Mandate field | Record field | Definition |
|---|---|---|
| MAE / MFE | `in_trade.mae_usd`, `mfe_usd`, `mae_r`, `mfe_r` | Largest adverse / favourable move from the fill to the recorded exit, in $ per ounce and in R (R = the original stop distance) |
| Time to +$10 / +$15 / +$20 | `race.usd10` / `usd15` / `usd20` `.hours` | Hours from the fill to the close of the 5-minute bar that first reached the level |
| Each target reached before the stop | `race.<target>.result` | `TARGET`, `STOP_FIRST` or `UNDECIDED`, for +$10, +$15, +$20, TP1 and TP2 against the **original** stop, for up to 7 days from the fill |
| Stop reached first | `stop.before_usd10`, `stop.hit`, `stop.hours` | The stop inside the race window (below) |
| Exit reason and timing | `exit.*`, `in_trade.hours` | Copied from the ledger, plus the hours from the fill to the exit |
| Execution cost | `cost.model_pts`, `cost.model_r`, `cost.measured_pts`, `cost.status` | The engine's modelled cost of record. `measured_pts` is `null`, because there are no broker fills yet (G2). The status names it `MODEL` |
| News day / major event | `news.*` | NFP / CPI / FOMC from `quantum/news_calendar.py`: same New York day, event inside the trade, fill within ±30 min. Scope: **these three only**, since no other release is in that calendar |
| Entry-bar and next-bar conventions | `race` and `next_open` | The race from the engine's fill, and the same +$10 / +$15 / +$20 race entered at the open of the first 5-minute bar after the signal |
| Lineage | `bars.sha256`, `bars.n`, `trade_sha256`, `versions`, `logged_utc` | SHA-256 of exactly the bars the record depends on and of the ledger trade it describes; code version; time written |

## Conventions

These are the engine's conventions, from `quantum/backtest.simulate`.

**Entry and fill**
- **Entry-bar convention.** The ledger's `entry_time` is the signal bar's open label. The fill is that bar's close, and the path starts with the first 5-minute bar opening at the close.
- **Next-bar convention.** The entry is the open of that first 5-minute bar. `entry_shift_usd` > 0 means a worse price than the engine's fill.
- **Session close.** `first_bar_gap_min` > 0 means the signal closed at a session close. The market was shut at the engine's fill, and the next-bar open is the first bar of the next session.
- **That first open is the engine's repaired value** (`sources.repair_reopen`: that bar's close). The feed's first print is the quote carried through the closure, not a trade.

**Path rules**
- **Shared bar.** A 5-minute bar that reaches both the stop and a target counts as the stop, because the path inside a bar is unknown.
- **Opening beyond a level.** A bar that opens beyond a level reached it at the open.
- **Race window.** It ends at the stop (`STOP`), at the bar that reached the last target (`ALL_TARGETS`), or 7 days after the fill (`HORIZON`).
  - `race_window.mfe_usd` is the favourable move inside that window; the stop bar's favourable side is excluded.
  - A stop after every target was reached is outside the race. It is reported as `stop.hit: false` with scope "inside the race window".
- **In-trade window.**
  - For an exit at a price (SL, SL_GAP, BE, BE_GAP, TP2), it ends at the first 5-minute bar of the exit bar that reaches the exit price. In that bar only the exit side counts, capped at the exit price.
  - For an exit at a close (FLIP), it ends at the exit bar's close.

## No look-ahead, and final when written

1. Only 5-minute bars that had **closed** by the run time are read. The store also keeps the still-forming bar, whose high and low can still move.
2. A record is written only when:
   - both races are decided, or the 7-day horizon has passed; and
   - the bars reach the close of the exit bar.

   Until then the trade is **pending**.
3. Every field depends only on bars up to the end of its race window or the exit, so a later bar cannot change it.
4. **Written once.**
   - A record already in the log is never written again.
   - The forward-ledger copy is a union by trade key, so nothing in it is removed or changed.
   - The ledger files themselves are only read.

## Where it runs

| Step | What |
|---|---|
| `.github/workflows/quantum-site.yml`, after the outcome log | `python -m quantum.trade_diag --append store` writes `store/trade_diag/<UTC day>.jsonl`. A failure is a warning on the run; the saves and the site still run |
| Same file, "Save the forward ledger" | `--merge-ledger store/trade_diag ledger/trade_diag` merges into `forward-ledger` (normal commits, never force-pushed) |

## How it was validated

**Tests.** `tests/test_trade_diag.py`, built on hand-made 5-minute bars in a throwaway store. The cases are worked by hand:

- a long trade with a break-even exit;
- the next-bar open worse than the fill;
- a Friday-close signal filled at the Sunday reopen;
- a short stopped by a gap, and the shared-bar rule;
- every target reached before a later stop;
- no record while either race is undecided;
- the forming bar is not read;
- the exit bar is not yet stored;
- a malformed bar that opens beyond a level;
- write-once and ledger byte-identity;
- archives, manifests and open trades skipped;
- the New York news day;
- Wilson intervals, the summary and the markdown table;
- the workflow wiring;
- nothing in production reads the module.

Two further tests:
- **Random paths.** On 40 random 5-minute paths the records agree with the independent checker.
- **Mutated records.** The checker flags six kinds of corrupted record.

**Mutation test.** `audit/tools/mutation_trade_diag.py` applies each rule's mutant to a copy of the module; the test suite must fail on every mutant.

**Independent recomputation.** `audit/tools/trade_diag_check.py` recomputes every record with different code:
- the race code of `audit/tools/h4_forward_diagnosis.races`;
- its own bar loader and epoch conversion;
- its own exit-bar rule.

Only the data cleaning is shared, because it is the engine's: shut-market bars dropped and session reopens repaired. With `--raw` the repair is skipped, and records that differ only at a session reopen are listed apart.

**Real data.** The module was run on a copy of the production market-data store at its latest commit.

## Results (generated from the evidence files)

The evidence files are in `docs/final_audit/evidence/`:
- `g4_trade_diag_2026-11-27.txt` (the run)
- `g4_trade_diag_check_2026-11-27.json`
- `g4_trade_diag_check_raw_2026-11-27.json`
- `g4_trade_diag_summary_2026-11-27.json`
- `g4_mutation_2026-11-27.json` / `.txt`

<!-- G4:BEGIN (generated by audit/tools/g4_doc.py; do not edit) -->

### Run

| Item | Value |
|---|---|
| Store | origin/market-data at 1800b2810269cdb39a296f2a0db7404b2c94b5a1 (committed 2026-11-27T21:33:58Z), extracted with git archive |
| Run time | 2026-11-27T21:33:58Z (the store's commit time) |
| Code | quantum/trade_diag.py sha256[:16] 081523789c83368e |
| Closed ledger trades | 849 |
| Records written | 837 |
| Pending (race undecided, horizon open) | 12 |
| Records file | `trade_diag/2026-11-27.jsonl`, SHA-256 `ba651e62390fe8725922f45984da2f439a830cf5711b50d7f9fbb07402f060f2`, 837 lines |
| Ledgers before / after (SHA-256 of all `holdout/*.json`) | `55795551604456fa…` / `55795551604456fa…`: byte-identical |

### Validation

| Check | Result |
|---|---|
| Independent recomputation (reopen repaired as the engine does) | 837 of 837 agree; 0 disagree; 0 ledger trades changed |
| Same, raw feed bars | 830 of 837 agree; 7 differ only at a session reopen; 0 disagree |
| Mutation test (`audit/tools/mutation_trade_diag.py`) | 19 of 19 mutants killed |

Records whose raw-feed result differs, all at a session reopen (the repaired first print is the engine's):

- `15m|h4|2026-11-16T21:45:00+00:00|SHORT`: next open 3856.63 vs 3856.2301; next_open race mfe 4.995 vs 4.595
- `15m|h4|2026-11-20T21:45:00+00:00|LONG`: next open 3576.12 vs 3533.04581; next_open.usd10: TARGET 49.417 vs TARGET 49.083333333333336; next_open.usd15: TARGET 51.167 vs TARGET 49.083333333333336; next_open.usd20: TARGET 51.167 vs TARGET 49.083333333333336; next_open race mfe 26.27 vs 44.388
- `15m|h4|2026-11-23T21:45:00+00:00|LONG`: next open 3638.718 vs 3634.61412; next_open race mfe 4.688 vs 8.792
- `15m|h4|2026-11-25T21:45:00+00:00|LONG`: next open 3583.343 vs 3589.50803; next_open race mfe 6.732 vs 0.567
- `30m|h4|2026-11-19T21:30:00+00:00|SHORT`: next open 3632.676 vs 3628.36952; next_open.usd10: TARGET 1.25 vs TARGET 1.6666666666666665; next_open race mfe 37.8 vs 33.494
- `4h|h4|2026-11-19T18:00:00+00:00|SHORT`: next open 3632.676 vs 3628.36952; next_open.usd10: TARGET 1.25 vs TARGET 1.6666666666666665; next_open race mfe 37.8 vs 33.494
- `5m|h4|2026-11-23T21:55:00+00:00|LONG`: next open 3638.718 vs 3634.61412; next_open race mfe 4.688 vs 8.792; in_trade mae 0.0 vs 2.253

### Totals over all arms and timeframes

| Item | Count |
|---|---|
| Records | 837 |
| Race window ended: ALL_TARGETS | 253 |
| Race window ended: STOP | 584 |
| In-trade window: exit bar close | 446 |
| In-trade window: exit price touched | 391 |
| Signal filled at a session close (engine fill while the market was shut) | 7 |
| Cost measured from broker fills | 0 (no broker fills yet: G2) |
| Covered by the NFP / CPI / FOMC calendar | 837 |
| On a New York news day | 4 |
| Event inside the trade | 0 |
| Fill within the ±30 min window | 0 |

### Per arm and timeframe

Rates are target-before-stop among decided races, against the original stop, with Wilson 95% intervals. Descriptive only: no baseline and no test here; the matched random-entry comparison is reported separately.

| Arm · TF | n | +$10 first | +$15 first | +$20 first | +$15 first, next-bar open | median MAE R | median MFE R | stop before +$10 | filled at a session close |
|---|---|---|---|---|---|---|---|---|---|
| challenger · 15m | 7 | 0.57 [0.25, 0.84] | 0.43 [0.16, 0.75] | 0.43 [0.16, 0.75] | 0.43 [0.16, 0.75] | 1.0 | 0.5227 | 3 | 0 |
| challenger · 1h | 4 | 1.00 [0.51, 1.00] | 0.75 [0.30, 0.95] | 0.75 [0.30, 0.95] | 1.00 [0.51, 1.00] | 0.8054 | 1.1185 | 0 | 0 |
| challenger · 30m | 3 | 0.67 [0.21, 0.94] | 0.33 [0.06, 0.79] | 0.33 [0.06, 0.79] | 0.67 [0.21, 0.94] | 1.0 | 0.7017 | 1 | 0 |
| challenger · 4h | 1 | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 0.0441 | 2.0 | 0 | 0 |
| challenger · 5m | 13 | 0.62 [0.36, 0.82] | 0.62 [0.36, 0.82] | 0.46 [0.23, 0.71] | 0.62 [0.36, 0.82] | 1.0 | 2.1886 | 5 | 0 |
| control · 15m | 1 | 1.00 [0.21, 1.00] | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 1.0 | 0.5227 | 0 | 0 |
| control · 1h | 1 | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 0.6109 | 1.9138 | 0 | 0 |
| control · 30m | 2 | 0.50 [0.09, 0.91] | 0.00 [0.00, 0.66] | 0.00 [0.00, 0.66] | 0.50 [0.09, 0.91] | 1.579 | 0.4733 | 1 | 0 |
| control · 5m | 2 | 0.50 [0.09, 0.91] | 0.50 [0.09, 0.91] | 0.50 [0.09, 0.91] | 0.50 [0.09, 0.91] | 0.7322 | 1.2682 | 1 | 0 |
| h2 · 15m | 1 | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 0.066 | 1.0341 | 0 | 0 |
| h2 · 30m | 1 | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 0.00 [0.00, 0.79] | 1.00 [0.21, 1.00] | 1.0 | 0.9289 | 0 | 0 |
| h2 · 5m | 4 | 0.75 [0.30, 0.95] | 0.50 [0.15, 0.85] | 0.50 [0.15, 0.85] | 0.75 [0.30, 0.95] | 1.0 | 0.6675 | 1 | 0 |
| h3 · 15m | 5 | 0.20 [0.04, 0.62] | 0.20 [0.04, 0.62] | 0.00 [0.00, 0.43] | 0.20 [0.04, 0.62] | 1.0 | 0.5143 | 4 | 0 |
| h3 · 1h | 1 | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 0.00 [0.00, 0.79] | 1.00 [0.21, 1.00] | 1.0 | 0.8356 | 0 | 0 |
| h3 · 30m | 1 | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 1.0 | 0.0939 | 1 | 0 |
| h3 · 5m | 9 | 0.67 [0.35, 0.88] | 0.44 [0.19, 0.73] | 0.44 [0.19, 0.73] | 0.44 [0.19, 0.73] | 1.0 | 2.4942 | 3 | 0 |
| h4 · 15m | 158 | 0.59 [0.51, 0.66] | 0.51 [0.44, 0.59] | 0.46 [0.38, 0.53] | 0.53 [0.45, 0.60] | 0.3985 | 0.5072 | 65 | 4 |
| h4 · 1h | 40 | 0.70 [0.55, 0.82] | 0.65 [0.50, 0.78] | 0.57 [0.42, 0.71] | 0.60 [0.45, 0.74] | 0.4772 | 0.3005 | 12 | 0 |
| h4 · 30m | 76 | 0.70 [0.59, 0.79] | 0.63 [0.52, 0.73] | 0.54 [0.43, 0.65] | 0.63 [0.52, 0.73] | 0.3722 | 0.5061 | 23 | 1 |
| h4 · 4h | 8 | 1.00 [0.68, 1.00] | 1.00 [0.68, 1.00] | 1.00 [0.68, 1.00] | 1.00 [0.68, 1.00] | 0.3994 | 0.6333 | 0 | 1 |
| h4 · 5m | 447 | 0.45 [0.40, 0.49] | 0.37 [0.33, 0.41] | 0.31 [0.27, 0.36] | 0.37 [0.33, 0.42] | 0.4385 | 0.3951 | 247 | 1 |
| h5 · 5m | 7 | 0.29 [0.08, 0.64] | 0.14 [0.03, 0.51] | 0.14 [0.03, 0.51] | 0.14 [0.03, 0.51] | 1.0 | 0.2744 | 5 | 0 |
| h6 · 15m | 4 | 0.75 [0.30, 0.95] | 0.50 [0.15, 0.85] | 0.25 [0.05, 0.70] | 0.50 [0.15, 0.85] | 1.0 | 0.4133 | 1 | 0 |
| h6 · 1h | 2 | 1.00 [0.34, 1.00] | 0.50 [0.09, 0.91] | 0.50 [0.09, 0.91] | 0.50 [0.09, 0.91] | 0.9937 | 3.9631 | 0 | 0 |
| h6 · 30m | 3 | 0.67 [0.21, 0.94] | 0.67 [0.21, 0.94] | 0.67 [0.21, 0.94] | 0.67 [0.21, 0.94] | 0.6731 | 2.9967 | 1 | 0 |
| h6 · 4h | 1 | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 0.00 [0.00, 0.79] | 1.0 | 0.1232 | 1 | 0 |
| h6 · 5m | 3 | 0.67 [0.21, 0.94] | 0.33 [0.06, 0.79] | 0.33 [0.06, 0.79] | 0.33 [0.06, 0.79] | 1.0 | 1.234 | 1 | 0 |
| treatment · 15m | 7 | 0.57 [0.25, 0.84] | 0.43 [0.16, 0.75] | 0.43 [0.16, 0.75] | 0.43 [0.16, 0.75] | 1.0 | 0.5227 | 3 | 0 |
| treatment · 1h | 4 | 1.00 [0.51, 1.00] | 0.75 [0.30, 0.95] | 0.75 [0.30, 0.95] | 1.00 [0.51, 1.00] | 0.8054 | 1.1185 | 0 | 0 |
| treatment · 30m | 3 | 0.67 [0.21, 0.94] | 0.33 [0.06, 0.79] | 0.33 [0.06, 0.79] | 0.67 [0.21, 0.94] | 1.0 | 0.7017 | 1 | 0 |
| treatment · 4h | 1 | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 1.00 [0.21, 1.00] | 0.0441 | 2.0 | 0 | 0 |
| treatment · 5m | 17 | 0.47 [0.26, 0.69] | 0.47 [0.26, 0.69] | 0.35 [0.17, 0.59] | 0.41 [0.22, 0.64] | 1.0 | 0.8731 | 9 | 0 |

<!-- G4:END -->

## Limits

- **Descriptive, not a test of an edge.**
  - These rates have no baseline and no correction for multiple comparisons.
  - A target rate depends on the stop distance: a wide stop reaches +$10 more often.
  - The matched random-entry comparison and the multiple-testing corrections are a separate step of the mandate.
- **Mid prices from one vendor** (Twelve Data XAU/USD), without bid / ask.
  - A spread or a broker's own feed can turn a touch into a miss.
  - Measured costs need the MT5 specification and fills (G2).
- **5-minute bars versus the arm's own bars.**
  - The ledger was simulated on the arm's timeframe bars. These records use the stored 5-minute bars of the same vendor.
  - When no 5-minute bar of the exit bar reaches the exit price, `in_trade.ends` says so. The whole exit bar is then counted.
- **News scope.**
  - NFP, CPI and FOMC only, and only the calendar's dated events.
  - The totals above count the forward trades with an event inside them. A news comparison is G3, research only.
- **Old-key trades.** Arm H6 trades carry the previous freeze key (`freeze_key` is copied into each record). Group by key before comparing arms.
- **Small samples.** Many arm and timeframe groups are small; the n column and the intervals show it.

## Reproduce

- The run used `market-data` at `1800b2810`. That branch is replaced every run, so the commit is not fetchable for long.
- A later snapshot should give the same records:
  - the store keeps every month of 5-minute bars;
  - `--now` drops every bar that closed after that time;
  - trades closed later stay pending.
- A vendor revision of a bar would show as a different `bars.sha256`.
- This has not yet been tried on a later snapshot.

```sh
git fetch origin market-data
mkdir st && git archive origin/market-data | tar -x -C st
python -m quantum.trade_diag --append st --now 2026-11-27T21:33:58Z
python audit/tools/trade_diag_check.py --store st                      # exit 0 = no disagreement
python audit/tools/trade_diag_check.py --store st --raw                # REOPEN differences listed
python -m quantum.trade_diag --summary st/trade_diag --json
python audit/tools/mutation_trade_diag.py <empty scratch dir>
python audit/tools/g4_doc.py --check                                   # this document matches the evidence
```
