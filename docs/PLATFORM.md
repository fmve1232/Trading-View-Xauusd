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
| `OANDA_API_TOKEN` | secret | A free OANDA **practice** account's API token: bid/ask candles and a pricing snapshot for the Price-sources panel (`quantum/reference.py`). Display and validation only. Without it the panel says UNAVAILABLE. |
| `OANDA_ENV`, `OANDA_ACCOUNT_ID` | variable | Optional. `OANDA_ENV=live` for a live account (default `practice`); the account id is otherwise read from the token. |
| `METAAPI_TOKEN`, `METAAPI_ACCOUNT_ID` | secret | Your own MT5 broker feed through MetaApi, read in the cloud with no PC. **Not free:** MetaApi showed USD 0.0126 per account-hour (about $9 a month) on 3 Oct 2026, so it is optional, and the MT5 panel stays hidden unless an account is connected. Connect the account with the MT5 **investor (read-only)** password. Feeds the MT5 panel (`quantum/mt5.py`). Display and validation only. |
| `MT5_SYMBOL` | variable | Your broker's gold symbol in MT5, e.g. `XAUUSD`, `XAUUSDm` or `GOLD`. Default `XAUUSD`. |
| `GH_DISPATCH_TOKEN` | secret | A fine-grained GitHub token (this repository only, **Actions: Read and write**). The `scheduler` workflow uploads it as a Worker secret, and the Worker (`scheduler/`) starts this site's runs at :01/:16/:31/:46 UTC. GitHub's own cron is then the backup. |
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
| D-09 | OANDA's first print after a reopen is a real trade | Twelve Data's is the quote carried through the closure; the session's first bar is rebuilt from repaired 5-minute bars | on 27 Sep the stale print set Monday's high at 4287.25; repaired 4275.33 = OANDA 4275.325 (web.4) |
| D-10 | TradingView bars only | Yahoo's latest-quote snapshots at off-minute times are dropped from every Yahoo series | they were being stored as bars; one carried Friday's close into Sunday (web.4) |
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

- **Market-closed bars are dropped** (since web.4: Friday 17:00 → **Sunday 18:00** New York, and the
  **daily 17:00–18:00 break**, Monday–Thursday; daily bars dated Saturday or Sunday). Twelve Data's free
  XAU/USD feed prints the last quote with a few cents of jitter 24/7; on the first live week those were
  ~30% of the 15-minute chart and corrupted ATR, PDH/PDL (fake weekend "days"), VWAP and the return
  volatility. The data-status panel reports how many were dropped per series. The raw store keeps them.
- **The first bar of each session is repaired** (web.4). Its first print is the quote carried through the
  closure, not a trade; it is removed and the bar is rebuilt from 5-minute bars (D-09).
- **Off-minute rows are dropped** (web.4). Yahoo's latest-quote snapshots (e.g. 22:04:41) were being stored
  as bars (D-10); the store is cleaned as each series is re-saved.
- **4-hour bars sit on the 17:00 New York grid through DST** (bucketed on New York wall-clock time).
- **Daily bars:** Yahoo futures dailies are re-indexed to their 17:00 New York session open; Twelve Data
  dailies are UTC calendar days and keep their 00:00 UTC open. Either way the alignment rule reads only
  the previous completed day.
