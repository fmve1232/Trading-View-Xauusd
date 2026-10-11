#!/usr/bin/env python3
"""Expectancy / profit-factor / sample-size check (v44), against 'Trading is Math' (S. & H. Burns), ch. 1.

Executes the Pine text AS WRITTEN (pine_exec), never a reconstruction:
  1. the book's worked examples (arithmetic of the definition E = W*AvgWin - L*AvgLoss);
  2. the stats engine's EV line (Strategy.pine): with no timeouts it must equal the book's formula, and with
     timeouts the three rates partition every analog, so EV = W*AvgW - L*AvgL + T*AvgT;
  3. the on-chart scorecard block on random trade histories (split exits, an open position, the start filter):
     N positions, mean $/position (= the book's expectancy), sample SD, profit factor, 95% t-interval, verdict;
  4. the scorecard's 95% t quantile (Fisher expansion) against a numerically integrated Student t;
  5. what 50 trades can show: the 95% interval of each book example's expectancy at n = 50 / 100.
Usage: python3 audit/tools/expectancy_check.py
"""
import math
import os
import random
import re
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pine_exec as P  # noqa: E402

T = "artefacts/XAUUSD_Quantum_5_0_Strategy.pine"
fails = 0


def check(ok, msg):
    global fails
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    fails += 0 if ok else 1


def book(w, aw, al):
    return w * aw - (1 - w) * al


# 1. the book's worked examples
for (w, aw, al, want) in [(0.42, 850, 320, 171.40), (0.68, 280, 650, -17.60), (0.56, 650, 450, 166.0), (0.60, 650, 450, 210.0)]:
    check(abs(book(w, aw, al) - want) < 0.005, f"book example W={w:.2f} AvgWin={aw} AvgLoss={al}: E = {book(w, aw, al):.2f} (book {want})")
check(abs(210 / 166 - 1 - 0.265) < 0.001, "book: raising the win rate 56% -> 60% raises E by 26.5%")

# 2. the engine's EV line, executed
src = open(T, encoding="utf-8").read().split("\n")
ev = next(l.strip() for l in src if l.strip().startswith("_cEvVal := (wr * avgW)"))
rng = random.Random(3)
worst = 0.0
worst2 = 0.0
for _ in range(2000):
    wr, avgW, avgL = rng.uniform(0.05, 0.9), rng.uniform(0.2, 3), rng.uniform(0.2, 3)
    env = P.Env(wr=wr, lr=1 - wr, avgW=avgW, avgL=avgL, tr=0.0, avgT=0.0, _cEvVal=0.0)
    P.run([ev], env)
    worst = max(worst, abs(env["_cEvVal"] - book(wr, avgW, avgL)))
    tr = rng.uniform(0, 0.8) * (1 - wr)
    lr = 1 - wr - tr
    avgT = rng.uniform(-0.5, 0.5)
    env = P.Env(wr=wr, lr=lr, avgW=avgW, avgL=avgL, tr=tr, avgT=avgT, _cEvVal=0.0)
    P.run([ev], env)
    worst2 = max(worst2, abs(env["_cEvVal"] - (wr * avgW - lr * avgL + tr * avgT)))
check(worst < 1e-12, f"engine EV line with no timeouts == book formula: 2000 cases, max |diff| {worst:.1e}")
check(worst2 < 1e-12, f"engine EV with timeouts == W*AvgW - L*AvgL + T*AvgT (rates partition every analog): max |diff| {worst2:.1e}")


# 4 (needed by 3). exact Student-t quantile by numerical integration
def t_pdf(x, v):
    return math.exp(math.lgamma((v + 1) / 2) - math.lgamma(v / 2)) / math.sqrt(v * math.pi) * (1 + x * x / v) ** (-(v + 1) / 2)


def t_q975(v):
    def cdf(x, n=2000):
        h = x / n
        s = t_pdf(0, v) + t_pdf(x, v) + sum((4 if i % 2 else 2) * t_pdf(i * h, v) for i in range(1, n))
        return 0.5 + s * h / 3
    lo, hi = 1.9, 6.0
    for _ in range(50):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if cdf(m) < 0.975 else (lo, m)
    return (lo + hi) / 2


TQ = {}

