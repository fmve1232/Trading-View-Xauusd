# Quantitative validation — web.6 record and web.7 evaluation design (2026-11-01)

**Status:** analysis only. No forward-test rule, decision rule, parameter or engine file is changed by this document.
Where it touches a decision, `audit/PREREGISTRATION.md` governs (§4, §7 and Amendments 5, 7, 8, 10, 12).

## 0. Three kinds of evidence, never mixed

| Kind | Source | What it can show | Used here for |
|---|---|---|---|
| **Recorded forward results** | `forward-ledger`: trades written once, under a frozen key, after the key's start | the only out-of-sample performance this system has | §1: web.6 (archived), and web.7 once trades accrue |
| **Historical backtests** | the engine re-run on the stored price history (`market-data`) | in-sample behaviour on data the parameters were chosen on; an upper bound, not a forecast | §2 context, trade rates for §3 |
| **Hypothetical simulations** | changed execution assumptions on the same history (`audit/GAP_SENSITIVITY_2026-11-01.md`) | how sensitive results are to assumptions; never actual fills | referenced only |

## 1. web.6 recorded forward results (2026-10-17 21:26 → 2026-10-31 17:23 UTC, 13.8 days)

**Source:** `forward-ledger` @ `5f72626c`, `holdout/archive/`, trades under key `5e4630924d663fc5:6f3964ad97813cc9`
(798 trades). **Tool:** `python audit/tools/forward_stats.py <checkout> <key> --archive`, bootstrap seed 7.

R is net of the modelled costs. The bootstrap treats trades as independent. Serial dependence (overlapping
positions, clustered regimes) would widen every interval.

| Ledger | n | Win % [Wilson 95%] | Mean R [bootstrap 95%] | t | PF [bootstrap 95%] | Sum R | Max DD (R) |
|---|---|---|---|---|---|---|---|
| 15m_challenger | 1 | 0.0 [0.0, 79.3] | -1.044 | — | 0.00 | -1.04 | 1.04 |
| 15m_h2 | 1 | 0.0 [0.0, 79.3] | -1.028 | — | 0.00 | -1.03 | 1.03 |
| 15m_h3 | 8 | 50.0 [21.5, 78.5] | +0.053 [-0.831, +0.998] | +0.11 | 1.14 [0.10, 7.57] | +0.42 | 3.55 |
| 15m_h4 | 171 | 38.6 [31.6, 46.1] | -0.092 [-0.210, +0.033] | -1.50 | 0.76 [0.50, 1.13] | -15.74 | 19.88 |
| 15m_treatment | 1 | 0.0 [0.0, 79.3] | -1.044 | — | 0.00 | -1.04 | 1.04 |
| 1h_challenger | 2 | 50.0 [9.5, 90.5] | +0.289 | +0.22 | 2.68 | +0.58 | 1.05 |
| 1h_h3 | 3 | 33.3 [6.1, 79.2] | -0.164 | -0.18 | 1.38 | -0.49 | 2.20 |
| 1h_h4 | 49 | 32.7 [21.2, 46.6] | -0.187 [-0.360, -0.004] | -2.06 | 0.55 [0.20, 1.15] | -9.15 | 11.05 |
| 1h_treatment | 3 | 33.3 [6.1, 79.2] | -0.163 | -0.18 | 1.47 | -0.49 | 2.12 |
| 4h_h4 | 12 | 25.0 [8.9, 53.2] | -0.107 [-0.557, +0.392] | -0.42 | 0.71 [0.00, 2.33] | -1.28 | 4.39 |
| 5m_challenger | 8 | 50.0 [21.5, 78.5] | +0.904 [-0.599, +2.558] | +1.04 | 3.29 [0.34, 20.48] | +7.23 | 2.20 |
| 5m_control | 1 | 100.0 [20.7, 100.0] | +1.965 | — | — | +1.97 | 0.00 |
| 5m_h2 | 3 | 33.3 [6.1, 79.2] | -0.313 | -0.43 | 0.19 | -0.94 | 2.08 |
| 5m_h3 | 14 | 64.3 [38.8, 83.7] | +0.553 [-0.330, +1.520] | +1.11 | 3.69 [1.10, 16.24] | +7.75 | 4.16 |
| 5m_h4 | 511 | 33.5 [29.5, 37.7] | -0.179 [-0.251, -0.104] | -4.75 | 0.58 [0.46, 0.74] | -91.39 | 99.23 |
| 5m_h5 | 2 | 50.0 [9.5, 90.5] | +0.452 | +0.30 | 1.59 | +0.90 | 1.06 |
| 5m_treatment | 8 | 50.0 [21.5, 78.5] | +0.938 [-0.551, +2.676] | +1.05 | 3.17 [0.38, 21.34] | +7.50 | 2.20 |

