"""Post-deploy shadow audit from the records (for when the site's index.json cannot be fetched).

Reads the market-data store and the forward-ledger checkout after a deployed run, a snapshot of both taken before the
merge, and the run's own log text; uses the deployed code for its constants. Fails (exit 1) on:

  freeze     the production freeze key moved
  b24        with --b24-off: B24 state, or a live record file, exists (the recorder must not have started); a record
             replaced by A2's void tombstone counts as not started, and its void copy must exist
  shadow     the panel's state: a TRADE verdict; a CONFIRMED row outside $15-$20 from its trigger; an overshoot not
             EXPIRED; levels not from the trigger price; the event log reported broken; the deployed code's constants
             (mode SHADOW, all six types NOT VALIDATED, the $20 cap) not in force
  events     CONFIRM-EVENTS.jsonl: chain or anchor broken; a duplicate event id; a CONFIRMED event outside $15-$20;
             the store and ledger copies differ
  untouched  existing records (B9-GRAB-FWD, B15-ENGINE-FWD, SETUP-LIVE): a row present before the merge changed or
             vanished; alerts_state.json gained a key that neither the panel ("confirm"), the recorder ("b24", when
             on) nor the existing alert code (quantum/notify.py) writes
  config     the run log's alert settings differ from the pre-merge run's (ALERT_MODE, ALERT_TFS, PLAN_*, ...); the
             FWD_B24 / CONFIRM_PANEL values in the log are not what was expected; the run's tests did not pass

  python docs/deploy/shadow_store_check.py --store <market-data> --ledger <forward-ledger> --before-store <snapshot>
      --before-ledger <snapshot> --log <run log> --log-before <pre-merge run log> --b24-off
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum import confirm_panel as cp
from quantum import fwd_b24 as fb

FREEZE_KEY = "5e4630924d663fc5:a6f2be58c74887ed"
EPS = 1e-6
SETTINGS = ("ALERT_TFS", "ALERT_MODE", "ALERT_SETUPS", "SETUP_LEVELS", "ALERT_LIQUIDITY", "LIQ_NEAR_USD", "PLAN_LOT", "PLAN_SL_USD",
            "PLAN_TP_USD", "PLAN_TP2_USD", "PLAN_COST_PER_LOT", "PLAN_LATE_FRAC", "MT5_PRICE_OFFSET", "ALERT_LOCAL_TZ")
OUT: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    OUT.append((name, bool(ok), str(detail)))


def jload(p):
    with open(p) as fh:
        return json.load(fh, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"non-strict {x}")))


def env_block(log: str) -> dict:
    """The env block of the 'Run pipeline' step: NAME: value lines after its ##[group]Run python -m quantum.pipeline."""
    i = log.find("Run python -m quantum.pipeline")
    if i < 0:
        return {}
    j = log.find("##[endgroup]", i)
    env = {}
    for ln in log[i:j].splitlines():
        m = re.search(r"Z\s+([A-Z][A-Z0-9_]+):\s?(.*)$", ln)
        if m:
            env[m.group(1)] = m.group(2).strip()
    return env


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    for a in ("--store", "--ledger", "--before-store", "--before-ledger"):
        ap.add_argument(a, required=True)
    ap.add_argument("--log", help="the deployed run's log text (optional: the config checks need it)")
    ap.add_argument("--log-before", help="the pre-merge run's log text")
    ap.add_argument("--b24-off", action="store_true")
    ap.add_argument("--panel-expected", default="", help="the CONFIRM_PANEL value expected in the log ('' = unset = on)")
    a = ap.parse_args(argv)

    key = jload(os.path.join(a.store, "holdout_manifest.json")).get("freeze_key")
    check("freeze: production freeze key unchanged", key == FREEZE_KEY, key)

    st = jload(os.path.join(a.store, "alerts_state.json"))
    st0 = jload(os.path.join(a.before_store, "alerts_state.json"))
    rf, rf_l = os.path.join(a.store, "research_forward"), os.path.join(a.ledger, "research_forward")
    if a.b24_off:
        live, void_ok = [], True
        for d in (rf, rf_l):
            f = os.path.join(d, fb.FILE)
            if os.path.exists(f):
                r = jload(f)
                if r.get("void"):
                    void_ok &= os.path.exists(os.path.join(d, r.get("moved_to", "")))
                else:
                    live.append(d)
        check("b24: not started (no state; no live record in the store or the ledger; a void tombstone keeps its copy)",
              "b24" not in st and not live and void_ok, {"state": "b24" in st, "live_records": live, "void_copies": void_ok})
    with open(os.path.join(os.path.dirname(cp.__file__), "notify.py")) as fh:
        src = fh.read()
    alert_keys = set(re.findall(r'state\[\s*"([A-Za-z0-9_]+)"\s*\]', src)) | set(
        re.findall(r'state\.(?:get|setdefault|pop)\(\s*"([A-Za-z0-9_]+)"', src))
    allowed = {"confirm"} | (set() if a.b24_off else {"b24"}) | alert_keys
    new_keys = set(st) - set(st0)
    check("untouched: the alert state gained only keys the panel, the recorder or the existing alert code write",
          new_keys <= allowed, {"new": sorted(new_keys), "not allowed": sorted(new_keys - allowed)})

    C = st.get("confirm") or {}
    check("shadow: the panel ran (its state exists)", bool(C), sorted(C)[:8])
    rows = (C.get("rows") or []) + (C.get("log") or [])
    bad = []
    for r in rows:
        d, p0 = r["dir"], r["p0"]
        if r.get("verdict") == "TRADE":
            bad.append(f"#{r.get('id')} TRADE")
        if "confirm_at" in r and (abs(r["confirm_at"] - round(p0 + 15 * d, 2)) > EPS or abs(r["invalid_at"] - round(p0 - 13 * d, 2)) > EPS
                                  or abs(r.get("cap_at", float("nan")) - round(p0 + 20 * d, 2)) > EPS):
            bad.append(f"#{r.get('id')} levels")
        if r.get("t_conf") is not None and not (15 - EPS <= r.get("move_usd", -1) <= 20 + EPS):
            bad.append(f"#{r.get('id')} confirmed at {r.get('move_usd')}")
        if r.get("overshoot_usd") is not None and not (r.get("status") == "EXPIRED" and r["overshoot_usd"] > 20):
            bad.append(f"#{r.get('id')} overshoot as {r.get('status')}")
    from collections import Counter
    check("shadow: no TRADE; confirmations $15-$20; overshoots EXPIRED; levels from the trigger price", not bad,
          f"{len(rows)} rows {dict(Counter(r.get('status') for r in rows))}; " + "; ".join(bad[:5]))
    es = C.get("events_status") or {}
    check("events: the panel reports its log intact", es.get("ok") is True, es.get("why"))
    check("shadow: deployed constants (SHADOW mode, six types NOT VALIDATED, $20 cap)",
          len(cp.EVIDENCE) == 6 and not any(v["validated"] for v in cp.EVIDENCE.values()) and cp.CAP_USD == 20.0
          and cp.panel({}, {}, 0)["mode"] == "SHADOW", cp.__file__)

    p, pl = os.path.join(rf, cp.EVENTS_FILE), os.path.join(rf_l, cp.EVENTS_FILE)
    ok, why = cp.verify_events(p, C.get("events_head"))
    check("events: chain and anchor verified from the store's file", ok and os.path.exists(p), why)
    if os.path.exists(p):
        with open(p) as fh:
            ev = [json.loads(x) for x in fh if x.strip()]
        ids = [e["event_id"] for e in ev]
        conf = [e.get("move_usd") for e in ev if e["event"] == "CONFIRMED"]
        check("events: no duplicate event id", len(ids) == len(set(ids)), f"{len(ids)} events")
        check("events: every CONFIRMED event within $15-$20", all(m is not None and 15 - EPS <= m <= 20 + EPS for m in conf),
              f"{len(conf)} confirmed")
        same = False
        if os.path.exists(pl):
            with open(p, "rb") as f1, open(pl, "rb") as f2:
                same = f1.read() == f2.read()
        check("events: the forward-ledger copy equals the store's", same)

    for nm in ("B9-GRAB-FWD.json", "B15-ENGINE-FWD.json", "SETUP-LIVE.json"):
        pb, pa = os.path.join(a.before_store, "research_forward", nm), os.path.join(rf, nm)
        if not os.path.exists(pb):
            continue
        before, after = jload(pb), (jload(pa) if os.path.exists(pa) else None)
        bad = [] if after is not None else ["file missing"]
        for k, v in before.items() if after is not None else []:
            w = after.get(k)
            if isinstance(v, list):                      # an append-only list: what was there must still be there
                if not isinstance(w, list) or w[:len(v)] != v:
                    bad.append(f"{k}: earlier entries changed")
            elif k in ("id", "registration", "rules", "started_utc") and w != v:
                bad.append(f"{k} changed")
        lists = {k: f"{len(v)}->{len(after.get(k) or [])}" for k, v in before.items() if isinstance(v, list)} if after else {}
        check(f"untouched: {nm} (identity unchanged; list entries recorded before the merge unchanged)", not bad, bad or lists)

    if not (a.log and a.log_before):
        print("note: no run logs given; the config checks (settings, FWD_B24 / CONFIRM_PANEL values, test gate) are skipped")
        return finish()
    with open(a.log) as fh:
        log = fh.read()
    with open(a.log_before) as fh:
        log0 = fh.read()
    e, e0 = env_block(log), env_block(log0)
    diff = {k: (e0.get(k), e.get(k)) for k in SETTINGS if e0.get(k) != e.get(k)}
    check("config: alert and plan settings identical to the pre-merge run", not diff and bool(e), diff or f"{len(e)} env lines")
    old = os.environ.get("FWD_B24")
    os.environ["FWD_B24"] = e.get("FWD_B24", "")
    rec_on = fb.on()                                          # the deployed code's own rule for this value
    if old is None:
        os.environ.pop("FWD_B24")
    else:
        os.environ["FWD_B24"] = old
    check("config: the run's FWD_B24 value keeps the recorder " + ("off" if a.b24_off else "on"),
          rec_on is (not a.b24_off), f"FWD_B24={e.get('FWD_B24')!r} -> {'on' if rec_on else 'off'}")
    check("config: CONFIRM_PANEL as expected", e.get("CONFIRM_PANEL", "") == a.panel_expected, repr(e.get("CONFIRM_PANEL")))
    m = re.search(r"(\d+) passed", log)
    check("config: the run's test gate passed", bool(m) and " failed" not in log.split("Run # A failed clone")[0][-2000:],
          m.group(0) if m else "no test summary")
    return finish()


def finish() -> int:
    for name, ok, detail in OUT:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    n = sum(not ok for _, ok, _ in OUT)
    print(f"\n{'SHADOW STORE AUDIT PASSED' if not n else f'SHADOW STORE AUDIT FAILED: {n} check(s)'}")
    return 0 if not n else 1


if __name__ == "__main__":
    sys.exit(main())
