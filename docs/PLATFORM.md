# XAUUSD Quantum — web platform

The Pine Master (build v32) and its three strategy arms, ported to Python and run on free
market data by GitHub Actions, published to GitHub Pages. No server, no paid feed, no
TradingView limits (no compiled-token ceiling, no per-bar loop budget, no chunked scans,
full-history backtests).

**The website is the production system. TradingView/Pine is the reference implementation used
to validate it.** Nothing on the site needs TradingView at run time: data, signals,
probability, risk, backtests, Monte Carlo, the forward test and alerts all come from this
engine. Since `PREREGISTRATION.md` Amendment 2 (before the start) the website's forward test is the
primary one and the TradingView arms are withdrawn.

```
GitHub Actions (every 15 min, Sun 22:00 – Fri 21:00 UTC)
  ├─ download   Yahoo · FRED · CFTC (+ Twelve Data if keyed)   → market-data branch (monthly CSVs)
  ├─ engine     quantum/  (treatment · control · challenger arms, 5m · 15m · 1h · 4h)
  ├─ backtest   3 arms, walk-forward, Monte Carlo, calibration, frozen forward holdout
  ├─ ledger     forward-test log → forward-ledger branch (normal commits, full history)
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
| `STREAM_URL` | variable | `wss://…/stream` of the tick relay (`relay/README.md`): the live chip and forming candle stream ticks. Empty = the 60 s gold-api poll. Display only. |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `FINNHUB_KEY` | secret | Used only by the `stream-relay` workflow, to deploy the relay. The Finnhub key becomes a Worker secret and never reaches the site. |

## Local use

