"""The SIGNAL alert's first line names the plan stop and labels the engine's own SL / TP1-3 as reference levels
(operator approval 2026-11-13, audit F-06). Wording only: the levels, the plan, the plan line and every record are
unchanged.

tests/conftest.py runs every test in "quality" mode; the whole-run test also runs in "sixty", the production default."""
import json
import os
import re
from datetime import datetime, timezone

import pytest

from quantum import notify as N

# 12 Nov 15:00 UTC, the first 15m alert of the day, as production sent it
M12 = {"t": 1794494700, "type": "SIGNAL", "dir": -1, "px": 3871.20, "tq": 72, "sl": 3910.34, "tp1": 3832.07, "tp2": 3792.93,
       "tp3": 3753.80}
OLD_12 = "XAUUSD 15m SELL (confirmed close) | entry 3871.20 SL 3910.34 TP1 3832.07 TP2 3792.93 TP3 3753.80 | TQ 72"
NEW_12 = ("XAUUSD 15m SELL (confirmed close) | entry 3871.20 | plan stop SL 3884.20 (-$650) | engine reference only, "
          "not the plan: SL 3910.34 TP1 3832.07 TP2 3792.93 TP3 3753.80 | TQ 72")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "MT5_PRICE_OFFSET", "ALERT_LIQUIDITY",
              "PLAN_LATE_FRAC", "PLAN_TP2_USD", "NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")


def _old_head(m, tf, d, pl, off=0.0):
    """The first line before 2026-11-13."""
    f = N._fmt
    return (f"XAUUSD {tf} {d} (confirmed close) | entry {f(m['px'], off)} SL {f(m['sl'], off)} "
            f"TP1 {f(m['tp1'], off)} TP2 {f(m['tp2'], off)} TP3 {f(m['tp3'], off)} | TQ {m['tq']}")


def _pay(markers, tf="15m"):
    return {"meta": {"tf": tf, "synthetic": False, "generated_utc": "2026-11-12T15:04:00+00:00", "price_source": "td"},
            "markers": markers, "decisions": [], "chart": {"t": [], "h": [], "l": []}}


def test_the_12_nov_alert_names_the_plan_stop_first():
    assert N.signal_head(M12, "15m", "SELL", N.plan_cfg()) == NEW_12
    assert _old_head(M12, "15m", "SELL", N.plan_cfg()) == OLD_12          # what the phone was sent that day


def test_the_plan_stop_is_the_plan_lines_stop_on_both_sides_and_with_the_mt5_offset(monkeypatch):
    for off in ("0", "-2.61"):
        monkeypatch.setenv("MT5_PRICE_OFFSET", off)
        for d, px in ((-1, 3871.20), (1, 4000.0)):
            m = {**M12, "dir": d, "px": px}
            lines = N.messages(_pay([m]), M12["t"] - 1)
            head, plan = lines[0], next(x for x in lines if x.startswith("YOUR PLAN"))
            named = re.search(r"\| plan stop SL ([0-9.]+) \(-\$650\) \|", head).group(1)
            assert named == re.search(r"^YOUR PLAN [0-9.]+ lot: SL ([0-9.]+) ", plan).group(1)
            assert float(named) == pytest.approx(px - d * 13.0 + float(off))


def test_every_engine_level_is_still_shown_unchanged():
    head = N.signal_head(M12, "15m", "SELL", N.plan_cfg())
    tail = head.split("engine reference only, not the plan: ", 1)[1]
    assert tail == OLD_12.split("entry 3871.20 ", 1)[1]                    # SL TP1 TP2 TP3 and TQ, byte for byte


def test_no_plan_stop_is_named_when_no_plan_is_offered(monkeypatch):
    """A REPEAT offers no plan, and PLAN=0 none at all: the engine levels are still reference, no stop is named."""
    rep = N.signal_head(M12, "15m", "SELL", None)
    assert rep == ("XAUUSD 15m SELL (confirmed close) | entry 3871.20 | engine reference only: SL 3910.34 TP1 3832.07 "
                   "TP2 3792.93 TP3 3753.80 | TQ 72")
    assert "plan stop" not in N.signal_head({**M12, "px": None}, "15m", "SELL", N.plan_cfg())
    monkeypatch.setenv("PLAN", "0")
    lines = N.messages(_pay([M12]), M12["t"] - 1)
    assert lines[0] == rep and not any(x.startswith("YOUR PLAN") for x in lines)


def test_a_plan_stop_is_named_exactly_when_a_plan_line_follows(monkeypatch):
    for plan in ("1", "0"):
        monkeypatch.setenv("PLAN", plan)
        lines = N.messages(_pay([M12]), M12["t"] - 1)
        assert ("plan stop" in lines[0]) == any(x.startswith("YOUR PLAN") for x in lines)
    monkeypatch.setenv("PLAN", "1")
    rp = {"id": 7, "tf": "15m", "dir": -1, "entry": 3871.20, "t": M12["t"] - 900}
    lines = N.messages(_pay([M12]), M12["t"] - 1, ctx={"repeats": {M12["t"]: rp}})
    assert lines[1].startswith("REPEAT of #7") and "plan stop" not in lines[0]
    assert "| engine reference only: SL 3910.34 " in lines[0]


def test_the_named_stop_follows_the_plan_settings(monkeypatch):
    """A $400 stop with a $650 target: the line names the stop's own amount and price, not the target's."""
    monkeypatch.setenv("PLAN_SL_USD", "400")
    monkeypatch.setenv("PLAN_TP2_USD", "0")
    head = N.signal_head(M12, "15m", "SELL", N.plan_cfg())
    assert "| plan stop SL 3879.20 (-$400) |" in head                              # 3871.20 + $400 / 50 oz


