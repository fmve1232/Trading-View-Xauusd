"""The two-stage confirmation panel (quantum/confirm_panel.py): the live rule is B19's research rule, the verdict never
claims what was not validated, the evidence is the committed measurement, and the phone is untouched."""
import json

import numpy as np
import pandas as pd
import pytest

from quantum import confirm_panel as cp
from quantum import holdout, notify
from quantum.research import b19

T0 = 1793973600                                   # 2026-11-06 14:00 UTC (Friday)


def _payload(tf, t, o, h, l, c, markers=(), gen="2026-11-06T14:40:00+00:00"):
    return {"meta": {"tf": tf, "synthetic": False, "generated_utc": gen, "price_source": "td"}, "markers": list(markers),
            "decisions": [], "news": None, "chart": {"t": list(t), "o": list(o), "h": list(h), "l": list(l), "c": list(c)}}


def _bars(rows, t0=T0, sec=900):
    """rows: (o, h, l, c) -> t, o, h, l, c lists on consecutive bars."""
    t = [t0 + k * sec for k in range(len(rows))]
    return t, [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]


def _P(rows, markers=()):
    return cp.path(_payload("15m", *_bars(rows), markers=markers))


# ---------------- the live rule equals the research rule ----------------
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_live_state_machine_and_exits_equal_b19_on_random_paths(seed):
    rng = np.random.default_rng(seed)
    n = 3000
    idx = pd.date_range("2021-03-01 00:00", periods=n, freq="15min", tz="UTC")
    step = rng.normal(0, 3.0, n)
    c = 4000.0 + np.cumsum(step)
    o = np.concatenate([[c[0]], c[:-1]]) + np.where(rng.random(n) < 0.02, rng.normal(0, 12.0, n), 0.0)   # some gaps
    h = np.maximum(o, c) + np.abs(rng.normal(0, 2.0, n))
    lo_ = np.minimum(o, c) - np.abs(rng.normal(0, 2.0, n))
    up, dn = rng.random(n) < 0.03, rng.random(n) < 0.03
    df = pd.DataFrame({"open": o, "high": h, "low": lo_, "close": c}, index=idx)
    P_res = b19.make_path(df, up, dn)
    ii = np.sort(rng.choice(np.arange(20, n - 400), 300, replace=False))
    trigs = [{"tf": "15m", "kind": "T", "i": int(i), "t_close": int(idx[i].timestamp()) + 900, "dir": int(rng.choice([-1, 1])),
              "p0": float(c[i])} for i in ii]
    A = b19.attach(trigs, P_res)
    t = [int(x.timestamp()) for x in idx]
    mk = [{"t": t[k], "type": "BOS", "dir": 1} for k in np.flatnonzero(up)] + \
         [{"t": t[k], "type": "MSS", "dir": -1} for k in np.flatnonzero(dn)]
    P = cp.path(_payload("15m", t, o.tolist(), h.tolist(), lo_.tolist(), c.tolist(), mk))
    checked = 0
    for conf, X in (("X15F0", 15.0), ("X20F0", 20.0)):
        C = b19.confirm(P_res, A, conf)
        for T in (15.0, 20.0):
            R = b19.plan_and_exit(P_res, A, C, conf, "E1", "S13", T)
            for x in range(len(A["d"])):
                d, p0 = int(A["d"][x]), float(A["p0"][x])
                s = p0 / 4000.0
                live = cp.confirm_one(P, int(A["j0"][x]), p0, d, X, s)
                assert live["status"] == C["status"][x]
                if live["status"] == "INVALIDATED":
                    assert live["why"] == C["inv_kind"][x]
                if live["status"] != "CONFIRMED":
                    assert not R["execute"][x]
                    continue
                assert live["k"] == C["k"][x] and R["execute"][x]
                ex = cp.exit_one(P, live["k"], d, T, s)
                assert ex["out"] == R["outcome"][x]
                assert ex["usd"] / s == pytest.approx(R["net"][x] + R["cost"][x], abs=1e-6)
                checked += 1
    assert checked > 100


# ---------------- the state machine, by hand ----------------
FLAT = (4000.0, 4002.0, 3998.0, 4000.0)


def test_a_touch_never_confirms_and_96_bars_expire():
    rows = [FLAT] + [(4000.0, 4016.0, 3995.0, 4010.0)] + [FLAT] * 96         # +$16 high, close only +$10
    P = _P(rows)
    assert cp.confirm_one(P, 1, 4000.0, 1, 15.0)["status"] == "EXPIRED"
    assert cp.confirm_one(_P(rows[:50]), 1, 4000.0, 1, 15.0)["status"] == "PENDING"


