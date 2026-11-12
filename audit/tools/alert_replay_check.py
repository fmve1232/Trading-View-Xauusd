"""Compare two alert replays (audit/tools/alert_replay.py) and check the stale-signal rules on each (read-only).

  python audit/tools/alert_replay_check.py <before.json> <after.json>

Comparison: the phone messages (every line, every run), the final alert state and every record file must be
identical, or each difference is listed.
Rules checked on BOTH outputs, from the records themselves (not from the code under test):
  R1  a plan line ("YOUR PLAN ...") is only sent for a signal whose bar closed at most 60 minutes before the send;
  R2  a plan line for a signal 15-60 minutes old is always in a message that carries a "DELAYED ALERT" line;
  R3  a plan whose decision is NOT ACTIONABLE never has a result line ("... YOUR PLAN <side> from <entry>") on the phone;
  R4  no phone line starts with the RECORD ONLY prefix.
Exit status 1 if a rule is broken in the AFTER output."""
import json
import re
import sys

TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
RECORD_ONLY = "RECORD ONLY"
SEND_DELAY = 300                 # alert_replay.py sends 5 minutes after each step


def _plans(out):
    st = out["state"]
    return [p for p in (st.get("plans") or []) + (st.get("plan_log") or []) if p.get("sl") is not None]


def rules(out):
    bad, n_plan_lines, n_delayed = [], 0, 0
    plans = _plans(out)
    by_sl = {}
    for p in plans:
        by_sl.setdefault(f"{p['sl']:.2f}", []).append(p)
    quiet = {(int(v["t_close"])) for k, v in (out["state"].get("fresh_gate") or {}).items()
             if k.startswith("plan:") and v.get("state") == "NOT ACTIONABLE"}
    quiet_plans = [p for p in plans if int(p["t"]) + TF_SEC.get(p["tf"], 0) in quiet]
    for m in out["phone"]:
        t_send = m["step"] + SEND_DELAY
        lines = m["lines"]
        delayed = any(x.startswith("DELAYED ALERT") for x in lines)
        for x in lines:
            if x.startswith(RECORD_ONLY):
                bad.append(("R4", m["step"], x[:90]))
            if x.startswith("YOUR PLAN"):
                n_plan_lines += 1
                sl = re.search(r"SL ([0-9]+\.[0-9]{2})", x)
                cands = by_sl.get(sl.group(1), []) if sl else []
                ages = [t_send - (int(p["t"]) + TF_SEC.get(p["tf"], 0)) for p in cands]
                ages = [a for a in ages if a >= 0]
                if not ages:
                    bad.append(("UNMATCHED", m["step"], x[:90]))
                    continue
                age = min(ages)
                if age > 3600:
                    bad.append(("R1", m["step"], f"age {age // 60} min: {x[:70]}"))
                elif age > 900:
                    n_delayed += 1
                    if not delayed:
                        bad.append(("R2", m["step"], f"age {age // 60} min without DELAYED: {x[:60]}"))
            for p in quiet_plans:
                side = "BUY" if p["dir"] == 1 else "SELL"
                if x.startswith(f"XAUUSD {p['tf']} YOUR PLAN {side} from {p['entry']:.2f}"):
                    bad.append(("R3", m["step"], x[:90]))
    return {"plan_lines": n_plan_lines, "delayed_plan_lines": n_delayed, "quiet_plans": len(quiet_plans),
            "violations": bad}


def diff(a, b):
    out = []
    pa = {m["step"]: m["lines"] for m in a["phone"]}
    pb = {m["step"]: m["lines"] for m in b["phone"]}
    for s in sorted(set(pa) | set(pb)):
        if pa.get(s) != pb.get(s):
            la, lb = pa.get(s) or [], pb.get(s) or []
            out.append({"step": s, "only_before": [x for x in la if x not in lb], "only_after": [x for x in lb if x not in la]})
    st = [k for k in sorted(set(a["state"]) | set(b["state"])) if a["state"].get(k) != b["state"].get(k)]
    fl = [k for k in sorted(set(a["files"]) | set(b["files"])) if a["files"].get(k) != b["files"].get(k)]
    return {"phone_steps_differing": out, "state_keys_differing": st, "files_differing": fl}


def main():
    a, b = (json.load(open(p)) for p in sys.argv[1:3])
    d = diff(a, b)
    ra, rb = rules(a), rules(b)
    rep = {"runs": len(b["runs"]), "phone_messages": len(b["phone"]), "phone_lines": sum(len(m["lines"]) for m in b["phone"]),
           "identical": not (d["phone_steps_differing"] or d["state_keys_differing"] or d["files_differing"]),
           "diff": d, "rules_before": ra, "rules_after": rb}
    print(json.dumps(rep, indent=1, default=str))
    return 1 if rb["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
