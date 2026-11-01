# 14 — Implementation roadmap and prioritised findings (2026-11-01)

**Nothing below changes production strategy logic without the operator's written approval.** Display fixes need
approval as a group. New strategies need registration under Amendment 11/13.

## 1. Prioritised table (Part 25 of the brief)

| Priority | Problem | Evidence | Proposed fix | Expected benefit | Test | Acceptance criterion |
|---|---|---|---|---|---|---|
| **P0** | The H4 playbook signal has no directional information | 47.7–50.6% direction at 1–48 bars on 5m / 15m / 1h; gross −0.035 R; forward 5m t −4.75 (`03`) | Keep the levels as display; state on the card that the triggers are not signals (already "levels to watch"); no re-tuning | Avoids trading a losing rule | Display test | The card shows the in-sample and forward record honestly (next row) |
| **P0** | The site says "triggers won 35% of 986" and shows R:R from the trigger | `03` §1, §2 | Text: "986 in-sample trades: 35% ended positive; −0.11 R per trade after costs". Show R:R from the expected entry as well | Correct reading | Playwright text check | The figures equal `h4_outcome_audit.py` output |
| **P0** | The web.6 forward verdict vanished after the restart | `03` §7 | Show the archived web.6 record ("previous engine, archived"), separately from web.7 | No loss of evidence | Render test | Both records shown, never pooled |
| **P0** | No displayed probability is calibrated | `CURRENT_PERFORMANCE_AUDIT` §4 | Keep "score" labels; build calibrated event models (`07` / `08`) on research data | Honest probabilities | `09` §5 | ECE < 5 points and slope interval contains 1 on validation |
| **P0** | Broker costs unverified | `audit/COST_PROFILES.md` | MT5 evidence E1–E6 from the operator | Real net expectancy | Derivation rules §4.2 | Each profile VERIFIED or corrected |
| **P1** | No research harness (labels, purged CV, registry) | — | Build `quantum/research/`: event labeller (§2 of `09`), purged walk-forward, CPCV / PBO, DSR, Reality Check, trial registry | Ability to test anything honestly | Unit tests on synthetic data with known edge / no edge | Detects a planted edge; reports PBO ≈ 0.5 on noise |
| **P1** | Strategy families untested (`04` B) | — | B1: TSMOM, Donchian, session breakouts, vol regime on development data | First candidate with real evidence, or a documented null | `09` | Passes §3 thresholds on validation |
| **P1** | Splits by direction / session / regime only exploratory | `03` §4 | Pre-register any split as a hypothesis before validation | Avoids subgroup mining | `09` §6 | FDR-controlled |
| **P2** | No regime classifier with measured value | — | Volatility-state classifier (EWMA / GARCH terciles, then HMM) tested for conditional expectancy | Strategy selection by regime | Out-of-sample conditional expectancy | Regime label changes next-period net R significantly |
| **P2** | No trend-transition or target-zone engine with validation | — | Specs `11`, `12`; BOCPD (R16) and quantile models; scored as events | Early warnings with known hit rates | Event scoring | Calibrated, coverage reported |
| **P3** | ML / ensembles | — | Only after P1 features show signal; GBM against logistic baseline | Possibly small gains | Purged CV + DSR | Beats the baseline net of costs |
| **P3** | Drift monitoring | — | Rolling calibration and expectancy monitors on live arms | Early detection of decay | Synthetic drift test | Alerts on planted drift |

## 2. Phases and approval gates

| Phase | Content | Production impact | Gate |
|---|---|---|---|
| **A (this delivery)** | Audits: strategy, performance, signal outcome, data; root cause (`03`); literature (`01`); matrix (`04`); validation framework (`09`); this roadmap; acceptance tests (`15`) | none | **The operator reviews A** |
| A-fix | The three P0 display corrections in §1 | display only (no key change) | **done** (PR #57, live) |
| B0 | Research harness (P1, row 1) + trial registry | none (research code; outside `ENGINE_SOURCES`) | **done** (`quantum/research/harness.py`, tests) |
| B1 | Families with an empirical prior on development data; documents `02`, `05`, `06`, `07`, `08`, `10` written from results | none | **done for TSMOM / Donchian / session breakouts / vol conditioning: all rejected** (`B1_DEVELOPMENT_RESULTS.md`); nothing to register |
| B2 | SMC families against matched baselines, on the operator's trade (+$20 / +$10 / +$2 before −$10) | none | **done: 54 trials, all rejected** (`B2_DEVELOPMENT_RESULTS.md`); nothing to register |
| B2b | The same setups on +$20 before −$20 (SL / TP $1,000 at 0.5 lot) | none | **done: 18 trials, all rejected** (`B2B_DEVELOPMENT_RESULTS.md`); nothing to register |
| B2c | The same setups on +$15 before −$10 (completes +$10 / +$15 / +$20 with a −$10 stop) | none | **done: 18 trials, all rejected** (`B2C_DEVELOPMENT_RESULTS.md`); nothing to register |
| B3 | Combinations: 1h trend alignment + confirmation entry + SMC sequences (sweep → MSS → FVG) on the −$10 stop | none | **done: 210 trials, all rejected** (`B3_DEVELOPMENT_RESULTS.md`); no ingredient moves success more than ±1 point over matched random |
| B4 | Entry-price hypotheses from the literature: round numbers (Osler), session-open momentum (Gao et al.), limit entries (adverse selection) | none | **done: 48 trials, none passes**; round-number continuation is the one consistent lead and the candidate for a single pre-declared validation test (`ENTRY_PRICE_RESEARCH.md`) |
| C (B4-RN-V1) | One validation test of the round-number lead, registered before the data was read, approved by the operator | none | **done: FAIL** (41.5% vs random 40.3%, z +0.20; net −0.044 R). Lead closed; holdout stays sealed |
| B5 | Order flow: exploratory proxy on stored GC bars (no signal). Real CME study run 2026-11-01 on 74.5M trades (amendment A1, trades schema, $93.27 from the free credit): **all 18 trials rejected**, AUC 0.50 (`B5_DEVELOPMENT_RESULTS.md`). B5b (OANDA) unavailable in Pakistan; B5c (Dukascopy) declared and paused | none | done |
| C | Validation, then a one-time holdout; a promoted strategy becomes a **new forward arm** with its own freeze key | new arm only; existing arms untouched | Operator approves promotion |
| D | Dashboard: regime, selected strategy, calibrated probabilities, coverage tiers (Part 21) — only for components that passed C | display | Operator approves |

**Documents not yet written** (`02`, `05`–`08`, `10`–`13`) depend on Phase B results. Writing them now would mean
writing specifications whose numbers are invented. Each will state its measured inputs.

## 3. What to expect, stated now

- **The evidence today supports no claim of edge.** The realistic first goal is a validated strategy with net
  expectancy > 0 at t > 3, not 90% accuracy.
- **High-accuracy tiers are only admissible** with n ≥ 184 per claim (90% observed, 85% floor), with coverage and
  net expectancy reported (`09` §4). At current trade rates a 1H arm would need years to reach that. Shorter
  timeframes reach n faster but pay 2–5× more cost per R.
- **A possible outcome of Phase B is a documented null:** no tested family survives. That is a valid, valuable
  result, and the site would keep saying WAIT.
