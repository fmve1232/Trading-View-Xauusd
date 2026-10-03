"""Integrity gates (spec §123, §152): reference prices, data versioning, and patterns that must
never reach a production path. The network is replaced by fakes shaped like the real responses."""
import json
import os
import re
import subprocess

import pandas as pd
import pytest

from quantum import holdout, manifest, reference

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ reference prices
class _Resp:
    def __init__(self, j, date="Fri, 02 Oct 2026 12:00:01 GMT"):
        self._j, self.headers = j, {"Date": date}

    def json(self):
        return self._j

    def raise_for_status(self):
        pass


def _oanda_fake(mid_shift=0.0, bid=4300.10, ask=4300.40):
    t0 = 1790942400                                     # 2026-10-02 12:00 UTC

    def get(url, headers=None, params=None, timeout=None):
        assert headers is None or "Bearer secret-token" in headers.get("Authorization", "") or "gold-api" in url
        if url.endswith("/candles"):
            assert params["price"] == "BA"
            cs = [{"time": pd.Timestamp(t0 - 3600 * k, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                   "complete": k > 0, "bid": {"c": f"{4300.0 + k:.3f}"}, "ask": {"c": f"{4300.3 + k:.3f}"}} for k in range(5, -1, -1)]
            return _Resp({"candles": cs})
        if url.endswith("/accounts"):
            return _Resp({"accounts": [{"id": "101-001-1-001"}]})
        if url.endswith("/pricing"):
            return _Resp({"prices": [{"time": "2026-10-02T12:00:00.201836422Z", "tradeable": True,
                                      "bids": [{"price": f"{bid:.2f}"}], "asks": [{"price": f"{ask:.2f}"}]}]})
        if "gold-api" in url:
            return _Resp({"price": (bid + ask) / 2 + mid_shift, "updatedAt": "2026-10-02T12:00:00Z"})
        raise AssertionError(url)
    return get, t0


def test_timestamps_keep_exact_ns_and_never_pad_precision():
    assert reference.parse_ts_ns("2016-06-22T18:41:36.201836422Z") == (1466620896201836422, "NANOSECOND")
    assert reference.parse_ts_ns("2026-10-02T12:00:01.120Z")[1] == "MILLISECOND"
    assert reference.parse_ts_ns("2026-10-02T12:00:00.000000000Z")[1] == "SECOND"     # padded zeros are not precision
    assert reference.parse_ts_ns("2026-10-02T08:00:00-04:00")[0] == 1790942400 * 10**9
    assert reference.parse_ts_ns("garbage") == (None, "UNKNOWN")


def test_divergence_bands_and_the_2707_case():
    assert reference.classify(0.01) == "CONSISTENT"
    assert reference.classify(-0.05) == "MINOR_DIVERGENCE"
    assert reference.classify(0.5) == "SIGNIFICANT_DIVERGENCE"
    assert reference.classify((2707 - 4373) / 4373 * 100) == "CRITICAL_DIVERGENCE"
    assert reference.classify(None) == "UNAVAILABLE"


def test_reference_without_token_is_unavailable_never_filled(monkeypatch):
    def boom(*a, **k):
        raise OSError("blocked")
    monkeypatch.setattr(reference.requests, "get", boom)
    out = reference.build({"t": [1], "c": [4300.0]}, token="")
    o, g = out["observations"]
    assert o["status"] == "UNAVAILABLE" and o["mid"] is None and "OANDA_API_TOKEN" in o["note"]
    assert g["status"] == "ERROR" and g["mid"] is None
    assert out["live_divergence"] is None and out["bar_divergence_1h"]["status"] == "UNAVAILABLE"


def test_reference_with_token_compares_the_same_bars_and_hides_the_token(monkeypatch):
    get, t0 = _oanda_fake()
    monkeypatch.setattr(reference.requests, "get", get)
    t = [t0 - 3600 * k for k in range(5, 0, -1)]                 # the five complete bars
    c = [4300.15 + k for k in range(5, 0, -1)]                   # = reference mid close exactly
    c[-1] += 0.5                                                 # last bar: primary $0.50 above the reference
    out = reference.build({"t": t, "c": c}, token="secret-token", price_source="twelvedata:XAU/USD")
    o = out["observations"][0]
    assert (o["bid"], o["ask"], o["spread"], o["status"], o["quality"]) == (4300.10, 4300.40, 0.3, "LIVE", "VALID")
    assert o["timestamp_precision"] == "NANOSECOND" and o["source_ts_ns"] == 1790942400201836422
    assert o["received_ts_ns"] <= o["processed_ts_ns"] and o["latency_ms"] is not None
    b = out["bar_divergence_1h"]
    assert b["n"] == 5 and b["diff"] == 0.5 and b["status"] == "CONSISTENT"     # $0.50 at $4,301 = 0.012%
    assert b["median_diff"] == 0.0 and b["spread_median"] == 0.3
    assert out["live_divergence"]["status"] == "CONSISTENT"
    assert "secret-token" not in json.dumps(out)


def test_crossed_quote_is_flagged_not_fixed(monkeypatch):
    get, _ = _oanda_fake(bid=4300.50, ask=4300.10)
    monkeypatch.setattr(reference.requests, "get", get)
    o = reference.build(None, token="secret-token")["observations"][0]
    assert o["quality"] == "CROSSED" and (o["bid"], o["ask"]) == (4300.50, 4300.10)


def test_errors_never_carry_the_token(monkeypatch):
    def leak(url, headers=None, params=None, timeout=None):
        raise OSError("401 for token secret-token")
    monkeypatch.setattr(reference.requests, "get", leak)
    o = reference.build(None, token="secret-token")["observations"][0]
    assert o["status"] == "ERROR" and "secret-token" not in o["note"] and "***" in o["note"]


# ------------------------------------------------------------------ data versioning
def _git(d, *a):
    subprocess.run(["git", "-C", d, *a], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "GIT_AUTHOR_DATE": "2026-10-02T12:30:00Z",
                        "GIT_COMMITTER_DATE": "2026-10-02T12:30:00Z"})


