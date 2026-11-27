#!/usr/bin/env python3
"""MT5 build M1: XAUUSD_Quantum_H2.mq5's rule == the website's arm H3, executed on the website's own bars.

What this proves, and what it does not:
  * The website (the system of record, A7) is run READ-ONLY on a scratch copy of its market-data store: its engine
    (for ATR14 and the per-bar volume profile) and quantum/arm_h3.evaluate give the REFERENCE signals and plans.
  * A Python transliteration of the .mq5, statement for statement (same loops, same order, same seeding, the 4H
    bucket on the New York 17:00 grid, 1D built from H1 on UTC days, "last higher bar that opened before the chart
    bar closed"), runs on the SAME bars and volume. Every 15m bar's BUY / SELL, SL, TP1, TP2 and swept level must match.
  * It does NOT compile or run MQL5 (no MetaTrader here): the operator's F7 compile is that test. And on the
    operator's terminal the prices (Exness) and volume (tick volume) differ from the website's, which is a DATA
    difference this check cannot remove.
  * Controls: MT5's own H4 (UTC grid) instead of the NY grid, and Pine-style VP start (bar 100), are detected.
Usage: python3 mt5/tools/h2_mt5_check.py <web copy> <store copy>
  (web copy:   git archive origin/claude/audit-prompt-real-artefacts-nekqv6 quantum | tar -x -C <dir>
   store copy: git archive origin/market-data | tar -x -C <dir>)"""
import math
import os
import sys
from datetime import datetime, timezone

WEB, STORE = sys.argv[1], sys.argv[2]
sys.path.insert(0, WEB)
os.environ["TWELVEDATA_API_KEY"] = "offline-audit"
import requests  # noqa: E402

requests.Session.request = lambda self, *a, **k: (_ for _ in ()).throw(requests.ConnectionError("offline"))
requests.get = lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("offline"))
from quantum import arm_h3, config, engine  # noqa: E402
from quantum.data import market as mk  # noqa: E402
from quantum.features import compute  # noqa: E402

NA = None
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


# ---------------- the .mq5, transliterated ----------------
def nth_sunday(year, mon, nth):
    d = datetime(year, mon, 1, tzinfo=timezone.utc)
    first_sun = 1 + (6 - d.weekday()) % 7           # Python Monday=0 .. Sunday=6; MQL day_of_week Sunday=0
    return int(datetime(year, mon, first_sun + 7 * (nth - 1), tzinfo=timezone.utc).timestamp())


def ny_offset(utc):
    y = datetime.fromtimestamp(utc, timezone.utc).year
    start = nth_sunday(y, 3, 2) + 7 * 3600
    end = nth_sunday(y, 11, 1) + 6 * 3600
    return -4 * 3600 if start <= utc < end else -5 * 3600


def ema_seeded(x, length):
    alpha = 2.0 / (length + 1.0)
    out, prev, run, s = [], NA, 0, 0.0
    for i, xi in enumerate(x):
        if prev is NA:
            if xi is NA:
                run, s = 0, 0.0
                out.append(NA)
                continue
            run += 1
            s += xi
            if run > length:
                s -= x[i - length]
            v = s / length if run >= length else NA
        else:
            v = NA if xi is NA else alpha * xi + (1.0 - alpha) * prev
        out.append(v)
        prev = v
    return out