**By regime** (ledgers with n ≥ 30; groups with n < 10 shown for completeness only)

| Ledger | regime | n | Win % | Mean R [bootstrap 95%] | Sum R |
|---|---|---|---|---|---|
| 15m_h4 | RANGE | 81 | 36 | -0.104 [-0.28, +0.08] | -8.44 |
| 15m_h4 | EXPANSION | 33 | 48 | +0.104 [-0.14, +0.36] | +3.43 |
| 15m_h4 | STRONG TR | 23 | 35 | -0.122 [-0.42, +0.24] | -2.80 |
| 15m_h4 | COMPRESS | 17 | 41 | -0.174 [-0.53, +0.21] | -2.96 |
| 15m_h4 | WEAK TR | 12 | 42 | -0.223 [-0.60, +0.17] | -2.67 |
| 15m_h4 | ABNORMAL | 5 | 20 | -0.459 | -2.30 |
| 1h_h4 | RANGE | 13 | 31 | -0.288 [-0.65, +0.11] | -3.74 |
| 1h_h4 | EXPANSION | 12 | 25 | -0.063 [-0.30, +0.29] | -0.76 |
| 1h_h4 | COMPRESS | 11 | 45 | -0.055 [-0.40, +0.31] | -0.60 |
| 1h_h4 | STRONG TR | 7 | 14 | -0.452 | -3.16 |
| 1h_h4 | WEAK TR | 3 | 67 | -0.195 | -0.58 |
| 1h_h4 | ABNORMAL | 3 | 33 | -0.100 | -0.30 |
| 5m_h4 | RANGE | 234 | 32 | -0.205 [-0.31, -0.09] | -48.00 |
| 5m_h4 | COMPRESS | 79 | 42 | -0.079 [-0.30, +0.15] | -6.23 |
| 5m_h4 | STRONG TR | 77 | 29 | -0.179 [-0.35, +0.01] | -13.75 |
| 5m_h4 | EXPANSION | 68 | 25 | -0.282 [-0.44, -0.12] | -19.21 |
| 5m_h4 | WEAK TR | 28 | 43 | +0.085 [-0.25, +0.44] | +2.37 |
| 5m_h4 | ABNORMAL | 25 | 44 | -0.262 [-0.50, -0.02] | -6.56 |

**By session** (ledgers with n ≥ 30; groups with n < 10 shown for completeness only)

| Ledger | session | n | Win % | Mean R [bootstrap 95%] | Sum R |
|---|---|---|---|---|---|
| 15m_h4 | ASIAN | 61 | 30 | -0.225 [-0.41, -0.02] | -13.73 |
| 15m_h4 | LONDON | 32 | 47 | +0.003 [-0.32, +0.35] | +0.11 |
| 15m_h4 | OFF | 24 | 33 | -0.117 [-0.39, +0.18] | -2.80 |
| 15m_h4 | NY | 18 | 50 | +0.127 [-0.24, +0.54] | +2.29 |
| 15m_h4 | NY-KZ | 13 | 54 | +0.079 [-0.25, +0.39] | +1.02 |
| 15m_h4 | LON-KZ | 12 | 42 | -0.130 [-0.40, +0.14] | -1.56 |
| 15m_h4 | LON-FIX | 6 | 67 | +0.212 | +1.27 |
| 15m_h4 | LON-CL | 5 | 0 | -0.469 | -2.34 |
| 1h_h4 | ASIAN | 17 | 18 | -0.315 [-0.46, -0.17] | -5.36 |
| 1h_h4 | LONDON | 12 | 33 | -0.217 [-0.64, +0.24] | -2.60 |
| 1h_h4 | NY-KZ | 5 | 40 | -0.246 | -1.23 |
| 1h_h4 | OFF | 4 | 50 | +0.236 | +0.94 |
| 1h_h4 | NY | 4 | 50 | -0.355 | -1.42 |
| 1h_h4 | LON-FIX | 3 | 33 | +0.244 | +0.73 |
| 1h_h4 | LON-KZ | 3 | 33 | -0.144 | -0.43 |
| 1h_h4 | LON-CL | 1 | 100 | +0.219 | +0.22 |
| 5m_h4 | ASIAN | 162 | 30 | -0.211 [-0.34, -0.07] | -34.20 |
| 5m_h4 | LONDON | 93 | 41 | -0.017 [-0.18, +0.15] | -1.62 |
| 5m_h4 | NY | 59 | 41 | -0.182 [-0.40, +0.04] | -10.74 |
| 5m_h4 | LON-KZ | 56 | 29 | -0.272 [-0.44, -0.09] | -15.23 |
| 5m_h4 | OFF | 48 | 35 | -0.194 [-0.46, +0.09] | -9.30 |
| 5m_h4 | NY-KZ | 45 | 22 | -0.294 [-0.49, -0.07] | -13.24 |
| 5m_h4 | LON-FIX | 28 | 39 | -0.164 [-0.51, +0.19] | -4.60 |
| 5m_h4 | LON-CL | 20 | 35 | -0.123 [-0.41, +0.20] | -2.46 |

