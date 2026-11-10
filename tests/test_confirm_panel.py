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


def test_time_stop_exits_at_the_unrounded_close_as_b19():
    """Found on 2020-22 history by research/tools/excursions.py: the time stop's price was rounded to cents."""
    base = [FLAT, (4000.0, 4016.0, 3999.0, 4015.123)]                         # confirmed at 4015.123
    drift = [(4015.0, 4016.0, 4014.0, 4015.0 + 0.0037 * k) for k in range(cp.HOLD)]
    x = cp.exit_one(_P(base + drift), 1, 1, 20.0)
    assert x["out"] == "TIMEOUT" and x["bar"] == 1 + cp.HOLD
    assert x["usd"] == pytest.approx(4015.0 + 0.0037 * (cp.HOLD - 1) - 4015.123, abs=1e-9)
    assert cp.exit_one(_P(base + drift[:-1]), 1, 1, 20.0)["out"] == "OPEN"


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
    assert why.startswith("confirmed, but INSUFFICIENT DATA — NOT STATISTICALLY VALIDATED") and "60% of 20 trades" in why
    assert "47.4%" in why
    v, why = cp.verdict({"kind": "GRAB", "dir": 1, "status": "CONFIRMED"})
    assert v == cp.NO_TRADE and "NOT VALIDATED: its registered test failed" in why and "43% of 302 trades (2020-22" in why
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


def _trunc(P, n):
    return {k: (v[:n] if isinstance(v, (list, np.ndarray)) else v) for k, v in P.items()}


@pytest.mark.parametrize("seed", [4, 5])
def test_no_look_ahead_on_every_prefix(seed):
    """On every prefix of the bars the state machine says PENDING until its event bar, and from that bar on exactly what
    the full history says: a decision never uses a bar after it, and a later bar never changes it."""
    rng = np.random.default_rng(seed)
    n = 700
    c = 4000.0 + np.cumsum(rng.normal(0, 3.0, n))
    o = np.concatenate([[c[0]], c[:-1]])
    h, l = np.maximum(o, c) + np.abs(rng.normal(0, 2, n)), np.minimum(o, c) - np.abs(rng.normal(0, 2, n))
    mk = [{"t": T0 + 900 * k, "type": "BOS", "dir": int(rng.choice([-1, 1]))} for k in np.flatnonzero(rng.random(n) < 0.02)]
    P = cp.path(_payload("15m", *_bars(list(zip(o, h, l, c))), markers=mk))
    for j0 in range(20, 300, 7):
        d = 1 if j0 % 2 else -1
        full = cp.confirm_one(P, j0, float(c[j0 - 1]), d, 15.0)
        ev = full["at"]
        for m in range(j0, min(n, j0 + cp.WIN + 2)):
            r = cp.confirm_one(_trunc(P, m), j0, float(c[j0 - 1]), d, 15.0)
            decided_later = (full["status"] in ("CONFIRMED", "INVALIDATED") and m <= ev) or \
                (full["status"] == "EXPIRED" and m < j0 + cp.WIN)
            if decided_later:
                assert r["status"] == "PENDING"
            else:
                assert (r["status"], r["k"]) == (full["status"], full["k"])
        if full["status"] == "CONFIRMED":
            fx = cp.exit_one(P, full["k"], d, 15.0)
            for m in range(full["k"] + 1, min(n, full["k"] + cp.HOLD + 3), 5):
                x = cp.exit_one(_trunc(P, m), full["k"], d, 15.0)
                assert x["out"] == ("OPEN" if m <= fx["bar"] else fx["out"])


def test_incremental_runs_equal_one_full_run():
    """Run by run (one new bar each time) the panel reaches the same decisions as one run over all the bars."""
    rows = [FLAT] * 30 + [(4000.0, 4009.0, 3995.0, 4008.0), (4008.0, 4016.0, 4003.0, 4015.5)] + \
           [(4015.0, 4024.0, 4010.0, 4022.0), (4022.0, 4031.0, 4020.0, 4030.0), (4030.0, 4036.0, 4025.0, 4035.5)] + [FLAT] * 4
    st_inc: dict = {}
    for m in range(29, len(rows) + 1):
        out_inc = cp.panel(_eng_payload(rows[:m], [(28, 1)]), st_inc, T0 + m * 900)
    st_one: dict = {}
    cp.panel(_eng_payload(rows[:29], [(28, 1)]), st_one, T0 + 29 * 900)
    out_one = cp.panel(_eng_payload(rows, [(28, 1)]), st_one, T0 + len(rows) * 900)
    a = next(r for r in out_inc["rows"] if r["id"] == 1)
    b = next(r for r in out_one["rows"] if r["id"] == 1)
    for k in ("status", "t_conf", "entry", "sl", "tp1", "tp2"):
        assert a[k] == b[k]
    assert a["entry"] == 4015.5 and a["result"]["T15"]["out"] == b["result"]["T15"]["out"] == "TP"
    assert a["result"]["T20"]["out"] == b["result"]["T20"]["out"] == "TP" and not a.get("revised") and not b.get("revised")


