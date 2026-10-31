# Independent verification of engine web.7 (Amendment 14) — 2026-11-01

**Scope:**

- the merged implementation (`quantum/backtest.py` at `fbd866b04`);
- its tests (`tests/test_backtest_gaps.py`);
- the forward ledgers on `forward-ledger` @ `5f72626c81ee11bf91e5cf9ebbf000f1a8a14de8` (the first web.7 run).

**No engine file, configuration or forward test was changed by this review.** The freeze key is
`5e4630924d663fc5:60bb01794d03c9ac`; the arm suffixes are unchanged (re-checked after the review).

## 1. Code against the approved rule

| Approved rule (Amendment 14 §2) | Code (`backtest.simulate`) | Verdict |
|---|---|---|
| A1: open at or beyond TP2 → everything left at the open; TP1's half too if not done | `if gap_ok and beyond(pos["tp2"])` … legs (0.5, open) when TP1 not done … `_close(pos, oi, …, "TP2")` | matches |
| A2: otherwise, TP1 not done and open at or beyond TP1 → half at the open, then continue | `elif gap_ok and not pos["tp1_done"] and beyond(pos["tp1"])` | matches |
| B1: open at or through the stop → the rest at the open, `SL_GAP` / `BE_GAP` | `if gap_ok and through(pos["sl"])` → `_close(pos, oi, …, stop_lbl + "_GAP")` | matches |
| B2: otherwise low / high touches the stop → the stop price | unchanged intrabar test | matches |
| C: otherwise TP1 / TP2 intrabar; breakeven from the next bar | unchanged | matches |
| Long and short mirrored | `beyond` / `through` lambdas chosen by `pos["long"]` (`≥` / `≤` swapped) | matches |
| A NaN open falls back to the old rule | `gap_ok = not math.isnan(oi)` | matches |
| Costs unchanged, charged once | `cost` is still set once at entry; `_close` subtracts it once; no new cost term | matches |

**One behaviour worth naming.** It is inside the approved rule, and it was disclosed in PR #52.

- After TP1, if the bar closes beyond entry, the breakeven stop is already crossed when it goes live.
- It fills at the next open (`BE_GAP`). That is how MT5 behaves: a stop cannot rest beyond the current price, so the
  position closes at market.
- Test 14 asserts that every difference from web.6 on a gap-free feed is exactly this case.

## 2. Do the tests establish the behaviour?

### 2.1 Requirement → test map

