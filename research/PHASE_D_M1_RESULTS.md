# Phase D Workstream B: one-minute validation (MT5 M1 and Dukascopy M1)

**Status: INSUFFICIENT DATA — RESEARCH INCOMPLETE** (2026-11-09). No MT5 export or Dukascopy one-minute data has been received, so this document contains **no result**. Every figure will be filled from the committed outputs of the registered run (`registrations/PHASE_D.json`); nothing here is estimated, simulated or assumed. Synthetic data were used only to test the code and are not results.

## What will be here

**1. Importer reports.** `m1_report_*.json` from `tools/mt5_m1_check.py`:
- encoding and parse;
- the conversion from server time to UTC;
- sealed rows dropped (count only);
- duplicates and OHLC consistency;
- Saturday and daily-break bars;
- discontinuities and spikes;
- digit changes;
- coverage by month and year;
- the clock check per week.

**2. B26's AMBIGUOUS trades resolved at one minute.** How many of the 15-minute "both levels in one bar" trades were in fact TP-first, per direction and period.

**3. The benchmark with the real spread.** Expectancy per direction on the one-minute bid / ask (Dukascopy, MT5), compared with B26's modelled spread on the same decisions.

**4. The $3 / $5 / $7 / $10 grid.**
- TP × SL, 16 pairs, symmetric and asymmetric.
- Per direction: the decided TP-first rate (worst case, best-case bound), neither share, AMBIGUOUS share, and expectancy.
- Compared with B29's 15-minute bounds (`results/b29_fix`), which left these brackets INCONCLUSIVE.

**5. Stop-entry sequencing.**
- Stop entries $3 / $5 / $7 / $10 beyond the decision close, within 60 minutes, then ±$15.
- The fill minute is bounded worst / best.

**6. Spread effects.** MT5 spread by session and month against the ENG model, a sensitivity only.

All of these are all-bar measurements (base rates), not selected strategies. A grid cell above its own break-even would be a registration for a later study, not a finding.

## Agreement with B26 (code check, synthetic)

On synthetic paths, the one-minute race reproduces B26's outcome and exit price on every trade whose 15-minute bars are unambiguous, and it resolves every ambiguous one (`test_one_minute_race_agrees_with_b26_wherever_the_15m_bar_is_unambiguous`).
