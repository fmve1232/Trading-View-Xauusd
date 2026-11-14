"""P-0 notification delivery integrity (operator, 2026-11-14; docs/deploy/P0_NOTIFICATION_INTEGRITY_SPEC.md §10).

The transport is a stand-in (Net): requests.post / requests.get are replaced, so no request ever leaves a test and
nothing reaches the operator's phone. A test that forgets the stand-in fails (the autouse fixture makes any real
request an error).

Reference case, plan #12 of 13 Nov 2026: the plan's levels, its signal bar, the six REPEAT bars and entries, the
engines' headline SL / TP1 and every send time are the production records' (market-data store @ 8e982370d:
alerts_state.json plan / plan_repeats, alerts_delivery.json). Values the records do not hold (the headlines' TP2 / TP3,
the REPEATs' TQ) are left empty (None), not invented. The price path that closes the plan at TP1 on the 13:15 5m bar
(as recorded) is a minimal fixture, not market data."""
import json
import os
import shutil
from datetime import UTC, datetime

import pytest

from quantum import fwd_b24, holdout
from quantum import notify as N
from quantum.config import DEFAULT

TOPIC = "p0-test-topic-not-a-real-topic"


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp())


T07 = ts("2026-11-13 07:00")                    # plan #12's signal bar (15m, closed 07:15)
ENTRY, SL, TP1, TP2 = 3897.97, 3910.97, 3884.97, 3877.97
OPEN = {"t": T07, "type": "SIGNAL", "dir": -1, "px": ENTRY, "sl": 3909.51, "tp1": 3875.22, "tp2": None, "tp3": None, "tq": 68}
REPEATS = [(ts("2026-11-13 07:15"), 3895.24, 3906.01, 3875.22, ts("2026-11-13 07:34:50")),
           (ts("2026-11-13 07:30"), 3898.36, 3905.42, 3875.22, ts("2026-11-13 07:51:05")),
           (ts("2026-11-13 08:00"), 3897.10, 3905.41, 3875.22, ts("2026-11-13 08:19:11")),
           (ts("2026-11-13 08:15"), 3892.70, 3904.79, 3876.63, ts("2026-11-13 08:36:12")),
           (ts("2026-11-13 08:30"), 3894.53, 3904.79, 3875.22, ts("2026-11-13 08:51:09")),
           (ts("2026-11-13 08:45"), 3896.92, 3904.78, 3875.22, ts("2026-11-13 09:06:06"))]
SIGS = [OPEN] + [{"t": t, "type": "SIGNAL", "dir": -1, "px": px, "sl": sl, "tp1": tp, "tp2": None, "tp3": None, "tq": None}
                 for t, px, sl, tp, _ in REPEATS]
SENT_OPEN, SENT_TP1 = ts("2026-11-13 07:19:35"), ts("2026-11-13 13:21:32")
BLOCK = ["ORIGINAL ALERT NOT DELIVERED — plan #12: 15m SELL, bar closed 07:15 UTC; the 07:19 UTC alert failed twice (ConnectionError)",
         "PLAN #12 LEVELS: entry 3897.97 | SL 3910.97 (-$650) | TP1 3884.97 (+$325 on half, then SL to entry) | TP2 3877.97 (+$500)"]
WARNING = ("DELIVERY WARNING: 1 alert was NOT delivered (13 Nov 07:19 UTC, 15m SELL plan #12, 2 attempts, ConnectionError). "
           "Its levels follow where it matters.")
PREFIX = "UNDELIVERED PLAN #12 (its alert never reached you; if you did not enter it, there is nothing to manage): "
REPEAT_LINE = "REPEAT of #12 (15m SELL from 3897.97 at 07:15 UTC, still open): the same idea -- don't add a trade (no new plan)"
CE = N.requests.exceptions.ConnectionError


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_TP2_USD", "MT5_PRICE_OFFSET", "PLAN_LATE_FRAC", "ALERT_MODE",
              "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL", "DELIVERY_RETRY", "FWD_B24", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(k, raising=False)                # ALERT_MODE unset = sixty, the production mode
    for k in ("ALERT_STRUCTURE", "ALERT_LIQUIDITY", "ALERT_SETUPS", "CONFIRM_PANEL"):
        monkeypatch.setenv(k, "0")
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)

    def no_net(*a, **k):
        raise AssertionError("a real request was attempted")
    monkeypatch.setattr(N.requests, "post", no_net)
    monkeypatch.setattr(N.requests, "get", no_net)
    monkeypatch.setattr(N, "_sleep", lambda s: None)
    N._DELIVERIES.clear()
    yield
    N._DELIVERIES.clear()


class _R:
    def __init__(self, code, body=None, text=""):
        self.status_code, self._b, self.text = code, body, text

    def json(self):
        return self._b


class Net:
    """ntfy / Telegram / Discord stand-in. Script items per channel, consumed in order (default "ok"): "ok" (200, and
    ntfy caches it), an HTTP code, an exception (nothing arrives), or ("arrived", exception): the server got it, the
    client saw the exception (the uncertain case)."""

    def __init__(self, mp, ntfy=(), telegram=(), discord=(), poll="ok"):
        self.script = {"ntfy": list(ntfy), "telegram": list(telegram), "discord": list(discord)}
        self.poll, self.posts, self.polls, self.sleeps, self.cache = poll, [], [], [], []
        mp.setattr(N.requests, "post", self._post)
        mp.setattr(N.requests, "get", self._get)
        mp.setattr(N, "_sleep", self.sleeps.append)

    def _post(self, url, data=None, json=None, headers=None, timeout=None):
        ch = "ntfy" if url.startswith("https://ntfy.sh/") else "telegram" if "api.telegram.org" in url else "discord"
        text = data.decode() if data is not None else (json.get("text") if ch == "telegram" else json.get("content"))
        tag = (headers or {}).get("Tags")
        self.posts.append({"ch": ch, "text": text, "tag": tag, "timeout": timeout, "headers": dict(headers or {}), "url": url})
        out = self.script[ch].pop(0) if self.script[ch] else "ok"
        arrived = out == "ok" or isinstance(out, int) and 200 <= out < 300 or isinstance(out, tuple)
        if arrived and ch == "ntfy":
            self.cache.append(tag)
        if isinstance(out, tuple):
            out = out[1]
        if isinstance(out, BaseException):
            raise out
        return _R(200 if out == "ok" else out, {"id": f"m{len(self.posts)}"})

    def _get(self, url, timeout=None):
        self.polls.append(url.rsplit("since=", 1)[-1])
        if self.poll == "fail":
            raise CE("poll failed")
        rows = [{"event": "open"}] + [{"event": "message", "tags": [t]} for t in self.cache if t]
        return _R(200, text="\n".join(json.dumps(r) for r in rows))

    def texts(self, ch="ntfy"):
        return [p["text"] for p in self.posts if p["ch"] == ch]


