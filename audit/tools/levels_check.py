"""Independent recomputation of the previous-day / previous-week levels the live monitors cite (read-only; mandate §9).

  python3 audit/tools/levels_check.py --state <alerts_state.json> --bars <market-data checkout>

It does NOT import the production code. From the stored 15-minute XAU/USD bars (<bars>/XAU_USD_15m/*.csv) it keeps
only bars opening inside spot gold's trading hours, written here independently (Sunday 18:00 to Friday 17:00 New York,
without the daily 17:00-18:00 break: the store also holds the feed's carried quotes from closed hours), assigns
each bar to a trading day with its own New York 17:00 rollover (zoneinfo America/New_York; a bar opening at or after
17:00 New York belongs to the next day), takes each trading day's high and low, and each trading week's (Monday to
Friday trading days; Sunday evening belongs to Monday). For every M15 breakout and every sweep in the state whose
levels include PDH / PDL / PWH / PWL, it compares the cited price with the recomputed one for the trading day / week
before the event bar's own. Agreement is within $0.01 (the site payload rounds prices to 2 decimals).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
TOL = 0.0101


def load(d: str) -> pd.DataFrame:
    fr = []
    for f in sorted(glob.glob(os.path.join(d, "XAU_USD_15m", "*.csv"))):
        x = pd.read_csv(f, index_col=0)
        x.index = pd.to_datetime(x.index, utc=True)
        fr.append(x[["high", "low"]].astype(float))
    df = pd.concat(fr)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[[open_market(t.to_pydatetime()) for t in df.index]]


def open_market(ts: datetime) -> bool:
    ny = ts.astimezone(NY)
    wd, hr = ny.weekday(), ny.hour                    # Monday 0 .. Sunday 6
    if wd == 5 or (wd == 4 and hr >= 17) or (wd == 6 and hr < 18):
        return False
    return hr != 17                                   # the daily 17:00-18:00 break


def trading_day(ts: datetime):
    ny = ts.astimezone(NY)
    return (ny + timedelta(days=1)).date() if ny.hour >= 17 else ny.date()


def tables(df: pd.DataFrame):
    td = [trading_day(t.to_pydatetime()) for t in df.index]
    g = df.assign(td=td).groupby("td").agg(high=("high", "max"), low=("low", "min"))
    wk = g.assign(w=[(d - timedelta(days=d.weekday())) for d in g.index]).groupby("w").agg(high=("high", "max"), low=("low", "min"))
    return g, wk


def check(state: dict, df: pd.DataFrame) -> dict:
    days, weeks = tables(df)
    dl, wl = list(days.index), list(weeks.index)
    out = {"checked": 0, "agree": 0, "disagree": [], "skipped_no_prior_data": 0, "by_kind": {}}
    recs = [r for r in state["brk"]["events"].values() if r.get("tf") == "15m"] + list(state["brk"]["sw"].values())
    for r in recs:
        t = datetime.fromtimestamp(r["t"], UTC)
        d = trading_day(t)
        prev_d = max((x for x in dl if x < d), default=None)
        w = d - timedelta(days=d.weekday())
        prev_w = max((x for x in wl if x < w), default=None)
        for lv in r.get("levels") or []:
            k = lv.get("kind")
            if k not in ("PDH", "PDL", "PWH", "PWL"):
                continue
            if lv.get("tf", "15m") != "15m":
                continue
            ref = prev_d if k in ("PDH", "PDL") else prev_w
            if ref is None or (k[:2] == "PW" and ref < dl[0]) or (k[:2] == "PD" and ref == dl[0] and ref not in days.index):
                out["skipped_no_prior_data"] += 1
                continue
            tab = days if k[:2] == "PD" else weeks
            want = float(tab.loc[ref, "high" if k.endswith("H") else "low"])
            out["checked"] += 1
            b = out["by_kind"].setdefault(k, [0, 0])
            b[0] += 1
            if abs(want - float(lv["price"])) <= TOL:
                out["agree"] += 1
                b[1] += 1
            else:
                out["disagree"].append({"id": r["id"], "kind": k, "cited": lv["price"], "recomputed": round(want, 2),
                                        "ref": str(ref)})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--bars", required=True)
    a = ap.parse_args(argv)
    with open(a.state) as f:
        st = json.load(f)
    res = check(st, load(a.bars))
    print(json.dumps(res, indent=1))
    return 1 if res["disagree"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
