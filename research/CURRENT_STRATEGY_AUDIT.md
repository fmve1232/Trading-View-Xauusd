# Current strategy audit — what generates signals today (2026-11-01, engine web.7)

This is an inventory and audit, and nothing was changed. Code facts come from the repository at `8b2311179`.
`audit/INSTITUTIONAL_AUDIT_2026-10-31.md` has the full component inventory.

## 1. Signal generators (each arm is a separate pre-registered hypothesis)

| Arm | Source | Entry logic (summary) | Stop / targets | Decides on | Registered |
|---|---|---|---|---|---|
| **Treatment** | `engine.py` | Bull / bear composite scores; a trigger candle (structure break or strong candle); gates for trend, HTF, recent, session ≥ 30, news (off), drawdown; vetoes for trade quality < floor, race EV < 0, calibrated P < minimum, risk lock | Plan from structure / liquidity / ATR (`_plan`); 50% at TP1, then breakeven, then TP2 | 1H | §7 |
| **Control** | `engine.py` "control" | The treatment with the old, stricter gates | same | 1H (comparison only) | §3 |
| **Challenger (H1)** | `engine.py` "challenger" | The treatment with a different trend gate | same | 1H | §3 / Amendment 3 |
| **H2 "Sweep and Value"** | `arm_h2.py` | Trend (close > EMA200, EMA20 > EMA100) + a liquidity sweep within 3 bars + low ≤ VAL + close > previous high + session ≥ 30 | Stop below the swept low − 0.1 ATR; TP1 POC (≥ 1R), TP2 VAH / resistance | 1H | Amendment 5 |
| **H3 "Sweep-to-Value"** | `arm_h3.py` | 2 of the 1H / 4H / 1D trend scores ≥ 60 + a swing-low sweep + close ≤ POC + risk within 0.5–5 ATR | Stop low − 0.15 ATR; TP1 max(POC, 1R), TP2 max(VAH, 2R) | 1H | Amendment 7 |
| **H4 "Playbook"** | `arm_h4.py` | A close beyond the nearest of 15 levels (PDH/L, PWH/L, PMH/L, EQH/L, day high/low, internal pivots, VAH / VAL / POC) at least 0.1 ATR from the previous close | Stop at trigger ∓ (regime SL multiple × adaptive ATR); TP1 / TP2 at the next levels ≥ 1 stop beyond, else 2R | 15m | Amendment 8 |
| **H5 "High confidence"** | `arm_h5.py` | The treatment's signal AND bias BULL / BEAR AND the live 4H / 1D ≥ 60 / ≤ 40 AND the macro vote AND session ≥ 30 | the engine's plan | 1H (N ≥ 30) | Amendment 10 |
| **H6 "No score veto"** | `arm_h6.py` | The treatment's signal without the calibration veto | the engine's plan | 1H | Amendment 12 |

**Overlaps.**

- H5 and H6 are subsets / supersets of the treatment, so their trades coincide with it (5m: H6 = treatment, 37 = 37).
- The control and the challenger share most treatment trades (15m: challenger = treatment, 12 = 12).
- These are **not independent pieces of evidence**.

## 2. Probability calculations and calibration

| Output | Where | Status |
|---|---|---|
| `cal_p_long` / `cal_p_short` (P of +1R before −1R) | `engine.py` calibration block | **No skill:** AUC 0.38–0.52, negative Brier skill (Amendment 12; audit §7). Relabelled "score" on the site; still used by the calibration veto (H6 tests the effect of removing it) |
| `hit_prob` / touch rates (P of reaching TP1 / TP2 / TP3 within N bars) | `analog.py` | Unconditional excursion frequencies, not a TP-before-SL race; not calibrated forward |
| `race_prob` → plan EV | `analog.py` → `engine._plan` | In-sample estimate; feeds the EV veto; not calibrated forward |
| Analog win rate, IS / ROLL | `analog.py` | ROLL is a trailing slice, **not a holdout** (F-037) |
| Kelly % | `report.kelly` | Correct maths, applied to the uncalibrated rates above. In practice it sizes to 0 when the edge is negative |

## 3. Hard-coded thresholds

`config.py` has 71 fields: 55 numeric parameters and 15 switches, all Pine v32 input defaults. Examples:

- `adx_threshold` 25, `trend_threshold` 60, `tq_min_score` 55;
- session ≥ 30, the HTF 60 / 40 bands, `max_daily_loss_r` 3;
- the H4 constants GAP 0.1 / MERGE 0.05 / MIN_TP 1R / FALLBACK 2R.

**None was fitted on the website's data.** All were inherited (Pine) or pre-registered, so the record is honest.
But it also means **nobody has ever verified out of sample that any of them carries information**. They are frozen
so that the forward test means something.

## 4. Data paths with risk

| Path | Risk | Control |
|---|---|---|
| Price fallback: Twelve Data → Yahoo `XAUUSD=X` → Yahoo `GC=F` (futures) | Futures carry a basis to spot of several dollars; running the engine on the wrong instrument | Every payload and every ledger trade records `price_source`; §7 counts only `twelvedata:XAU/USD` trades. **This audit itself hit the fallback** when the API key variable was unset (its first run was discarded) |
| `--synthetic` | Synthetic bars | Only on request; labelled SYNTHETIC; alerts and ledgers skip it |
| 24/7 quote bars | Weekend "bars" | Removed (`trading_week_only`); research loader too (D-R1) |

## 5. Look-ahead and leakage

- **Tested:** `test_no_lookahead` and the per-arm truncation tests. HTF series read `close[1]` (D-01). Pivots are
  published late. The H4 playbook is built at bar i−1.
- **The leakage that remains is in interpretation, not in code:** every "past data" figure on the site is computed on
  the same window the operator looks at. Only the forward ledgers are out of sample.

## 6. Dead and duplicate code

- `pyflakes` reports unused names in `arm_h4.py` / `arm_h2.py`. They are inside their arms' freeze keys, so they
  are kept (L-01).
- `config.commission_per_oz` is unused (L-04).
- The JS sizing maths mirrors Python, and a parity test enforces it.

## 7. Presentation claims to correct (display; proposed in `03` §7)

1. "Triggers won 35% of 986" → trades, in-sample, net.
2. The reward:risk tile is measured from the trigger, not the entry.
3. The web.6 forward verdict is no longer shown after the restart.
