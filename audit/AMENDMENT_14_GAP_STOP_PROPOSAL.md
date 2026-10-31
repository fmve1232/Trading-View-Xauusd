# Amendment 14 (PROPOSED) — realistic stop and target fills when a bar opens beyond them

**Status: APPROVED by the operator on 2026-11-01 ("Apprive it and Merge it"); recorded as Amendment 14 in `audit/PREREGISTRATION.md`. The text below is the version that was reviewed.**

- The engine and the forward test are unchanged until the operator approves this text in writing.
- The current main freeze key is `5e4630924d663fc5:6f3964ad97813cc9`, engine Q7.2-web.6, started 2026-10-17 21:26:18
  UTC.
- On approval, this text is copied **verbatim** into `audit/PREREGISTRATION.md` as Amendment 14, before any code
  changes.

Written 2026-11-01. Every number below was produced by `audit/tools/gap_impact.py` with `audit/tools/gapsim.py`, a copy of `quantum/backtest.simulate`
with the rule below added.

- That copy is run on the stored data (`market-data` @ `0bb2c8a96`, XAU/USD spot from Twelve Data).
- Its "current" mode was checked **trade for trade** against the production `backtest.simulate` on every timeframe
  and arm: entry bar, exit bar and P&L are all identical.

---

## 1. Current behaviour and its limitation

`quantum/backtest.py` (lines 23–69), on each bar after entry:

1. **Stop test:** long if `low ≤ stop`, short if `high ≥ stop`. The fill is at the **stop price**, labelled SL, or BE
   after TP1.
2. Otherwise **TP1:** if `high ≥ TP1` (long), half the position fills at **TP1**.
3. **TP2:** if `high ≥ TP2`, the rest fills at **TP2**. Otherwise, after TP1, the stop moves to entry from the next
   bar.
4. Stop first on a bar that touches both (conservative).

**The limitation (B-02):** when a bar **opens beyond the stop**, the stop is filled at the stop price. That price
never traded.

- The open is the first price at which the stop could have filled, so a real stop order fills at the open (or worse).
- The losses this optimism hides are the gap losses that matter most: weekend reopens, the daily 17:00 New York
  break, and news.
- Symmetrically, a TP limit that the bar opens beyond fills at the open in reality, which is **better** than the
  limit. That is a smaller, opposite error.

## 2. Proposed rule

For an open position on bar i (i > entry bar), using **only bar i's own OHLC**. Long is shown; short is the mirror
image.

| Step | Condition (long) | Condition (short) | Fill | Exit label |
|---|---|---|---|---|
| A1 | `open ≥ TP2` | `open ≤ TP2` | everything left at the **open**. If TP1 was not yet done, its half also fills at the open | TP2 |
| A2 | otherwise, TP1 not done and `open ≥ TP1` | `open ≤ TP1` | half at the **open** | (continue to B) |
| B1 | `open ≤ stop` | `open ≥ stop` | the rest at the **open** | `SL_GAP`, or `BE_GAP` after TP1 |
| B2 | otherwise `low ≤ stop` | `high ≥ stop` | the rest at the **stop price** (unchanged) | SL / BE |
| C | otherwise | otherwise | TP1 / TP2 intrabar exactly as now | TP1 / TP2 |

**Why the open goes first:** the open is the earliest price in the bar. A level the bar opens beyond was crossed
before any other price in that bar, so there is no ordering ambiguity and the stop-first tie rule does not apply.
Within the bar after the open, the existing stop-first rule is kept.

The new rule applies to the stop and both targets. Unchanged:

- entry at the signal bar's close;
- the flip at the close;
- the breakeven move from the next bar;
- the 50% split;
- open trades marked at the last close.

**Not adopted: a separate "gap slippage" charge.** A gap fill at the open already records the gap loss. Adding more
would invent a number that OHLC data cannot measure (§4).

## 3. Long and short positions