def test_a_bar_that_invalidates_and_closes_beyond_is_invalid():
    P = _P([FLAT, (4000.0, 4016.0, 3986.5, 4015.5)])                         # low -$13.5, close +$15.5
    r = cp.confirm_one(P, 1, 4000.0, 1, 15.0)
    assert r["status"] == "INVALIDATED" and r["why"] == "price"


def test_an_opposite_structure_break_invalidates_and_a_same_side_one_does_not():
    rows = [FLAT, FLAT, (4000.0, 4016.0, 3999.0, 4015.0)]
    assert cp.confirm_one(_P(rows, [{"t": T0 + 900, "type": "CHoCH", "dir": -1}]), 1, 4000.0, 1, 15.0)["why"] == "structure"
    r = cp.confirm_one(_P(rows, [{"t": T0 + 900, "type": "BOS", "dir": 1}]), 1, 4000.0, 1, 15.0)
    assert r["status"] == "CONFIRMED" and r["k"] == 2


def test_sell_mirror_and_the_plan_levels():
    rows = [FLAT, (4000.0, 4001.0, 3984.0, 3985.0), (3985.0, 3986.0, 3969.0, 3969.5)]   # -$15 close, then -$15.5 more
    P = _P(rows)
    r = cp.confirm_one(P, 1, 4000.0, -1, 15.0)
    assert r["status"] == "CONFIRMED" and r["k"] == 1
    x = cp.exit_one(P, 1, -1, 15.0)
    assert x["out"] == "TP" and x["px"] == pytest.approx(3970.0) and x["usd"] == pytest.approx(15.0)
    assert x["mfe"] == pytest.approx(15.0) and x["mae"] == pytest.approx(1.0)


def test_exit_gap_at_the_open_and_the_ambiguous_bar():
    base = [FLAT, (4000.0, 4016.0, 3999.0, 4015.0)]                           # confirmed at 4015
    gap = cp.exit_one(_P(base + [(3990.0, 3995.0, 3985.0, 3990.0)]), 1, 1, 15.0)
    assert gap["out"] == "SL" and gap["px"] == 3990.0 and gap["usd"] == pytest.approx(-25.0)   # filled at the open
    amb = cp.exit_one(_P(base + [(4015.0, 4031.0, 4001.0, 4020.0)]), 1, 1, 15.0)
    assert amb["out"] == "AMBIGUOUS" and amb["usd"] == pytest.approx(-13.0)                  # counted as the stop
    assert cp.exit_one(_P(base + [(4015.0, 4020.0, 4010.0, 4016.0)]), 1, 1, 15.0)["out"] == "OPEN"


# ---------------- the evidence is the committed measurement ----------------
def _kn(s):
    n = s["trades"]
    return round(s["tp_first"] * n), n


def test_evidence_matches_the_committed_results():
    def load(name):
        with open(f"research/results/{name}") as fh:
            return json.load(fh)
    b21 = load("b21_development_2026-11-07.json")["results"]
    b19d = load("b19_development_2026-11-07.json")["configs"]
    b19v = load("b19_validation_2026-11-07.json")["configs"]
    b18 = load("b18_development_2026-11-06.json")["trials"]["B18 confirmed T15"]
    for kind in ("GRAB", "BREAK", "SWEEP", "BREAKOUT"):
        ev = cp.EVIDENCE[kind]
        for key, v in ev["rates"].items():
            X, T = key.split()
            s = b21[f"{kind} {X}F0 {T}"]
            assert list(_kn(s)) == v[0][:2], (kind, key)
            assert ev["confirmed"][X] == s["confirmed"] and ev["triggers"] == s["triggers"]
            assert ev["hold_min"][T] == round(b21[f"{kind} X15F0 {T}"]["avg_hold_min"])
        for T, v in ev["at_trigger"].items():
            assert list(_kn(b21[f"{kind} none {T}"])) == v[:2]
    eng = cp.EVIDENCE["ENG"]
    for key, vs in eng["rates"].items():
        X, T = key.split()
        assert list(_kn(b19d[f"ENG {X}F0 E1 S13 {T}"])) == vs[0][:2]
        if len(vs) > 1:
            assert list(_kn(b19v[f"ENG {X}F0 E1 S13 {T}"])) == vs[1][:2]
    assert cp.EVIDENCE["4H"]["at_trigger"]["T15"][:2] == [b18["wins"], b18["n"]]
    for key, v in cp.RANDOM["rates"].items():
        X, T = key.split()
        assert list(_kn(b21[f"N2 {X}F0 {T}"])) == v


