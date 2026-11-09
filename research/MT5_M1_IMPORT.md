# MT5 M1 history: the preferred route to lower-timeframe data (prepared 2026-11-09, not yet available)

> **Superseded for Phase D (2026-11-09) by `PHASE_D_DATA_REQUIREMENTS.md` §3.** The Phase D validator reads UTF-16 exports, supports the common `NY+7` server convention (Europe/Athens is an hour wrong for about three weeks a year when the broker follows the US daylight-saving dates), checks the clock per week, drops sealed rows, and treats `<SPREAD>` as a sensitivity, not the primary cost (`PHASE_D_PLAN.md` §2.2). The text below is kept as written.

**Why it is needed.**
- **Small brackets are only bounded, not measured.** Phase C's 15m bars cannot order the high and low inside a bar. Brackets with a $3–$7 leg are therefore INCONCLUSIVE (B29), as are stop entries of $10 or more (B28).
- **5m covers too little time.** The live store has only Sep–Nov 2026.
- **Years of 1-minute bars** turn those bounds into measurements, and give 5m execution checks over the development period.

**Why MT5, and what is not used.**
- **It is your broker's own price,** with its own spread, as you trade it.
- **The production Twelve Data key is not used.** A multi-year Twelve Data fetch would share the production API key and its daily credits with web.8's live feed (`PHASE_C_PLAN.md` §4).
- **MetaApi (the site's optional broker feed) is not used for history either.** It is a production integration with its own token.

## How to export (on your computer; nothing to install)

1. In the MetaTrader 5 terminal: **View → Symbols** (Ctrl+U) → the **Bars** tab.
2. Choose **XAUUSD** (your broker's exact symbol), timeframe **M1**, and the range. The broker serves what it holds. Ideally pick 2020-01-24 → 2023-01-24 (development), and at least 2026-01-01 → today (the 2026 check). Do not request 2023-01 → 2026-01: those are the sealed validation and holdout periods.
3. Press **Request**, then **Export Bars**, and save the `.csv`.
4. Note three facts about your broker:
   - its **server time zone** (many use GMT+2 in winter and GMT+3 in summer, i.e. `Europe/Athens`);
   - the **contract size** of 1.00 lot (Phase C ASSUMES 100 oz);
   - the **point size** (the `<SPREAD>` column is in points).

**No password is involved.** The terminal exports the bars itself. Never share a trading password; the investor (read-only) login is enough for anything else.

## Checking the file (on your computer)

```sh
python research/tools/mt5_m1_check.py --file XAUUSD_M1.csv --server-tz Europe/Athens --report m1_report.json
```

**What the check covers:**
- the columns and the parse;
- duplicates and order;
- OHLC consistency and non-positive prices;
- the conversion of server time to UTC;
- gaps: weekends and holidays, the daily break, and unexpected holes;
- the spread column.

**With `--reference`** (a UTC 15m file with `time,close` columns, e.g. exported from the research store), it also checks the clock. The correlation of 15m close changes must peak at a shift of 0 hours. A wrong server offset shows as a peak at ±1–3 hours, and the file is then marked NOT USABLE.

**Keep the file on your computer.** Send only `m1_report.json`. The bars are your broker's data and are not committed to this public repository; a study using them will be registered first and will read them from a local path.

## Conventions the research will apply

| Item | Convention |
|---|---|
| Time | MT5 bars are in server time; converted to UTC with the broker's zone (DST-aware), then labelled by bar open time like every other series here |
| Price side | MT5 bars are built from the BID; ask = bid + spread × point. BUY entries fill at the ask, SELL at the bid, and each side's levels trigger on the exit side (B26's model) |
| Spread | the `<SPREAD>` column (points per bar) replaces the modelled $0.30 / $0.50 when present; zero or missing spreads fall back to the model and are counted |
| Tick volume | quote updates, not traded volume; never used as volume |
| Partitions | development and 2026 only; validation and holdout stay sealed |