def test_a_revised_bar_never_changes_a_decision_already_shown():
    rows = [FLAT] * 30 + [(4000.0, 4016.0, 3999.0, 4015.0)] + [(4015.0, 4020.0, 4010.0, 4016.0)]
    st: dict = {}
    cp.panel(_eng_payload(rows[:29], [(28, 1)]), st, T0 + 29 * 900)
    first = next(r for r in cp.panel(_eng_payload(rows, [(28, 1)]), st, T0 + 32 * 900)["rows"] if r["id"] == 1)
    assert first["status"] == "CONFIRMED" and first["entry"] == 4015.0
    revised = list(rows)
    revised[30] = (4000.0, 4016.0, 3999.0, 4012.0)                   # the feed now says the confirming close was +$12
    revised[29] = (4000.0, 4002.0, 3985.0, 3990.0)                   # ... and an earlier bar fell $15 (invalid if recomputed)
    again = next(r for r in cp.panel(_eng_payload(revised + [FLAT], [(28, 1)]), st, T0 + 33 * 900)["rows"] if r["id"] == 1)
    assert again["status"] == "CONFIRMED" and again["entry"] == 4015.0 and again["t_conf"] == first["t_conf"]
    assert "revised" in again["revised"]


def test_a_pending_row_is_not_confirmed_on_a_bar_already_examined():
    rows = [FLAT] * 30 + [(4000.0, 4012.0, 3999.0, 4010.0)]
    st: dict = {}
    cp.panel(_eng_payload(rows[:29], [(28, 1)]), st, T0 + 29 * 900)
    assert next(r for r in cp.panel(_eng_payload(rows, [(28, 1)]), st, T0 + 31 * 900)["rows"] if r["id"] == 1)["status"] == "PENDING"
    rows2 = list(rows)
    rows2[30] = (4000.0, 4017.0, 3999.0, 4016.0)                     # revised afterwards to a +$16 close
    r = next(x for x in cp.panel(_eng_payload(rows2 + [FLAT], [(28, 1)]), st, T0 + 32 * 900)["rows"] if x["id"] == 1)
    assert r["status"] == "PENDING" and "confirmed" in r["revised"]   # kept as shown, the revision flagged


def test_an_expired_row_never_becomes_confirmed():
    rows = [FLAT] * 3 + [FLAT] * cp.WIN + [FLAT]
    st: dict = {}
    cp.panel(_eng_payload(rows[:3], [(2, 1)]), st, T0 + 3 * 900)
    cp.panel(_eng_payload(rows, [(2, 1)]), st, T0 + len(rows) * 900)
    assert st["confirm"]["log"][0]["status"] == "EXPIRED"
    later = rows + [(4000.0, 4020.0, 3999.0, 4018.0)] * 3                # a +$18 close after the window
    out = cp.panel(_eng_payload(later, [(2, 1)]), st, T0 + len(later) * 900)
    assert [r["status"] for r in out["rows"] if r["id"] == 1] == ["EXPIRED"] and len(st["confirm"]["log"]) == 1


def test_every_finished_row_goes_to_the_durable_audit_file(tmp_path):
    rows = [FLAT] * 3 + [(4000.0, 4001.0, 3986.0, 3990.0)] + [FLAT] * 3
    st: dict = {}
    cp.panel(_eng_payload(rows[:3], [(2, 1)]), st, T0 + 3 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(2, 1), (5, -1)]), st, T0 + 7 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(2, 1), (5, -1)]), st, T0 + 8 * 900, store_dir=str(tmp_path))   # nothing new: no duplicate
    rec = json.loads((tmp_path / "research_forward" / cp.AUDIT_FILE).read_text())
    assert [(r["id"], r["status"]) for r in rec["rows"]] == [(1, "INVALIDATED")] and "against" in rec["rows"][0]["why"]