def test_no_type_is_validated_so_nothing_is_accepted():
    """The operator's rule: never label a signal above what independent out-of-sample data showed."""
    assert not any(v["validated"] for v in cp.EVIDENCE.values())
    row = {"kind": "ENG", "dir": 1, "status": "CONFIRMED"}
    v, why = cp.verdict(row)
    assert v == cp.NO_TRADE == "NO TRADE — INSUFFICIENT CONFIRMATION"
    assert "not validated" in why and "60%" in why and "47.4%" in why
    assert cp.verdict({"kind": "4H", "dir": 1, "status": "CONFIRMED"})[0] == cp.NO_TRADE
    assert cp.verdict({"kind": "GRAB", "dir": -1, "status": "PENDING", "confirm_at": 3985.0, "invalid_at": 4013.0})[0] == "WAIT"


# ---------------- the panel over runs ----------------
def _eng_payload(rows, sig_bars, extra_markers=()):
    t, o, h, l, c = _bars(rows)
    mk = [{"t": t[i], "type": "SIGNAL", "dir": d, "px": c[i], "tq": 61} for i, d in sig_bars] + list(extra_markers)
    return {"15m": _payload("15m", t, o, h, l, c, mk)}


def test_panel_tracks_confirms_and_never_accepts(monkeypatch):
    rows = [FLAT] * 30 + [(4000.0, 4016.0, 3999.0, 4015.0)] + [(4015.0, 4031.0, 4014.0, 4030.5)]
    st: dict = {}
    first = cp.panel(_eng_payload(rows[:29], [(28, 1)]), st, T0 + 29 * 900)      # first run: backfill
    assert first["headline"] == cp.NO_TRADE and first["rows"][0]["status"] == "PENDING" and first["rows"][0]["backfill"]
    out = cp.panel(_eng_payload(rows, [(28, 1)]), st, T0 + 32 * 900)
    r = out["rows"][0]
    assert r["status"] == "CONFIRMED" and r["entry"] == 4015.0 and r["sl"] == 4002.0 and r["tp1"] == 4030.0 and r["tp2"] == 4035.0
    assert r["result"]["T15"]["out"] == "TP" and r["result"]["T20"]["out"] == "OPEN"
    assert r["verdict"] == cp.NO_TRADE and out["headline"] == cp.NO_TRADE
    assert set(r["checks"]) == set(cp.CHECK_TEXT)
    json.dumps(out, allow_nan=False)                                             # the site's JSON.parse rejects NaN


def test_repeat_folding_late_and_vanished_flags():
    rows = [FLAT] * 40
    st: dict = {}
    cp.panel(_eng_payload(rows[:30], [(20, 1)]), st, T0 + 30 * 900)
    out = cp.panel(_eng_payload(rows[:32], [(20, 1), (25, 1)]), st, T0 + 32 * 900)   # bar 25 was already closed last run
    assert [x["id"] for x in out["rows"]] == [1]                                    # same idea (within 4 h and $15): folded
    assert out["rows"][0]["repeats"] == 1
    out = cp.panel(_eng_payload(rows[:34], [(20, 1), (25, 1), (29, -1)]), st, T0 + 34 * 900)
    late = next(x for x in out["rows"] if x["dir"] == -1)
    assert late["late"] and not late["backfill"]                                     # appeared on an already-seen bar
    out = cp.panel(_eng_payload(rows[:36], [(25, 1)]), st, T0 + 36 * 900)          # bar 20's signal disappeared
    gone = next(x for x in out["rows"] if x["id"] == 1)
    assert gone["vanished"] and gone["status"] == "PENDING"                          # kept as it was seen


def test_finished_rows_move_to_the_log_and_the_record_skips_backfill():
    rows = [FLAT] * 3 + [(4000.0, 4001.0, 3986.0, 3990.0)] + [FLAT] * 3       # -$14 low: invalidated
    st: dict = {}
    cp.panel(_eng_payload(rows[:3], [(2, 1)]), st, T0 + 3 * 900)                  # backfill row
    out = cp.panel(_eng_payload(rows, [(2, 1), (5, -1)]), st, T0 + 7 * 900)
    assert st["confirm"]["log"][0]["status"] == "INVALIDATED" and "against" in st["confirm"]["log"][0]["why"]
    assert out["record"] == {}                                                       # the backfilled row is not counted
    assert [x["status"] for x in out["rows"] if x["id"] == 2] == ["PENDING"]


