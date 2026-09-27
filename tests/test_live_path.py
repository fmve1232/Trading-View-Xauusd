"""The live download/assembly path, with the network replaced by fakes shaped like the real
responses (Yahoo intraday = bar-open timestamps, Yahoo daily = midnight trade dates, FRED =
observation dates, CFTC = release-time index). Catches assembly bugs before the first real run."""
import numpy as np
import pandas as pd
import pytest

from quantum import pipeline
from quantum.data import market as mk
from quantum.data import sources


END = pd.Timestamp("2026-09-24 20:00", tz="UTC")


def _bars(start, periods, freq, px, seed):
    idx = mk._trading_index(start, periods, freq)
    idx = idx[idx <= END]
    return mk._gbm(idx, px, 0.001, np.random.default_rng(seed))


@pytest.fixture
def fake_net(monkeypatch):
    cache = {}

    def yahoo(symbol, interval, rng):
        if symbol == "XAUUSD=X":
            raise sources.FetchError("yahoo XAUUSD=X: no bars")      # spot unavailable -> futures fallback
        key = (symbol, interval)
        if key not in cache:
            base = {"GC=F": 2650.0, "SI=F": 31.0, "DX-Y.NYB": 104.0, "^TNX": 4.3, "EURUSD=X": 1.08, "^GSPC": 5900.0, "^VIX": 16.0}[symbol]
            seed = abs(hash(key)) % 1000
            if interval == "1d":
                d = _bars("2023-01-02", 1400, "1D", base, seed)
                d.index = d.index.normalize()
                d = d[d.index.dayofweek < 5]
            elif interval == "60m":
                d = _bars("2025-06-01", 12000, "60min", base, seed)
            else:
                mins = int(interval[:-1])
                d = _bars("2026-07-27", int(60 * 24 * 60 / mins), f"{mins}min", base, seed)
            cache[key] = d
        return cache[key]

    def fred(sid):
        idx = pd.date_range("2024-01-01", "2026-09-01", freq="B", tz="UTC")
        return pd.Series(np.linspace(4.5, 3.8, len(idx)), index=idx)

    def cot():
        rel = pd.date_range("2024-01-05", "2026-09-25", freq="W-FRI", tz="UTC") + pd.Timedelta(hours=19, minutes=30)
        n = len(rel)
        return pd.DataFrame({"nc_long": np.linspace(2e5, 3e5, n), "nc_short": np.linspace(8e4, 5e4, n),
                             "open_interest": 4.5e5 + np.sin(np.arange(n)) * 1e4,
                             "asof": (rel - pd.Timedelta(days=3)).tz_localize(None).normalize()}, index=rel)

    monkeypatch.setattr(sources, "yahoo", yahoo)
    monkeypatch.setattr(sources, "fred", fred)
    monkeypatch.setattr(sources, "cftc_gold_cot", cot)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)


def test_live_pipeline_offline(fake_net, tmp_path):
    out, store = tmp_path / "out", tmp_path / "store"
    rc = pipeline.main(["--out", str(out), "--store", str(store), "--tfs", "15m,4h"])
    assert rc == 0
    import json
    ix = json.loads((out / "index.json").read_text())
    assert not ix["errors"], ix["errors"]
    p = json.loads((out / "15m.json").read_text())
    assert p["meta"]["price_source"] == "yahoo:GC=F" and not p["meta"]["synthetic"]
    st = {s["name"]: s for s in p["data_status"]}
    assert st["GC=F_15m"]["ok"] and not st["XAUUSD=X_15m"]["ok"]
    assert p["macro"]["gc"]["enabled"] is False            # price IS futures: confirmation layer off
    assert p["macro"]["DXY"]["valid"] and p["macro"]["cot"]["valid"]
    assert (store / "holdout_manifest.json").exists()
    assert any(d.name.startswith("GC_F_15m") for d in store.iterdir())
    # a second run merges into the store instead of duplicating it
    assert pipeline.main(["--out", str(out), "--store", str(store), "--tfs", "15m"]) == 0
    df = mk.store.load(str(store), "GC=F_15m")
    assert df.index.is_unique


def test_market_closed_bars_are_dropped():
    idx = pd.date_range("2026-09-25 18:00", "2026-09-27 23:00", freq="1h", tz="UTC")   # Fri 14:00 NY .. Sun 19:00 NY
    df = pd.DataFrame({c: 1.0 for c in sources.COLS}, index=idx)
    kept = sources.trading_week_only(df).index.tz_convert("America/New_York")
    assert kept.min().hour == 14 and kept.min().dayofweek == 4           # Friday before 17:00 kept
    assert not ((kept.dayofweek == 5).any())                             # no Saturday
    assert ((kept.dayofweek == 6) & (kept.hour < 17)).sum() == 0          # Sunday only from 17:00
    assert ((kept.dayofweek == 6) & (kept.hour >= 17)).sum() == 3
    d = pd.DataFrame({c: 1.0 for c in sources.COLS}, index=pd.date_range("2026-09-21", periods=7, freq="D", tz="UTC"))
    assert list(sources.trading_week_only(d, daily=True).index.dayofweek) == [0, 1, 2, 3, 4]


