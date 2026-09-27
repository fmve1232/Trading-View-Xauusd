"""Upcoming economic events for the dashboard -- DISPLAY ONLY.

Nothing in the engine reads this file's output: it is not in `holdout.ENGINE_SOURCES`, the
pipeline does not import it, and the workflow runs it as a separate, non-fatal step. The engine's
own news window (NFP / CPI by rule, `use_news_suppress` default OFF) is unchanged.

Calendar: the Forex Factory weekly calendar JSON (unofficial, no key; fields title, country,
date, impact, forecast, previous; no released "actual"). If it cannot be read, the panel says so
and shows the next NFP estimated by rule (first Friday, 08:30 New York), labelled as an estimate.

Headlines: free public RSS/Atom feeds (Myfxbook calendar-events and news; FXStreet news), kept
only when they mention gold / USD / rates drivers. Each feed fails on its own and reports its
status; URLs can be changed without a code change through the MYFXBOOK_CAL_RSS,
MYFXBOOK_NEWS_RSS and FXSTREET_NEWS_RSS environment variables (repository variables). FXStreet's
economic calendar itself is a paid, OAuth-protected API and is deliberately not used.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from .data import sources

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SOURCE = "Forex Factory weekly calendar (nfs.faireconomy.media)"
KEEP_IMPACT = ("High", "Medium")
NY = ZoneInfo("America/New_York")


FEEDS = (  # (name, env var that overrides the URL, default URL)
    ("Myfxbook calendar", "MYFXBOOK_CAL_RSS", "https://www.myfxbook.com/rss/forex-economic-calendar-events"),
    ("Myfxbook news", "MYFXBOOK_NEWS_RSS", "https://www.myfxbook.com/rss/latest-forex-news"),
    ("FXStreet news", "FXSTREET_NEWS_RSS", "https://www.fxstreet.com/rss/news"),
)
RELEVANT = re.compile(r"\b(gold|xau|bullion|precious metals?|fed|fomc|powell|usd|dollar|dxy|treasur\w*|yields?|"
                      r"cpi|pce|inflation|payrolls?|nfp|jobless|unemployment|jobs|gdp|ism|pmi|retail sales|"
                      r"rate cuts?|rate hikes?|interest rates?|safe[- ]haven)\b", re.I)
US = re.compile(r"(?<![A-Za-z])(US|U\.S\.?)(?![A-Za-z])")     # case-sensitive: "US"/"U.S.", not the pronoun "us"


def relevant(title: str) -> bool:
    return bool(RELEVANT.search(title) or US.search(title))
MAX_FEED_BYTES = 2_000_000
HEADLINES_KEEP = 20


def _txt(el, *tags):
    for t in tags:
        x = el.find(t)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return ""


def parse_feed(raw: bytes, source: str) -> list[dict]:
    """RSS 2.0 or Atom -> [{t, iso, title, link, source}]. Items without a parseable time are dropped."""
    if len(raw) > MAX_FEED_BYTES:
        raise ValueError(f"feed larger than {MAX_FEED_BYTES} bytes")
    if b"<!ENTITY" in raw[:4096].upper():
        raise ValueError("feed declares XML entities; refused")
    root = ET.fromstring(raw)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall("./channel/item") or root.findall(f"{atom}entry") or root.findall(".//item")
    out = []
    for it in items:
        title = re.sub(r"\s+", " ", _txt(it, "title", f"{atom}title"))[:160]
        link = _txt(it, "link")
        if not link:
            le = it.find(f"{atom}link")
            link = le.get("href", "") if le is not None else ""
        if not link.startswith(("https://", "http://")):
            link = ""
        ts = _txt(it, "pubDate", f"{atom}published", f"{atom}updated", "{http://purl.org/dc/elements/1.1/}date")
        try:
            t = parsedate_to_datetime(ts) if "," in ts or ts[:3].isalpha() else datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (TypeError, ValueError, IndexError):
            continue
        if not title or t is None or t.tzinfo is None:
            continue
        t = t.astimezone(timezone.utc)
        out.append({"t": int(t.timestamp()), "iso": t.isoformat(), "title": title, "link": link, "source": source})
    return out


def headlines(fetch_feed=None, now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """All configured feeds -> (relevant headlines of the last 48 h, newest first; per-feed status)."""
    now = now or datetime.now(timezone.utc)
    fetch_feed = fetch_feed or (lambda url: sources._get(url, timeout=20, tries=2).content)
    items, status = [], []
    for name, env, default in FEEDS:
        url = os.environ.get(env, "").strip() or default
        st = {"name": name, "host": re.sub(r"^https?://([^/]+).*$", r"\1", url), "ok": False, "n": 0, "note": ""}
        try:
            got = parse_feed(fetch_feed(url), name)
            keep = [h for h in got if relevant(h["title"]) and now.timestamp() - h["t"] <= 48 * 3600]
            items += keep
            st.update(ok=True, n=len(keep), note=f"{len(keep)} relevant of {len(got)} in the last 48 h")
        except Exception as e:  # noqa: BLE001 -- one feed never breaks another
            st["note"] = sources.redact(f"{type(e).__name__}: {e}")[:160]
        status.append(st)
    seen, uniq = set(), []
    for h in sorted(items, key=lambda h: -h["t"]):
        k = re.sub(r"\W+", "", h["title"].lower())[:60]
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    return uniq[:HEADLINES_KEEP], status


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


def build(now: datetime | None = None, fetch=None, fetch_feed=None) -> dict:
    now = now or datetime.now(timezone.utc)
    fetch = fetch or (lambda: sources._get(FF_URL, timeout=20, tries=2).json())
    doc = {"generated_utc": now.isoformat(), "source": SOURCE, "display_only": True, "ok": False, "note": "", "events": [],
           "headlines": [], "feeds": []}
    try:
        ev = parse_ff(fetch())
        doc["ok"] = True
        doc["events"] = ev
        doc["note"] = f"{len(ev)} USD high/medium-impact events this week"
    except Exception as e:  # noqa: BLE001 -- the panel must degrade, never break the run
        doc["note"] = "calendar unavailable: " + sources.redact(f"{type(e).__name__}: {e}")[:160]
        doc["source"] = "rule-based estimate (calendar unavailable)"
        doc["events"] = [next_nfp(now)]
    doc["headlines"], doc["feeds"] = headlines(fetch_feed, now)
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
    for st in doc["feeds"]:
        print(f"[feed] {st['name']} ({st['host']}): {'OK' if st['ok'] else 'FAILED'} {st['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
