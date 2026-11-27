"""Independent recomputation of the G4 per-trade diagnostics (quantum/trade_diag.py).

Every logged record is recomputed from the store's 5-minute bars with a DIFFERENT implementation and a different bar
loader: audit/tools/h4_forward_diagnosis.races (written and tested for the 26 Nov H4 diagnosis) on bars read by
audit/tools/forward_report.load_bars, with its own epoch conversion. Only the data cleaning is shared with the module,
because it is the engine's (shut-market bars dropped, each session's first print repaired: sources.trading_week_only,
sources.repair_reopen); with --raw the repair is skipped and a disagreement on a record whose window contains a
session reopen is reported separately as REOPEN. Checked per record:
  * each target's result (+$10 / +$15 / +$20 / TP1 / TP2 against the original stop: TARGET / STOP_FIRST / UNDECIDED)
    and the hours to it, for the engine's fill and for the next bar's open (next_open);
  * the race window: whether the stop ended it, and the favourable excursion inside it (when every target was
    reached first, the window is cut at the last target, recomputed here from this code's own hours);
  * the in-trade MAE / MFE, recomputed here: for an exit at a close, the excursion from the fill to the exit bar's
    close; for an exit at a price, the excursion before the first 5-minute bar of the exit bar that reaches the exit
    price, plus that bar's exit side capped at the exit price (the whole exit bar when no bar reaches it);
  * the ledger trade's SHA-256 (the record still describes the trade as it stands in the ledger).

  python3 audit/tools/trade_diag_check.py --store <market-data store> [--diag <dir of trade_diag *.jsonl>] [--json out] [--raw]
Exit status 1 when any disagreement (REOPEN excepted under --raw) or a changed ledger trade is found.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forward_report as FR
import h4_forward_diagnosis as H

TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
LEVEL_EXITS = ("SL", "SL_GAP", "BE", "BE_GAP", "TP2")      # exits at a price; FLIP exits at the bar's close
HORIZON = 7 * 86400


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_diag(d: str) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        with open(f) as fh:
            rows.extend(json.loads(x) for x in map(str.strip, fh) if x)
    return rows


def ledger(store: str) -> dict:
    out = {}
    for f in glob.glob(os.path.join(store, "holdout", "*_*.json")):
        b = os.path.basename(f)[:-5]
        if b.startswith("manifest") or "_" not in b:
            continue
        tf, arm = b.split("_", 1)
        if tf not in TF_SEC:
            continue
        with open(f) as fh:
            rows = json.load(fh)
        for t in rows if isinstance(rows, list) else []:
            out[f"{tf}|{arm}|{t['entry_time']}|{t['dir']}"] = t
    return out


RES = {"TP": "TARGET", "SL": "STOP_FIRST", None: "UNDECIDED"}
TOL_H, TOL_USD = 5e-4, 1.5e-3                  # the record stores hours and dollars to 3 decimals


def _race_diffs(tag: str, rc: dict, got: dict, names, shift_h: float) -> list[str]:
    """shift_h: races() counts hours from the first bar's open, the record from the fill (they differ after a break)."""
    out = []
    for name in names:
        res, hrs = rc[name]
        hrs = None if hrs is None else hrs + shift_h
        g = got[name]
        if RES[res] != g["result"] or (hrs is not None and (g["hours"] is None or abs(hrs - g["hours"]) > TOL_H)):
            out.append(f"{tag}{name}: {g['result']} {g['hours']} vs {RES[res]} {hrs}")
    return out


def _window(B5: dict, j0: int, j_end: int, long: bool, e: float, sl: float, tg: dict) -> tuple[dict, bool, float]:
    """This code's race, whether the stop ended the race window, and the favourable excursion in the window."""
    rc = H.races(B5, j0, j_end, long, e, sl, tg)
    if all(rc[n][0] == "TP" for n in tg):          # every target before any stop: the window ends at the last one
        t_close = int(B5["t"][j0]) + round(max(rc[n][1] for n in tg) * 3600)
        jx = int(np.searchsorted(B5["t"], t_close - 300, side="left"))
        return rc, False, H.races(B5, j0, jx + 1, long, e, sl, tg)["mfe_usd"]
    return rc, bool(rc["stopped"]), rc["mfe_usd"]


def _excursion(B5: dict, a: int, b: int, long: bool, e: float) -> tuple[float, float]:
    if b <= a:
        return 0.0, 0.0
    hi, lo = float(np.max(B5["h"][a:b])), float(np.min(B5["l"][a:b]))
    return (max(e - lo, 0.0), max(hi - e, 0.0)) if long else (max(hi - e, 0.0), max(e - lo, 0.0))   # (MAE, MFE)