def pay15(last_open: int, markers=(), gen=None, low=None):
    t = list(range(ts("2026-11-13 04:00"), last_open + 1, 900))
    lo = [(low or {}).get(x, 3895.0) for x in t]
    meta = {"tf": "15m", "synthetic": False, "generated_utc": datetime.fromtimestamp(gen or last_open + 960, UTC).isoformat(),
            "price_source": "td", "forming": None}
    return {"meta": meta, "markers": [m for m in markers if m["t"] <= last_open], "decisions": [], "dashboard": {},
            "chart": {"t": t, "o": [3896.5] * len(t), "h": [3897.5] * len(t), "l": lo, "c": [3896.5] * len(t)}}


def pay5(last_open: int, low=None):
    t = list(range(ts("2026-11-13 04:00"), last_open + 1, 300))
    lo = [(low or {}).get(x, 3895.0) for x in t]
    meta = {"tf": "5m", "synthetic": False, "generated_utc": datetime.fromtimestamp(last_open + 360, UTC).isoformat(),
            "price_source": "td", "forming": None}
    return {"meta": meta, "markers": [], "decisions": [], "dashboard": {},
            "chart": {"t": t, "o": [3896.5] * len(t), "h": [3897.5] * len(t), "l": lo, "c": [3896.5] * len(t)}}


# The production runs of 13 Nov from 06:50 to the TP1 follow-up: (send time, last closed 15m bar's open, 5m low override)
RUNS = [(ts("2026-11-13 06:50"), ts("2026-11-13 06:30")), (SENT_OPEN, T07)] + \
    [(sent, t) for t, *_, sent in REPEATS[:2]] + [(ts("2026-11-13 08:04:30"), ts("2026-11-13 07:45"))] + \
    [(sent, t) for t, *_, sent in REPEATS[2:]] + [(SENT_TP1, ts("2026-11-13 13:00"))]
TP1_LOW = {ts("2026-11-13 13:15"): 3884.0}               # fixture: the 13:15 5m bar reaches TP1 (recorded t_tp1 13:15)


def timeline(store, net, runs=RUNS, upto=None):
    """Runs plan #12's day on a fresh store (plan_seq 11 before, as in production); returns per-run (report, posts)."""
    os.makedirs(store, exist_ok=True)
    with open(os.path.join(store, N.STATE), "w") as f:
        json.dump({"plan_seq": 11}, f)
    out = []
    for sent, last in runs[:upto]:
        k = len(net.posts)
        last5 = sent - sent % 300 - 300                    # the last 5m bar closed before the send
        rep = N.run(store, {"15m": pay15(last, SIGS, gen=sent - 60), "5m": pay5(last5, TP1_LOW if sent == SENT_TP1 else None)},
                    ["15m"], sent_t=sent)
        out.append((rep, net.posts[k:]))
    return out


def records(store):
    rows = []
    d = os.path.join(store, N.NOTIF_DIR)
    for nm in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        with open(os.path.join(d, nm)) as f:
            rows += [json.loads(x) for x in f if x.strip()]
    return rows


def protected(store):
    """The records P-0 must never change: the alert state (plans, plan_log, plan_repeats, ...), plan_validation.json
    and every research_forward / holdout file, byte for byte."""
    out = {}
    for root, _, names in os.walk(store):
        for nm in names:
            p = os.path.join(root, nm)
            rel = os.path.relpath(p, store)
            if rel in (N.STATE, N.VALIDATION) or rel.startswith(("research_forward", "holdout")):
                with open(p, "rb") as f:
                    out[rel] = f.read()
    return out


# ---------------- T6: the reference case -------------------------------------------------------------------------

def test_t6_plan12_failed_opening_then_six_repeats_and_tp1_carry_the_plan_levels(tmp_path, monkeypatch, capsys):
    net = Net(monkeypatch, ntfy=[CE("Connection aborted."), CE("Connection aborted.")])
    res = timeline(str(tmp_path / "s"), net)
    (_, p0), (rep1, p1) = res[0], res[1]
    assert p0 == []                                                      # the position run sends nothing
    key = N.notif_key([N.event_key("OPEN", "15m", T07, "SELL")])
    assert [p["tag"] for p in p1] == [f"xq-{key}"] * 2 and rep1["15m"]["sent"] == []
    assert p1[0]["text"].startswith("XAUUSD 15m SELL (confirmed close) | entry 3897.97 SL 3909.51 TP1 3875.22")
    assert p1[1]["text"] == "RESENT (first attempt failed: ConnectionError)\n" + p1[0]["text"]
    assert p1[0]["timeout"] == (5, 10) and p1[0]["headers"]["Title"] == "XAUUSD Quantum"
    assert "::warning title=phone alert not delivered::15m OPEN:15m:" in capsys.readouterr().out
    und = json.loads((tmp_path / "s" / N.NOTIFY_STATE).read_text())["open"]["12"]
    assert (und["entry"], und["sl"], und["tp"], und["tp2"], und["final_state"], und["attempts"]) == \
        (ENTRY, SL, TP1, TP2, "RETRY_FAILED", 2)
    msgs = [p[0]["text"].split("\n") for _, p in res[2:] if p]
    assert len(msgs) == 7                                                # six REPEATs and the TP1 follow-up
    assert msgs[0] == [WARNING] + BLOCK + [msgs[0][3], PREFIX + REPEAT_LINE]       # the first accepted one: the warning
    assert msgs[0][3].startswith("XAUUSD 15m SELL (confirmed close) | entry 3895.24 SL 3906.01 TP1 3875.22")
    for i, ((t, px, sl, tp, _), m) in enumerate(zip(REPEATS, msgs[:6], strict=True)):
        m = m[1:] if i == 0 else m                                       # only the first one carries the warning
        assert len(m) == 4 and m[:2] == BLOCK and m[3] == PREFIX + REPEAT_LINE and WARNING not in m
        assert m[2].startswith(f"XAUUSD 15m SELL (confirmed close) | entry {px:.2f} SL {sl:.2f} TP1 {tp:.2f}")
    assert msgs[6][:2] == BLOCK and msgs[6][2].startswith(PREFIX + "XAUUSD 15m YOUR PLAN SELL from 3897.97: TP1 3884.97 HIT +$325 on half")
    assert len(msgs[6]) == 3 and "13 Nov 13:15 UTC" in msgs[6][2]
    st = json.loads((tmp_path / "s" / N.STATE).read_text())               # the plan itself: opened once, TP1, tracked
    assert [p["id"] for p in st["plans"]] == [12] and st["plans"][0]["tp1_sent"] and st["plan_seq"] == 12
    assert [r["of_id"] for r in st["plan_repeats"]] == [12] * 6 and [r["entry"] for r in st["plan_repeats"]] == [x[1] for x in REPEATS]
    # the same day with a working transport: every record byte-identical, every website line identical
    ok = timeline(str(tmp_path / "ok"), Net(monkeypatch))
    assert protected(str(tmp_path / "s")) == protected(str(tmp_path / "ok"))
    assert [r.get("15m", {}).get("lines") for r, _ in res] == [r.get("15m", {}).get("lines") for r, _ in ok]
    assert [r.get("plans") for r, _ in res] == [r.get("plans") for r, _ in ok]
    assert not (tmp_path / "ok" / N.NOTIFY_STATE).exists()                # no failure, no state file


