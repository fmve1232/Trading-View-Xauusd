# Forward test status (2026-11-26)

**Status: INSUFFICIENT EVIDENCE.**
- **No registered forward test has reached its first registered look.**
- **Nothing was changed.** The frozen engine, its arms and every registered rule are unchanged since the freeze of 2026-11-15 11:46:48 UTC. The freeze key `1f88aad357497da4:4440d52587f5cc6b` was recomputed today and is unchanged.
- **No test was stopped early** and none was restarted.

**Sources:**
- `forward-ledger` `c8a99d64e` (2026-11-26 11:04 UTC): `research_forward/*.json` and `holdout/*.json`.
- Detailed statistics: `STRATEGY_PERFORMANCE_REPORT.md`.

## 1. Registered forward tests

| Test | Registration | Since (UTC) | Record now | Registered looks / decision rule | Status |
|---|---|---|---|---|---|
| B15b-ENGINE-FWD (+$13 before −$13 from each engine signal's close) | `research/registrations/B15b-ENGINE-FWD.json` | 2026-11-15 11:48 | 12 TP, 8 SL of 20 decided | first look at 30 | INSUFFICIENT EVIDENCE |
| B15-ENGINE-FWD | `B15-ENGINE-FWD.json` | 2026-11-06 → ended 2026-11-15 (Amendment F) | 5 TP, 8 SL of 13 | ended before its first look; record kept read only | ENDED, no verdict |
| B9-GRAB-FWD | `B9-GRAB-FWD.json` | 2026-11-04 23:47 | 12 TP, 11 SL of 23 | looks at 30, 40 … 100 decided; "proven" needs the Wilson lower bound above 51% (21 of 30, 27 of 40, …) | INSUFFICIENT EVIDENCE |
| B31b-SHADOW-FWD (B31's five modules, records only) | `B31b-SHADOW-FWD.json` | 2026-11-15 13:23 | 84 setups | as registered | INSUFFICIENT EVIDENCE |
| B24-CONFIRM-FWD | `B24-CONFIRM-FWD*.json` | — | OFF (`FWD_B24` never set); the voided start is kept | — | OFF (by the operator's rule) |
| C1 CONFIRM-LIVE (descriptive) | operator directive 2026-11-15 | 2026-11-10 21:35 | 347 rows: 94 CONFIRMED, 217 INVALIDATED, 36 EXPIRED | descriptive only | DESCRIPTIVE |
| SETUP-LIVE (descriptive) | B16–B18 rules | 2026-11-06 | 275 setups | descriptive only | DESCRIPTIVE |
| Sweep monitor record (W7 A3) | `B31b-W7.json` | 2026-11-23 07:24 | 21 sweeps, all decided; +$10 first 5 (23.8%) | descriptive until 100 decided per level timeframe; Wilson from 30 | INSUFFICIENT EVIDENCE (and not durable in production: GA-03) |
| Breakout monitor record (W7) | `B31b-W7.json` | 2026-11-19 12:22 | 93 events (M15 49, M30 24, H1 12, H4 8) | descriptive until 100 decided shadow trades per variant | INSUFFICIENT EVIDENCE (GA-03) |

## 2. Engine arms under the frozen key

| Arm | Basis | Live trades (closed) | Status |
|---|---|---|---|
| Treatment / Control / Challenger | PREREGISTRATION §7, Amendment 3 | 1–17 per timeframe | INSUFFICIENT EVIDENCE |
| H2, H3, H5 | Amendments 5, 7, 10 | 1–8 per timeframe | INSUFFICIENT EVIDENCE |
| H4 Playbook | Amendment 8 | 410 (5m), 148 (15m), 70 (30m), 37 (1h), 8 (4h) | 5m and 1h negative with 95% intervals below zero; no registered stop rule applies before the registered decision point (PREREGISTRATION §4 / §5); continues unchanged |
| H6 | Amendments 12 and F | closed; final record of 13 trades kept read only | CLOSED |

## 3. Separation of records

| Kind | Where | Changed retrospectively? |
|---|---|---|
| Original registered strategies | `forward-ledger/holdout/` and `research_forward/` | no: append-only commits; `ledger_check.py` finds 0 problems |
| Experimental strategies (shadow) | `research_forward/B31b-SHADOW-FWD.json`, breakout shadow entries in the outcome records | no |
| New candidate strategies | none: no candidate passed any registered check (W8, W12, W13: NO CANDIDATE / NO SUPPORTED MECHANISM) | — |

Each ledger trade keeps its original decision, key, levels and recorded time, its path (`bars`, `tp1_hit`) and its
exit and reason. `ledger_check.py` checks that no trade was recorded before its exit and that every trade sits inside
its key's window.