def test_only_the_first_line_changes_and_the_old_prefix_still_holds(monkeypatch):
    new = N.messages(_pay([M12]), M12["t"] - 1)
    monkeypatch.setattr(N, "signal_head", _old_head)
    old = N.messages(_pay([M12]), M12["t"] - 1)
    assert new[1:] == old[1:] and new[0] != old[0]
    assert new[0].startswith("XAUUSD 15m SELL (confirmed close) | entry 3871.20")   # existing filters and tests key on this
    assert not new[0].startswith(N.RECORD_ONLY) and N.phone_only(new) == new


# ---- the whole run, both modes: only the first line of each SIGNAL alert changes; no record does --------------------
def _ts(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


T0 = _ts("2026-11-06 14:00")
SIG = {"t": T0 + 900, "type": "SIGNAL", "dir": 1, "px": 4000.0, "tq": 70, "sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0,
       "tp3": 4030.0}
REP = {**SIG, "t": T0 + 3600, "px": 4001.0}                                       # the same idea again: a REPEAT
B = [(T0 + 900, 4001, 3999), (T0 + 1800, 4005, 3998), (T0 + 2700, 4006, 3998), (T0 + 3600, 4006, 3998),
     (T0 + 4500, 4013.5, 3998)]                                                    # +$13 is reached on the last bar: TP
RUNS = [  # (t_last, now, markers, bars)
    (T0, "2026-11-06T14:05:00+00:00", [], []),
    (T0 + 1800, "2026-11-06T14:35:00+00:00", [SIG], B[:1]),                       # the alert: FRESH, a plan opens
    (T0 + 2700, "2026-11-06T14:50:00+00:00", [SIG], B[:2]),
    (T0 + 4500, "2026-11-06T15:20:00+00:00", [SIG, REP], B[:4]),                  # the REPEAT: the plan is still open
    (T0 + 5400, "2026-11-06T15:35:00+00:00", [SIG, REP], B),                      # TP hit
    (T0 + 5400, "2026-11-06T22:10:00+00:00", [], []),                             # daily + weekly
]


def _payload(t_last, markers, bars, now):
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": now}, "markers": markers, "decisions": [],
            "news": None, "chart": {"t": [b[0] for b in bars] + [t_last], "h": [b[1] for b in bars] + [None],
                                    "l": [b[2] for b in bars] + [None]}}


def _scenario(tmp_path, monkeypatch, new=True):
    if not new:
        monkeypatch.setattr(N, "signal_head", _old_head)
    raw = []
    monkeypatch.setattr(N, "send", lambda lines: raw.append(list(lines)) or (["test"] if lines else []))
    store = str(tmp_path)
    reps = [N.run(store, {"15m": _payload(t, list(m), list(b), now)}, ["15m"], sent_t=_ts(now[:16].replace("T", " ")))
            for t, now, m, b in RUNS]
    files = {}
    for root, _, fs in os.walk(store):
        for f in fs:
            p = os.path.join(root, f)
            files[os.path.relpath(p, store)] = open(p, "rb").read()
    return raw, reps, files


@pytest.mark.parametrize("mode", ["sixty", "quality"])
def test_whole_run_only_signal_first_lines_change(tmp_path, monkeypatch, mode):
    if mode == "sixty":
        monkeypatch.delenv("ALERT_MODE", raising=False)
    assert N.alert_mode() == mode
    monkeypatch.setenv("PLAN_TP2_USD", "0")
    n_raw, n_reps, n_files = _scenario(tmp_path / "new", monkeypatch, new=True)
    o_raw, o_reps, o_files = _scenario(tmp_path / "old", monkeypatch, new=False)
    assert n_files == o_files and N.VALIDATION in n_files and N.STATE in n_files
    assert [r.get("plans") for r in n_reps] == [r.get("plans") for r in o_reps]
    closed = json.loads(n_files[N.VALIDATION])
    assert [(r["entry"], r["result"]) for r in closed] == [(4000.0, "TP")]          # one plan; the REPEAT opened none

    def heads(raw):
        return [x for m in raw for x in m if x.startswith("XAUUSD 15m BUY (confirmed close)")]
    nh, oh = heads(n_raw), heads(o_raw)
    assert len(nh) == len(oh) == 2
    assert nh[0] == ("XAUUSD 15m BUY (confirmed close) | entry 4000.00 | plan stop SL 3987.00 (-$650) | engine reference "
                     "only, not the plan: SL 3990.00 TP1 4010.00 TP2 4020.00 TP3 4030.00 | TQ 70")
    assert nh[1] == ("XAUUSD 15m BUY (confirmed close) | entry 4001.00 | engine reference only: SL 3990.00 TP1 4010.00 "
                     "TP2 4020.00 TP3 4030.00 | TQ 70")                              # the REPEAT: no plan, no stop named
    swap = dict(zip(nh, oh))
    assert [[swap.get(x, x) for x in m] for m in n_raw] == o_raw                    # nothing else differs, phone or not
    for i in range(len(RUNS)):
        nl, ol = (n_reps[i].get("15m") or {}).get("lines"), (o_reps[i].get("15m") or {}).get("lines")
        assert (nl is None) == (ol is None) and (nl is None or [swap.get(x, x) for x in nl] == ol)   # the website too
