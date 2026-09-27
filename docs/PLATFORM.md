# XAUUSD Quantum — web platform

The Pine Master (build v21), ported to Python and run on free market data by GitHub Actions,
published to GitHub Pages. No server, no paid feed, no TradingView limits (no compiled-token
ceiling, no per-bar loop budget, no chunked scans, full-history backtests).

```
GitHub Actions (every 15 min, Sun 22:00 – Fri 21:00 UTC)
  ├─ download   Yahoo · FRED · CFTC (+ Twelve Data if keyed)   → market-data branch (monthly CSVs)
  ├─ engine     quantum/  (treatment arm + control arm, 5m · 15m · 1h · 4h)
  ├─ backtest   A/B, walk-forward, Monte Carlo, calibration, frozen forward holdout
  ├─ alerts     ntfy / Telegram / Discord (optional, confirmed bars only, never repeated)
  └─ publish    site/ + site/data/*.json  → GitHub Pages
```

## Setup (one time, about five minutes)

1. **Merge this branch into the repository's default branch.** GitHub only runs scheduled
   workflows from the default branch (currently `claude/audit-prompt-real-artefacts-nekqv6`).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write.**
4. **Actions → quantum-site → Run workflow** once. The site appears at
   `https://fmve1232.github.io/Trading-View-Xauusd/` a few minutes later.

Optional, in **Settings → Secrets and variables → Actions**:

| Name | Kind | Effect |
|---|---|---|
| `TWELVEDATA_API_KEY` | secret | Spot XAU/USD from Twelve Data (free key, 800 calls/day; the pipeline uses ~400). Without it: Yahoo spot, else COMEX futures. |
| `NTFY_TOPIC` | secret | Push alerts to the free ntfy app. Pick an unguessable topic name. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | secret | Telegram alerts. |
| `DISCORD_WEBHOOK_URL` | secret | Discord alerts. |
| `MT5_PRICE_OFFSET` | variable | Broker minus feed, in points, applied to alert prices (display only). |
| `ALERT_TFS` | variable | Timeframes that alert. Default `15m,1h`. |

## Local use

```sh
pip install -r requirements.txt
python -m pytest -q tests                                        # 49 tests, ~15 s
python -m quantum.pipeline --synthetic --out site/data           # offline, labelled SYNTHETIC
python -m quantum.pipeline --store store --out site/data         # live free data
cd site && python -m http.server 8000                            # http://localhost:8000
```

## Parity with the Pine Master

The engine follows the Master in its own order; each block names the Pine section it ports.
The deliberate differences, all removals of TradingView limits and none chosen by results:

| ID | Pine | Here | Why |
|---|---|---|---|
| D-01 | `request.security(close[1], lookahead_off)` is one HTF bar later on historical bars than live | live semantics on every bar | backtest computed the way the signal is |
| D-02 | hand-rolled DST; EU summer time can start up to 4 days early | IANA zoneinfo | sessions gate entries |
| D-03 | analog buffer scanned in chunks over several bars | whole buffer, every confirmed bar | no stale statistics |
| D-04 | calibration / regime counts kept across cycles with 0.7 / 0.5 decay: each analog counted ~3.3× | distinct analogs only | `N ≥ 30` means 30 observations |
| D-05 | COT keyed on its Tuesday as-of date; percentile over chart bars | keyed on Friday release; percentile over weeks | no look-ahead |
| D-06 | volume profile on the last bar only (F-A07) | every bar | historical plans can use VAL/VAH/POC; the `°` markers go |
| D-07 | OANDA tick volume | COMEX GC futures volume, bar for bar; missing = 0 (counted). While an anchor period has no volume yet, VWAP is the equal-weighted mean price rather than na | real traded volume; a na VWAP would disable the analog scan for 100 bars after every COMEX daily break |
| D-08 | Cornish-Fisher inverse by 6 Newton steps, accepted whatever they return | accepted only where it solves q(w) = z, else the raw z | the cubic has no inverse for thin tails or strong skew; Newton ran to 1e213 on live data and pinned mrComposite at ±100 — **fixed in Pine v32 too (F-A38)**, so this is parity now, not a difference |
| — | daily open interest | weekly CFTC open interest | no free daily OI; labelled |
| — | `pivothigh` tie-break unknown | strict pivot (a plateau is not a pivot) | unverified on exact ties |