The rule is written once per side and mirrored. Long uses `open ≤ stop` and `open ≥ TP`; short uses `open ≥ stop` and
`open ≤ TP`. R stays `net / |entry − initial stop|`, unchanged, so an `SL_GAP` exit can be below −1 R. This is
intended: it is the real loss. Tests check each side separately (§7).

## 4. What OHLC data can and cannot show

- **Can:** that the first traded (quoted) price of the bar was beyond the level. The open is a recorded price.
- **Cannot:**
  - the path inside the bar;
  - the depth available at the open;
  - whether the broker's first fill was worse than the feed's open;
  - bid / ask at the open.

  The fill at the open is therefore a **lower bound on the damage**, not an exact broker fill. Real gap fills can be
  worse.
- **Reopen bars:**
  - The Sunday 22:00 UTC reopen bars (most gap exits measured here) carry an open that `sources.repair_reopen`
    rebuilt from 5-minute bars (D-09), because Twelve Data's first print is the quote carried through the closure.
    That open is itself an estimate, capped by `_cap_stale_open`.
  - The rule inherits that estimate.
  - It cannot be bettered without tick data, which the free data sources do not give.
- **Tick data:** an exact fill model would need the operator's broker ticks, or MT5 history with real fills. That is
  out of scope; it is listed as an open limitation.

## 5. Spread, slippage and commission: no double counting

- **Unchanged:** the round-trip cost `session spread + 2 × slippage + commission / 100`, charged **once per trade at
  entry** (§6.4 of the audit report).
- **The gap fill moves only the exit price.** It does not add a cost.
  - The spread is still charged once (the half-spread on each side is inside it).
  - Slippage is still 0.20 per side.
  - Commission is still per lot round turn.
- **A partial exit (TP1 at the open) does not charge a second commission:** commission is already a whole-trade
  round-turn figure.
- **Prices:** the feed's OHLC are quotes, used without bid / ask adjustment, as now. So a gap fill at the open is
  comparable with a normal fill at the stop.

## 6. Before and after (stored window; forward window = entries from 2026-10-17 21:26:18 UTC)

Two variants were measured:

- **"stop":** steps B1 / B2 only.
- **"proposed":** the full rule, A + B + C.

### 6.1 Treatment (the engine's own BUY / SELL), every timeframe

| TF | n | Mean R | PF | Max DD (R) |
|---|---|---|---|---|
| 5m | 37 | +0.189 | 1.30 | 8.56 |
| 15m | 12 | +0.589 | 2.55 | 3.14 |
| 1h | 30 | +0.052 | 1.48 | 5.51 |

There were **no gap exits** on any timeframe, so **no trade changes**: these figures are the same before and after,
and the forward ledgers are unaffected.

### 6.2 H4 Playbook (the only arm that trades through gaps)

| TF | Window | n | Current: mean R / PF / sum R / max DD R | Stop only: mean R / PF / sum R / max DD R | Proposed: mean R / PF / sum R / max DD R | Gap exits | Limit gap fills |
|---|---|---|---|---|---|---|---|
| 5m | all, 09-09 → 10-30 | 1731 | −0.1758 / 0.613 / −304.30 / 314.59 | −0.1771 / 0.612 / −306.56 / 316.84 | −0.1758 / 0.613 / −304.39 / 314.76 | 8 | 5 |
| 5m | forward | 498 | −0.1845 / 0.582 / −91.89 / 99.05 | −0.1847 / 0.581 / −91.97 / 99.14 | −0.1847 / 0.581 / −91.97 / 99.14 | — | — |
| 15m | all, 08-05 → 10-30 | 986 | −0.1073 / 0.675 / −105.83 / 111.11 | −0.1082 / 0.673 / −106.67 / 111.94 | −0.1077 / 0.674 / −106.15 / 111.42 | 12 | 3 |
| 15m | forward | 170 | −0.1095 / 0.727 / −18.61 / 22.75 | −0.1099 / 0.726 / −18.69 / 22.83 | −0.1099 / 0.726 / −18.69 / 22.83 | — | — |
| 1h | all, 03-02 → 10-30 | 729 | −0.0391 / 0.896 / −28.52 / 40.84 | −0.0443 / 0.884 / −32.32 / 44.33 | −0.0406 / 0.892 / −29.58 / 44.20 | 13 | 5 |
| 1h | forward | 49 | −0.1859 / 0.545 / −9.11 / 11.03 | unchanged | unchanged | — | — |