def test_t6_the_opening_attempts_are_recorded_with_their_full_text(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[CE("Connection aborted."), CE("Connection aborted.")])
    timeline(str(tmp_path), net, upto=2)
    rows = [r for r in records(str(tmp_path)) if r["stream"] == "15m"]
    assert [(r["attempt"], r["state"], r["final_state"], r["exception"], r["cache_check"]) for r in rows] == \
        [(1, "SEND_FAILED", "RETRY_FAILED", "ConnectionError", "none"), (2, "RETRY_FAILED", "RETRY_FAILED", "ConnectionError", "miss")]
    assert [r["text"] for r in rows] == [p["text"] for p in net.posts] and rows[0]["plan_ids"] == [12]
    assert rows[1]["trail"] == ["SIGNAL_GENERATED", "SEND_ATTEMPTED", "SEND_FAILED", "SEND_ATTEMPTED", "RETRY_FAILED"]
    assert rows[0]["uncertain"] is True and rows[0]["event_keys"] == [N.event_key("OPEN", "15m", T07, "SELL")]
    assert all(r["t_end"] >= r["t_start"] and r["t_run"] == SENT_OPEN for r in rows)
    win = json.loads((tmp_path / N.DELIVERY).read_text())                # the website's window: same records, no text
    assert [r["rid"] for r in win if r.get("stream") == "15m"] == [r["rid"] for r in rows] and all("text" not in r for r in win)
    assert net.polls == ["6h", "15m"] and net.sleeps == [5]


def test_t6_a_not_actionable_repeat_then_a_fresh_one_the_block_and_prefix_land_on_the_right_lines(tmp_path, monkeypatch):
    """The NOT ACTIONABLE summary line is inserted above the lines of later signals; the line references follow it,
    so the block precedes the summary (it names plan #12's idea) and the prefix lands on the fresh REPEAT line only."""
    net = Net(monkeypatch, ntfy=[CE("aborted"), CE("aborted")])
    store = str(tmp_path)
    timeline(store, net, upto=2)
    late = {"t": ts("2026-11-13 07:45"), "type": "SIGNAL", "dir": -1, "px": 3896.0, "sl": 3905.0, "tp1": 3875.22, "tp2": None,
            "tp3": None, "tq": None}                                     # closed 08:00: 66 minutes before the send
    fresh = {**late, "t": ts("2026-11-13 08:45"), "px": 3896.92}          # closed 09:00: 6 minutes before
    sent = REPEATS[5][4]
    k = len(net.posts)
    N.run(store, {"15m": pay15(ts("2026-11-13 08:45"), [OPEN, late, fresh], gen=sent - 60), "5m": pay5(sent - sent % 300 - 300)},
          ["15m"], sent_t=sent)
    lines = net.posts[k]["text"].split("\n")
    assert lines[0].startswith("DELIVERY WARNING") and lines[1:3] == BLOCK
    assert "NOT ACTIONABLE" in lines[3] and not lines[3].startswith(PREFIX)
    assert lines[4].startswith("XAUUSD 15m SELL (confirmed close) | entry 3896.92") and lines[5] == PREFIX + REPEAT_LINE
    assert len(lines) == 6


# ---------------- T1-T5: the send path ----------------------------------------------------------------------------

def test_t1_first_attempt_succeeds_and_the_text_is_unchanged(tmp_path, monkeypatch):
    net = Net(monkeypatch)
    captured = []
    res = timeline(str(tmp_path / "a"), net, upto=3)
    rows = records(str(tmp_path / "a"))
    assert [(r["attempt"], r["state"], r["final_state"], r["ok"]) for r in rows] == [(1, "SERVER_ACCEPTED", "DELIVERY_UNCONFIRMED", True)] * 2
    assert rows[0]["trail"] == ["SIGNAL_GENERATED", "SEND_ATTEMPTED", "SERVER_ACCEPTED", "DELIVERY_UNCONFIRMED"]
    assert [r["15m"]["sent"] for r, _ in res[1:]] == [["ntfy"], ["ntfy"]] and len(net.posts) == 2 and net.sleeps == []
    # the bytes posted are exactly what the code before P-0 would have posted ("\n".join of the phone lines)
    monkeypatch.setattr(N, "send", lambda lines: captured.append("\n".join(lines)) or (["ntfy"] if lines else []))
    timeline(str(tmp_path / "b"), net, upto=3)
    assert net.texts()[:2] == [c for c in captured if c]
    assert N._EVENTS is None


