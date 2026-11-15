# B30: does waiting for a $10 / $15 / $20 favourable move before entry raise TP-first odds?

**Registration:** `research/registrations/B30.json`. It was approved by the operator's directive of 2026-11-15, committed (`015739041`) and pushed **before** any of the code (`4007aa81d`), and that code ran before any result was seen.

**Results file:** `research/results/b30_all_partitions_2026-11-15.json`. The trials are appended to `research/trials.jsonl` (128 lines).

**Code under test:** the production engine at `51f9142d8`, freeze key `5e4630924d663fc5:a6f2be58c74887ed` (unchanged).

## 1. Answer

**No threshold is supported out of sample. B30 recommends none of $10, $15 or $20 on evidence.**

- **The registered primary rule.** The test uses engine signals (ENG), the operator's two-target plan recalculated from the actual entry (G1), model costs, and validation + holdout pooled. Each threshold had to clear three conditions:
  - a positive out-of-sample mean with its bootstrap lower bound above 0;
  - a gain over no confirmation at Holm p < 0.05;
  - the same direction on development.
- **The result.** None cleared them. Every out-of-sample interval contains 0, and the Holm p-values are 0.81, 0.81 and 0.52.
- **The random-entry control (RND).** It gives the large-sample answer to "does a $X favourable move by itself carry information":
  - not consistently;
  - net expectancy is negative for every model in every period;
  - confirmation helped only in the 2024-25 holdout, and hurt or did nothing in 2020-22, 2023-24 and 2026.
- **"Wait for $20" looks best on the engine's signals out of sample** (TP1 first 61.8% on 34 trades). That is the kind of result the operator warned against reading at face value:
  - it is not significant (p 0.52 after Holm);
  - it was worse than $15 on development;
  - it was the worst of the four in 2026;
  - on random entries, $20 is no better than entering at once.
- **If the stop and target stay at the levels set at the trigger, confirmation is almost always rejected.** The remaining reward is too small for the risk, exactly as the operator anticipated:
  - with the engine's own levels (G2), 0 of 26 $10-confirmed development trades remained executable;
  - with the phone's ±$13 levels set at the trigger (G0), after $10 at most $3 is left to TP1 for $23 of risk; after $15 or $20, TP1 has already been passed.
- **Confirmation can therefore only be applied as the operator directs:** recalculate entry, stop and targets from the actual entry. That is what G1 tests, and G1 is the plan used in the table below.

## 2. The comparison table the operator asked for

Population and plan:
- **Population:** the frozen engine's signals on 15m / 30m / 1h / 4h, one per idea (REPEAT rule).
- **Plan:** stop 13, TP1 +13 for half, TP2 +20 for the other half, stop to entry after TP1. All distances are from the actual entry, in $ at $4,000 scaled by price; costs are the engine's model, about $0.78/oz here.
- **Sizing:** every trade risks $650 including cost (0.46 lot at $4,000, N1). So 1 R = $650.

**Out of sample: validation (2023-01-24 → 2024-06-30) + holdout (2024-07-01 → 2025-12-31), pooled, each scored after its warm-up (from 2023-04-01 and 2024-09-06).**

| Model | Confirmation | Trades | TP1 first (Wilson 95%) | TP2 first | SL first | Ambiguous | Net expectancy per trade, R (bootstrap 95%) | $ per trade at $650 | Holm p vs Baseline | Supported |
|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | none (entry at the trigger close) | 110 | 51.8% (43–61) | 34.5% (26–44) | 47.3% (38–57) | 1 | −0.01 | −$9 | — | — |
| Model A | $10 | 48 | 56.2% (42–69) | 29.2% (18–43) | 43.8% (31–58) | 0 | +0.00 (−0.28 to +0.27) | +$3 | 0.81 | **no** |
| Model B | $15 | 42 | 54.8% (40–69) | 35.7% (23–51) | 45.2% (31–60) | 0 | +0.03 (−0.26 to +0.30) | +$19 | 0.81 | **no** |
| Model C | $20 | 34 | 61.8% (45–76) | 41.2% (26–58) | 38.2% (24–55) | 0 | +0.17 (−0.17 to +0.46) | +$109 | 0.52 | **no** |

**Break-even** for this plan at $0.78/oz is a TP1-first rate of about 52.7%.
- Formula: p* = (13 + c) / (19.5 + 10q), where q = TP2 given TP1 ≈ 0.67.
- Every model's Wilson interval contains it.

### Per period (same population and plan)