**Calibration of the recorded P (TP1 reached), ledgers with ≥ 10 trades carrying P**

- No ledger has 10 or more trades with a recorded P: **calibration NOT ASSESSABLE** on this record.


### 1.1 What the web.6 record does and does not show

1. **H4 Playbook lost money in its forward record.**
   - **5m:** n 511, mean −0.179 R. The bootstrap interval [−0.251, −0.104] lies entirely below zero; t −4.75. PF 0.58 [0.46, 0.74].
   - **1h:** n 49, interval [−0.360, −0.004]; t −2.06. This meets the site's "Verdict: losing" rule (N ≥ 50 and
     t ≤ −2) only in spirit, because it is one trade short of N 50.
   - **15m (H4's pre-registered deciding timeframe):** n 171, mean −0.092 R [−0.210, +0.033]. It **does not**
     reach the pre-registered EDGE SHOWN standard (mean above zero), and its interval includes zero. Under
     Amendment 8 the 15m verdict is therefore "not shown", not "proven losing". The 5m and 1h results are reported,
     and decide nothing.
2. **Every other ledger has n ≤ 14.**
   - Intervals are very wide. For example, the 5m treatment's mean R interval is [−0.55, +2.68] with PF [0.38, 21.3].
   - **No conclusion is possible**, positive or negative. The +0.94 R on the 5m treatment is 8 trades, and its
     interval includes zero.
3. **No arm reached the pre-registered decision size (N ≥ 50) on its deciding timeframe** before web.6 ended:
   - 1H for treatment, control, challenger, H2, H3, H5 and H6;
   - 15m for H4.

   **No pre-registered verdict was reached under web.6.**
4. **Regime and session splits** (H4 only; the other ledgers are too small) are **exploratory**:
   - There are 18 regime groups and 24 session groups from three ledgers. At least one 95% interval excluding zero
     is expected by chance alone.
   - The Asian-session results (5m −0.21 R [−0.34, −0.07]; 15m −0.23 [−0.41, −0.02]) are the strongest pattern.
     They are a **question for a future registered hypothesis, not a filter to add**. Adding it now would tune on
     the evaluation data (CLAUDE.md, "Do not tune").
5. **Calibration is NOT ASSESSABLE on the forward record.** No ledger has 10 or more trades carrying a recorded P
   (H4 records none). The in-sample calibration (audit §7) found negative Brier skill on 5m, 15m and 1h. That is a
   historical backtest result, not forward evidence.
6. **Drawdown.**
   - H4 5m reached a 99 R peak-to-trough in 14 days. At 1% risk per trade that is about a 63% equity drawdown
     (compounded).
   - This is the practical meaning of a −0.18 R expectancy at high frequency.

## 2. Historical backtest context (in-sample; not evidence of edge)

The stored-history backtests (audit §6.2; `audit/GAP_SENSITIVITY_2026-11-01.md` §2) have:

- t below 1.3 for every arm except H4;
- H4 negative on every timeframe.

These windows overlap the data the frozen parameters were chosen on (`audit/AUDIT_PROMPT.md` §9). An in-sample
result is an optimistic upper bound. It is cited only for trade frequency and cost sensitivity.

## 3. web.7 evaluation design (written 2026-11-01, before any web.7 trade exists)

### 3.1 What decides (unchanged; restated from the pre-registration)

| Arm | Deciding timeframe | Decision rule | Deadline |
|---|---|---|---|
| Treatment | 1H | EDGE SHOWN: N ≥ 50, the 95% t-interval of mean R above 0, PF ≥ 1.2 | 2027-03-31 (otherwise "insufficient data") |
| Challenger (H1) | 1H | ADOPT H1 only if EDGE SHOWN and its mean R > the treatment's over the same window | 2027-03-31 |
| Control | 1H | reported; decides nothing | — |
| H2 | 1H | as for the treatment | 2027-03-31, otherwise NOT SHOWN |
| H3 | 1H | as for the treatment (Amendment 7) | 2027-03-31 |
| H4 | **15m** | as for the treatment (Amendment 8) | 2027-03-31 |
| H5 | 1H | **N ≥ 30**, t-interval above 0, PF ≥ 1.2; the win rate is reported, never decides | 2027-03-31 |
| H6 | 1H | N ≥ 50, as for the treatment | 2027-03-31 |

- The web.7 clock starts at **2026-10-31 17:23:01 UTC**.
- web.6 and earlier trades are never pooled with web.7.
- **One evaluation per arm, at its decision point.** Interim looks are reported descriptively and decide nothing.
  That avoids optional stopping on repeated looks.

### 3.2 What is reported alongside (descriptive; never decides)

Computed by `audit/tools/forward_stats.py` on the web.7 key, for every ledger with n ≥ 5:

| Quantity | How |
|---|---|
| Net expectancy | mean R, with the t-interval (the decision statistic) and a bootstrap 95% interval |
| Profit factor | with a bootstrap 95% interval |
| Win rate | with its Wilson 95% interval |
| Drawdown | max drawdown in R, and in % at 1% fixed-fractional risk |
| Regime and session | splits once an arm has n ≥ 30, labelled exploratory, with the number of groups stated |
| Calibration | Brier score and skill, and a reliability table, once n ≥ 30 trades carry a recorded P; otherwise "not assessable" |
| Execution | the share of `SL_GAP` / `BE_GAP` exits; their mean R against ordinary stops |
| Data source | the trade's recorded `price_source`. Trades on a fallback source are reported separately and never counted (§7) |

### 3.3 How much evidence is realistically obtainable (planning, not a rule)

Trades per month are taken from the stored-history backtest (1h: 2026-03-02 → 10-30; 15m: 08-05 → 10-30); the
projection is the expected N by 2027-03-31.

| Arm, deciding TF | Backtest trades per month | Expected N by 2027-03-31 | Reaches its N? |
|---|---|---|---|
| Treatment 1H | 3.8 | ≈ 19 | **no** |
| Challenger 1H | 4.0 | ≈ 20 | **no** |
| Control 1H | 0.3 | ≈ 1 | no (decides nothing) |
| H2 1H | 1.0 | ≈ 5 | **no** |
| H3 1H | 3.0 | ≈ 15 | **no** |
| H4 15m | 353 | ≈ 1,766 | yes (in about 5 days) |
| H5 1H (N 30) | 0.4 | ≈ 2 | **no** |
| H6 1H | 4.5 | ≈ 23 | **no** |

**Power.** Spread of R on the web.6 record:

| Record | SD of R |
|---|---|
| H4 | 0.63–0.89 |
| 5m treatment / challenger (n 8) | ≈ 2.5 |
| Pooled | 0.94 |

To detect a true mean of +0.2 R with 80% power at the two-sided 5% level:

| SD of R | Trades needed |
|---|---|
| 1.0 | ≈ 197 |
| 1.3 | ≈ 332 |

At +0.1 R it needs 785 trades (SD 1.0).

**What follows, stated now so that nobody reads it after the fact:**

- **Under the existing rules, only H4 will reach a verdict by 2027-03-31.**
- Every 1H arm is expected to end "insufficient data" / NOT SHOWN, **whatever its true edge**.
- Even an arm that does reach N 50 has low power to show a modest edge.
- A positive interim result on a handful of trades must not be read as evidence.

Changing the deciding timeframe, N or deadline would be a change to the forward-test rules. That needs a written
amendment and the operator's approval **before** any web.7 result is seen, and it must not be chosen by looking at
which timeframe "is doing well".

### 3.4 What must not happen during web.7

- **No re-optimisation** of thresholds, gates or weights against web.7 data, or against any data already used.
- **No subgroup filter** added because a subgroup looks good or bad (§1.1 item 4).
- **No pooling** of web.6 and web.7, and no cherry-picked windows.
- **No 5m / 15m / 4h result cited as an arm's verdict**, except H4's 15m.
- **Research on the Amendment 13 data** (development 2020-01-24 → 2023-01-24) is the only place where a new
  hypothesis may be developed. It then follows Amendment 11/13's protocol, with a new arm and its own pre-registration.

## 4. Limitations

1. 13.8 days of web.6 forward data, in one market regime (gold falling from about 4,170 to about 3,890).
2. The bootstrap ignores serial dependence.
3. The trade-rate projections come from in-sample backtests and are approximate.
4. Costs are the frozen engine model; broker costs are unverified (`audit/COST_PROFILES.md`).
5. Gap fills at the open are a lower bound on gap damage (Amendment 14 §4).
