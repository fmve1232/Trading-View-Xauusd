# Phase D data requirements: exactly what is needed, in what format, and how to produce it

**Status (2026-11-09): nothing has been received.**
- **Done:** every importer, validator and the full run are built and tested on synthetic data.
- **The rule:** no real observation has been invented, substituted or assumed.
- **What it means:** until the inputs below arrive, every Phase D result reads **INSUFFICIENT DATA — RESEARCH INCOMPLETE**.

| # | Input | From | Required? | Used for | Status |
|---|---|---|---|---|---|
| 1 | Dukascopy XAUUSD ticks, development and 2026 | Your computer, by one command (§2) | **Required** | Workstreams A, C, D, E; the one-minute bid / ask path; the dynamic track | not run |
| 2 | Dukascopy intermarket ticks (EURUSD, XAGUSD, US dollar index CFD, US T-bond CFD) | Your computer, optional stage (§2.4) | Optional | Model C (without it, C is reported NOT RUN) | not run |
| 3 | MT5 M1 bars from your broker, development and 2026 | MT5 terminal export (§3) | Recommended | Workstream B: your broker's prices and spread at one minute | not received |
| 4 | Broker XAUUSD specification | MT5 symbol specification plus account page (§4) | Recommended | Account-currency P&L and drawdown (otherwise only $ / oz and R) | not received |
| 5 | A decision: where D3 runs | You (§5) | Required | Dukascopy's terms restrict redistribution | open |

**Never send** a trading password, an investor password, an account number, an API key or any raw tick file in chat or to GitHub. None of them is needed.

---

## 1. Partitions: what may be fetched

| Period (UTC) | Name | Fetch? |
|---|---|---|
| 2020-01-24 02:00 → 2023-01-24 02:00 | development | **yes** |
| 2023-01-24 02:00 → 2026-01-01 00:00 | validation + holdout, **sealed** | **no** |
| 2026-01-01 00:00 → yesterday | 2026 (unsealed) | **yes** |

How the seal is enforced:
- The extractor refuses any request touching the sealed span before it makes it.
- On the boundary day it fetches only 00:00 and 01:00.
- The MT5 validator drops sealed rows and only counts them.

## 2. Dukascopy (required)

### 2.1 The exact source format (no account, free)

**URL.** One file per UTC hour:

```
https://datafeed.dukascopy.com/datafeed/XAUUSD/{YYYY}/{MM-1:02d}/{DD:02d}/{HH:02d}h_ticks.bi5
```

The month counts from **00** (January = 00, December = 11); hours are UTC.

**No ticks.** An hour without ticks is a 0-byte file or HTTP 404. Saturdays are skipped.

**Container.** The file is LZMA-compressed ("alone" / `.lzma` format). Decompressed, it is a sequence of 20-byte big-endian records `>3I2f`:

| Bytes | Type | Field |
|---|---|---|
| 0–3 | uint32 | milliseconds since the start of the hour |
| 4–7 | uint32 | best ask, in integer price units |
| 8–11 | uint32 | best bid, in integer price units |
| 12–15 | float32 | volume displayed at the best ask |
| 16–19 | float32 | volume displayed at the best bid |

**Price units.** For XAUUSD the unit is $0.001 (1850.250 is stored as 1850250). The scale is **detected**: the median ratio of Dukascopy's mid to the spot close, rounded to a power of ten. The run stops if the median basis exceeds 0.5%.

**What it is.** The best bid and best offer on Dukascopy's SWFX ECN at every change, with the liquidity displayed at the best level.

**What it is not:**
- order-book depth beyond the best level;
- traded volume;
- trade direction;
- exchange (COMEX) data.

### 2.2 What the extractor writes (stays on your computer)

`quantum/research/d_dukascopy.py` writes, per UTC day, under `%USERPROFILE%\b5c_cache` (shared with B5c):