def _csv(rows):
    return "datetime,open,high,low,close,volume\n" + "".join(f"{t},{o:.6f},{o + 1:.6f},{o - 1:.6f},{c:.6f},\n" for t, o, c in rows)


def test_manifest_records_tree_hash_and_keeps_revised_closed_bars(tmp_path):
    store, ledger = str(tmp_path / "store"), str(tmp_path / "ledger")
    os.makedirs(os.path.join(store, "XAU_USD_60m"))
    f = os.path.join(store, "XAU_USD_60m", "2026-10.csv")
    old = [("2026-10-02 10:00:00+00:00", 4300.0, 4301.0), ("2026-10-02 11:00:00+00:00", 4301.0, 4302.0),
           ("2026-10-02 12:00:00+00:00", 4302.0, 4302.5)]           # 12:00 bar still forming at the 12:30 snapshot
    with open(f, "w") as fh:
        fh.write(_csv(old))
    _git(store, "init", "-q", "-b", "market-data")
    _git(store, "add", "-A")
    _git(store, "commit", "-q", "-m", "snapshot")
    first = manifest.record(store, ledger, "1", "abc", "k")
    new = [old[0], ("2026-10-02 11:00:00+00:00", 4301.0, 4299.0), ("2026-10-02 12:00:00+00:00", 4302.0, 4303.0)]
    with open(f, "w") as fh:
        fh.write(_csv(new))
    line = manifest.record(store, ledger, "2", "abc", "k")
    assert line["tree_sha256"] != first["tree_sha256"] and line["changed"] == ["XAU_USD_60m/2026-10.csv"]
    assert line["revised_closed_bars"] == 1 and line["forming_bar_updates"] == 1     # 11:00 revised; 12:00 just finished
    rev = pd.read_csv(os.path.join(ledger, "revisions", "XAU_USD_60m", "2026-10.csv"))
    assert list(rev["bar_open"]) == ["2026-10-02 11:00:00+00:00"] and rev["old_close"][0] == 4302.0 and rev["new_close"][0] == 4299.0
    runs = open(os.path.join(ledger, "manifests", "runs-" + pd.Timestamp.now("UTC").strftime("%Y-%m") + ".jsonl")).read().splitlines()
    assert len(runs) == 2 and json.loads(runs[1])["freeze_key"] == "k"
    assert manifest.tree_hash({"a": ["1", 1], "b": ["2", 1]}) == manifest.tree_hash({"b": ["2", 1], "a": ["1", 1]})


# ------------------------------------------------------------------ forbidden patterns
def test_no_random_or_synthetic_price_paths_in_production():
    for rel in ("site/app.js", "relay/worker.js", "scheduler/worker.js"):
        src = _read(rel)
        assert not re.search(r"Math\.(random|sin|cos)\s*\(", src), rel
    allowed = {"backtest.py", "market.py"}          # seeded bootstrap; the labelled offline test generator
    for root, _, files in os.walk(os.path.join(ROOT, "quantum")):
        for fn in files:
            if fn.endswith(".py") and fn not in allowed:
                src = open(os.path.join(root, fn), encoding="utf-8").read()
                assert not re.search(r"\bnp\.random\b|\bimport random\b|\brandom\.\w+\(", src), fn
    wf = _read(".github/workflows/quantum-site.yml")
    assert "--synthetic" not in wf


def test_no_literal_gold_prices_in_the_page():
    src = _read("site/app.js")
    assert not re.findall(r"(?<![\w.])[1-9]\d{3}\.\d{1,3}(?![\w.])", src)    # e.g. 4323.50 hard-coded


def test_no_credentials_in_tracked_files():
    files = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    pat = re.compile(r"""(api[_-]?key|apikey|token|secret|password)["']?\s*[:=]\s*["'][A-Za-z0-9_\-]{20,}["']"""
                     r"""|[?&](apikey|api_key|token)=[A-Za-z0-9_\-]{16,}""", re.I)
    for rel in files:
        # tests hold dummy keys by design; vendored and binary files are not ours to scan
        if rel.startswith(("site/vendor/", "artefacts/", "tests/")) or rel.endswith((".png", ".xlsx", ".pdf")):
            continue
        try:
            src = _read(rel)
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        assert not pat.search(src), rel


def test_reference_and_manifest_are_outside_the_freeze_key():
    for mod in ("reference.py", "manifest.py"):
        assert mod not in holdout.ENGINE_SOURCES
    for rel in holdout.ENGINE_SOURCES:
        src = _read("quantum/" + rel)
        assert "from .reference" not in src and "from .manifest" not in src and "from ..reference" not in src