| Period | Model | Triggers → trades | TP1 first | SL first | Net R (bootstrap 95%) | Max drawdown at $650 / trade | Longest losing run | Median entry delay |
|---|---|---|---|---|---|---|---|---|
| Development 2020-04 → 2023-01 | Baseline | 64 → 64 | 42.2% | 57.8% | −0.25 (−0.47 to −0.01) | $12,717 | 8 | 0 |
| | $10 | 64 → 26 | 50.0% | 50.0% | −0.15 (−0.57 to +0.22) | $4,834 | 3 | 90 min |
| | $15 | 64 → 20 | 60.0% | 40.0% | +0.07 (−0.43 to +0.51) | $2,600 | 4 | 165 min |
| | $20 | 64 → 19 | 47.4% | 52.6% | −0.06 (−0.54 to +0.39) | $3,101 | 3 | 150 min |
| Validation 2023-04 → 2024-06 | Baseline | 24 → 24 | 45.8% | 54.2% | −0.11 (−0.50 to +0.29) | $4,567 | 7 | 0 |
| | $10 | 24 → 9 | 55.6% | 44.4% | +0.02 (−0.74 to +0.61) | $1,043 | 1 | 120 min |
| | $15 | 24 → 7 | 71.4% | 28.6% | +0.31 (−0.53 to +0.88) | $650 | 1 | 135 min |
| | $20 | 24 → 5 | 60.0% | 40.0% | +0.13 (−1.00 to +0.88) | $1,300 | 2 | 150 min |
| Holdout 2024-09 → 2025-12 | Baseline | 86 → 86 | 53.5% | 45.3% | +0.01 (−0.19 to +0.22) | $6,090 | 3 | 0 |
| | $10 | 86 → 39 | 56.4% | 43.6% | +0.00 (−0.29 to +0.28) | $3,402 | 4 | 120 min |
| | $15 | 86 → 35 | 51.4% | 48.6% | −0.03 (−0.31 to +0.26) | $3,236 | 3 | 210 min |
| | $20 | 86 → 29 | 62.1% | 37.9% | +0.17 (−0.19 to +0.49) | $1,693 | 2 | 315 min |
| 2026 (recent, not sealed) 2026-03 → 2026-11 | Baseline | 55 → 55 | 47.3% | 52.7% | −0.17 (−0.39 to +0.04) | $7,324 | 4 | 0 |
| | $10 | 55 → 26 | 61.5% | 38.5% | +0.01 (−0.32 to +0.29) | $1,680 | 2 | 68 min |
| | $15 | 55 → 23 | 56.5% | 43.5% | −0.01 (−0.38 to +0.31) | $1,950 | 3 | 90 min |
| | $20 | 55 → 21 | 57.1% | 42.9% | −0.09 (−0.43 to +0.22) | $1,696 | 2 | 105 min |

How to read the drawdown and timing columns:
- Drawdowns are lower with confirmation mainly because there are **fewer trades**, not better ones. The comparable figure is the net R per trade.
- Timeouts: 0% in every cell; every trade reached its stop or TP1 within 48 hours.
- Same-bar ambiguity: 1 of 110 out-of-sample Baseline trades and 0 elsewhere for ENG. On random entries it was 0.2–1.0%. Ambiguous bars are counted as stops, never as wins.

## 3. The lifecycle: favourable move, confirmation and entry are different events

ENG triggers on development, out of sample and in 2026:

| Period | Triggers | Touched +$10 / +$15 / +$20 at any time | Confirmed by a close: $10 / $15 / $20 | Invalidated ($13 against, or an opposite structure break) at $10 / $15 / $20 | Expired |
|---|---|---|---|---|---|
| Development | 64 | 52 / 40 / 36 | 26 / 20 / 19 | 38 / 44 / 45 | 0 |
| Validation | 24 | 16 / 13 / 13 | 9 / 7 / 5 | 15 / 17 / 19 | 0 |
| Holdout | 86 | 70 / 64 / 57 | 39 / 35 / 29 | 47 / 51 / 57 | 0 |
| 2026 | 55 | 44 / 42 / 40 | 26 / 23 / 21 | 29 / 32 / 34 | 0 |

What the lifecycle shows:
- **About half the triggers that touch +$10 never confirm.** Price trades $13 against the trigger, or the structure breaks the other way, before any 15m close $10 beyond.
  - A touch is not an entry. The system must not treat it as one; the alerts PR (C1) keeps them apart.
- **Missed opportunities** (triggers not entered whose no-confirmation trade reached TP1 first):

| Period | $10 | $15 | $20 |
|---|---|---|---|
| Development | 2 of 38 | 7 of 44 | 8 of 45 |
| Holdout | 7 of 47 | 11 of 51 | 17 of 57 |

- **Entry delay grows with the threshold:** median 1–2 h at $10, up to 5 h at $20 in the holdout. Means run to several hours because some ideas confirm only near the 24-hour limit.
- **Excursions per trade** (mean, $ at $4,000, from the entry):