| Folder | Contents | Size (all periods) |
|---|---|---|
| `days\` | B5c's 15-minute sums (identical to B5c's own) | ~30 MB |
| `dext\` | Phase D's 23 extra 15-minute sums: spread min / max / first / last / sum of squares, best-bid and best-ask moves, displayed volume at each side, path length, realised variance, mid high / low, direction flips, the longest direction run, ticks in each half and the last 5 minutes, OFI in the last 5 minutes, spread widenings / narrowings, active seconds | ~60 MB |
| `m1\` | one-minute best-bid and best-ask OHLC plus tick count | ~150–300 MB |
| `inter\<SYM>\` | (optional) 15-minute mid first / last / high / low per instrument | ~40 MB |

Raw ticks are never stored. Each hour is reduced in memory as soon as it is downloaded.

### 2.3 Commands (Windows, from the repository folder)

```bat
py -3.11 -m pip install -r research\requirements-phase-d.txt
py -m quantum.research.d_dukascopy --period development
py -m quantum.research.d_dukascopy --period y2026
```

- **Interruptions.** Each command resumes where it stopped. Run it again if it reports incomplete days.
- **Time.** About 30–60 minutes for development and 10–20 for 2026 on a home connection.
- **Disk.** About 0.5 GB free disk is needed.

### 2.4 Intermarket (optional)

```bat
py -m quantum.research.d_dukascopy --period development --stage intermarket
py -m quantum.research.d_dukascopy --period y2026 --stage intermarket
```

**The probe.** The stage first probes one hour of each instrument (`EURUSD`, `XAGUSD`, `DOLLARIDXUSD`, `USTBONDTRUSD`). An instrument Dukascopy does not serve is reported unavailable and is never replaced by another series.

**What the instruments are:**
- The T-bond CFD is a bond **price**, an inverse proxy of long-term yields; it is **not** the 10-year yield.
- The dollar index CFD is Dukascopy's instrument, not ICE's DXY.

**Time.** EURUSD has dense ticks, so this stage takes a few hours.

### 2.5 Then the registered run (if D3 runs on your computer)

```bat
py -m quantum.research.d_run --cache %USERPROFILE%\b5c_cache --out phase_d_out
```

**What it downloads.** The spot paths (the `research-data` and `market-data` branches, about 35 MB) into the cache, once.

**What it runs.** The data gates, then the study, the questions, the one-minute measurements and the dynamic track. It takes about 3–5 hours.

**What to send back.**
- The folder `phase_d_out\` holds summaries and trade lists with times, directions, outcomes and net $ / oz, **no prices**.
- Send it together with `phase_d_trials.jsonl`.

**If a data gate fails.** It stops with `INSUFFICIENT DATA — RESEARCH INCOMPLETE` and writes `data_report.json`; send that file.

## 3. MT5 M1 export (recommended)

### 3.1 How to export (MT5 desktop terminal; nothing to install, no password involved)

1. **View → Symbols** (Ctrl+U) → the **Bars** tab.
2. Choose your broker's gold symbol (e.g. `XAUUSD`, `XAUUSD.r`, `GOLD`), timeframe **M1**.
3. **Range 1:** 2020-01-24 → 2023-01-24, then **Request**, then **Export Bars** → `XAUUSD_M1_dev.csv`.
4. **Range 2:** 2026-01-01 → today, then **Request**, then **Export Bars** → `XAUUSD_M1_2026.csv`.
5. **Do not request 2023-01-24 → 2025-12-31** (sealed). If your broker serves only one continuous range, export it anyway: the validator drops and only counts the sealed rows.

### 3.2 The exact file format the validator accepts

| Property | Accepted |
|---|---|
| Encoding | UTF-16 LE / BE with or without a BOM (MT5's usual "Unicode"), UTF-8, UTF-8 with a BOM |
| Separator | tab (MT5's default), comma or semicolon |
| Header | `<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>` (the `<>` are optional) |
| `<DATE>` / `<TIME>` | `YYYY.MM.DD` and `HH:MM` or `HH:MM:SS` (also `YYYY-MM-DD`, `YYYY/MM/DD`): **server time**, bar open |
| Prices | the **BID** side (MT5 builds bars from the bid) |
| `<TICKVOL>` | the number of quote updates (never used as traded volume) |
| `<VOL>` | real volume (usually 0 for CFDs; ignored) |
| `<SPREAD>` | points. MT5 does not define whether this is the bar's minimum, last or average spread, so Phase D uses it as a **sensitivity**, never as the primary cost. |

Example (tab-separated):

```
<DATE>	<TIME>	<OPEN>	<HIGH>	<LOW>	<CLOSE>	<TICKVOL>	<VOL>	<SPREAD>
2026.02.02	01:00:00	2771.45	2772.10	2771.30	2771.95	84	0	16
```

### 3.3 Three facts about your broker that I need with the file

- **The server time zone convention:**
  - **NY+7** (GMT+2 in winter, GMT+3 in summer, switching on the **US** dates, so that New York 17:00 = 00:00 server) is the most common;
  - otherwise an IANA zone such as `Europe/Athens` (switching on the **EU** dates);
  - otherwise a fixed offset.
  - If unsure, say so. The validator's `--suggest-zone` shows which convention lines up week by week, but the broker must confirm it; it is never applied automatically.
- **The point size:** the `<SPREAD>` unit, e.g. $0.01.
- **The exact symbol name and the broker / server name.**

### 3.4 Check the file (on your computer; send only the report)

```bat
py research\tools\mt5_m1_check.py --file XAUUSD_M1_dev.csv --server-tz NY+7 --broker "<broker>" --symbol XAUUSD ^
    --point 0.01 --reference-rd %USERPROFILE%\b5c_cache\research-data\<folder> --suggest-zone ^
    --report m1_report_dev.json --write-utc m1_dev_utc.csv
```

The file is **USABLE** only if all of the following hold:
- every row parses;
- no duplicates;
- the OHLC is consistent;
- no Saturday bars;
- discontinuities are at most 0.1% of consecutive minutes;
- no price-scale change between months;
- the clock peaks at a shift of 0 hours overall **and in every week**.

Send `m1_report_dev.json` and `m1_report_2026.json`. If the run happens on your computer, `d_run --mt5 m1_dev_utc.csv --mt5-point 0.01` uses the converted file.

## 4. Broker specification (recommended)

**How.** Fill **every** field of `research/broker/BROKER_SPEC_TEMPLATE.json` from MT5: right-click the symbol → **Specification**, plus your account type page. Then check it:

```bat
py -m quantum.research.d_broker research\broker\my_broker.json
```

**What it checks.** It refuses missing, empty, `null`, `ASSUMED`, `UNKNOWN` or `TBD` values, and it checks consistency:
- tick value = contract × tick size for a USD account;
- the lot step divides the minimum lot.

**How it is used.**
- **Theoretical price movement** ($ / oz, R) is always reported. It needs no broker data.
- **Executable account P&L** is reported only from a validated specification. Your balance is an **input** of the risk report only; it never selects or tunes anything.

## 5. Where D3 runs (your decision)

| Option | What moves | Pros | Cons |
|---|---|---|---|
| **(a) Your computer (default)** | Only summaries and price-free trade lists come back | Nothing derived from Dukascopy leaves your computer | 3–5 h of your computer's time; one command |
| **(b) This session, private upload** | The cache's `days\`, `dext\` and `m1\` folders (≈0.3–0.5 GB) uploaded privately, never committed | No compute on your side; easier re-runs of D4 checks | Derived Dukascopy data leave your computer: your call under Dukascopy's terms |

Either way, raw ticks and the derived bars are **never** committed to this public repository.
