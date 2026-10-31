# Forward test, engine web.6 — final record before the Amendment 14 restart

Written 2026-11-01, before the engine change (`audit/PREREGISTRATION.md` Amendment 14, §10).

- **Source:** `forward-ledger` @ `a9bc97a1a8821c8ff95a15d7b23dec47f816ad68` (2026-10-31 17:15 UTC).
- **Trades counted:** closed trades only, under the web.6 main key.
- **web.6 engine code:** merge commit `cc2ecd9d351d88ce4ae23de4f65497ae2e4bd698`.

**These results are stated separately and are never pooled with web.7.** Scheduled runs between this snapshot and
the web.7 deploy may still append web.6 trades. The complete web.6 record is whatever the first web.7 run moves to
`holdout/archive/` on `forward-ledger`, plus that branch's git history. Nothing is deleted.

Main key 5e4630924d663fc5:6f3964ad97813cc9, engine Q7.2-web.6, started 2026-10-17T21:26:18.328813+00:00.

| Ledger | Arm key suffix | N closed | Win % [Wilson 95%] | Mean R | t | PF | Sum R | First → last entry |
|---|---|---|---|---|---|---|---|---|
| 15m_challenger | (engine) | 1 | 0.0 [0.0, 79.3] | -1.044 | — | 0.00 | -1.04 | 2026-10-26T13:45 → 2026-10-26T13:45 |
| 15m_control | — | 0 | — | — | — | — | — | — |
| 15m_h2 | adeaccb163806651 | 1 | 0.0 [0.0, 79.3] | -1.028 | — | 0.00 | -1.03 | 2026-10-21T19:30 → 2026-10-21T19:30 |
| 15m_h3 | 0eb650f81d99803e | 8 | 50.0 [21.5, 78.5] | +0.053 | 0.11 | 1.14 | +0.42 | 2026-10-21T09:30 → 2026-10-27T22:45 |
| 15m_h4 | 090418672c210848 | 171 | 38.6 [31.6, 46.1] | -0.092 | -1.50 | 0.76 | -15.74 | 2026-10-18T22:00 → 2026-10-30T17:00 |
| 15m_h5 | — | 0 | — | — | — | — | — | — |
| 15m_h6 | — | 0 | — | — | — | — | — | — |
| 15m_treatment | (engine) | 1 | 0.0 [0.0, 79.3] | -1.044 | — | 0.00 | -1.04 | 2026-10-26T13:45 → 2026-10-26T13:45 |
| 1h_challenger | (engine) | 2 | 50.0 [9.5, 90.5] | +0.289 | 0.22 | 2.68 | +0.58 | 2026-10-19T14:00 → 2026-10-27T07:00 |
| 1h_control | — | 0 | — | — | — | — | — | — |
| 1h_h2 | — | 0 | — | — | — | — | — | — |
| 1h_h3 | 0eb650f81d99803e | 3 | 33.3 [6.1, 79.2] | -0.164 | -0.18 | 1.38 | -0.49 | 2026-10-20T14:00 → 2026-10-28T00:00 |
| 1h_h4 | 090418672c210848 | 49 | 32.7 [21.2, 46.6] | -0.187 | -2.06 | 0.55 | -9.15 | 2026-10-18T23:00 → 2026-10-30T11:00 |
| 1h_h5 | — | 0 | — | — | — | — | — | — |
| 1h_h6 | — | 0 | — | — | — | — | — | — |
| 1h_treatment | (engine) | 3 | 33.3 [6.1, 79.2] | -0.163 | -0.18 | 1.47 | -0.49 | 2026-10-19T14:00 → 2026-10-27T07:00 |
| 4h_challenger | — | 0 | — | — | — | — | — | — |
| 4h_control | — | 0 | — | — | — | — | — | — |
| 4h_h2 | — | 0 | — | — | — | — | — | — |
| 4h_h3 | — | 0 | — | — | — | — | — | — |
| 4h_h4 | 090418672c210848 | 12 | 25.0 [8.9, 53.2] | -0.107 | -0.42 | 0.71 | -1.28 | 2026-10-20T01:00 → 2026-10-29T05:00 |
| 4h_h5 | — | 0 | — | — | — | — | — | — |
| 4h_h6 | — | 0 | — | — | — | — | — | — |
| 4h_treatment | — | 0 | — | — | — | — | — | — |
| 5m_challenger | (engine) | 8 | 50.0 [21.5, 78.5] | +0.904 | 1.04 | 3.29 | +7.23 | 2026-10-19T12:00 → 2026-10-30T13:10 |
| 5m_control | (engine) | 1 | 100.0 [20.7, 100.0] | +1.965 | — | — | +1.97 | 2026-10-23T14:05 → 2026-10-23T14:05 |
| 5m_h2 | adeaccb163806651 | 3 | 33.3 [6.1, 79.2] | -0.313 | -0.43 | 0.19 | -0.94 | 2026-10-20T12:35 → 2026-10-29T14:45 |
| 5m_h3 | 0eb650f81d99803e | 14 | 64.3 [38.8, 83.7] | +0.553 | 1.11 | 3.69 | +7.75 | 2026-10-19T04:35 → 2026-10-29T14:45 |
| 5m_h4 | 090418672c210848 | 511 | 33.5 [29.5, 37.7] | -0.179 | -4.75 | 0.58 | -91.39 | 2026-10-18T22:00 → 2026-10-30T20:25 |
| 5m_h5 | 40d438ea0c144199 | 2 | 50.0 [9.5, 90.5] | +0.452 | 0.30 | 1.59 | +0.90 | 2026-10-23T14:05 → 2026-10-23T14:20 |
| 5m_h6 | — | 0 | — | — | — | — | — | — |
| 5m_treatment | (engine) | 8 | 50.0 [21.5, 78.5] | +0.938 | 1.05 | 3.17 | +7.50 | 2026-10-19T12:00 → 2026-10-30T13:10 |

**Reading this table:**

- **"(engine)"** = the treatment / control / challenger arms, which use the engine key itself. Arm suffixes are each
  arm file's hash.
- **H4 Playbook** is the only ledger with enough trades to judge, and it **lost**: 5m t −4.75 (n 511); 1h t −2.06
  (n 49), which meets the site's "Verdict: losing" rule.
- **Every other ledger has n ≤ 14.** Win rates there carry Wilson intervals 40–80 points wide; they show nothing yet.
- **No arm met a pre-registered success criterion under web.6.**