| Period | Baseline | $10 | $15 | $20 |
|---|---|---|---|---|
| Development, MFE / MAE | 12.4 / 11.3 | 13.3 / 10.2 | 15.7 / 8.4 | 13.6 / 9.8 |
| Holdout, MFE / MAE | 13.6 / 10.2 | 13.1 / 9.9 | 14.2 / 10.9 | 14.6 / 9.4 |

  No model separates them consistently.
- **Reversal** (stopped after first moving half-way to TP1): 0–26% across cells, with no consistent ordering by threshold.
- **Realised reward-to-risk** (mean winner / mean loser, net): 0.6–1.0 in every cell. It is below 1 because the second half often exits at entry.

## 4. Secondary results (not decisive)

**RND: every 8th 15m close, both directions (thousands of trades per period).**

| Period | Baseline net R | $10 | $15 | $20 |
|---|---|---|---|---|
| Development | −0.087 | −0.116 | −0.126 | −0.129 |
| Validation | −0.081 | −0.085 | −0.113 | −0.103 |
| Holdout | −0.076 | −0.018 | −0.008 | −0.013 |
| 2026 | −0.102 | −0.123 | −0.132 | −0.180 |

- The Baseline TP1-first and SL-first rates are both 49.5–49.8%. This is the symmetry check a correct labeller must pass on random entries.
- **Confirmation helped only in the holdout** (Welch p 0.001–0.004 there) and hurt in the other three periods.
- A $X move is not a stable predictor of continuation on this market, and every model loses after costs.

**STR: B19's structure triggers.**
- The pattern is the same: confirmation helps in some periods and hurts in others.
- Validation: $15 −0.20 R vs Baseline −0.04.
- 2026: all three thresholds are near 0 against −0.18 for the Baseline.
- Every interval contains 0.

**G2: the engine's own stop / TP1 fixed at the trigger, with the R:R re-check.**
- Confirmation is rejected almost always (development: 0 of 26 / 20 / 19 executable; holdout: 4 / 1 / 0). This is the operator's "reject if too little reward remains" rule doing its job.
- **Lead, not a result:** the G2 *Baseline* (engine levels, entered at the trigger, only when the plan passes R:R ≥ 1 and a 5–40 stop) was positive in three of four periods:

| Period | Net R | Trades |
|---|---|---|
| Development | +0.42 | 24 |
| Validation | −0.14 | 13 |
| Holdout | +0.32 | 46 |
| 2026 | +0.14 | 21 |

  - Every bootstrap interval contains 0 (holdout −0.18 to +0.87).
  - It would need its own registration and a forward test; it is not evidence of an edge.

**Operator cost ($0.26/oz instead of about $0.78).**
- It lifts every cell by about +0.04 R.
- Out of sample, Baseline and the three thresholds stay within a few hundredths of 0 (holdout +0.05 / +0.04 / +0.01 / +0.22). The conclusion is unchanged.

**NOT RUN** (registered as secondary, not implemented in `b30.py`):
- the regime breakdown (trending / ranging / volatile / news);
- the per-timeframe breakdown.

With 5–40 ENG trades per period, cells of a few trades each would say nothing. They can be added on request; they cannot change the primary verdict.

## 5. What this does and does not mean

**Limits of the test.** It does **not** show that confirmation is harmful. The engine's signals are too rare for that:
- 64 development ideas;
- 110 out-of-sample trades without confirmation and 34–48 with it;
- the smallest effect detectable at 80% power is about 0.55 R (registration).

**Data already seen.** The validation and holdout periods had already been read by B19 for $15 / $20 confirmation:
- B19 found a development gain that reversed on validation (−$3.04/oz, 49 trades);
- B30's out-of-sample test there is therefore not a first look. The $10 level and the two-target plan were new.

**Research engine.** It runs without volume, macro or cross-asset inputs (2020-24 has no volume). Its signals are rarer than live.

**Bar data.** 15m bars hide the order inside a bar. Same-bar stop-and-target bars are reported as ambiguous and scored as stops. On the TP1 bar, a touch of the entry level scores the second half at entry. Both choices are conservative.

**Costs.** The model cost (about $0.78/oz here, $0.77–0.97 by session) is **not broker-verified** (audit D1). Neither is the operator's $0.26.

**For the alerts (C1).** The operator may still require a $10 / $15 / $20 confirmation as a risk preference. If so, it must:
1. keep the touch, the confirming close, eligibility and the entry as separate states;
2. recalculate entry, stop, targets and lot from the actual entry (G1);
3. say on the phone that confirmation has **not** been shown to raise the chance of TP before SL (B19, B30).

**NO TRADE** remains the verdict for any signal without a validated edge.

**No stop or target distance was searched or tuned** (registration; operator section 4). The stop / target grids in B19, B27 and B29 found no edge; they were not re-run here.
