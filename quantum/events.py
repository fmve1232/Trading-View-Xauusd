"""Upcoming economic events for the dashboard -- DISPLAY ONLY.

Nothing in the engine reads this file's output: it is not in `holdout.ENGINE_SOURCES`, the
pipeline does not import it, and the workflow runs it as a separate, non-fatal step. The engine's
own news window (NFP / CPI by rule, `use_news_suppress` default OFF) is unchanged.

Source: the Forex Factory weekly calendar JSON (unofficial, no key; fields title, country, date,
impact, forecast, previous; no released "actual"). If it cannot be read, the panel says so and
shows the next NFP estimated by rule (first Friday, 08:30 New York), labelled as an estimate.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .data import sources

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SOURCE = "Forex Factory weekly calendar (nfs.faireconomy.media)"
KEEP_IMPACT = ("High", "Medium")
NY = ZoneInfo("America/New_York")


def parse_ff(rows: list, country: str = "USD") -> list[dict]:
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("country") != country or r.get("impact") not in KEEP_IMPACT:
            continue
        try:
            t = datetime.fromisoformat(str(r["date"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if t.tzinfo is None:          # a naive time is ambiguous: skip rather than guess its zone
            continue
        t = t.astimezone(timezone.utc)
        out.append({"t": int(t.timestamp()), "iso": t.isoformat(), "title": str(r.get("title", ""))[:80],
                    "country": country, "impact": r["impact"], "forecast": str(r.get("forecast") or "")[:20],
                    "previous": str(r.get("previous") or "")[:20], "estimated": False})
    out.sort(key=lambda e: e["t"])
    return out


def next_nfp(now: datetime) -> dict:
    """First Friday of the month, 08:30 New York: the rule the engine's news window also uses."""
    ny_now = now.astimezone(NY)
    y, m = ny_now.year, ny_now.month
    for _ in range(3):
        d = datetime(y, m, 1, 8, 30, tzinfo=NY)
        d += timedelta(days=(4 - d.weekday()) % 7)
        if d > ny_now:
            t = d.astimezone(timezone.utc)
            return {"t": int(t.timestamp()), "iso": t.isoformat(), "title": "Non-Farm Payrolls (estimated: first Friday)",
                    "country": "USD", "impact": "High", "forecast": "", "previous": "", "estimated": True}
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    raise AssertionError("unreachable")


def build(now: datetime | None = None, fetch=None) -> dict:
    now = now or datetime.now(timezone.utc)
    fetch = fetch or (lambda: sources._get(FF_URL, timeout=20, tries=2).json())
    doc = {"generated_utc": now.isoformat(), "source": SOURCE, "display_only": True, "ok": False, "note": "", "events": []}
    try:
        ev = parse_ff(fetch())
        doc["ok"] = True
        doc["events"] = ev
        doc["note"] = f"{len(ev)} USD high/medium-impact events this week"
    except Exception as e:  # noqa: BLE001 -- the panel must degrade, never break the run
        doc["note"] = "calendar unavailable: " + sources.redact(f"{type(e).__name__}: {e}")[:160]
        doc["source"] = "rule-based estimate (calendar unavailable)"
        doc["events"] = [next_nfp(now)]
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data/events.json")
    a = ap.parse_args(argv)
    doc = build()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"[events] ok={doc['ok']} n={len(doc['events'])} {doc['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