def test_t2_connection_error_cache_miss_then_the_retry_succeeds_marked_resent(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[CE("Connection aborted.")])
    res = timeline(str(tmp_path), net, upto=2)
    assert len(net.posts) == 2 and net.posts[0]["tag"] == net.posts[1]["tag"] == "xq-" + N.notif_key([N.event_key("OPEN", "15m", T07, "SELL")])
    assert net.posts[1]["text"].split("\n")[0] == "RESENT (first attempt failed: ConnectionError)"
    assert net.posts[1]["text"].split("\n")[1:] == net.posts[0]["text"].split("\n")
    rows = records(str(tmp_path))
    assert [(r["state"], r["cache_check"], r["resent"]) for r in rows] == [("SEND_FAILED", "none", False), ("RETRY_SUCCEEDED", "miss", True)]
    assert {r["final_state"] for r in rows} == {"DELIVERY_UNCONFIRMED"} and res[1][0]["15m"]["sent"] == ["ntfy"]
    assert not (tmp_path / N.NOTIFY_STATE).exists()                       # accepted on the retry: nothing undelivered


def test_t3_both_attempts_fail_warning_on_actions_and_on_the_next_accepted_message_then_cleared(tmp_path, monkeypatch, capsys):
    summ = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    net = Net(monkeypatch, ntfy=[503, 503])
    res = timeline(str(tmp_path / "s"), net, upto=4)
    out = capsys.readouterr().out
    assert out.count("::warning title=phone alert not delivered::") == 1 and "RETRY_FAILED (HTTP 503)" in out
    assert "phone alert not delivered" in summ.read_text() and TOPIC not in out + summ.read_text()
    first, second = res[2][1][0]["text"].split("\n"), res[3][1][0]["text"].split("\n")
    w = "DELIVERY WARNING: 1 alert was NOT delivered (13 Nov 07:19 UTC, 15m SELL plan #12, 2 attempts, HTTP 503)."
    assert first[0] == w + " Its levels follow where it matters." and not any(x.startswith("DELIVERY WARNING") for x in second)
    assert json.loads((tmp_path / "s" / N.NOTIFY_STATE).read_text())["pending_warnings"] == []
    assert first[1].endswith("the 07:19 UTC alert failed twice (HTTP 503)")


def test_t4_read_timeout_after_ntfy_accepted_is_found_in_its_cache_and_not_resent(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[("arrived", N.requests.exceptions.ReadTimeout("read timed out"))])
    res = timeline(str(tmp_path), net, upto=2)
    assert len(net.posts) == 1 and net.polls == ["6h", "15m"]
    rows = records(str(tmp_path))
    assert [(r["attempt"], r["state"], r["cache_check"], r["request"]) for r in rows] == \
        [(1, "SEND_FAILED", "none", True), (2, "RETRY_SUCCEEDED", "hit", False)]
    assert rows[0]["uncertain"] is True and rows[0]["exception"] == "ReadTimeout" and res[1][0]["15m"]["sent"] == ["ntfy"]
    assert {r["final_state"] for r in rows} == {"DELIVERY_UNCONFIRMED"} and not (tmp_path / N.NOTIFY_STATE).exists()


def test_t4b_an_earlier_failure_that_ntfys_cache_shows_did_arrive_is_reclassified_not_claimed_lost(tmp_path, monkeypatch):
    """Both attempts raised, but the server had the second: the next run's cache read removes the undelivered entry and
    its warning, so no message claims the alert never reached the phone."""
    net = Net(monkeypatch, ntfy=[CE("aborted"), ("arrived", N.requests.exceptions.ReadTimeout("read timed out"))])
    res = timeline(str(tmp_path), net, upto=3)
    nxt = res[2][1][0]["text"].split("\n")
    assert not any(x.startswith(("DELIVERY WARNING", "ORIGINAL ALERT")) for x in nxt) and nxt[-1] == REPEAT_LINE
    st = json.loads((tmp_path / N.NOTIFY_STATE).read_text())
    assert st == {"open": {}, "pending_warnings": []}
    assert any(r.get("note", "").startswith("recorded as failed by an earlier run, but found in ntfy's cache") for r in records(str(tmp_path)))


def opening(store, sent):
    return N.run(store, {"15m": pay15(T07, SIGS, gen=sent - 60), "5m": pay5(sent - sent % 300 - 300)}, ["15m"], sent_t=sent)


def _lost_save_runs(tmp_path, net, restore, clear_cache=False):
    """The opening run; then the store put back as it was before it (all of it: a lost store save; or only the alert
    state: a crash before json.dump(state)) and the same invocation again two minutes later (runs never overlap)."""
    store = str(tmp_path / "s")
    timeline(store, net, upto=1)
    snap = str(tmp_path / "snap")
    shutil.copytree(store, snap)
    opening(store, SENT_OPEN)
    if restore == "store":
        shutil.rmtree(store)
        shutil.copytree(snap, store)
    else:
        shutil.copy(os.path.join(snap, N.STATE), os.path.join(store, N.STATE))
    if clear_cache:
        net.cache.clear()
    k = len(net.posts)
    rep = opening(store, SENT_OPEN + 120)
    return store, rep, net.posts[k:]


def test_t5_duplicate_invocation_after_a_lost_store_save_is_not_sent_twice_when_ntfy_holds_it(tmp_path, monkeypatch):
    net = Net(monkeypatch)
    store, rep, posts = _lost_save_runs(tmp_path, net, "store")
    assert posts == [] and rep["15m"]["sent"] == ["ntfy"]
    last = [r for r in records(store) if r["stream"] == "15m"][-1]
    assert (last["attempt"], last["state"], last["found_in"], last["cache_check"]) == (0, "SERVER_ACCEPTED", "cache", "hit")
    st = json.loads(open(os.path.join(store, N.STATE)).read())
    assert [p["id"] for p in st["plans"]] == [12] and st["plan_seq"] == 12  # the plan, recreated once


def test_t5_limitation_a_lost_store_save_with_an_empty_cache_resends_unmarked(tmp_path, monkeypatch):
    """Pinned limitation (spec §4): with the store lost AND nothing in ntfy's cache, no record of the first send
    survives anywhere the run can read, so the message goes out again and cannot be marked as a resend."""
    net = Net(monkeypatch)
    store, rep, posts = _lost_save_runs(tmp_path, net, "store", clear_cache=True)
    assert len(posts) == 1 and not posts[0]["text"].startswith("RESENT") and rep["15m"]["sent"] == ["ntfy"]