def test_every_probability_carries_its_sample_period_and_status():
    for kind, ev in cp.EVIDENCE.items():
        assert ev["status"] in cp.STATUS_TEXT and not ev["validated"]
        for key, vals in ev["rates"].items():
            for k, n, period in vals:
                assert 0 <= k <= n and n > 0 and period in ("2020-22", "2023-24"), (kind, key)
        for k, n, period in ev["at_trigger"].values():
            assert 0 <= k <= n and period == "2020-22"
    assert cp.EVIDENCE["ENG"]["status"] == cp.EVIDENCE["4H"]["status"] == "INSUFFICIENT"
    assert cp.STATUS_TEXT["INSUFFICIENT"] == "INSUFFICIENT DATA — NOT STATISTICALLY VALIDATED"


def _events(tmp_path):
    p = tmp_path / "research_forward" / cp.EVENTS_FILE
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_every_stage_event_is_recorded_once_in_order_with_its_bar_time(tmp_path):
    """Setup -> $15 confirmation -> TP1 result, each event once, timed by the bar it happened on (not the run), with the
    trigger and confirmation prices, the confirmed move, the data source; a re-run with nothing new adds nothing."""
    rows = [FLAT] * 30 + [(4000.0, 4016.0, 3999.0, 4015.0)] + [(4015.0, 4031.0, 4014.0, 4030.5)]
    st: dict = {}
    cp.panel(_eng_payload(rows[:29], [(28, 1)]), st, T0 + 29 * 900, store_dir=str(tmp_path))
    out = cp.panel(_eng_payload(rows, [(28, 1)]), st, T0 + 32 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(28, 1)]), st, T0 + 33 * 900, store_dir=str(tmp_path))          # nothing new
    ev = _events(tmp_path)
    assert [e["event"] for e in ev] == ["SETUP", "CONFIRMED", "X20_CLOSE", "EXIT_T15"]         # 4030.5: a later $20 close
    s, c, x20, x = ev
    assert x20["close_price"] == 4030.5 and x20["event_utc"] == T0 + 32 * 900 and "milestone" in x20["note"]
    assert s["setup_id"] == c["setup_id"] == x["setup_id"] == f"CF-ENG-15m-{T0 + 28 * 900}-B" and s["panel_no"] == 1
    assert s["direction"] == "BUY" and s["tf"] == "15m" and len({e["event_id"] for e in ev}) == 4
    assert s["event_utc"] == T0 + 29 * 900 and s["trigger_price"] == rows[28][3] and s["confirm_at"] == rows[28][3] + 15
    assert c["event_utc"] == T0 + 31 * 900 and c["confirmation_price"] == 4015.0 and c["move_usd"] == 4015.0 - rows[28][3]
    assert c["move_usd"] >= 15 and c["sl"] == 4002.0 and c["tp1"] == 4030.0 and c["tp2"] == 4035.0
    assert x["outcome"] == "TP" and x["exit_reason"] == "target" and x["pnl_usd_per_oz"] == 15.0
    assert x["pnl_after_operator_cost"] == round(15.0 - cp.OP_COST, 2) and "15m bars" in x["data_source"]
    assert all(e["logged_utc"] >= e["event_utc"] for e in ev) and s["flags"] == ["backfill"]
    assert out["rows"][0]["move_usd"] == c["move_usd"]
    assert cp.verify_events(str(tmp_path / "research_forward" / cp.EVENTS_FILE)) == (True, "4 events, chain intact")
    assert out["events"] == {"file": cp.EVENTS_FILE, "ok": True, "why": "4 events, chain intact", "appended": 3}


def test_a_lost_state_file_neither_duplicates_nor_renumbers_events(tmp_path):
    """Ids come from the trigger and the log itself is the dedupe key: a fresh state (lost / reset) re-sees the same
    triggers and appends nothing it already holds; the next real event still goes in."""
    rows = [FLAT] * 30 + [(4000.0, 4016.0, 3999.0, 4015.0)]
    cp.panel(_eng_payload(rows[:29], [(28, 1)]), {}, T0 + 29 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(28, 1)]), {}, T0 + 31 * 900, store_dir=str(tmp_path))       # state lost between runs
    ev = _events(tmp_path)
    assert [e["event"] for e in ev] == ["SETUP", "CONFIRMED"]
    assert len({e["event_id"] for e in ev}) == len(ev)
    assert cp.verify_events(str(tmp_path / "research_forward" / cp.EVENTS_FILE))[0]