- The daily break (17:00–18:00 New York) is shut for spot gold as well as COMEX futures (web.4). Until web.3
  the site assumed spot kept trading there; the stored quotes show it only repeats the last price.

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
| web.4 | From a same-minute comparison with TradingView (28 Sep, 02:02 UTC). **Engine inputs:** gold's hours corrected (Sunday reopen 18:00 NY, daily 17:00–18:00 break shut); the stale first print of each session repaired (D-09; Monday high 4287.25 → 4275.33 = OANDA); Yahoo off-minute snapshot rows dropped (D-10). The engine code hash changes, so the **website forward test restarted** (Amendment 4: decided with no 1H trades; one −1.021R 1H trade in Treatment and Challenger arrived before the delayed merge and is archived and must be reported with the final result). **Schedule:** runs at :02/:17/:32/:47, just after each bar closes (at 02:02 the site was one hourly bar behind). **Display:** PDH/PDL/PWH/PWL price labels on the chart; a one-line summary strip (Signal / Structure / Liquidity / Price / Macro / Risk / Decision) above the chart. Same-minute agreement before the fixes: decision, bias and session identical; PDH/PDL within $0.20, PWL within $0.95, price within $1.4. |
| web.4 + validation | Outside the engine and the freeze key (`3252a9f0d312db75` unchanged). **Price sources panel** (`quantum/reference.py`, separate non-fatal step): an OANDA practice feed (bid/ask candles, `price=BA`, and a pricing snapshot) and gold-api.com. Each observation has source / received / processed / published times in epoch ns and the precision the source actually carries (padded zeros are not counted). The engine's last 1h closes are compared with OANDA's mid closes **on the same bars** (median, MAD, robust z, p95/max, observed spread, share of bars inside the spread). Fixed display bands are <0.03% consistent, <0.1% minor, <1% significant, otherwise critical. Both raw prices are always shown; neither is replaced. **Data versioning** (`quantum/manifest.py`): every run writes the store's tree hash and per-file SHA-256 to `forward-ledger` (`manifests/`), and the old values of any *closed* bar a later download changed go to `revisions/`. A forming bar finishing is counted, not listed. **Integrity tests:** no `Math.random`/`np.random` on production paths, no `--synthetic` in the workflow, no literal gold prices in the page, no credential-shaped strings in tracked files, and the token is never written to the output or to error text. **Display:** the market-closed rule in the browser matches the pipeline; statistics over zero observations show "—"; the volume card is labelled as a proxy. |
| web.4 + NFP review | From two screenshots of the 2 Oct NFP release (12:30 UTC), taken at the same minute: TradingView and the site. **The prices agree:** PDH $0.57 apart (4192.52 vs 4193.09); 5m EMA200 at 12:40 $0.08 apart (4178.88 vs 4178.96); the release-bar high $2 apart (4225.47 vs 4227.53, normal in a news spike). **The site was late.** Its last bar closed 12:25, while price had moved +$42.58. GitHub's cron delivered only 100 of 153 scheduled runs on 1–2 Oct (median gap 23 min), so no run happened between 12:27 and 12:52. **Fixes (display and workflow only; freeze key unchanged):** (1) `scheduler/`, a free Cloudflare Worker cron that dispatches the workflow at :01/:16/:31/:46. GitHub's cron becomes a backup that stands down within 10 min of a dispatched run (the `gate` job), keeping Twelve Data at about 384 calls a day. (2) The "updated" chip goes stale at **2 bars behind for the chart's timeframe** (it used 90 minutes for every timeframe). (3) **Out-of-date guard** above the decision: when 2 bars have closed since, or the live price is ≥1.5 ATR from the last close (a fixed display constant), the plan is dimmed and marked "do not act". (4) **Event guard:** a high-impact USD release within ±30 min is announced above the decision. (5) Chart axis labels follow the Time selector (they were UTC beside a local legend), and a time the chart cannot format is blank, not "Invalid Date". |
| web.4 + MT5 | **MT5 broker feed in the cloud** (optional and paid via MetaApi; the panel is hidden unless connected; `quantum/mt5.py`, a separate non-fatal step; outside the freeze key). On each update MetaApi's REST API supplies the broker's latest tick (bid/ask, spread, ms time), its 5m/15m/1h candles with **tick volume** (stored as `MT5_<symbol>_<tf>` and versioned by the manifest), the same-bar difference from the engine's Twelve Data closes, and a **footprint** of the last 1,000 ticks per $0.50. The footprint uses real deal side and volume when the broker sends them, and is otherwise the tick rule, **labelled PROXY**: spot gold has no central traded volume. Six API calls per update. The token is sent only in a header and scrubbed from every output. Without the secrets the panel says so and fills nothing. |
| web.4 + H2 | **Arm H2 "Sweep and Value"** (`quantum/arm_h2.py`; pre-registered in Amendment 5 *before* any run). LONG when: trend up (close > EMA200, EMA20 > EMA100); a sell-side sweep (PDL/PWL/PML or the swing low) in the last 3 bars that reached VAL; a close above the previous high; an active session. SHORT is the mirror. Stop beyond the sweep extreme ± 0.1 ATR; TP1 = POC or 1R; TP2 = nearer of VAH or the swing level, else TP1 + 1R. It reads only the frozen engine's outputs and uses the same execution model. Its **own freeze key** (engine key + SHA-256 of `arm_h2.py`), manifest (`holdout/manifest_h2.json`) and ledgers (`holdout/<tf>_h2.json`); the main freeze key is unchanged (`report.py` and `arm_h2.py` are outside `ENGINE_SOURCES`). Site: an H2 card with the 5-rule checklist, the current or last signal and its plan, the open H2 trade, "next movement" statistics from past signals (labelled in-sample), and the forward record; H2 arrows on the chart. **First in-sample run** (rules already frozen): 1h 12 signals Mar–Oct (7 trades, +2.1R), 15m 6 (−3.7R), 5m 7 (−1.6R), 4h 1. Too few to judge, and at about 1.7 trades a month on 1h the N ≥ 50 bar is unlikely to be reached by 2027-03-31, so the pre-registered verdict will probably be NOT SHOWN. **Also fixed:** the report wrote the forming bar's time in nanoseconds. The site therefore never used the forming bar's OHLC and pushed a bar at an impossible future time, the likely root cause of the "Invalid Date" axis label (display only). |
