"""Dated NFP / CPI / FOMC calendar — DISPLAY ONLY (ported from the Pine line, Visuals v86 / v92).

Release times in New York: BLS Employment Situation (NFP) and CPI at 08:30; the FOMC statement at 14:00 on the second
meeting day. The dates are as published by the BLS and the Federal Reserve on 2026-10-22, and are copied verbatim from
the Pine line's Visuals (`nwCode`, checked there against the official lists by `v86_check.py`). FOMC dates are
tentative until the meeting before. The list ends 2027-12-10 and must be extended before then.

Used by the site's Risk & sizing card (the news-time cost multiplier, v92 B-03), the "Next release" check and the
news-window alert. It is NOT in `holdout.ENGINE_SOURCES`. The engine's own news window is a different, date-guessing
rule (F-A74); it stays unchanged, and so does every forward-test record.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SOURCE = "BLS and Federal Reserve schedules as published 2026-10-22 (Pine Visuals v86 / v92 list)"
VALID_UNTIL = "2027-12-10"
BEFORE_MIN, AFTER_MIN = 30, 30          # Pine defaults nwBefore / nwAfter
COST_MULT = 3.0                         # Pine nwCostMult: spread + slippage x 3 inside a window; commission unchanged

# yyyymmddhhmm, New York time, in date order (Pine nwCode / nwName, verbatim)
_CODES = (202610281400, 202611060830, 202611100830, 202612040830, 202612091400, 202612100830, 202701080830,
          202701130830, 202701271400, 202702050830, 202702110830, 202703050830, 202703100830, 202703171400,
          202704020830, 202704130830, 202704281400, 202705070830, 202705120830, 202706040830, 202706091400,
          202706100830, 202707020830, 202707140830, 202707281400, 202708060830, 202708110830, 202709030830,
          202709140830, 202709151400, 202710080830, 202710140830, 202710271400, 202711050830, 202711100830,
          202712030830, 202712081400, 202712100830)
_NAMES = ("FOMC", "NFP", "CPI", "NFP", "FOMC", "CPI", "NFP", "CPI", "FOMC", "NFP", "CPI", "NFP", "CPI", "FOMC",
          "NFP", "CPI", "FOMC", "NFP", "CPI", "NFP", "FOMC", "CPI", "NFP", "CPI", "FOMC", "NFP", "CPI", "NFP",
          "CPI", "FOMC", "NFP", "CPI", "FOMC", "NFP", "CPI", "NFP", "FOMC", "CPI")


def events() -> list[dict]:
    """[{t: epoch seconds UTC, name, ny: 'YYYY-MM-DD HH:MM'}], in time order."""
    out = []
    for c, nm in zip(_CODES, _NAMES, strict=True):
        y, mo, d, hh, mi = c // 10**8, c // 10**6 % 100, c // 10**4 % 100, c // 100 % 100, c % 100
        dt = datetime(y, mo, d, hh, mi, tzinfo=NY)
        out.append({"t": int(dt.timestamp()), "name": nm, "ny": dt.strftime("%Y-%m-%d %H:%M")})
    return out


def state(t: int, before_min: int = BEFORE_MIN, after_min: int = AFTER_MIN) -> dict:
    """At epoch t: the window t is in (if any) and the next release still ahead (Pine nwI / nwBarIn, for one instant)."""
    cur = nxt = None
    for e in events():
        if e["t"] - before_min * 60 <= t <= e["t"] + after_min * 60 and cur is None:
            cur = e
        if e["t"] > t and nxt is None:
            nxt = e
    return {"in_window": cur, "next": nxt, "expired": nxt is None}


def export() -> dict:
    return {"events": events(), "before_min": BEFORE_MIN, "after_min": AFTER_MIN, "cost_mult": COST_MULT,
            "source": SOURCE, "valid_until": VALID_UNTIL}


def now_utc() -> int:
    return int(datetime.now(timezone.utc).timestamp())