Kept exactly as in Pine, even where the audit questions them, because changing them would be tuning or would
break the A/B: every threshold and weight, the rolling IS/ROLL split (labelled ROLL, not a holdout), the
feature-accuracy denominator that includes timeouts, the SMT pair condition (it needs pivots on consecutive
bars, which 2/2 pivots cannot produce, so SMT is dormant here as it is in Pine), and the `recentBars` gate
(the strategy arms' *Backtest all bars* default is used, F-A29).

## What is new beyond the Pine version

- **Frozen forward holdout.** The configuration is hashed; trades entered after the freeze are appended
  once to a ledger on the `market-data` branch and never rewritten. Changing a parameter restarts the
  holdout and keeps the old one in the manifest's history. It is the only out-of-sample evidence.
- **History that accumulates.** Each run merges into the store, so 5m/15m history grows past Yahoo's
  60-day window.
- **No-look-ahead is tested.** `tests/test_engine.py::test_no_lookahead` truncates the data at bar k and
  checks that no earlier decision changes.
- **Backtest reporting:** both A/B arms, walk-forward folds (no refitting), bootstrap Monte Carlo,
  per-session / regime / direction breakdowns, and the F-A12 calibration test of P at entry.
- **Alerts** on confirmed bars only, deduplicated across runs.

## Limits

Free data is delayed and occasionally wrong; GitHub's scheduler can run late or skip a run; parity
with a TradingView chart has not been demonstrated (no chart was available to compare against); fills
are modelled (entry at signal close, stop first on same-bar ties). The Method tab on the site states
these to every visitor.

## Keeping Pine and Python in step

A change to the engine in the Pine artefacts must be ported to `quantum/` in the same build (and the
reverse), and `python -m pytest -q tests` must pass. Any change to `quantum/config.py` changes the
configuration hash and therefore restarts the holdout — that is intended.

## Data handling

- **Market-closed bars are dropped** (Friday 17:00 → Sunday 17:00 New York; daily bars dated Saturday
  or Sunday). Twelve Data's free XAU/USD feed prints flat quotes 24/7; on the first live week those were
  ~30% of the 15-minute chart and corrupted ATR, PDH/PDL (fake weekend "days"), VWAP and the return
  volatility. The data-status panel reports how many were dropped per series. The raw store keeps them.
- **4-hour bars sit on the 17:00 New York grid through DST** (bucketed on New York wall-clock time).
- **Daily bars:** Yahoo futures dailies are re-indexed to their 17:00 New York session open; Twelve Data
  dailies are UTC calendar days and keep their 00:00 UTC open. Either way the alignment rule reads only
  the previous completed day.
- The COMEX daily break (17:00–18:00 New York) has no futures volume while spot keeps printing; those bars
  get volume 0 and are counted as imputed in Diagnostics.

## Web changelog

| Build | Change |
|---|---|
| web.1 | First release (Pine v21 engine). |
| web.1 + data fixes | Market-closed bars dropped; 4h DST grid; Twelve Data daily index; VWAP with no volume yet (D-07); Cornish-Fisher guard (D-08). Found on the first live run: 1h sat in WARMUP because the analog scan was disabled daily, and 30% of 15m bars were weekend quotes. The configuration hash is unchanged, so the holdout continues; its ledgers were still empty. |
| web.2 | Pine v32: the Cornish-Fisher guard is now in Pine as well (D-08 → parity); bias label and WAIT reason computed from the final scores (Pine v26, display only). `SCHEMA_BUILD` 6. Config hash unchanged, so the web holdout continues. |