# ---------------- production boundaries ----------------
def test_not_an_engine_source_and_no_research_import():
    assert "confirm_panel.py" not in holdout.ENGINE_SOURCES
    with open("quantum/confirm_panel.py") as fh:
        src = fh.read()
    assert "research" not in "".join(x for x in src.splitlines() if x.startswith(("import", "from")))


def _p15(bars, gen="2026-11-06T14:40:00+00:00"):
    n = len(bars)
    ch = {"t": [b[0] for b in bars], "o": [b[3] for b in bars], "h": [b[1] for b in bars], "l": [b[2] for b in bars],
          "c": [b[3] for b in bars], "pdh": [4147.6] * n, "pdl": [4058.44] * n, "pwh": [4081.97] * n, "pwl": [3871.19] * n,
          "vpoc": [4059.0] * n, "vah": [4075.0] * n, "val": [4040.0] * n,
          "ob_bull_lo": [None] * n, "ob_bull_hi": [None] * n, "ob_bear_lo": [None] * n, "ob_bear_hi": [None] * n}
    x = bars[-1][3]
    mk = [{"t": bars[-1][0], "type": "SIGNAL", "dir": 1, "px": x, "tq": 60, "sl": x - 13, "tp1": x + 13, "tp2": x + 20, "tp3": x + 30}]
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": gen, "price_source": "td"}, "markers": mk,
            "decisions": [], "news": None, "chart": ch}


@pytest.mark.parametrize("mode", ["sixty", "all"])
def test_the_phone_and_the_state_are_identical_with_the_panel_on_or_off(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("ALERT_MODE", mode)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    runs = [[(T0, 4066.0, 4061.0, 4062.0)]]
    runs.append(runs[0] + [(T0 + 900, 4063.0, 4055.22, 4060.10)])
    runs.append(runs[1] + [(T0 + 1800, 4076.0, 4058.0, 4075.0)])
    out = {}
    for flag in ("0", "1"):
        monkeypatch.setenv("CONFIRM_PANEL", flag)
        sent: list = []
        monkeypatch.setattr(notify, "send", lambda lines, sent=sent: sent.append(list(lines)) or ["test"])
        store = tmp_path / flag
        store.mkdir()
        reps = [notify.run(str(store), {"15m": _p15(b)}, ["15m"], sent_t=T0 + 1000 + k * 900) for k, b in enumerate(runs)]
        state = json.loads((store / notify.STATE).read_text())
        out[flag] = (sent, [{k: v for k, v in r.items() if k != "confirm"} for r in reps], {k: v for k, v in state.items() if k != "confirm"})
        if flag == "1":
            assert "confirm" in reps[-1] and "error" not in reps[-1]["confirm"] and "confirm" in state
            json.dumps(reps[-1]["confirm"], allow_nan=False)
        else:
            assert all("confirm" not in r for r in reps) and "confirm" not in state
    assert out["0"] == out["1"]


def test_a_panel_failure_never_stops_the_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "panel", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(notify, "send", lambda lines: ["test"])
    b = [(T0, 4066.0, 4061.0, 4062.0)]
    notify.run(str(tmp_path), {"15m": _p15(b)}, ["15m"], sent_t=T0 + 1000)
    rep = notify.run(str(tmp_path), {"15m": _p15(b + [(T0 + 900, 4063.0, 4055.22, 4060.10)])}, ["15m"], sent_t=T0 + 1900)
    assert rep["confirm"] == {"on": True, "error": "RuntimeError: boom"} and "15m" in rep


def test_index_alerts_block_is_strict_json_on_a_day_with_nothing_decided(tmp_path, monkeypatch):
    """Found 2026-11-07: the validation block's empty "today" carried NaN, which the browser's JSON.parse rejects, so the
    whole alerts block of index.json was lost on most days. notify.run now returns None there."""
    monkeypatch.setattr(notify, "send", lambda lines: ["test"])
    b = [(T0, 4066.0, 4061.0, 4062.0)]
    notify.run(str(tmp_path), {"15m": _p15(b)}, ["15m"], sent_t=T0 + 1000)
    rep = notify.run(str(tmp_path), {"15m": _p15(b + [(T0 + 900, 4063.0, 4055.22, 4060.10)])}, ["15m"], sent_t=T0 + 1900)
    v = rep["plans"]["validation"]
    assert v["today"]["n"] == 0 and v["today"]["rate"] is None and v["today"]["wilson"] == [None, None]
    json.dumps(rep, allow_nan=False)
    assert notify.json_safe({"a": float("nan"), "b": [1.0, float("inf")], "c": (2.5, "x")}) == {"a": None, "b": [1.0, None], "c": [2.5, "x"]}