def test_4h_grid_stays_on_17h_new_york_across_dst():
    idx = pd.date_range("2026-02-20", "2026-04-10", freq="1h", tz="UTC")   # spans the 2026-03-08 US DST change
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
    r = sources.resample_ny_session(df, 4)
    assert sorted(set(r.index.tz_convert("America/New_York").hour)) == [1, 5, 9, 13, 17, 21]
    later = sources.resample_ny_session(df[df.index >= "2026-03-20"], 4)   # starts after the change
    common = r.index.intersection(later.index)
    assert len(common) == len(later)                                     # same grid whatever the start date


def test_api_key_never_reaches_published_errors(monkeypatch):
    """A requests network error quotes the full URL; the key must not survive into status notes."""
    from quantum.data import sources
    secret = "abcdef0123456789abcdef0123456789"
    monkeypatch.setenv("TWELVEDATA_API_KEY", secret)
    raw = ("ConnectionError: HTTPSConnectionPool(host='api.twelvedata.com', port=443): Max retries "
           f"exceeded with url: /time_series?symbol=XAU%2FUSD&interval=1h&apikey={secret}&order=ASC")
    out = sources.redact(raw)
    assert secret not in out and "apikey=***" in out and "symbol=XAU%2FUSD" in out
    assert secret not in sources.redact(f"bare {secret} in text")
    monkeypatch.setattr(sources, "requests", type("R", (), {"get": staticmethod(lambda *a, **k: (_ for _ in ()).throw(OSError(raw)))}))
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    try:
        sources._get("https://api.twelvedata.com/time_series", params={"apikey": secret}, tries=1)
    except sources.FetchError as e:
        assert secret not in str(e)
    else:
        raise AssertionError("expected FetchError")


def test_events_parse_and_fallback():
    from datetime import datetime, timezone
    from quantum import events, holdout
    rows = [{"title": "Non-Farm Employment Change", "country": "USD", "date": "2026-10-02T08:30:00-04:00", "impact": "High",
             "forecast": "120K", "previous": "98K"},
            {"title": "CPI m/m", "country": "USD", "date": "2026-09-29T08:30:00-04:00", "impact": "Medium", "forecast": "0.3%", "previous": "0.2%"},
            {"title": "German CPI", "country": "EUR", "date": "2026-09-29T08:00:00+02:00", "impact": "High"},
            {"title": "Bank Holiday", "country": "USD", "date": "2026-09-30T00:00:00-04:00", "impact": "Holiday"},
            {"title": "naive time", "country": "USD", "date": "2026-09-30T10:00:00", "impact": "High"},
            "junk"]
    ev = events.parse_ff(rows)
    assert [e["title"] for e in ev] == ["CPI m/m", "Non-Farm Employment Change"]          # USD high/medium, sorted
    assert ev[1]["iso"] == "2026-10-02T12:30:00+00:00"                                    # EDT -> UTC
    now = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    doc = events.build(now, fetch=lambda: (_ for _ in ()).throw(OSError("blocked")))
    assert not doc["ok"] and doc["events"][0]["estimated"] and doc["events"][0]["iso"] == "2026-10-02T12:30:00+00:00"
    assert events.next_nfp(datetime(2026, 11, 1, tzinfo=timezone.utc))["iso"] == "2026-11-06T13:30:00+00:00"   # EST
    assert "events.py" not in holdout.ENGINE_SOURCES                                      # display only: outside the freeze key


def test_headline_feeds_rss_atom_filter_and_isolation():
    from datetime import datetime, timezone
    from quantum import events
    now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
      <item><title>Gold slips as US dollar firms</title><link>https://example.com/a</link><pubDate>Mon, 28 Sep 2026 10:00:00 GMT</pubDate></item>
      <item><title>EUR/JPY consolidates</title><link>https://example.com/b</link><pubDate>Mon, 28 Sep 2026 09:00:00 GMT</pubDate></item>
      <item><title>Fed minutes (old)</title><link>https://example.com/c</link><pubDate>Thu, 24 Sep 2026 09:00:00 GMT</pubDate></item>
      <item><title>U.S. CPI preview</title><link>javascript:alert(1)</link><pubDate>Mon, 28 Sep 2026 08:00:00 +0000</pubDate></item>
      <item><title>no date gold</title><link>https://example.com/d</link></item>
    </channel></rss>"""
    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Powell: rates to stay higher</title><link href="https://example.org/p"/><updated>2026-09-28T11:30:00Z</updated></entry>
      <entry><title>Gold slips as US dollar firms</title><link href="https://example.org/dup"/><updated>2026-09-28T10:05:00Z</updated></entry>
    </feed>"""
    feeds = {"myfxbook.com/rss/forex-economic-calendar-events": rss, "myfxbook.com/rss/latest-forex-news": atom}
    def fetch(url):
        for k, v in feeds.items():
            if k in url:
                return v
        raise OSError("HTTP 403")                                   # FXStreet blocked: must not affect the others
    hl, st = events.headlines(fetch, now)
    assert [h["title"] for h in hl] == ["Powell: rates to stay higher", "Gold slips as US dollar firms", "U.S. CPI preview"]
    assert hl[2]["link"] == ""                                      # non-http(s) link dropped
    assert [s["ok"] for s in st] == [True, True, False] and "403" in st[2]["note"]
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
    try:
        events.parse_feed(bomb, "x")
    except ValueError as e:
        assert "entities" in str(e)
    else:
        raise AssertionError("entity declarations must be refused")
    doc = events.build(now, fetch=lambda: [], fetch_feed=fetch)
    assert doc["ok"] and len(doc["feeds"]) == 3 and doc["headlines"]