```sh
pip install -r requirements.txt
python -m pytest -q tests                                        # 59 tests, ~60 s
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

- **Frozen forward holdout, pre-registered** (`audit/PREREGISTRATION.md` §7). It starts at
  2026-09-28 00:00 UTC. The freeze key is the configuration hash plus a hash of every
  signal-producing source file (`holdout.ENGINE_SOURCES`), so a parameter change **or** an engine
  code change restarts it automatically. Trades entered after the freeze are appended once, with
  their price source, and never rewritten. On a restart the old entries move to
  `holdout/archive/` and the old freeze stays in the manifest's history. The log is kept on
  `market-data` and also, with full git history, on `forward-ledger`; a run restores it from
  there if the store ever loses it. 1H decides; the other timeframes are descriptive. It is the
  only out-of-sample evidence, and it is independent of the operator's Excel log.
- **History that accumulates.** Each run merges into the store, so 5m/15m history grows past Yahoo's
  60-day window.
- **No-look-ahead is tested.** `tests/test_engine.py::test_no_lookahead` truncates the data at bar k and
  checks that no earlier decision changes.
- **Backtest reporting:** both A/B arms, walk-forward folds (no refitting), bootstrap Monte Carlo,
  per-session / regime / direction breakdowns, and the F-A12 calibration test of P at entry.
- **Alerts** on confirmed bars only, deduplicated across runs.

## Known, not tuned (holdout rules)

- `mrComposite` sits at ±100 on about 60% of bars. This is a research item for the next build,
  after the forward test.
- F-035 (outcome horizon) is open. Same-bar SL/TP ties count as the stop.
- The score has no resolution on the development history (F-A34), so calibration is shown, not
  trusted.
- Macro votes overlap (DXY/EURUSD, US10Y/TIPS). Their weights come from each series' own
  correlation with gold, not from their overlap with each other.
- Costs are a fixed session spread + slippage + commission. There is no widened news spread yet.
- The engine runs on a rolling window of the last 16,000 bars, and providers can revise a
  stored bar (the newer download wins). Either can shift *backtest* history slightly between
  runs. The forward log is immune: each trade is written once.

## Limits

Free data is delayed and occasionally wrong; GitHub's scheduler can run late or skip a run; parity
with a TradingView chart has not been demonstrated yet (scheduled for the first holdout week, bar by bar,
every difference classified as D-xx or a bug; a bug fix restarts the website holdout); fills
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
| web.2 + fix | API keys redacted from every error text that can reach the published site. |
| web.3 | **Challenger arm** (Pine v31 H1) on every timeframe. Freeze key = config hash + engine code hash; first freeze pinned to 2026-09-28 00:00 UTC; ledger entries archived on a restart, not dropped; price source recorded per trade; `forward-ledger` branch with history. Workflow: a failed store clone now stops the run, so it can no longer force-push an empty store over the history. Pre-registered in `PREREGISTRATION.md` §7. The earlier web freeze (2026-09-26, no trades) is closed in the manifest's history. |
| web.3 + display | **Live spot ticker** (header chip; your browser reads gold-api.com every 60 s; rejected if more than 5% from the engine's last close; shows age and Δ vs the last bar). **Upcoming events panel** (USD high/medium impact from the Forex Factory weekly JSON, written by `quantum/events.py` in a separate, non-fatal workflow step; if that fails, the next NFP estimated by rule, labelled). Both are display only: `events.py` is outside `ENGINE_SOURCES`, nothing in the engine reads either, and the freeze key is unchanged (`32babc71ed938b30`). |
| web.3 + news | **News in the calendar panel:** Myfxbook calendar-events RSS, Myfxbook news RSS and FXStreet news RSS, kept only when a headline mentions gold / USD / rates drivers (last 48 h, de-duplicated, newest first, linked to the publisher). Each feed fails on its own and shows its status. URLs can be changed through the repository variables `MYFXBOOK_CAL_RSS`, `MYFXBOOK_NEWS_RSS` and `FXSTREET_NEWS_RSS`. FXStreet's *calendar* is a paid OAuth API and is not used. Display only; the freeze key is unchanged. |
| web.3 + review fixes | From the operator's screenshots (display only): the Trade-quality card no longer breaks (the veto label "TQ<floor" was inserted unescaped, and the browser read `<floor` as a tag); no ± interval on the rolling win rate (F-037/F-A14); the footer says v32; the live chip reads "market closed · last quote" on weekends; the holdout chip reads "starts" until the start; the plan pill reads "· no signal" and explains its regime-call side; the probability pill reads "fitted in-sample" (F-A34); the multi-timeframe card lists only timeframes above the chart's. **Layout:** the chart card no longer stretches to the side column's height (it left ~1,200 px of empty card below the chart); Calendar & news moved under the chart as two columns (calendar | news); on phones the order is unchanged. Freeze key unchanged. |
| audit: xcheck | **Independent price cross-check** (`audit/tools/xcheck_dukascopy.py`, workflow `xcheck-dukascopy`, on demand and Saturdays 06:17 UTC). It downloads Dukascopy's public 1-minute BID/ASK candles for complete past days, builds MID 15m/1h bars on the same UTC grid, and compares them with the stored Twelve Data bars: bias, median/p95/max close difference ($ and bps), high/low differences, return correlation and sign agreement, a best-lag scan (catches bar-labelling offsets), and the ten largest disagreements. The decode is self-checked: the price scale is detected, and ≥ 99% of minutes must pass OHLC sanity, or the report says NOT RUN. Read-only; the report goes to the run summary and artifact, never to the site (Dukascopy's terms restrict redistribution). Not part of the engine or the freeze key. |
| web.3 + stream | **Streaming ticks (display only).** `relay/` is a Cloudflare Worker with one Durable Object hub. It holds a single Finnhub WebSocket while anyone is watching and relays ticks, at most 4 a second, carrying the high and low since the previous update. Only the site's origin may connect; the key stays a Worker secret. The page reads the relay address from `data/stream.json` (repository variable `STREAM_URL`). Ticks update the live chip and the **forming** candle only; closed bars are never touched. A tick more than 5% from the engine close is rejected, and the 60 s gold-api poll stands down while ticks arrive and resumes if they stop. Deployed by the `stream-relay` workflow, which skips cleanly until its secrets exist. Also: `xcheck_dukascopy.py` now fails fast (one 20 s attempt per file; stops after 3 failed days) and logs each day. The first run stalled on retries without printing why. |
| audit: xcheck + Yahoo | Run 2 showed that **Dukascopy refuses GitHub's cloud addresses** (read timeout, connection reset, connect timeout), so it reports NOT RUN there; run the tool on a home PC for Dukascopy. **Yahoo spot `XAUUSD=X`** is added as a reference that runs on GitHub: 15m/60m bars from the last ≤ 60 days, completed bars only, weekend quotes dropped. It must be within 5% of Twelve Data's price level (catches a different instrument or scale; a NaN level fails) and pass OHLC sanity on ≥ 98% of bars, or it reports NOT RUN. The same comparison and verdict as Dukascopy. The workflow is renamed `xcheck-prices` (input `ref`: yahoo / dukascopy / both; default both). |
| audit: xcheck GC | Run 3: Yahoo no longer serves `XAUUSD=X` (HTTP 404), so it reports NOT RUN. **New default reference: COMEX gold futures GC=F**, already in the store, so nothing is downloaded and it runs anywhere. The futures premium is removed per New York trading day (the session starts at 17:00 NY); days whose premium jumps by more than $5 are listed as probable contract rolls; a premium outside −2%…+5% of spot means NOT RUN. The largest differences are tagged with a heuristic window (08:30 data, 14:00–16:00 FOMC + press conference, Friday close, COMEX break) or **unexplained**; unexplained differences above max($5, 6 × median) add "review" to the verdict. Correlation is now rank (Spearman), so one bad bar shows as an outlier instead of dragging the correlation down. **First result (1–27 Sep):** timing correct (best lag 0), median difference 2.1 bps, rank correlation 0.976 (1h) and 0.905 (15m), no rolls, and three 15m differences of about $7.6 outside event windows to review. It tests timing and integrity, not the spot level (that needs Dukascopy from a home PC). |
