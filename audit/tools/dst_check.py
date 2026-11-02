#!/usr/bin/env python3
"""The session engine's DST tracker, fast (v99; v90 mutation gap m05 outside the 25-minute tf_check).

tf_check 4 runs the whole session engine on every timeframe (~25 min), so the fast suite had no behavioural DST test:
v90 mutant m05 (US DST starting on the FIRST Sunday of March) was tripwire-only there. This runs the Master's DST block
(`hourUTC = hour(time, "UTC")` ... `bool euIsDST = `) AS WRITTEN with its `var` state on every 1H trading bar of
2020-2027 (session from Sunday 17:00 New York to Friday 17:00) and compares usIsDST / euIsDST with the IANA zones
(America/New_York, Europe/London) bar by bar. The switches fall on Sunday mornings, when gold is closed, so the
tracker's UTC-date rule is exact on trading bars. Every engine copy with an identical block is covered by
diag_parity / tf_check; Visuals' own tracker by tf_check 6.
Positive controls: m05 (US start on the 1st Sunday), US end on the 2nd Sunday, EU start on the 25th (the pre-v63 rule).
Usage: python3 audit/tools/dst_check.py"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

NY, LDN, UTC = ZoneInfo("America/New_York"), ZoneInfo("Europe/London"), dt.timezone.utc
M = open("artefacts/XAUUSD_Quantum_5_0_Master.pine", encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


P.BUILTINS.update({
    "hour": lambda t, tz=None: float(dt.datetime.fromtimestamp(t / 1000, UTC).hour),
    "dayofmonth": lambda t, tz=None: float(dt.datetime.fromtimestamp(t / 1000, UTC).day),
    "month": lambda t, tz=None: float(dt.datetime.fromtimestamp(t / 1000, UTC).month),
    "year": lambda t, tz=None: float(dt.datetime.fromtimestamp(t / 1000, UTC).year),
    "dayofweek": lambda t, tz=None: float(dt.datetime.fromtimestamp(t / 1000, UTC).isoweekday() % 7 + 1),
    "int": lambda x: P.NA if P.isna(x) else int(x)})

a = next(i for i, l in enumerate(M) if l.startswith('hourUTC = hour(time, "UTC")'))
b = next(i for i, l in enumerate(M) if l.startswith("bool euIsDST = "))
BLOCK = [l for l in M[a:b + 1] if l.strip() and not l.lstrip().startswith("//")]


def opens():
    out, d = [], dt.datetime(2020, 1, 1, tzinfo=NY)
    while d.year <= 2027:
        if d.weekday() < 5:
            t = dt.datetime(d.year, d.month, d.day, 17, tzinfo=NY) - dt.timedelta(days=1)
            e = dt.datetime(d.year, d.month, d.day, 17, tzinfo=NY)
            while t < e:
                out.append(t.astimezone(UTC))
                t += dt.timedelta(hours=1)
        d += dt.timedelta(days=1)
    return out


OPENS = opens()


def run(block):
    first = [l[4:] if l.startswith("var ") else l for l in block]
    later = [l for l in block if not l.startswith("var ")]
    env = P.Env()
    us = eu = 0
    for n, t in enumerate(OPENS):
        env["time"] = t.timestamp() * 1000.0
        P.run(first if n == 0 else later, env)
        us += bool(env["usIsDST"]) != bool(t.astimezone(NY).dst())
        eu += bool(env["euIsDST"]) != bool(t.astimezone(LDN).dst())
    return us, eu


if __name__ == "__main__":
    us, eu = run(BLOCK)
    report(us == 0 and eu == 0, f"Master DST tracker vs IANA on {len(OPENS)} 1H trading bars 2020-2027 (16 US and 16 EU "
           f"changes): US wrong on {us}, EU wrong on {eu}")
    for name, o, n in (("m05 US DST from the 1st Sunday of March", "usDstStartDom := _firstSunDom + 7", "usDstStartDom := _firstSunDom"),
                       ("US DST ends on the 2nd Sunday of November", "usDstEndDom := _firstSunDom", "usDstEndDom := _firstSunDom + 7"),
                       ("EU DST from the 25th (the pre-v63 rule)", "euDstStartDom := 31 - ((_dow - 1 + 31 - _dom) % 7)", "euDstStartDom := 25")):
        hits = [i for i, l in enumerate(BLOCK) if l.strip().startswith(o)]
        assert len(hits) == 1, (name, len(hits))
        mb = list(BLOCK)
        mb[hits[0]] = mb[hits[0]].replace(o, n)
        u, e = run(mb)
        report(u + e > 0, f"control {name}: detected (US {u}, EU {e} bars wrong)")
    print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- the Master's DST block executed in Python; TradingView runtime NOT exercised")
    sys.exit(1 if fails else 0)