**Worst single gap exits:**

| TF | Exits |
|---|---|
| 5m | −2.94 R (2026-09-13 22:00, a Sunday reopen) |
| 1h | −2.78 R (2026-05-24 22:00) and −2.42 R (2026-06-14 22:00), both Sunday reopens |
| 15m | ≤ −0.26 R |

Under the current rule each of these was recorded at about −1 R.

**Win rate** falls by at most 0.3 points (1h: 39.09 → 38.82%).

## 7. Tests required before any engine change is merged

**Unit tests** (`tests/test_backtest_gaps.py`, hand-worked bars, written before the code):

1. Long, `open < stop`: exits at the open, label SL_GAP, R < −1 by exactly `(stop − open) / risk` plus cost.
2. Short, `open > stop`: the mirror of 1.
3. Long, open between the stop and entry, `low < stop`: fills at the stop (unchanged behaviour).
4. Long, `open ≥ TP2` with TP1 not done: both halves at the open; label TP2.
5. Long, TP1 ≤ open < TP2: half at the open, then the rest of the bar as now (it can still hit TP2 or the stop in the
   same bar).
6. After TP1 (breakeven stop), `open < entry`: BE_GAP at the open, which can now lose.
7. Short versions of 4–6.
8. A bar with open = stop exactly: counts as a gap (`≤` / `≥`), and fills at the same price either way.
9. NaN open: falls back to the existing rule. The data loader never emits one, but it is defended.
10. Costs: `cost_pts` is identical before and after for every trade (no double counting).

**Integration tests:**

11. `engine.run` → `backtest.simulate` on `load_synthetic` with forced gaps: every SL_GAP / BE_GAP trade has
    `exit = open[exit_i]`, and no trade's exit lies outside that bar's [low, high].
12. All arms (H2–H6, control, challenger) use the new fills through `backtest.simulate`; their own tests still pass.
13. `test_no_lookahead` and every arm's look-ahead test: a fill on bar i reads only bar i.

**Regression tests:**

14. On a fixture with **no gaps**, the new simulator gives trade lists identical to web.6's (entry, exit, P&L,
    labels).
15. Golden numbers from §6 (the stored window, frozen fixture): trade counts, number of gap exits, and sum R to 1e-3.
16. `holdout`: the new engine hash produces a new freeze key; `load_or_freeze` archives web.6 and starts web.7; no
    ledger entry is deleted.

**Edge cases:**