def test_a_torn_last_line_is_reported_not_raised_and_nothing_is_appended(tmp_path):
    rows = [FLAT] * 3 + [(4000.0, 4001.0, 3986.0, 3990.0)] + [FLAT] * 3
    st: dict = {}
    cp.panel(_eng_payload(rows[:3], [(2, 1)]), st, T0 + 3 * 900, store_dir=str(tmp_path))
    p = tmp_path / "research_forward" / cp.EVENTS_FILE
    p.write_bytes(p.read_bytes() + b'{"seq": 2, "prev": "ab')                    # a run killed mid-write
    before = p.read_bytes()
    out = cp.panel(_eng_payload(rows, [(2, 1)]), st, T0 + 7 * 900, store_dir=str(tmp_path))
    assert p.read_bytes() == before and out["events"]["ok"] is False and "not valid JSON" in out["events"]["why"]
    assert out["headline"] == cp.NO_TRADE


def test_a_confirmed_setup_whose_bars_leave_the_chart_is_unresolved_not_no_trade(tmp_path):
    """Stage B reached, an exit still open, then the trigger's bars drop off the chart (the site was down for days): the
    log says UNRESOLVED after CONFIRMED, the verdict does not call it unconfirmed, and the record still counts the
    confirmation (its exits stay undecided)."""
    rows = [FLAT] * 30 + [(4000.0, 4016.0, 3999.0, 4015.0)]
    st: dict = {}
    cp.panel(_eng_payload(rows[:29], [(28, 1)]), st, T0 + 29 * 900, store_dir=str(tmp_path))
    st["confirm"]["started"] = T0                                                 # count it in the live record
    for r in st["confirm"]["rows"]:
        r["backfill"] = False
    cp.panel(_eng_payload(rows, [(28, 1)]), st, T0 + 31 * 900, store_dir=str(tmp_path))
    later = {"15m": _payload("15m", *_bars([FLAT] * 5, t0=T0 + 40 * 900))}
    out = cp.panel(later, st, T0 + 45 * 900, store_dir=str(tmp_path))
    ev = _events(tmp_path)
    assert [e["event"] for e in ev] == ["SETUP", "CONFIRMED", "STALE"]
    assert ev[-1]["outcome"] == "UNRESOLVED" and ev[-1]["event_utc"] == T0 + 45 * 900
    row = st["confirm"]["log"][-1]
    assert row["status"] == "STALE" and row["verdict"] == "NO TRADE" and "it was confirmed" in row["reason"]
    assert out["record"]["ENG"]["confirmed"] == 1 and out["record"]["ENG"]["T15"] == [0, 0]
    assert cp.verdict({"kind": "ENG", "dir": 1, "status": "STALE", "why": "gone"})[1] == "gone; never confirmed"


def test_a_cancelled_setup_is_recorded_as_no_trade(tmp_path):
    rows = [FLAT] * 3 + [(4000.0, 4001.0, 3986.0, 3990.0)] + [FLAT] * 3
    st: dict = {}
    cp.panel(_eng_payload(rows[:3], [(2, 1)]), st, T0 + 3 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(2, 1)]), st, T0 + 7 * 900, store_dir=str(tmp_path))
    ev = _events(tmp_path)
    assert [e["event"] for e in ev] == ["SETUP", "INVALIDATED"]
    assert ev[1]["outcome"] == "NO TRADE" and "against" in ev[1]["exit_reason"] and ev[1]["event_utc"] == T0 + 4 * 900


def test_the_event_log_is_tamper_evident_and_never_extended_when_broken(tmp_path):
    rows = [FLAT] * 3 + [(4000.0, 4001.0, 3986.0, 3990.0)] + [FLAT] * 3
    st: dict = {}
    cp.panel(_eng_payload(rows[:3], [(2, 1)]), st, T0 + 3 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(2, 1)]), st, T0 + 7 * 900, store_dir=str(tmp_path))
    p = tmp_path / "research_forward" / cp.EVENTS_FILE
    lines = p.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["trigger_price"] = 1.0                                                   # an edited record
    p.write_text("\n".join([json.dumps(rec)] + lines[1:]) + "\n")
    ok, why = cp.verify_events(str(p))
    assert not ok and "event 2" in why
    before = p.read_text()
    cp.panel(_eng_payload(rows + [FLAT], [(2, 1), (6, -1)]), st, T0 + 8 * 900, store_dir=str(tmp_path))
    assert p.read_text() == before and "breaks the chain" in st["confirm"]["events_status"]["why"]
    assert st["confirm"]["events_status"]["ok"] is False