def check(store: str, diag_dir: str, raw: bool = False) -> dict:
    df = H.bars(store, "5m")
    if not raw:
        df = H.sources.repair_reopen(df, 300)
    B5 = H.arrays(df)
    reopen_bar = np.r_[False, np.diff(B5["t"]) >= 3600]        # the first bar after a break of an hour or more
    led = ledger(store)
    rows = load_diag(diag_dir)
    agree = disagree = reopen = changed = missing = 0
    worst = []
    for r in rows:
        t = led.get(r["key"])
        if t is None:
            missing += 1
            continue
        if _sha(t) != r["trade_sha256"]:
            changed += 1
            worst.append({"key": r["key"], "what": "ledger trade changed since the record was written"})
            continue
        long, e, sl = r["dir"] == "LONG", r["entry"], r["sl"]
        sgn, sec = (1 if long else -1), TF_SEC[r["tf"]]
        t_fill = FR.ts(r["entry_time"]) + sec
        j0 = int(np.searchsorted(B5["t"], t_fill, side="left"))
        j_end = int(np.searchsorted(B5["t"], t_fill + HORIZON, side="left"))
        diffs = []
        shift_h = (int(B5["t"][j0]) - t_fill) / 3600.0 if j0 < len(B5["t"]) else 0.0
        # the engine's fill
        tg = {f"usd{u}": e + sgn * u for u in (10, 15, 20)}
        tg.update({"tp1": r["race"]["tp1"]["price"], "tp2": r["race"]["tp2"]["price"]})
        rc, stopped, mfe_w = _window(B5, j0, j_end, long, e, sl, tg)
        diffs += _race_diffs("", rc, r["race"], tg, shift_h)
        if stopped != r["stop"]["hit"]:
            diffs.append(f"stop hit {r['stop']['hit']} vs {stopped}")
        if abs(mfe_w - r["race_window"]["mfe_usd"]) > TOL_USD:
            diffs.append(f"race mfe {r['race_window']['mfe_usd']} vs {round(mfe_w, 3)}")
        # the next bar's open
        o0 = float(B5["o"][j0])
        if abs(o0 - r["next_open"]["entry"]) > TOL_USD:
            diffs.append(f"next open {r['next_open']['entry']} vs {o0}")
        tg_n = {f"usd{u}": o0 + sgn * u for u in (10, 15, 20)}
        rc_n, _, mfe_n = _window(B5, j0, j_end, long, o0, sl, tg_n)
        diffs += _race_diffs("next_open.", rc_n, r["next_open"]["race"], tg_n, shift_h)
        if abs(mfe_n - r["next_open"]["race_window"]["mfe_usd"]) > TOL_USD:
            diffs.append(f"next_open race mfe {r['next_open']['race_window']['mfe_usd']} vs {round(mfe_n, 3)}")
        # in-trade MAE / MFE
        t_x = FR.ts(r["exit"]["exit_time"])
        xb0 = int(np.searchsorted(B5["t"], t_x, side="left"))
        xb1 = int(np.searchsorted(B5["t"], t_x + sec, side="left"))
        mae, mfe, ends = *_excursion(B5, j0, max(xb1, j0 + 1), long, e), "exit bar close"
        xp, why = r["exit"]["exit"], r["exit"]["reason"]
        if why in LEVEL_EXITS and xp is not None:
            ends = "exit price not found in the stored bars"
            down = xp < e or (xp == e and long)          # the exit price is reached from above
            for k in range(max(xb0, j0), xb1):
                if B5["l"][k] <= xp <= B5["h"][k] or (B5["o"][k] < xp if down else B5["o"][k] > xp):
                    mae, mfe = _excursion(B5, j0, k, long, e)
                    if down:                             # that bar's low, never below the exit price
                        px = max(float(B5["l"][k]), xp)
                        mae, mfe = (max(mae, e - px), mfe) if long else (mae, max(mfe, e - px))
                    else:                                # that bar's high, never above the exit price
                        px = min(float(B5["h"][k]), xp)
                        mae, mfe = (mae, max(mfe, px - e)) if long else (max(mae, px - e), mfe)
                    ends = "exit price touched"
                    break
        it = r["in_trade"]
        if ends != it["ends"]:
            diffs.append(f"in_trade ends {it['ends']!r} vs {ends!r}")
        diffs += [f"in_trade {nm} {g} vs {round(v, 3)}" for nm, g, v in (("mae", it["mae_usd"], mae), ("mfe", it["mfe_usd"], mfe))
                  if abs(g - v) > TOL_USD]
        if not diffs:
            agree += 1
            continue
        # under --raw this loader did not repair each session's first print, as the module did
        w_end = max(j0 + max(r["race_window"]["bars"], r["next_open"]["race_window"]["bars"]), xb1)
        at_reopen = raw and bool(reopen_bar[j0:min(w_end, len(reopen_bar))].any())
        if at_reopen:
            reopen += 1
        else:
            disagree += 1
        worst.append({"key": r["key"], "what": "REOPEN" if at_reopen else "DISAGREE", "diffs": diffs})
    return {"records": len(rows), "bars": "raw (no reopen repair)" if raw else "reopen repaired as the engine does",
            "agree": agree, "disagree": disagree, "reopen_only": reopen,
            "ledger_changed": changed, "trade_not_in_ledger": missing, "details": worst[:50]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True)
    ap.add_argument("--diag", help="trade_diag directory (default: <store>/trade_diag)")
    ap.add_argument("--json")
    ap.add_argument("--raw", action="store_true", help="skip the engine's session-reopen repair (REOPEN reported apart)")
    a = ap.parse_args(argv)
    out = check(a.store, a.diag or os.path.join(a.store, "trade_diag"), a.raw)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "details"}))
    for w in out["details"][:10]:
        print(" ", w)
    return 1 if out["disagree"] or out["ledger_changed"] else 0


if __name__ == "__main__":
    sys.exit(main())