# 3. the scorecard block, executed
a = next(i for i, l in enumerate(src) if l.strip().startswith("int _fwct = strategy.closedtrades"))
b = next(i for i, l in enumerate(src) if l.strip().startswith("string _fwv ="))
block = [l[4:] for l in src[a:b + 1]]
bad = 0
for case in range(300):
    trades, bar = [], 0
    for _ in range(rng.randint(0, 120)):
        bar += rng.randint(1, 30)
        p = rng.gauss(5, 60)
        if rng.random() < 0.5:
            x = rng.uniform(-1, 1) * abs(p)
            trades += [(bar, bar, x), (bar, bar, p - x)]
        else:
            trades.append((bar, bar, p))
    open_bar = -3
    if trades and rng.random() < 0.3:
        bar += 5
        open_bar = bar
        trades.append((bar, bar, rng.gauss(20, 5)))
    start = rng.choice([0, trades[len(trades) // 3][1] if trades else 0])
    f = {"strategy.closedtrades.entry_bar_index": lambda i: float(trades[int(i)][0]),
         "strategy.closedtrades.entry_time": lambda i: float(trades[int(i)][1]),
         "strategy.closedtrades.profit": lambda i: float(trades[int(i)][2]),
         "strategy.opentrades.entry_bar_index": lambda i: float(open_bar)}
    env = P.Env(funcs=f, **{"strategy.closedtrades": float(len(trades)), "strategy.opentrades": 1.0 if open_bar >= 0 else 0.0,
                            "fwdStart": float(start)})
    P.run(block, env)
    pos = {}
    for eb, et, pr in trades:
        if et >= start and eb != open_bar:
            pos[eb] = pos.get(eb, 0.0) + pr
    x = list(pos.values())
    n = len(x)
    m = sum(x) / n if n else float("nan")
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 1 else float("nan")
    gw, gl = sum(v for v in x if v > 0), -sum(v for v in x if v < 0)
    pf = gw / gl if gl > 0 else float("nan")

    def eq(u, v):
        return (P.isna(u) and v != v) or (not P.isna(u) and v == v and abs(u - v) <= 1e-6 * max(1.0, abs(v)))
    ok = int(env["_fwn"]) == n and eq(env["_fwm"], m) and eq(env["_fwsd"], sd) and eq(env["_fwpf"], pf)
    if n >= 10:
        tq = TQ.setdefault(n - 1, t_q975(n - 1))
        lo = m - tq * sd / math.sqrt(n)
        ok = ok and abs(env["_fwlo"] - lo) <= 0.005 * sd / math.sqrt(n) + 1e-9
        pfok = pf >= 1.2 if gl > 0 else gw > 0
        want = "COLLECTING " + str(n) + "/50" if n < 50 else ("EDGE SHOWN" if lo > 0 and pfok else "NOT SHOWN")
        ok = ok and (env["_fwv"] == want or abs(lo) < 0.005 * sd)
    bad += 0 if ok else 1
check(bad == 0, f"scorecard block (positions, mean = expectancy, SD, PF, 95% t-interval, verdict): 300 random histories, mismatches {bad}")

# 4. Fisher t quantile vs exact
fl = next(l.strip() for l in src if l.strip().startswith("float _fwt = "))
errs = []
for df in (9, 20, 49, 100):
    env = P.Env(_fwdf=float(df), _fwt=0.0)
    P.run([fl], env)
    errs.append((df, env["_fwt"] - t_q975(df)))
check(max(abs(e) for _, e in errs) < 0.005, "scorecard 95% t quantile vs exact Student t: " + ", ".join(f"df {d}: {e:+.4f}" for d, e in errs))

# 5. what n trades can show (binary-outcome SD of each book example)
print("  INFO  95% interval of the expectancy (two-outcome SD = sqrt(W(1-W))*(AvgWin+AvgLoss)):")
for (w, aw, al) in [(0.42, 850, 320), (0.68, 280, 650), (0.56, 650, 450)]:
    e, s = book(w, aw, al), math.sqrt(w * (1 - w)) * (aw + al)
    row = []
    for n in (50, 100):
        h = t_q975(n - 1) * s / math.sqrt(n)
        row.append(f"n={n}: {e:+.1f} [{e - h:+.1f}, {e + h:+.1f}]")
    print(f"        W={w:.2f} {aw}/{al}:  " + "   ".join(row))
print("RESULT: " + ("PASS" if fails == 0 else f"FAIL ({fails})") + " -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