def _two_setups(tmp_path):
    rows = [FLAT] * 3 + [(4000.0, 4001.0, 3986.0, 3990.0)] + [FLAT] * 3 + [(4000.0, 4016.0, 3999.0, 4015.5)] + [FLAT] * 2
    st: dict = {}
    cp.panel(_eng_payload(rows[:3], [(2, 1)]), st, T0 + 3 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(2, 1), (5, -1)]), st, T0 + 10 * 900, store_dir=str(tmp_path))
    return rows, st, tmp_path / "research_forward" / cp.EVENTS_FILE


@pytest.mark.parametrize("cut", ["drop the last line", "delete the file"])
def test_lines_cut_from_the_end_of_the_event_log_are_detected_by_the_anchor(tmp_path, cut):
    """A hash chain cannot show a cut tail on its own: the state keeps the last line this panel wrote (seq, SHA-256) and
    the next run requires it to still be there, unchanged. Nothing is appended until the log is restored."""
    rows, st, p = _two_setups(tmp_path)
    assert st["confirm"]["events_head"]["seq"] == 4
    if cut == "drop the last line":
        p.write_text("\n".join(p.read_text().splitlines()[:-1]) + "\n")
    else:
        p.unlink()
    before = p.read_text() if p.exists() else None
    out = cp.panel(_eng_payload(rows + [FLAT] * 30, [(2, 1), (5, -1), (30, 1)]), st, T0 + 41 * 900, store_dir=str(tmp_path))
    assert out["events"]["ok"] is False and "truncated or deleted" in out["events"]["why"]
    assert (p.read_text() if p.exists() else None) == before


def test_a_replaced_last_line_is_detected_and_a_lost_state_raises_no_false_alarm(tmp_path):
    _rows, st, p = _two_setups(tmp_path)
    lines = p.read_text().splitlines()
    rec = json.loads(lines[-1])
    rec["exit_reason"] = "edited"                                    # a valid-looking line, chained correctly
    lines[-1] = json.dumps(rec)
    p.write_text("\n".join(lines) + "\n")
    assert cp.verify_events(str(p))[0]                               # the chain alone cannot see it ...
    ok, why = cp.verify_events(str(p), st["confirm"]["events_head"])
    assert not ok and "replaced" in why                              # ... the anchor does
    rows2, st2, _p2 = _two_setups(tmp_path / "b")
    st2["confirm"].pop("events_head")                                # state lost: no anchor, no false alarm
    out = cp.panel(_eng_payload(rows2 + [FLAT] * 30, [(2, 1), (5, -1), (30, 1)]), st2, T0 + 41 * 900, store_dir=str(tmp_path / "b"))
    assert out["events"]["ok"] is True and out["events"]["appended"] == 1


def test_the_headline_figure_is_never_shown_without_its_sample_and_status():
    sub = cp.panel({}, {}, T0)["sub"]
    assert "12 of 20 engine signal trades, 2020-22, 95% 39%-78%" in sub and "not a proven accuracy" in sub
    assert cp.STATUS_TEXT["INSUFFICIENT"] in sub and "No signal type has a validated success rate" in sub


# ---------------- amendment B24-CONFIRM-FWD-A1: the confirming close must be $15 to $20 beyond ----------------
@pytest.mark.parametrize("d", [1, -1])
@pytest.mark.parametrize("p0", [4000.0, 4116.24, 3987.37])        # floating-point-hostile trigger prices as well
@pytest.mark.parametrize("move, status", [(14.99, "PENDING"), (15.0, "CONFIRMED"), (17.5, "CONFIRMED"), (20.0, "CONFIRMED"),
                                          (20.01, "EXPIRED"), (48.05, "EXPIRED")])
def test_the_confirming_close_must_be_15_to_20_beyond_the_trigger_both_ways(d, p0, move, status):
    """Exact bounds, to the cent, BUY and SELL alike: $15.00 and $20.00 confirm; $14.99 does not; $20.01 and beyond expire."""
    c = round(p0 + d * move, 2)
    bar = (p0, max(p0, c) + 0.01, min(p0, c) - 0.01, c)               # no -$13 touch on the way
    P = _P([(p0, p0 + 1, p0 - 1, p0)] * 2 + [bar] + [(c, c + 0.5, c - 0.5, c)] * 3)
    r = cp.confirm_one(P, 2, p0, d, 15.0, cap=cp.CAP_USD)
    assert r["status"] == status, (d, p0, move, r)
    if status == "CONFIRMED":
        assert r["k"] == 2
    if status == "EXPIRED":
        assert r["why"] == "overshoot" and r["at"] == 2 and r["move"] == pytest.approx(move, abs=1e-6)
    assert cp.confirm_one(P, 2, p0, d, 15.0)["status"] == ("CONFIRMED" if move >= 15 else "PENDING")   # B19's uncapped rule