def test_t5_crash_before_the_state_was_written_the_stores_own_record_stops_a_resend_on_every_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:telegram-token-not-real")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654")
    net = Net(monkeypatch)
    store, rep, posts = _lost_save_runs(tmp_path, net, "state", clear_cache=True)     # even without ntfy's cache
    assert posts == [] and rep["15m"]["sent"] == ["ntfy", "telegram"]
    opening_recs = [r for r in records(store) if N.event_key("OPEN", "15m", T07, "SELL") in r["event_keys"]]
    assert sum(1 for r in opening_recs if r["request"]) == 2                # one request per channel, ever
    assert {r["found_in"] for r in opening_recs if not r["request"]} == {"record"}


def test_t5_an_earlier_runs_failed_attempt_is_resent_marked(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[CE("aborted"), CE("aborted")])
    store, rep, posts = _lost_save_runs(tmp_path, net, "state")
    assert len(posts) == 1 and posts[0]["text"].startswith("RESENT (an earlier run's attempt failed: ConnectionError)\n")
    assert rep["15m"]["sent"] == ["ntfy"] and "ORIGINAL ALERT" not in posts[0]["text"]     # an opening never gets the block
    assert json.loads(open(os.path.join(store, N.NOTIFY_STATE)).read()) == {"open": {}, "pending_warnings": []}


# ---------------- T7-T9 --------------------------------------------------------------------------------------------

def _one_plan(store, net, d, path_lows, sent2):
    """A 15m plan opened at 07:19:35 whose opening fails twice, then one run at sent2 with the given 5m lows/highs."""
    sig = {**OPEN, "dir": d}
    os.makedirs(store, exist_ok=True)
    with open(os.path.join(store, N.STATE), "w") as f:
        json.dump({"plan_seq": 11}, f)
    N.run(store, {"15m": pay15(ts("2026-11-13 06:30"), [sig])}, ["15m"], sent_t=ts("2026-11-13 06:50"))
    N.run(store, {"15m": pay15(T07, [sig], gen=SENT_OPEN - 60), "5m": pay5(ts("2026-11-13 07:10"))}, ["15m"], sent_t=SENT_OPEN)
    k = len(net.posts)
    p5 = pay5(sent2 - sent2 % 300 - 600, None)
    for i, t in enumerate(p5["chart"]["t"]):
        if t in path_lows:
            p5["chart"]["l"][i], p5["chart"]["h"][i] = path_lows[t]
    rep = N.run(store, {"15m": pay15(sent2 - sent2 % 900 - 900, [sig], gen=sent2 - 60), "5m": p5}, ["15m"], sent_t=sent2)
    return rep, net.posts[k:]


def test_t7_sl_after_a_failed_opening_carries_the_block_and_the_result_is_recorded_as_without_p0(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[CE("aborted"), CE("aborted")])
    t_hit = ts("2026-11-13 09:00")
    rep, posts = _one_plan(str(tmp_path / "f"), net, -1, {t_hit: (3895.0, 3911.5)}, ts("2026-11-13 09:21"))
    lines = posts[0]["text"].split("\n")
    assert lines[1:3] == BLOCK and lines[3].startswith(PREFIX + "XAUUSD 15m YOUR PLAN SELL from 3897.97: SL 3910.97 HIT -$650")
    ok = Net(monkeypatch)
    _one_plan(str(tmp_path / "ok"), ok, -1, {t_hit: (3895.0, 3911.5)}, ts("2026-11-13 09:21"))
    assert protected(str(tmp_path / "f")) == protected(str(tmp_path / "ok"))
    st = json.loads((tmp_path / "f" / N.STATE).read_text())
    assert st["plans"] == [] and st["plan_log"][-1]["result"] == "SL" and st["plan_tally"] == {"SL": 1}
    und = json.loads((tmp_path / "f" / N.NOTIFY_STATE).read_text())["open"]["12"]
    assert und["closed_t"] == ts("2026-11-13 09:21")                      # kept 3 more days, then dropped
    Net(monkeypatch)                                   # a fresh transport (empty cache): only the expiry can remove it
    N.run(str(tmp_path / "f"), {"15m": pay15(ts("2026-11-15 09:15"), [])}, ["15m"], sent_t=ts("2026-11-15 09:30"))
    assert "12" in json.loads((tmp_path / "f" / N.NOTIFY_STATE).read_text())["open"]
    N.run(str(tmp_path / "f"), {"15m": pay15(ts("2026-11-16 09:15"), [])}, ["15m"], sent_t=ts("2026-11-16 09:30"))
    assert json.loads((tmp_path / "f" / N.NOTIFY_STATE).read_text())["open"] == {}


def test_t7_tp1_after_a_failed_opening_and_the_levels_are_the_plans_not_the_current_settings(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[CE("aborted"), CE("aborted")])
    store = str(tmp_path / "f")
    os.makedirs(store)
    sig = {**OPEN, "dir": -1}
    with open(os.path.join(store, N.STATE), "w") as f:
        json.dump({"plan_seq": 11}, f)
    N.run(store, {"15m": pay15(ts("2026-11-13 06:30"), [sig])}, ["15m"], sent_t=ts("2026-11-13 06:50"))
    N.run(store, {"15m": pay15(T07, [sig], gen=SENT_OPEN - 60)}, ["15m"], sent_t=SENT_OPEN)
    monkeypatch.setenv("PLAN_SL_USD", "500")                               # the operator changes the plan afterwards
    monkeypatch.setenv("PLAN_TP_USD", "400")
    k = len(net.posts)
    N.run(store, {"15m": pay15(ts("2026-11-13 09:00"), [sig], low={ts("2026-11-13 09:00"): 3884.0}, gen=ts("2026-11-13 09:16"))},
          ["15m"], sent_t=ts("2026-11-13 09:19"))
    lines = net.posts[k]["text"].split("\n")
    assert lines[1:3] == BLOCK and lines[3].startswith(PREFIX + "XAUUSD 15m YOUR PLAN SELL from 3897.97: TP1 3884.97 HIT +$325 on half")


