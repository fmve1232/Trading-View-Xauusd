"""Post-deploy check of the two-stage confirmation in SHADOW mode (PR #90 + amendment B24-CONFIRM-FWD-A1).

Fails (exit 1) on anything that would make the shadow deployment more than recording and testing:

  index      the site's index.json parses strictly (no NaN / Infinity)
  shadow     alerts.confirm: mode SHADOW; headline NO TRADE; the $20 cap and amendment A1 in force; every trigger type
             NOT VALIDATED; no row's verdict is TRADE; nothing in the block is a phone send
  rule       every CONFIRMED row's move from the trigger price is $15.00-$20.00; every overshoot is EXPIRED beyond $20;
             every row's levels come from its trigger price (confirm at +$15, cap at +$20, invalid at -$13)
  events     the event log's chain and anchor status as the panel reported it; with --ledger, the chain re-verified
             from the file and every CONFIRMED event's move within $15-$20
  freeze     with --store, holdout_manifest.json still carries the production freeze key
  b24        with --ledger, B24-CONFIRM-FWD.json: no confirmed row beyond the cap, overshoots EXPIRED, DATA GAP never decided

  python docs/deploy/shadow_check.py --index <index.json path or URL> [--store <market-data checkout>]
                                     [--ledger <forward-ledger checkout>] [--panel-off] [--b24-off]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum import confirm_panel as cp

FREEZE_KEY = "5e4630924d663fc5:a6f2be58c74887ed"
EPS = 1e-6
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))


def _strict(text: str):
    def bad(x):
        raise ValueError(f"non-strict JSON constant {x}")
    return json.loads(text, parse_constant=bad)


def load_index(src: str) -> dict:
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=30) as r:
            text = r.read().decode()
    else:
        with open(src) as fh:
            text = fh.read()
    return _strict(text)


def check_panel(C: dict) -> None:
    rows = C.get("rows") or []
    check("shadow: mode is SHADOW", C.get("mode") == "SHADOW", str(C.get("mode")))
    check("shadow: headline NO TRADE", C.get("headline") == cp.NO_TRADE, str(C.get("headline")))
    check("shadow: amendment A1 in force ($20 cap)", C.get("cap_usd") == 20.0 and "B24-CONFIRM-FWD-A1" in str(C.get("rule")),
          f"cap {C.get('cap_usd')}")
    ev = C.get("evidence") or {}
    check("shadow: all six trigger types NOT VALIDATED", len(ev) == 6 and not any(v.get("validated") for v in ev.values()),
          ", ".join(f"{k}={v.get('validated')}" for k, v in ev.items()))
    check("shadow: no row is TRADE", all(r.get("verdict") != "TRADE" for r in rows), f"{len(rows)} rows")
    check("shadow: the panel carries no phone send", "sent" not in C and all("sent" not in r for r in rows))
    bad = []
    for r in rows:
        d, p0 = r["dir"], r["p0"]
        if abs(r["confirm_at"] - round(p0 + 15 * d, 2)) > EPS or abs(r["invalid_at"] - round(p0 - 13 * d, 2)) > EPS \
                or abs(r.get("cap_at", math.nan) - round(p0 + 20 * d, 2)) > EPS:
            bad.append(f"#{r.get('id')} levels")
        if r.get("status") == "CONFIRMED" and not (15 - EPS <= r.get("move_usd", -1) <= 20 + EPS):
            bad.append(f"#{r.get('id')} confirmed at {r.get('move_usd')}")
        if r.get("overshoot_usd") is not None and not (r.get("status") == "EXPIRED" and r["overshoot_usd"] > 20):
            bad.append(f"#{r.get('id')} overshoot {r['overshoot_usd']} as {r.get('status')}")
    check("rule: levels from the trigger price; confirmations $15-$20; overshoots EXPIRED", not bad, "; ".join(bad[:5]))
    e = C.get("events") or {}
    check("events: the panel reports the log intact", e.get("ok") is True, str(e.get("why")))


def check_ledger(ledger: str, b24_on: bool, panel_on: bool) -> None:
    rf = os.path.join(ledger, "research_forward")
    p = os.path.join(rf, cp.EVENTS_FILE)
    if panel_on:
        ok, why = cp.verify_events(p)
        check("events: chain re-verified from the file", ok and os.path.exists(p), why)
        moves = []
        if os.path.exists(p):
            with open(p) as fh:
                moves = [json.loads(x).get("move_usd") for x in fh if '"event": "CONFIRMED"' in x]
        check("events: every CONFIRMED event within $15-$20", all(m is not None and 15 - EPS <= m <= 20 + EPS for m in moves),
              f"{len(moves)} confirmed events")
    b = os.path.join(rf, "B24-CONFIRM-FWD.json")
    if b24_on:
        check("b24: record file present", os.path.exists(b))
        if os.path.exists(b):
            with open(b) as fh:
                rec = _strict(fh.read())
            rows = rec.get("rows", [])
            conf_bad = [r.get("id") for r in rows if r.get("stage") == "CONFIRMED"
                        and not (15 - EPS <= (r["A"]["px"] - r["p0"]) * r["dir"] <= 20 + EPS)]
            over_bad = [r.get("id") for r in rows if r.get("why") == "overshoot" and r.get("stage") != "EXPIRED"]
            gap_bad = [r.get("id") for r in rows if r.get("stage") == "DATA GAP" and r.get("res")]
            check("b24: confirmations within $15-$20, overshoots EXPIRED, DATA GAP undecided",
                  not conf_bad and not over_bad and not gap_bad, f"{len(rows)} rows; bad {conf_bad + over_bad + gap_bad}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--store")
    ap.add_argument("--ledger")
    ap.add_argument("--panel-off", action="store_true", help="CONFIRM_PANEL=0 is set: the block must be absent")
    ap.add_argument("--b24-off", action="store_true", help="FWD_B24=0 is set: the recorder must be absent")
    a = ap.parse_args(argv)
    try:
        ix = load_index(a.index)
        check("index: index.json parses strictly", True)
    except Exception as e:  # noqa: BLE001
        check("index: index.json parses strictly", False, f"{type(e).__name__}: {e}")
        ix = {}
    al = ix.get("alerts") or {}
    if a.panel_off:
        check("switch: panel absent with CONFIRM_PANEL=0", "confirm" not in al)
    else:
        check("shadow: the confirmation block is present", isinstance(al.get("confirm"), dict) and not al["confirm"].get("error"),
              str((al.get("confirm") or {}).get("error")))
        if isinstance(al.get("confirm"), dict) and not al["confirm"].get("error"):
            check_panel(al["confirm"])
    if a.b24_off:
        check("switch: recorder absent with FWD_B24=0", "b24" not in al)
    elif "b24" in al:
        check("b24: recorder ran without error", not al["b24"].get("error"), str(al["b24"].get("error")))
    if a.store:
        with open(os.path.join(a.store, "holdout_manifest.json")) as fh:
            key = json.load(fh).get("freeze_key")
        check("freeze: production freeze key unchanged", key == FREEZE_KEY, str(key))
    if a.ledger:
        check_ledger(a.ledger, not a.b24_off, not a.panel_off)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    n_bad = sum(not ok for _, ok, _ in RESULTS)
    print(f"\n{'SHADOW CHECK PASSED' if not n_bad else f'SHADOW CHECK FAILED: {n_bad} check(s)'}")
    return 0 if not n_bad else 1


if __name__ == "__main__":
    sys.exit(main())