def test_an_overshoot_is_final_and_a_later_close_inside_the_band_never_confirms():
    rows = [FLAT, FLAT, (4000.0, 4026.0, 3999.0, 4025.0), (4025.0, 4026.0, 4016.0, 4017.0), FLAT]
    r = cp.confirm_one(_P(rows), 2, 4000.0, 1, 15.0, cap=cp.CAP_USD)
    assert r["status"] == "EXPIRED" and r["why"] == "overshoot" and r["at"] == 2


def test_a_wick_beyond_20_neither_confirms_nor_expires_only_closes_decide():
    """Stated in the amendment before any capped result: closes decide. A wick to +$25 that closes at +$10 leaves the
    setup open; a later close at +$18 (its wick at +$24) confirms."""
    rows = [FLAT, FLAT, (4000.0, 4025.0, 3999.0, 4010.0), (4010.0, 4024.0, 4009.0, 4018.0)]
    r = cp.confirm_one(_P(rows), 2, 4000.0, 1, 15.0, cap=cp.CAP_USD)
    assert r["status"] == "CONFIRMED" and r["k"] == 3


@pytest.mark.parametrize("d", [1, -1])
def test_the_minus_13_touch_and_the_opposite_structure_break_are_checked_before_the_cap(d):
    p0 = 4000.0
    over = (p0, p0 + 26 if d > 0 else p0 + 13, p0 - 13 if d > 0 else p0 - 26, p0 + d * 25)       # touches -$13, closes +$25
    r = cp.confirm_one(_P([FLAT, FLAT, over, FLAT]), 2, p0, d, 15.0, cap=cp.CAP_USD)
    assert r["status"] == "INVALIDATED" and r["why"] == "price"
    band = (p0, p0 + 18 if d > 0 else p0 + 1, p0 - 1 if d > 0 else p0 - 18, p0 + d * 17)
    mk = [{"t": T0 + 2 * 900, "type": "CHoCH", "dir": -d}]
    r = cp.confirm_one(_P([FLAT, FLAT, band, FLAT], mk), 2, p0, d, 15.0, cap=cp.CAP_USD)
    assert r["status"] == "INVALIDATED" and r["why"] == "structure"


@pytest.mark.parametrize("d", [1, -1])
def test_the_panel_records_an_overshoot_as_expired_no_trade_once(tmp_path, d):
    rows = [FLAT] * 29 + [(4000.0, 4000.0 + max(0, 24 * d) + 1, 4000.0 + min(0, 24 * d) - 1, 4000.0 + 23.4 * d)] + [FLAT] * 2
    st: dict = {}
    cp.panel(_eng_payload(rows[:29], [(28, d)]), st, T0 + 29 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(28, d)]), st, T0 + 32 * 900, store_dir=str(tmp_path))
    cp.panel(_eng_payload(rows, [(28, d)]), st, T0 + 33 * 900, store_dir=str(tmp_path))
    r = (st["confirm"]["rows"] + st["confirm"]["log"])[0]
    assert r["status"] == "EXPIRED" and r["verdict"] == "NO TRADE" and r["overshoot_usd"] == 23.4
    assert "over the $20 cap" in r["why"] and r["t_done"] == T0 + 30 * 900 and r.get("entry") is None
    assert r["cap_at"] == round(4000.0 + 20 * d, 2) and r["confirm_at"] == round(4000.0 + 15 * d, 2)
    ev = _events(tmp_path)
    assert [e["event"] for e in ev] == ["SETUP", "EXPIRED"] and ev[1]["outcome"] == "NO TRADE" and ev[1]["overshoot_usd"] == 23.4


def test_the_panel_states_its_shadow_mode_and_the_amended_rule():
    out = cp.panel({}, {}, T0)
    assert out["mode"] == "SHADOW" and out["cap_usd"] == 20.0 and "B24-CONFIRM-FWD-A1" in out["rule"]
    assert "original rule (no $20 cap)" in out["sub"]
    assert not any(v["validated"] for v in cp.EVIDENCE.values())