def test_t8_two_channels_ntfy_fails_telegram_accepts_so_it_counts_as_delivered_to_a_server(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:telegram-token-not-real")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654")
    net = Net(monkeypatch, ntfy=[CE("aborted"), CE("aborted")])
    res = timeline(str(tmp_path), net, upto=3)
    assert res[1][0]["15m"]["sent"] == ["telegram"]
    rows = [r for r in records(str(tmp_path)) if r["t_run"] == SENT_OPEN]
    assert {r["final_state"] for r in rows} == {"DELIVERY_UNCONFIRMED"}
    assert {(r["channel"], r["channel_final"]) for r in rows} == {("ntfy", "RETRY_FAILED"), ("telegram", "DELIVERY_UNCONFIRMED")}
    assert "15m on ntfy: RETRY_FAILED" in capsys.readouterr().out
    nxt = res[2][1][0]["text"].split("\n")
    assert not any(x.startswith(("DELIVERY WARNING", "ORIGINAL ALERT", "UNDELIVERED")) for x in nxt)
    tg = [p for p in net.posts if p["ch"] == "telegram"]
    assert "123456:telegram-token-not-real" in tg[0]["url"] and not any("telegram-token-not-real" in json.dumps(r) for r in records(str(tmp_path)))


def test_t9_no_channel_configured_is_send_failed_and_said(tmp_path, monkeypatch, capsys):
    """No channel at all: recorded SEND_FAILED and an Actions warning every time, but no phone-facing state (no
    pending DELIVERY WARNING, no UNDELIVERED block): there is no phone to tell, and a later setup must not open with a
    flood of stale warnings (review finding, 2026-11-14)."""
    monkeypatch.delenv("NTFY_TOPIC")
    timeline(str(tmp_path), Net(monkeypatch), upto=2)
    rows = records(str(tmp_path))
    assert [(r["channel"], r["state"], r["exception"], r["request"]) for r in rows] == [(None, "SEND_FAILED", "no channel configured", False)]
    assert "no channel configured" in capsys.readouterr().out
    assert not (tmp_path / N.NOTIFY_STATE).exists()


def test_t9_invalid_credentials_401_is_not_retried(tmp_path, monkeypatch, capsys):
    net = Net(monkeypatch, ntfy=[401])
    timeline(str(tmp_path), net, upto=2)
    assert len(net.posts) == 1 and net.sleeps == [] and net.polls == ["6h"]
    r = records(str(tmp_path))[0]
    assert (r["state"], r["http"], r["no_retry"], r["final_state"]) == ("SEND_FAILED", 401, "not retryable", "SEND_FAILED")
    assert "credentials or topic rejected" in capsys.readouterr().out


@pytest.mark.parametrize("code", [400, 403, 404, 413])
def test_other_4xx_are_not_retried(tmp_path, monkeypatch, code):
    net = Net(monkeypatch, ntfy=[code])
    timeline(str(tmp_path), net, upto=2)
    assert len(net.posts) == 1


@pytest.mark.parametrize("fail", [429, 500, 502, 503, 504, "timeout", "chunked", "reset"])
def test_retryable_failures_are_retried_once(tmp_path, monkeypatch, fail):
    exc = {"timeout": N.requests.exceptions.ConnectTimeout("connect timed out"),
           "chunked": N.requests.exceptions.ChunkedEncodingError("broken"), "reset": ConnectionResetError("reset")}.get(fail, fail)
    net = Net(monkeypatch, ntfy=[exc])
    timeline(str(tmp_path), net, upto=2)
    assert len(net.posts) == 2 and records(str(tmp_path))[-1]["state"] == "RETRY_SUCCEEDED"


def test_a_failed_poll_before_the_retry_fails_open_and_resends(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[CE("aborted")], poll="fail")
    timeline(str(tmp_path), net, upto=2)
    assert len(net.posts) == 2 and records(str(tmp_path))[-1]["cache_check"] == "unavailable"


def test_per_run_budget_a_channel_that_failed_twice_gets_one_attempt_for_the_rest_of_the_run(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[CE("a"), CE("b"), CE("c")])
    N._RUN = N._new_ctx(None, SENT_OPEN)
    try:
        N._say("one", ["first message"])
        N._say("two", ["second message"])
    finally:
        N._RUN = None
    assert [p["text"].split("\n")[-1] for p in net.posts] == ["first message", "first message", "second message"]
    assert N._DELIVERIES[-1]["no_retry"] == "channel failed twice earlier in this run"


def test_kill_switch_delivery_retry_0_one_attempt_no_cache_reads_blocks_still_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("DELIVERY_RETRY", "0")
    net = Net(monkeypatch, ntfy=[CE("aborted")])
    res = timeline(str(tmp_path), net, upto=3)
    assert len(res[1][1]) == 1 and net.polls == [] and net.sleeps == []
    assert res[2][1][0]["text"].split("\n")[1] == BLOCK[0].replace("failed twice", "failed")


# ---------------- review findings of 2026-11-14 (each test fails on the code before its fix) ----------------------

def _ctx_with_warning(store, t_run, key="zzzzzzzzzz"):
    R = N._new_ctx(store, t_run)
    R["state"]["pending_warnings"] = [{"id": f"{key}:1", "t": SENT_OPEN, "stream": "15m", "desc": "15m SELL plan #12",
                                       "attempts": 2, "why": "ConnectionError", "notif_key": key, "parts": 1, "open_plan": True}]
    return R


def test_a_message_skipped_as_already_delivered_does_not_clear_a_warning_it_never_showed(tmp_path, monkeypatch):
    net = Net(monkeypatch)
    net.cache.append("xq-" + N.notif_key(["OPEN:15m:1:SELL"]))           # an earlier run delivered this one
    N._RUN = _ctx_with_warning(str(tmp_path), SENT_OPEN)
    try:
        N._say("15m", ["regenerated opening"], ["OPEN:15m:1:SELL"])        # skipped: nothing posted
        assert net.posts == [] and len(N._RUN["state"]["pending_warnings"]) == 1
        N._say("news", ["XAUUSD NEWS WINDOW"], ["NEWS:1"])                 # really sent: carries the warning, then clears it
        assert net.posts[0]["text"].startswith("DELIVERY WARNING: 1 alert was NOT delivered")
        assert N._RUN["state"]["pending_warnings"] == []
    finally:
        N._RUN = None


def test_a_message_never_carries_a_warning_about_itself_and_its_acceptance_clears_it(tmp_path, monkeypatch):
    net = Net(monkeypatch)
    key = N.notif_key(["OPEN:15m:1:SELL"])
    N._RUN = _ctx_with_warning(str(tmp_path), SENT_OPEN, key)             # its own failure, from a run that crashed
    try:
        N._say("15m", ["the opening, sent again"], ["OPEN:15m:1:SELL"])
        assert not net.posts[0]["text"].startswith("DELIVERY WARNING") and N._RUN["state"]["pending_warnings"] == []
    finally:
        N._RUN = None


