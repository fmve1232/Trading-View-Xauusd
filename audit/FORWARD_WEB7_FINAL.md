# Forward test, engine web.7 — final record before the Amendment 15 restart

Written 2026-11-03, before the engine change (`audit/PREREGISTRATION.md` Amendment 15, procedure step 2).

- **Source:** `forward-ledger` @ `52243c305f3ddd791ec49c971d213eeaa660f895` (2026-11-03 23:06 UTC).
- **Trades counted:** closed trades under the web.7 main key, from `audit/tools/forward_stats.py` (read-only).
- **web.7 engine:** main key `5e4630924d663fc5:60bb01794d03c9ac`, `Q7.2-web.7`, started 2026-10-31 17:23:01 UTC
  (Amendment 14 start record).

**These results are stated separately and are never pooled with web.8.**

- Scheduled runs between this snapshot and the web.8 deploy may still append web.7 trades.
- The complete web.7 record is what the first web.8 run moves to `holdout/archive/` on `forward-ledger`, plus that
  branch's git history. Nothing is deleted.

The snapshot holds 106 web.7 records, all closed. Ledgers with no web.7 trade are not listed.

| Ledger | n | Win % [Wilson 95%] | Mean R [bootstrap 95%] | t | PF [bootstrap 95%] | Sum R | Max DD (R) |
|---|---|---|---|---|---|---|---|
| 15m_challenger | 1 | 0.0 [0.0, 79.3] | -1.057 | — | 0.00 | -1.06 | 1.06 |
| 15m_h4 | 22 | 36.4 [19.7, 57.0] | +0.022 [-0.390, +0.525] | +0.09 | 1.07 [0.30, 2.93] | +0.48 | 3.02 |
| 15m_h5 | 1 | 100.0 [20.7, 100.0] | +0.649 | — | — | +0.65 | 0.00 |
| 15m_h6 | 1 | 0.0 [0.0, 79.3] | -1.057 | — | 0.00 | -1.06 | 1.06 |
| 15m_treatment | 1 | 0.0 [0.0, 79.3] | -1.057 | — | 0.00 | -1.06 | 1.06 |
| 1h_h4 | 6 | 50.0 [18.8, 81.2] | +0.034 [-0.466, +0.552] | +0.12 | 0.95 [0.09, 13.23] | +0.20 | 1.40 |
| 4h_h4 | 2 | 0.0 [0.0, 65.8] | -0.463 | -3.09 | 0.00 | -0.93 | 0.93 |
| 5m_challenger | 1 | 100.0 [20.7, 100.0] | +0.545 | — | — | +0.54 | 0.00 |
| 5m_control | 1 | 100.0 [20.7, 100.0] | +0.545 | — | — | +0.54 | 0.00 |
| 5m_h2 | 2 | 50.0 [9.5, 90.5] | +0.167 | +0.13 | 3.70 | +0.33 | 1.12 |
| 5m_h3 | 3 | 66.7 [20.8, 93.9] | +0.081 | +0.10 | 1.30 | +0.24 | 1.40 |
| 5m_h4 | 62 | 33.9 [23.3, 46.3] | -0.149 [-0.379, +0.116] | -1.16 | 0.80 [0.35, 1.54] | -9.26 | 14.09 |
| 5m_h5 | 1 | 100.0 [20.7, 100.0] | +0.545 | — | — | +0.54 | 0.00 |
| 5m_h6 | 1 | 100.0 [20.7, 100.0] | +0.545 | — | — | +0.54 | 0.00 |
| 5m_treatment | 1 | 100.0 [20.7, 100.0] | +0.545 | — | — | +0.54 | 0.00 |

**What the restart costs on the deciding timeframe (1H).**

- The §7 arms (treatment, control, challenger) had **no** closed 1H trade under web.7.
- H2, H3, H5 and H6 had none on 1H either.
- H4 had 6, at 50.0% wins and +0.034 R per trade (95% interval −0.466 to +0.552). That is far too few to read.

So the restart discards no evidence that could have decided anything.

The other timeframes are descriptive only, as before. 5m H4 (62 trades, −0.149 R per trade, interval −0.379 to +0.116)
is the largest; it decides nothing.

**Complete record (added 2026-11-03 after the restart; facts only).** The first web.8 run moved 107 web.7 trades to
`holdout/archive/` (`forward-ledger` @ `4bb6ca8777040444f7d06ef3da20d80e7f4e2f0f`). These are the 106 above, plus one
that closed after the snapshot: 15m H4, short at 2026-11-03 19:00 UTC, stopped at 23:00, −1.105 R. It changes no 1H
figure.
