# Phase D risk report

**Status: INSUFFICIENT DATA — RESEARCH INCOMPLETE** (2026-11-09). No Dukascopy data or broker specification has been received, so this document contains **no result**. Every figure will be filled from the committed outputs of the registered run (`registrations/PHASE_D.json`); nothing here is estimated, simulated or assumed. Synthetic data were used only to test the code and are not results.

## What will be here, per strategy that reaches the frozen set

**1. Theoretical price movement**, always:
- net $ / oz and R (1R = the stop distance, $15 in 4000-equivalent development units);
- drawdown in R;
- block bootstrap (blocks of 10 trades, 2,000 paths of 250 trades): P(drawdown ≥ 15R), the 95th percentile drawdown, the longest losing run;
- sequence and regime sensitivity (by year, volatility tercile, trend);
- cost stress (ADV − ENG).

**2. Executable account P&L**, only from a **validated** broker specification (`d_broker.validate`):
- contract size, tick value, commission, typical spread, slippage, margin;
- P&L and drawdown in the account currency at the lot you name.

Development figures are 4000-equivalent, so they are illustrative; 2026 figures are literal.

**3. Exposure:** one position per direction, time in market, maximum concurrent (2: one BUY and one SELL).

## What is not done

- No account figure is computed from assumed broker values. Phase C's ASSUMED 100 oz / $100,000 figures remain Phase C's, labelled as such.
- The account balance is an input of this report only; it never selects or tunes anything.