def test_a_cache_hit_recorded_by_an_earlier_run_counts_as_delivered_in_the_stores_record(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=[("arrived", N.requests.exceptions.ReadTimeout("read timed out"))])
    for t_run in (SENT_OPEN, SENT_OPEN + 120):                            # the second run: the state was lost, the cache
        if t_run != SENT_OPEN:                                            # cannot be read; only the store's record knows
            net.poll = "fail"
        N._RUN = N._new_ctx(str(tmp_path), t_run)
        try:
            N._say("15m", ["the opening"], ["OPEN:15m:1:SELL"])
        finally:
            N._RUN = None
    assert len(net.posts) == 1                                            # never re-sent as "RESENT (... ReadTimeout)"
    assert records(str(tmp_path))[-1]["found_in"] == "record"


def test_a_split_opening_whose_first_part_arrived_is_not_registered_as_undelivered(tmp_path, monkeypatch):
    net = Net(monkeypatch, ntfy=["ok", CE("a"), CE("b")])                 # part 1 accepted, part 2 fails twice
    head = "XAUUSD 15m SELL (confirmed close) | entry 3897.97 SL 3909.51 TP1 3875.22 TP2 — TP3 — | TQ 68"
    lines = [head, "YOUR PLAN 0.5 lot: SL 3910.97 (-$650)"] + [f"filler {i:03d} " + "x" * 90 for i in range(45)]
    plan = {"id": 12, "tf": "15m", "t": T07, "dir": -1, "entry": ENTRY, "sl": SL, "tp": TP1, "tp2": TP2, "sl_usd": 650.0,
            "tp_usd": 650.0, "tp2_usd": 1000.0, "t_dec": T07 + 900}
    N._RUN = N._new_ctx(str(tmp_path), SENT_OPEN)
    try:
        N._say_tf("15m", lines, [], [(0, "HEAD", OPEN), (1, "BODY", OPEN)], 0, {T07: 12}, {}, [plan], 0.0, T07)
        assert len(net.posts) == 3 and N._RUN["state"]["open"] == {}
        assert N._RUN["state"]["pending_warnings"][0]["desc"].endswith("(only partly delivered)")
    finally:
        N._RUN = None


def test_the_run_budget_stops_retries_and_cache_reads_once_spent(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "DELIVERY_BUDGET_SEC", 0)
    net = Net(monkeypatch, ntfy=[CE("a")])
    N._RUN = N._new_ctx(str(tmp_path), SENT_OPEN)
    try:
        N._say("15m", ["one message"], ["OPEN:15m:1:SELL"])
    finally:
        N._RUN = None
    assert len(net.posts) == 1 and net.polls == [] and N._DELIVERIES[-1]["no_retry"] == "delivery time budget of this run used up"


def test_records_are_one_file_per_run_day(tmp_path, monkeypatch):
    timeline(str(tmp_path), Net(monkeypatch), upto=2)
    assert os.listdir(tmp_path / N.NOTIF_DIR) == ["2026-11-13.jsonl"]


# ---------------- T10: length limits ---------------------------------------------------------------------------------