17. A gap on the bar right after entry.
18. A gap on a flip bar.
19. A gap on the last bar while the trade is open.
20. A Sunday reopen bar rebuilt by `repair_reopen`.
21. TP1 = TP2 (H4's no-second-level case).
22. A stop gapped exactly to TP on a short.

## 8. Expected effects

| Measure | Expected change |
|---|---|
| Expectancy | Lower for any arm holding through gaps; unchanged where no trade gaps. Measured: H4 −0.0009 to −0.0052 R per trade (stop only); −0.0000 to −0.0015 with symmetric limit fills; treatment 0 |
| Profit factor | Slightly lower (H4 −0.002 to −0.013); treatment unchanged |
| Max drawdown | Higher where gap losses cluster (H4 1h: 40.8 → 44.2–44.3 R); unchanged elsewhere |
| Individual trades | A few become worse than −1 R (to −2.9 R here). Some TP fills improve slightly. Win rate falls by ≤ 0.3 points |
| Conclusions | **None change.** H4 stays significantly negative (5m t −8.4 → −8.36 / −8.46). The treatment's small positive mean stays insignificant |

The correction makes the record **more honest, not better**. Its size is small on this sample because few positions
are held across gaps.

## 9. Engine version and forward-test restart procedure (on approval only)

1. Copy this text into `audit/PREREGISTRATION.md` as Amendment 14, with the approval date and the operator's words.
   Commit that **before** any code.
2. Tag the last web.6 commit `engine-web.6-final`, so the original engine stays checkable.
3. Write the tests of §7 first. They fail on web.6 (except 3, 14 and 15, which define the unchanged behaviour).
4. Change `backtest.simulate` only. Set `ENGINE_VERSION = "Q7.2-web.7"`. No other change rides along unless it is
   separately approved, for example the commission profile of `audit/COST_PROFILES.md` §5, if you choose to bundle it.
5. Run `python -m pytest -q tests` (all tests, including look-ahead) and the re-simulation of §6. The golden numbers
   must match.
6. Merge, then dispatch `quantum-site.yml`. On its first run:
   - `holdout.load_or_freeze` sees the new engine hash, sets status RESET, records web.6 in `history` with its
     `ended_utc`, and starts web.7 with a new freeze time.
   - Every arm key (engine key + arm hash) changes with it, so H2–H6 restart together.
7. Verify: the new main key is published; web.6 is in `history`; web.6 ledger entries are in `holdout/archive/` on
   `forward-ledger`; no file is deleted.
8. Record the web.7 start in `PREREGISTRATION.md` (key, time, run ID), as was done for Amendment 9.

## 10. Preserving the original engine and its records

- **The web.6 record:**
  - Its ledgers stay in git history on `forward-ledger` (normal commits, never force-pushed).
  - On restart they are moved, not deleted, to `holdout/archive/<tf>_<arm>.json` (`holdout.update_ledger`).
  - Every trade carries its `freeze_key`, so web.6 and web.7 trades can always be told apart.
- **The web.6 engine:** the tag `engine-web.6-final` and `holdout_manifest.json`'s `history` (key, version, start,
  end).
- **A web.6 summary to write at the restart:**
  - `audit/FORWARD_WEB6_FINAL.md`, with per-arm N, win %, mean R, t and PF from the archived ledgers.
  - So the original result is stated separately, and it is never pooled with web.7.
- **No pooling.** web.6 and web.7 results are reported separately. A verdict uses only one key's trades, as now.

## 11. Cost and alternative (for the operator's decision)

**The cost of approving:** every forward test restarts, losing about two weeks of counted record. The record is kept
in the archive, but it no longer counts toward a verdict. On the measured data the correction changes the forward
ledgers by at most 0.09 R in total (5m H4), and by 0 for the treatment.

**The alternative (not recommended as permanent):**

- Record a **shadow ledger** under the new rule from a module outside `ENGINE_SOURCES`, display only. Keep web.6
  counting; switch at the next restart that is needed anyway.
- This avoids a restart now. But the counted record would keep the optimistic fill until then, and a display-only
  ledger must never be cited as evidence (CLAUDE.md, one system of record).

**Recommendation:** approve the replacement (§9). Optionally bundle it with the commission profile of your verified
main account, once your MT5 evidence is in, so that the forward test restarts only once.

## 12. Open assumptions and limitations

1. The fill at the open is a lower bound on the gap damage; there is no tick data (§4).
2. Reopen-bar opens are estimates rebuilt from 5-minute bars (D-09).
3. Re-simulating today's store gives 498 / 170 forward H4 trades (5m / 15m), against 511 / 171 in the recorded
   ledgers. The recorded ledger is the record. Re-simulation depends on the store's start date: the engine's state is
   path-dependent, and each recorded run began from the store as it was then. The §6 forward rows are therefore
   indicative, not a restatement of the ledger.
4. The impact figures are in-sample, on 2–8 months of data: small samples, one market regime.
5. The broker commission and spread are not yet verified from MT5 evidence (`audit/COST_PROFILES.md`).