| Requirement | Tests (long) | Tests (short) |
|---|---|---|
| Stop gap fills at the open | 01, 17, 18, 19, 20 (Sunday reopen, repaired open) | 02 |
| Boundary: open exactly at the stop is a gap | 08 | **08b (added by this review)** |
| Open inside, then through the stop → stop price (unchanged) | 03 | covered by 11 / 14 on synthetic data |
| TP2 gap → all at the open, TP1's half included | 04, 21 (TP1 = TP2) | 07, 22 |
| TP1 gap → half at the open, then the bar continues (TP2, or the original stop) | 05 | 07 |
| Breakeven after a partial exit, gapped through → `BE_GAP` at the open | 06 | 07 |
| Costs once; identical with or without a gap | 10, 12 (the gap exit's R includes exactly one cost) | 02 |
| No look-ahead | 13 | 13 |
| Equals the reviewed reference rule (`audit/tools/gapsim.py`, mode "both") | 14 (synthetic, with and without forced gaps) | 14 |
| Golden numbers on real data (1h H4: n 729, 13 gap exits, sum R −28.5189 → −29.5761) | 15 | 15 |
| Restart archives, never deletes | 16 | — |

### 2.2 Mutation test

`audit/tools/mutation_gaps.py` applies 15 deliberate faults, one at a time, to a **copy** of `backtest.py`, and runs
the 23 tests against each.

| Mutant | Fault | Result |
|---|---|---|
| M01 | stop gap filled at the stop price (the web.6 optimism) | killed (10 tests) |
| M02 | rule removed entirely | killed (16 tests) |
| M03 / M04 | TP2 / TP1 open-gap removed | killed |
| M05 | TP2 gap "forgets" TP1's half | **survived: equivalent mutant.** Both halves fill at the open either way, so P&L, R and the label are identical; no test can tell them apart |
| M06 | TP gap filled at the limit price instead of the open | killed |
| M07 | long boundary `<` instead of `≤` | killed (test 08) |
| M08 | short boundary `>` instead of `≥` | **survived the original 22 tests** (only the label differs; the price is the same). Killed by the added test 08b |
| M09 / M10 | short stop / target direction inverted | killed |
| M11 | breakeven stop never gaps | killed |
| M12 | gap exit charged a second cost | killed (tests 01, 02, 10, 15) |
| M13 | breakeven never labelled | killed |
| M14 | stop checked before targets at the open | **survived: equivalent mutant.** The stop and targets are on opposite sides of entry, so an open cannot be beyond both. All 1,179 archived trades satisfy the level order (§3) |
| M15 | partial at the open sized 100% | killed |

**Result:** every non-equivalent fault is detected. One real gap was found (M08, label only) and closed by test 08b.
That is a test-file change only; the engine is untouched.

## 3. Ledger consistency

`audit/tools/ledger_check.py` was run on the first web.7 snapshot. It checks:

- **Attribution:** each trade's key against its file's arm and the key active when it was entered.
- **Duplicates.**
- **Time window:** entry inside its key's window.
- **Each trade's own arithmetic:** pts = gross − cost; R = pts / initial risk; level order; exit price consistent
  with the label; recorded after its exit.

| Key | Engine | Where | Trades | Problems |
|---|---|---|---|---|
| `…32babc71ed938b30` | web.3 | archive | 27 | 0 |
| `…3252a9f0d312db75` | web.4 | archive | 14 | 0 |
| `…92b67584f33cc1f0` | web.5 | archive | 340 | 0 |
| `…6f3964ad97813cc9` | **web.6** | archive | **798** | 0 |
| `…60bb01794d03c9ac` | **web.7** | live | 0 (the market was shut: 31 Oct is a Saturday) | 0 |

- The 798 web.6 trades equal the last web.6 snapshot (`a9bc97a1`) exactly.
- No web.6 trade remains in a live ledger.
- No web.6 trade carries a web.7 label.
- All five arm manifests started at 2026-10-31 17:23:01 UTC, each keeping its previous key in `history`.

**Not yet testable:** web.7's own trades. Re-run `ledger_check.py` after the first trading week. A web.7 trade must
carry the new key, and every `SL_GAP` / `BE_GAP` exit must equal that bar's open.

## 4. Correction to the approved amendment's text (facts only)

Amendment 14 §6.2 called H4 "the only arm that trades through gaps". **That is wrong.** The impact study measured
only the treatment and H4. The per-arm re-run (`audit/GAP_SENSITIVITY_2026-11-01.md`) found two more gap exits in
the stored history:

| Arm | Gap exits | Effect |
|---|---|---|
| H3, 1h | 1 | mean R −0.373 → −0.385; max DD 12.2 → 13.9 R |
| H5, 15m | 1 (of 3 trades) | mean R −0.489 → −0.497 |

No other arm, and no conclusion, changes. The correction is recorded as a dated note under Amendment 14 in
`audit/PREREGISTRATION.md`; the approved text itself is not edited.

## 5. Evidence

| Check | Result |
|---|---|
| `python -m pytest -q tests` | all pass (204 = 203 + test 08b), run after the review |
| `tests/test_backtest_gaps.py` | 23 passed |
| Mutation suite | 13 of 15 killed; 2 equivalent |
| `ledger_check.py` | 0 problems in 1,179 archived trades |
| Freeze keys | unchanged by this review |