def test_t10_long_bodies_are_split_in_order_and_never_cut(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/api/webhooks/1/discord-token-not-real")
    net = Net(monkeypatch)
    body = [f"line {i:03d} " + "x" * 90 for i in range(60)] + ["é" * 2000]   # 6 KB, and one line longer than a part
    N._say("long", body)
    for ch, lim, size in (("ntfy", 4096, lambda s: len(s.encode())), ("discord", 2000, len)):
        parts = [p for p in net.posts if p["ch"] == ch]
        n = len(parts)
        assert n >= 2 and all(size(p["text"]) <= lim for p in parts)
        assert [p["text"].split(" ", 1)[0] for p in parts] == [f"({i}/{n})" for i in range(1, n + 1)]
        joined = "\n".join(p["text"].split(" ", 1)[1] for p in parts)
        assert joined.replace("\n", "") == "\n".join(body).replace("\n", "")   # every character, in order
    assert [p["tag"] for p in net.posts if p["ch"] == "ntfy"][:2] == [f"xq-{N._DELIVERIES[0]['notif_key']}-1", f"xq-{N._DELIVERIES[0]['notif_key']}-2"]
    assert not any("discord-token-not-real" in json.dumps(r) for r in N._DELIVERIES)


def test_t10_the_warning_and_the_block_are_in_part_one():
    lines = ["DELIVERY WARNING: x"] + BLOCK + ["y" * 300] * 30
    parts = N.split_parts(lines, "ntfy")
    assert len(parts) == 3 and parts[0][:3] == ["(1/3) DELIVERY WARNING: x"] + BLOCK
    assert N.split_parts(["short"], "discord") == [["short"]]


@pytest.mark.parametrize(("nbytes", "parts"), [(3946, 1), (3985, 1), (3986, 2), (4083, 2), (4496, 2)])
def test_t10_ntfy_splits_only_what_could_pass_4096_bytes_once_marked_resent(nbytes, parts):
    """12 Nov replay sizes (ALERT_MODE=all): up to 3,946 bytes was shown in full and stays one message; 4,083 fits
    today but not with a RESENT line; over 4,096 ntfy made an attachment. Sixty mode (production) peaked at 1,250."""
    body = ["a" * 99] * (nbytes // 100) + ["b" * (nbytes - 100 * (nbytes // 100))]    # 99 + "\n" per line
    assert len("\n".join(body).encode()) == nbytes
    got = N.split_parts(body, "ntfy")
    assert len(got) == parts and all(len("\n".join(N._marked(p, ["x" * 200], "ntfy", "t")).encode()) <= 4096 for p in got)


# ---------------- T11 / T12: records and invariants -------------------------------------------------------------------

@pytest.mark.parametrize("script", [[], [CE("a")], [CE("a"), CE("b")], [("arrived", N.requests.exceptions.ReadTimeout("t"))],
                                    [401], [503, 503]])
def test_t11_the_plans_and_every_record_are_identical_whatever_the_delivery(tmp_path, monkeypatch, script):
    res = timeline(str(tmp_path / "x"), Net(monkeypatch, ntfy=list(script)))
    ok = timeline(str(tmp_path / "ok"), Net(monkeypatch))
    assert protected(str(tmp_path / "x")) == protected(str(tmp_path / "ok"))
    assert [r.get("15m", {}).get("lines") for r, _ in res] == [r.get("15m", {}).get("lines") for r, _ in ok]
    st = json.loads((tmp_path / "x" / N.STATE).read_text())
    assert st["plan_seq"] == 12 and len(st["plans"]) == 1                 # one plan; six REPEATs, no plan from them


def test_t12_engine_sources_freeze_key_and_b24_untouched():
    assert holdout.freeze_key(DEFAULT) == "5e4630924d663fc5:a6f2be58c74887ed"   # every engine source, pipeline included
    assert "notify.py" not in holdout.ENGINE_SOURCES and fwd_b24.on() is False


def test_states_never_say_delivered():
    assert N.FINAL_OK == "DELIVERY_UNCONFIRMED" and set(N.ACCEPTED) == {"SERVER_ACCEPTED", "RETRY_SUCCEEDED"}
    src = open(N.__file__).read()
    assert '"DELIVERED"' not in src and "'DELIVERED'" not in src


# ---------------- T13: the module-level context -----------------------------------------------------------------------

def test_t13_events_are_cleared_after_every_send_even_when_send_is_replaced_or_fails(monkeypatch):
    Net(monkeypatch)
    N._say("x", ["a"], ["E:1"])
    assert N._EVENTS is None
    monkeypatch.setattr(N, "send", lambda lines: [])
    N._say("x", ["a"], ["E:1"])
    assert N._EVENTS is None

    def boom(lines):
        raise RuntimeError("send failed")
    monkeypatch.setattr(N, "send", boom)
    with pytest.raises(RuntimeError):
        N._say("x", ["a"], ["E:1"])
    assert N._EVENTS is None


def test_t13_a_send_without_events_is_recorded_under_a_content_key(monkeypatch):
    net = Net(monkeypatch)
    N._EVENTS = {"stream": "stale", "events": ["LEFT:OVER"]}
    N._say("fresh", ["hello"])                                            # _say sets its own context ...
    N.send(["plain"])                                                     # ... and a bare send has none left over
    a, b = N._DELIVERIES[-2:]
    assert a["event_keys"][0].startswith("CONTENT:fresh:") and b["stream"] == "unlabelled"
    assert b["event_keys"][0].startswith("CONTENT:unlabelled:")
    assert "LEFT:OVER" not in json.dumps(N._DELIVERIES) and len(net.posts) == 2


def test_identical_content_in_a_later_run_is_sent_again_as_before(tmp_path, monkeypatch):
    """Lines without an event of their own (structure / H-setup info in the all / quality modes) were re-sent by
    every run that produced them; P-0 must not start suppressing them (12 Nov replay, ALERT_MODE=all: 127 messages
    would have been)."""
    net = Net(monkeypatch)
    for t_run in (SENT_OPEN, SENT_OPEN + 900):
        N._RUN = N._new_ctx(str(tmp_path), t_run)
        try:
            N._say("4h", ["XAUUSD 4h H4 SELL entry 3942.65 [forward record] | info, not a DECISION"])
        finally:
            N._RUN = None
    assert len(net.posts) == 2 and net.posts[0]["tag"] != net.posts[1]["tag"]


def test_run_clears_its_context_even_when_it_fails(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("plan update failed")
    monkeypatch.setattr(N, "plan_updates", boom)
    with open(tmp_path / N.STATE, "w") as f:
        json.dump({"15m": ts("2026-11-13 06:30")}, f)
    with pytest.raises(RuntimeError):
        N.run(str(tmp_path), {"15m": pay15(T07, [OPEN])}, ["15m"], sent_t=SENT_OPEN)
    assert N._RUN is None and N._EVENTS is None


# ---------------- secrets, the ledger merge -----------------------------------------------------------------------------

def test_secrets_never_reach_a_record_or_the_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/api/webhooks/1/discord-token-not-real")
    Net(monkeypatch, ntfy=[CE(f"HTTPSConnectionPool(host='ntfy.sh'): Max retries exceeded with url: /{TOPIC}"), CE(f"/{TOPIC} down")],
        discord=[CE("POST /api/webhooks/1/discord-token-not-real failed"), CE("again /api/webhooks/1/discord-token-not-real")])
    N._RUN = N._new_ctx(str(tmp_path), SENT_OPEN)
    try:
        N._say("secret-check", ["XAUUSD test"])
    finally:
        N._RUN = None
    blob = json.dumps(records(str(tmp_path))) + json.dumps(N._DELIVERIES) + capsys.readouterr().out
    assert TOPIC not in blob and "discord-token-not-real" not in blob and "***" in blob


def test_ledger_merge_is_a_union_so_a_store_that_went_back_never_removes_a_record(tmp_path):
    src, dst = tmp_path / "store" / "notifications", tmp_path / "ledger" / "notifications"
    src.mkdir(parents=True)
    (src / "2026-11.jsonl").write_text('{"rid": "a"}\n{"rid": "b"}\n')
    assert N.merge_ledger(str(src), str(dst)) == 2
    (src / "2026-11.jsonl").write_text('{"rid": "a"}\n{"rid": "c"}\n')     # the store went back (lost "b"), then gained "c"
    assert N.merge_ledger(str(src), str(dst)) == 1
    assert (dst / "2026-11.jsonl").read_text() == '{"rid": "a"}\n{"rid": "b"}\n{"rid": "c"}\n'
    assert N.merge_ledger(str(src), str(dst)) == 0


def test_the_workflow_merges_the_records_into_the_ledger_and_passes_the_kill_switch():
    wf = open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "quantum-site.yml")).read()
    run = wf[wf.index("- name: Run pipeline"):wf.index("- name: Upcoming events")]
    led = wf[wf.index("- name: Save the forward ledger"):wf.index("- uses: actions/configure-pages")]
    assert "DELIVERY_RETRY: ${{ vars.DELIVERY_RETRY }}" in run
    assert "python -m quantum.notify --merge-ledger store/notifications ledger/notifications ||" in led
    assert led.index("--merge-ledger") < led.index("cd ledger")             # before the ledger commit
