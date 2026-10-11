#!/usr/bin/env python3
"""Volatility-regime check (v47): executes the Master's regime engine lines AS WRITTEN (pine_exec)
across every ATR percentile and every regime, plus the adaptive-ATR floor, and asserts the invariants
the rest of the engine relies on in LOW / NORMAL / HIGH / ABNORMAL volatility:
  * exactly one regime per bar, in the documented priority ABNORMAL > COMPRESS > EXPANSION > STRONG > WEAK > RANGE;
  * the label (mktRegime) and the volatility tag (LV <= 20th pct, HV >= 80th, else NV) agree with the flags;
  * SL multiple within [1.0, 2.2] and non-decreasing in the ATR percentile for a fixed regime;
  * size guidance 1.0 / 0.75 (HV) / 0.5 (ABNORMAL), confidence cap 60 in ABNORMAL, forecast >= 4 bars;
  * adaptiveATR never 0 or na after the first bar (floor 0.01% of price), so no division by ATR can blow up.
Usage: python3 audit/tools/regime_check.py [file.pine]   (default: the Master)
"""
import os
import random
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pine_exec as P  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "artefacts/XAUUSD_Quantum_5_0_Master.pine"
L = open(path, encoding="utf-8").read().split("\n")
a = next(i for i, l in enumerate(L) if l.strip().startswith("bool regCompression = not regAbnormal"))
b = next(i for i, l in enumerate(L) if l.strip().startswith("int effForecastBars ="))
blk = [l[4:] for l in L[a:b + 1] if l.strip() and not l.strip().startswith("//")]
blk = [l.split("//")[0].rstrip() if '"' not in l.split("//")[0] or l.count('"') % 2 == 0 else l for l in blk]
fails = 0


def check(ok, msg):
    global fails
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    fails += 0 if ok else 1


ORDER = ["ABNORMAL", "COMPRESS", "EXPANSION", "STRONG TR", "WEAK TR", "RANGE"]
rng = random.Random(11)
bad_excl = bad_label = bad_tag = bad_bounds = bad_size = 0
mono = {}
for _ in range(20000):
    pct = rng.uniform(0, 100)
    env = P.Env(regAbnormal=rng.random() < 0.15, bbWidthPct=rng.uniform(0, 100), adxVal=rng.uniform(5, 60),
                atrPercentile=pct, adxThreshold=25.0, adxPct=rng.uniform(0, 100), forecastBars=float(rng.choice([6, 12, 20])))
    env["bbWidthPct"] = P.Series([rng.uniform(0, 100) for _ in range(4)] + [env["bbWidthPct"]])
    env["adxVal"] = P.Series([rng.uniform(5, 60) for _ in range(6)] + [env["adxVal"]])
    P.run(blk, env)
    flags = [env["regAbnormal"], env["regCompression"], env["regExpansion"], env["regStrongTrend"], env["regWeakTrend"]]
    if sum(bool(f) for f in flags) > 1:
        bad_excl += 1
    want = next((ORDER[i] for i, f in enumerate(flags) if f), "RANGE")
    bad_label += env["mktRegime"] != want
    bad_tag += env["volTag"] != ("HV" if pct >= 80 else "LV" if pct <= 20 else "NV")
    bad_bounds += not (1.0 - 1e-12 <= env["regSLMult"] <= 2.2 + 1e-12) or env["effForecastBars"] < 4
    want_size = 0.5 if env["regAbnormal"] else 0.75 if pct >= 80 else 1.0
    bad_size += env["regSizeMult"] != want_size or env["regConfCap"] != (60 if env["regAbnormal"] else 100)
    mono.setdefault(env["mktRegime"], []).append((pct, env["regSLMult"]))
check(bad_excl == 0, f"exactly one regime per bar: 20000 random states, overlaps {bad_excl}")
check(bad_label == 0, f"mktRegime follows the priority ABNORMAL > COMPRESS > EXPANSION > STRONG > WEAK > RANGE: mismatches {bad_label}")
check(bad_tag == 0, f"volTag LV (<=20th pct) / NV / HV (>=80th pct): mismatches {bad_tag}")
check(bad_bounds == 0, f"SL multiple within [1.0, 2.2] and forecast >= 4 bars: violations {bad_bounds}")
check(bad_size == 0, f"size guidance 1.0 / 0.75 (HV) / 0.5 (ABNORMAL) and confidence cap 60 (ABNORMAL): mismatches {bad_size}")
nonmono = 0
for reg, v in mono.items():
    v.sort()
    nonmono += sum(1 for (p1, s1), (p2, s2) in zip(v, v[1:]) if s2 < s1 - 1e-12)
check(nonmono == 0, "SL multiple non-decreasing in the ATR percentile within each regime: " + ", ".join(
    f"{r} {min(s for _, s in v):.2f}-{max(s for _, s in v):.2f}" for r, v in sorted(mono.items())))

atr = next(l.strip() for l in L if l.strip().startswith("adaptiveATR = math.max("))
worst = 1e9
for raw, tr, c in [(P.NA, 0.0, 4100.0), (0.0, 0.0, 4100.0), (1e-9, 0.0, 2000.0), (3.5, 2.0, 4100.0), (P.NA, 1.2, 4100.0)]:
    env = P.Env(_rawAdaptiveATR=raw, close=c, **{"ta.tr": tr})
    P.run([atr], env)
    v = env["adaptiveATR"]
    worst = min(worst, (v / c) if not P.isna(v) else -1)
check(worst >= 0.0001 - 1e-12, f"adaptiveATR floor: never na or below 0.01% of price from the second bar on (na / 0 / 1e-9 inputs), min ratio {worst:.6f}")
env = P.Env(_rawAdaptiveATR=P.NA, close=4100.0, **{"ta.tr": P.NA})
P.run([atr], env)
print("  INFO  first bar of the chart only (no previous close, ta.tr = na): adaptiveATR = " + ("na" if P.isna(env["adaptiveATR"]) else str(env["adaptiveATR"])) + " -- warm-up; every statistic is still empty there")
print("RESULT: " + ("PASS" if fails == 0 else f"FAIL ({fails})") + " -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