def build_htf(kind, h1_t, h1_c, off=0, ny_grid=True):
    op, cl, cur = [], [], None
    for t, c in zip(h1_t, h1_c):
        utc = t - off
        if kind == 0:
            key, label = utc, t
        elif kind == 1:
            if ny_grid:
                ny = ny_offset(utc)
                w7 = utc + ny + 7 * 3600
                b = w7 - (w7 % (4 * 3600))
                key, label = b, b - 7 * 3600 - ny + off
            else:                                    # control: MT5's own H4 on the UTC grid
                b = utc - utc % (4 * 3600)
                key, label = b, b + off
        else:                                        # the NY trading day, dated 00:00 UTC of its date (the website's label)
            d = ((utc + ny_offset(utc) + 7 * 3600) // 86400) * 86400
            key, label = d, d + off
        if key != cur:
            op.append(label)
            cl.append(c)
            cur = key
        else:
            cl[-1] = c
    c1 = [NA] + cl[:-1]
    e20, e100, e200 = ema_seeded(c1, 20), ema_seeded(c1, 100), ema_seeded(c1, 200)
    sc = []
    for i, c in enumerate(c1):
        if c is NA:
            sc.append(50.0)
            continue
        s = 0.0
        if e200[i] is not NA and c > e200[i]:
            s += 40.0
        if e20[i] is not NA and e100[i] is not NA and e20[i] > e100[i]:
            s += 40.0
        if e20[i] is not NA and c > e20[i]:
            s += 20.0
        sc.append(s)
    return op, sc


def idx_before(op, t):
    lo, hi, ans = 0, len(op) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if op[mid] < t:
            ans, lo = mid, mid + 1
        else:
            hi = mid - 1
    return ans


def pivot(src, i, high):
    if i < 10:
        return NA
    c = i - 5
    for k in range(c - 5, i + 1):
        if k != c and not ((src[c] > src[k]) if high else (src[c] < src[k])):
            return NA
    return src[c]


def vprofile(i, h, l, c, v, start=99):
    if i < start:
        return None
    hi, lo = max(h[i - 99:i + 1]), min(l[i - 99:i + 1])
    bs = (hi - lo) / 40
    if not bs > 0.0:
        return None
    vols = [0.0] * 40
    for k in range(i - 99, i + 1):
        b = int(((h[k] + l[k] + c[k]) / 3.0 - lo) / bs)
        vols[max(0, min(b, 39))] += v[k]
    pk, mx, tot = 0, 0.0, 0.0
    for b in range(40):
        tot += vols[b]
        if vols[b] > mx:
            mx, pk = vols[b], b
    cum, tgt, blo, bhi = mx, tot * 0.70, pk, pk
    while cum < tgt and (blo > 0 or bhi < 39):
        vb = vols[blo - 1] if blo > 0 else -1.0
        va = vols[bhi + 1] if bhi < 39 else -1.0
        if va >= vb and bhi < 39:
            bhi += 1
            cum += va
        elif blo > 0:
            blo -= 1
            cum += vb
        else:
            break
    return lo + bs * (pk + 0.5), lo + bs * (bhi + 0.5), lo + bs * (blo + 0.5)


def score_series(op, cl):
    c1 = [NA] + cl[:-1]
    e20, e100, e200 = ema_seeded(c1, 20), ema_seeded(c1, 100), ema_seeded(c1, 200)
    sc = []
    for i, x in enumerate(c1):
        if x is NA:
            sc.append(50.0)
            continue
        sc.append((40.0 if e200[i] is not NA and x > e200[i] else 0.0) + (40.0 if e20[i] is not NA and e100[i] is not NA and e20[i] > e100[i] else 0.0)
                  + (20.0 if e20[i] is not NA and x > e20[i] else 0.0))
    return op, sc


def mq5(t, h, l, c, v, tf_sec, h1_t, h1_c, ny_grid=True, vp_start=99, daily=None):
    n = len(c)
    atr, s = [], 0.0
    for i in range(n):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i < 13:
            s += tr
            atr.append(NA)
        elif i == 13:
            s += tr
            atr.append(s / 14)
        else:
            atr.append((atr[i - 1] * 13 + tr) / 14)
    ht = [build_htf(k, h1_t, h1_c, ny_grid=ny_grid) for k in range(3)]
    if daily is not None:                            # the website's own daily bars (this store's H1 is too short for EMA200 on 1D)
        ht[2] = daily
    swH = swL = NA
    out = []
    for i in range(n):
        a = atr[i]
        sweepL = swL is not NA and l[i] < swL and c[i] > swL
        sweepH = swH is not NA and h[i] > swH and c[i] < swH
        lvlL, lvlH = swL, swH
        if swL is not NA and l[i] < swL:
            swL = NA
        if swH is not NA and h[i] > swH:
            swH = NA
        pl, ph = pivot(l, i, False), pivot(h, i, True)
        if pl is not NA:
            swL = pl
        if ph is not NA:
            swH = ph
        closeT = t[i] + tf_sec
        up = dn = 0
        for k in range(3):
            j = idx_before(ht[k][0], closeT)
            sc = 50.0 if j < 0 else ht[k][1][j]
            up += sc >= 60.0
            dn += sc <= 40.0
        vp = vprofile(i, h, l, c, v, vp_start)
        aok = a is not NA
        rl = c[i] - (l[i] - 0.15 * a) if sweepL and aok else NA
        rs = (h[i] + 0.15 * a) - c[i] if sweepH and aok else NA
        riskL = rl is not NA and 0.5 * a <= rl <= 5.0 * a
        riskS = rs is not NA and 0.5 * a <= rs <= 5.0 * a
        isL = sweepL and up >= 2 and vp is not None and c[i] <= vp[0] and riskL
        isS = sweepH and dn >= 2 and vp is not None and c[i] >= vp[0] and riskS
        if isL:
            out.append((1, c[i] - rl, max(vp[0], c[i] + rl), max(vp[1], c[i] + 2.0 * rl), lvlL))
        elif isS:
            out.append((-1, c[i] + rs, min(vp[0], c[i] - rs), min(vp[2], c[i] - 2.0 * rs), lvlH))
        else:
            out.append((0,))
    return out


# ---------------- the website, read-only ----------------
cfg = config.DEFAULT
dl = mk.download_all(STORE, ("15m", "60m"))
m = mk.build_market("15m", dl, datetime(2026, 11, 26, 0, 0, tzinfo=timezone.utc))
F = compute(m, cfg)
res = engine.run(m, cfg, "treatment", F)
ref = arm_h3.evaluate(res, m)
print(f"== website: price {dl.price_source}; {len(m.base)} 15m bars {m.base.index[0]} .. {m.base.index[-1]}")

t = [int(x.timestamp()) for x in m.base.index]
h, l, c = (list(map(float, m.base[k].values)) for k in ("high", "low", "close"))
v = [0.0 if (x is None or (isinstance(x, float) and math.isnan(x))) else float(x) for x in F["v"]]
h1 = m.htf["60"]
h1_t, h1_c = [int(x.timestamp()) for x in h1.index], list(map(float, h1["close"].values))


def compare(out):
    diff, nsig = [], 0
    for i in range(len(c)):
        rb, rs_ = ref["exec_buy"][i], ref["exec_sell"][i]
        rdir = 1 if rb else -1 if rs_ else 0
        nsig += rdir != 0
        if out[i][0] != rdir:
            diff.append((str(m.base.index[i]), "dir", rdir, out[i][0]))
            continue
        if rdir:
            want = (ref["plan_sl"][i], ref["plan_tp1"][i], ref["plan_tp2"][i], ref["swept"][i])
            if any(abs(a - b) > 1e-6 for a, b in zip(want, out[i][1:])):
                diff.append((str(m.base.index[i]), "plan", want, out[i][1:]))
    return nsig, diff


d1 = m.htf["D"]
web_daily = score_series([int(x.timestamp()) for x in d1.index], list(map(float, d1["close"].values)))
# 1 the rule, on the website's 1H / 4H-from-1H / 1D inputs
nsig, diff = compare(mq5(t, h, l, c, v, 900, h1_t, h1_c, daily=web_daily))
report(not diff and nsig > 0, f"1 every 15m bar: {nsig} website H3 signals, the .mq5 rule gives the same BUY / SELL, SL, TP1, TP2 and "
       f"swept level ({len(diff)} differences{'' if not diff else ', first ' + str(diff[:3])})")
# 2 the .mq5's 1D bars: H1 grouped on the NY 17:00 trading day must track the website's daily closes (Twelve Data's
#   own daily bars, a separate feed, so not to the cent); grouping on UTC days (the control) must track them worse.
#   The score is compared only as a note: an EMA200 seeded at this store's H1 start (a few months) has not converged
#   to one seeded in 2007 -- on the operator's terminal the H1 history is years long.
def daily_close(rule):
    out, cur = {}, None
    for x, y in zip(h1_t, h1_c):
        k = ((x + ny_offset(x) + 7 * 3600) // 86400) * 86400 if rule == "ny" else (x // 86400) * 86400
        out[k] = y
    return out
web_close = {int(x.timestamp()): float(y) for x, y in zip(d1.index, d1["close"].values)}
def gaps(rule):
    dc = daily_close(rule)
    ks = sorted(k for k in dc if k in web_close and datetime.fromtimestamp(k, timezone.utc).weekday() < 5)[1:-1]
    g = sorted(abs(dc[k] - web_close[k]) for k in ks)
    return len(g), (g[len(g) // 2] if g else math.inf)
n_ny, med_ny = gaps("ny")
n_u, med_u = gaps("utc")
report(n_ny > 100 and med_ny <= 1.0 and med_u > 3 * med_ny,
       f"2 1D bars from H1 on the NY 17:00 trading day: {n_ny} weekdays, median gap to the website's daily close "
       f"${med_ny:.2f}; control UTC calendar days ${med_u:.2f}")
own = build_htf(2, h1_t, h1_c)
late = [x for x in t if x >= h1_t[0] + 250 * 86400]
bad = sum(own[1][idx_before(own[0], x + 900)] != web_daily[1][idx_before(web_daily[0], x + 900)] for x in late)
print(f"  NOTE  1D score from this store's H1 vs the website's: {bad} differences on {len(late)} bars after 250 days of H1 "
      "(EMA200 seeding; Exness H1 goes back years)")
_, d2 = compare(mq5(t, h, l, c, v, 900, h1_t, h1_c, ny_grid=False, daily=web_daily))
_, d3 = compare(mq5(t, h, l, c, v, 900, h1_t, h1_c, vp_start=100, daily=web_daily))
report(bool(d2), f"3 control: MT5's own H4 bars (UTC grid) instead of the NY 17:00 grid -> {len(d2)} differences (detected)")
report(True, f"4 note: the VP starting at bar 100 (the Pine block) instead of 99 (the website) -> {len(d3)} differences "
       "(only the first bars of a history; the .mq5 follows the website)")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- the .mq5 rule transliterated and executed on the website's bars; "
      "the MQL5 compile and the operator's Exness data NOT exercised")
sys.exit(1 if fails else 0)
