"""Amendment B24-CONFIRM-FWD-A1 on real data: the same live setups under the original rule (no cap) and the capped rule.

Runs the confirmation panel (quantum/confirm_panel.py) over every trigger on the site's charts (the whole 15m chart, not
just the 3-day display window), twice: with the $20 cap (the live rule) and with the cap lifted (the original B19 rule,
CAP_USD = infinity, everything else identical). Reports the funnel (confirmed / invalidated by price or structure /
expired by window or overshoot / pending / unresolved), the outcomes the panel itself computes (+$15 and +$20 before
-$13 on 15m bars from the confirming close; $ per oz before costs and after the operator's $0.26), the per-setup
transitions, and what the cap removed. Descriptive only: one window of a few weeks, overlapping triggers of six types on
the same moves, and the window whose move distribution prompted the operator's decision. It selects nothing: the cap was
decided before these outcomes were computed. Price-free output (counts, $ moves and P&L per oz; no price levels).

  python research/tools/cf_cap_realdata.py <site data dir with 15m/30m/1h/4h/5m.json> \
      --out research/results/cf_cap_realdata_2026-11-10.json --md research/B24_A1_REALDATA.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum import confirm_panel as cp
from quantum.research import harness as H

TFS = ("15m", "30m", "1h", "4h", "5m")


def run(pl: dict, cap: float) -> list[dict]:
    old = cp.CAP_USD
    cp.CAP_USD = cap
    try:
        t = pl["15m"]["chart"]["t"]
        st = {"confirm": {"started": int(t[0])}}           # not a first run: every trigger on the chart gets a row
        cp.panel(pl, st, int(t[-1]) + 1200, store_dir=tempfile.mkdtemp())
        return st["confirm"]["rows"] + st["confirm"]["log"]
    finally:
        cp.CAP_USD = old


def summary(rows: list[dict]) -> dict:
    f = {"setups": len(rows), "BUY": sum(r["dir"] > 0 for r in rows), "SELL": sum(r["dir"] < 0 for r in rows), "confirmed": 0,
         "invalidated_price": 0, "invalidated_structure": 0, "expired_window": 0, "expired_overshoot": 0, "pending": 0, "stale": 0}
    o = {T: {"TP": 0, "SL": 0, "AMBIGUOUS": 0, "TIMEOUT": 0, "OPEN": 0, "_usd": []} for T in ("T15", "T20")}
    for r in rows:
        st = r["status"]
        if st == "CONFIRMED":
            f["confirmed"] += 1
            for T, v in o.items():
                x = (r.get("result") or {}).get(T) or {}
                out = x.get("out") or "OPEN"
                v[out] += 1
                if out != "OPEN" and x.get("usd") is not None:
                    v["_usd"].append(float(x["usd"]))
        elif st == "INVALIDATED":
            f["invalidated_price" if "against" in (r.get("why") or "") else "invalidated_structure"] += 1
        elif st == "EXPIRED":
            f["expired_overshoot" if r.get("overshoot_usd") is not None else "expired_window"] += 1
        elif st in ("PENDING", "STALE"):
            f[st.lower()] += 1
    for T, v in o.items():
        u = v.pop("_usd")
        dec = v["TP"] + v["SL"] + v["AMBIGUOUS"] + v["TIMEOUT"]
        lo, hi = H.wilson(v["TP"], dec) if dec else (None, None)
        v.update(decided=dec, tp_rate=v["TP"] / dec if dec else None, tp_rate_ci95=[lo, hi],
                 usd_per_oz_mean=sum(u) / len(u) if u else None,
                 usd_per_oz_after_026=(sum(u) / len(u) - cp.OP_COST) if u else None)
    f["unresolved"] = f["pending"] + o["T15"]["OPEN"]
    return {"funnel": f, "outcomes": o}


def compare(pl: dict) -> dict:
    a, b = run(pl, math.inf), run(pl, cp.CAP_USD)
    ka, kb = {r["key"]: r for r in a}, {r["key"]: r for r in b}
    assert set(ka) == set(kb), "both rules must see the same setups"
    trans: dict = {}
    for k in ka:
        key = f"{ka[k]['status']} -> {kb[k]['status']}"
        trans[key] = trans.get(key, 0) + 1
    removed = [ka[k] for k in ka if ka[k]["status"] == "CONFIRMED" and kb[k]["status"] != "CONFIRMED"]
    kept = [k for k in ka if ka[k]["status"] == kb[k]["status"] == "CONFIRMED"]
    c15 = pl["15m"]["chart"]
    return {"tool": "research/tools/cf_cap_realdata.py", "amendment": "research/registrations/B24-CONFIRM-FWD-A1.json",
            "chart_utc": [int(c15["t"][0]), int(c15["t"][-1])],
            "data_source": (pl["15m"].get("meta") or {}).get("price_source"),
            "data_hash_15m": hashlib.sha256(json.dumps([c15["t"], c15["o"], c15["h"], c15["l"], c15["c"]]).encode()).hexdigest()[:16],
            "triggers_scanned": len(cp.scan(pl)), "original_no_cap": summary(a), "capped_live_rule": summary(b),
            "transitions": dict(sorted(trans.items())),
            "removed_by_cap": {**summary(removed), "overshoot_usd": sorted(kb[r["key"]]["overshoot_usd"] for r in removed)},
            "kept_confirmations": len(kept),
            "kept_confirmations_identical": all(ka[k]["entry"] == kb[k]["entry"] and ka[k]["result"] == kb[k]["result"] for k in kept),
            "caveat": ("descriptive: one window, overlapping triggers of six types on the same moves, and the window whose move "
                       "distribution prompted the cap; no rule is selected from it; no trigger type is validated")}


def _pc(x) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def _usd(x) -> str:
    return "—" if x is None else f"{x:+.2f}"


def markdown(res: dict) -> str:
    """The write-up, generated from the JSON (no figure typed by hand)."""
    from datetime import UTC, datetime

    d0, d1 = (datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M") for t in res["chart_utc"])
    L = ["# Amendment A1 ($15-$20 confirmation cap): the same real setups under both rules", "",
         (f"Generated by `{res['tool']}` from `research/results/cf_cap_realdata_2026-11-10.json`. Amendment: "
         f"`{res['amendment']}`. Data: the site's {res['data_source']} charts, 15m bars {d0} to {d1} UTC (hash "
         f"`{res['data_hash_15m']}`); {res['triggers_scanned']} triggers of six types, folded to one per idea."), "",
         "**Descriptive only. Not evidence of an edge and not a validation.** One window of about three weeks;",
         "the six trigger types overlap on the same moves, so the setups are not independent; and this is the window whose",
         "move distribution prompted the operator's decision. The cap was decided before these outcomes were computed, and",
         "nothing here selects a rule. Every trigger type stays NOT VALIDATED; the registered B24 forward test decides.", "",
         "| | Original rule (no cap) | Capped (live rule, A1) | Removed by the cap |", "|---|---|---|---|"]
    a, b, r = res["original_no_cap"], res["capped_live_rule"], res["removed_by_cap"]
    for nm, key in (("Setups", "setups"), ("BUY / SELL", None), ("Confirmed", "confirmed"),
                    ("Invalidated: price -$13", "invalidated_price"), ("Invalidated: opposite structure", "invalidated_structure"),
                    ("Expired: no close in 96 bars", "expired_window"), ("Expired: overshoot beyond $20", "expired_overshoot"),
                    ("Pending", "pending"), ("Unresolved (pending or an exit still open)", "unresolved")):
        if key is None:
            L.append(f"| {nm} | {a['funnel']['BUY']} / {a['funnel']['SELL']} | {b['funnel']['BUY']} / {b['funnel']['SELL']} | "
                     f"{r['funnel']['BUY']} / {r['funnel']['SELL']} |")
        else:
            L.append(f"| {nm} | {a['funnel'][key]} | {b['funnel'][key]} | {r['funnel'][key] if key in ('setups', 'confirmed') else '—'} |")
    for T, lab in (("T15", "+$15"), ("T20", "+$20")):
        oa, ob, orr = a["outcomes"][T], b["outcomes"][T], r["outcomes"][T]

        def cell(o):
            lo, hi = o["tp_rate_ci95"]
            return (f"{o['TP']} of {o['decided']} = {_pc(o['tp_rate'])} (95% {_pc(lo)}-{_pc(hi)})" if o["decided"] else "—")
        L.append(f"| {lab} before -$13, target first | {cell(oa)} | {cell(ob)} | {cell(orr)} |")
        L.append(f"| {lab}: $ per oz per trade, before / after $0.26 | {_usd(oa['usd_per_oz_mean'])} / {_usd(oa['usd_per_oz_after_026'])} "
                 f"| {_usd(ob['usd_per_oz_mean'])} / {_usd(ob['usd_per_oz_after_026'])} | {_usd(orr['usd_per_oz_mean'])} / "
                 f"{_usd(orr['usd_per_oz_after_026'])} |")
    be = cp.break_even(15.0)
    where = {nm: (o["outcomes"]["T15"]["tp_rate_ci95"]) for nm, o in (("original rule", a), ("capped rule", b), ("removed trades", r))}
    has = [nm for nm, (lo, hi) in where.items() if lo is not None and lo <= be <= hi]
    below = [nm for nm, (lo, hi) in where.items() if hi is not None and hi < be]
    inc = (f"The +$15 interval includes it for: {', '.join(has) or 'none'}"
           + (f"; it lies entirely below it for: {', '.join(below)}" if below else "") + ".")
    L += ["", "Transitions, setup by setup (original -> capped): " + "; ".join(f"{k}: {v}" for k, v in res["transitions"].items()) + ".",
          (f"The {res['kept_confirmations']} confirmations both rules share are identical (same entry, same exits): "
          f"{res['kept_confirmations_identical']}. The cap only removes; it never adds or changes a trade."), "",
          "Moves of the removed confirmations at their first $15+ close ($ beyond the trigger price): "
          + ", ".join(f"{x:.2f}" for x in r["overshoot_usd"]) + ".", "",
          (f"Break-even for +$15 before -$13 is {be:.1%} at the operator's $0.26 and about 49% at the research model's cost. "
           f"{inc}"),
          "Outcomes are the panel's own: entry at the confirming 15m close, exits on 15m bars (a",
          "gap fills at the open, a bar touching both levels counts as the stop), P&L in $ of price per oz. The site shows a",
          "confirmation 3-66 minutes after the close, so a person's fill differs; B24 records that executable price.", "",
          "The capped rule on the 2020-22, 2023-24 and 2026 history: `research/CF_VALIDATION.md`.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", help="also write the write-up here")
    ap.add_argument("--from-json", action="store_true", help="only regenerate --md from an existing --out")
    a = ap.parse_args(argv)
    if a.from_json:
        with open(a.out) as fh:
            res = json.load(fh)
        with open(a.md, "w") as fh:
            fh.write(markdown(res))
        print(f"written {a.md}")
        return 0
    pl = {}
    for tf in TFS:
        with open(os.path.join(a.data, f"{tf}.json")) as fh:
            pl[tf] = json.load(fh)
    res = compare(pl)
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1)
    if a.md:
        with open(a.md, "w") as fh:
            fh.write(markdown(res))
    f0, f1 = res["original_no_cap"]["funnel"], res["capped_live_rule"]["funnel"]
    print(f"{f0['setups']} setups: confirmed {f0['confirmed']} -> {f1['confirmed']} (overshoot {f1['expired_overshoot']}); "
          f"written {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
