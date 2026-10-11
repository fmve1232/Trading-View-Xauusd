#!/usr/bin/env python3
"""Decision-chain check (v47): executes the Master's trend scores, entry gates, veto and DECISION label lines
AS WRITTEN (pine_exec) on random inputs and asserts:
  * bullTrendScore + bearTrendScore <= 100 (each term is a strict opposite), so with trendThreshold >= 51 (the
    input's minimum) bullTrend and bearTrend are never both true -> BUY and SELL can never fire on the same bar;
  * the entry rule: shouldBuy = trend AND HTF not against AND recent bar AND session >= 30 AND no news AND no
    drawdown breach AND (structure OR displacement) -- every condition is necessary (removing any one blocks);
  * the veto: tqVeto = (TQ < floor) OR (EV < 0) OR calibrated-P veto OR (risk limits ON and risk lock);
  * the DECISION precedence: RISK LOCK > NO TRADE > BUY > SELL > WARMUP > WAIT, and BUY/SELL never shown while vetoed.
Applies to the Master and the Treatment twin (Diagnostics too); Control and Challenger have different entry gates BY DESIGN
(the A/B difference), so their gate lines are not this rule.
Usage: python3 audit/tools/decision_check.py [file.pine]   (default: the Master)"""
import os
import random
import re
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pine_exec as P  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "artefacts/XAUUSD_Quantum_5_0_Master.pine"
L = open(path, encoding="utf-8").read().split("\n")
fails = 0


def check(ok, msg):
    global fails
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    fails += 0 if ok else 1


def line(prefix):
    h = [l.strip() for l in L if l.strip().startswith(prefix)]
    assert len(h) == 1, (prefix, len(h))
    return h[0]


a = next(i for i, l in enumerate(L) if l.startswith("bullTrendScore = 0"))
b = next(i for i, l in enumerate(L) if l.startswith("bearTrend = bearTrendScore >= trendThreshold"))
trend = [l for l in L[a:b + 1] if l.strip() and not l.strip().startswith("//")]
rng = random.Random(21)
over = both = 0
for _ in range(20000):
    e3 = rng.uniform(4000, 4200)
    env = P.Env(close=rng.uniform(4000, 4200), ema200=rng.uniform(4000, 4200), ema100=rng.uniform(4000, 4200),
                ema20=P.Series([e3, 0, 0, rng.uniform(4000, 4200)]), diplus=rng.uniform(5, 40), diminus=rng.uniform(5, 40),
                adxVal=rng.uniform(5, 50), adxThreshold=25.0, highVolume=rng.random() < 0.5, trendThreshold=float(rng.choice([51, 55, 60, 65, 70])))
    if rng.random() < 0.2:
        env["ema100"] = env["close"]
    P.run(trend, env)
    over += env["bullTrendScore"] + env["bearTrendScore"] > 100
    both += bool(env["bullTrend"]) and bool(env["bearTrend"])
check(over == 0, f"bullTrendScore + bearTrendScore <= 100: 20000 random states (incl. ties), violations {over}")
check(both == 0, f"bullTrend and bearTrend never both true at thresholds 51-70 -> BUY and SELL exclusive: violations {both}")

gates = [line("bool buyPreFilters = "), line("shouldBuy = buyPreFilters and")]
names = ["bullTrend", "htfBearScoreGate", "recentBars", "sessionQuality", "inNewsWindow", "_ddBreach"]
bad = 0
for _ in range(5000):
    env = P.Env(bullTrend=rng.random() < .7, htfBearScoreGate=rng.random() < .3, recentBars=rng.random() < .9,
                sessionQuality=float(rng.choice([10, 29, 30, 31, 80])), inNewsWindow=rng.random() < .2, _ddBreach=rng.random() < .1,
                bullStructActive=rng.random() < .4, displacementUp=rng.random() < .3)
    want = (env["bullTrend"] and not env["htfBearScoreGate"] and env["recentBars"] and env["sessionQuality"] >= 30
            and not env["inNewsWindow"] and not env["_ddBreach"] and (env["bullStructActive"] or env["displacementUp"]))
    P.run(gates, env)
    bad += bool(env["shouldBuy"]) != want
check(bad == 0, f"entry rule shouldBuy = trend & HTF not against & recent & session>=30 & no news & no DD & (structure | displacement): 5000 cases, mismatches {bad}")

veto = [line("bool tqVeto = "), line("tqVeto := tqVeto or (useRiskLimits and riskLock)")]
bad = 0
for _ in range(5000):
    ev = rng.choice([P.NA, -0.3, -0.0001, 0.0, 0.4])
    env = P.Env(effTqMinCot=float(rng.choice([0, 40, 55])), tradeQuality=float(rng.randint(0, 100)), planExpectancy=ev,
                _calVeto=rng.random() < .2, useRiskLimits=rng.random() < .8, riskLock=rng.random() < .2)
    want = ((env["effTqMinCot"] > 0 and env["tradeQuality"] < env["effTqMinCot"]) or (not P.isna(ev) and ev < 0)
            or env["_calVeto"] or (env["useRiskLimits"] and env["riskLock"]))
    P.run(veto, env)
    bad += bool(env["tqVeto"]) != want
check(bad == 0, f"veto = TQ<floor | EV<0 | calibrated-P veto | (risk limits & lock); EV na does not veto: 5000 cases, mismatches {bad}")

dec = [line("bool _rkBlockedConf = "), line("bool _tqBlockedConf = "), line("_confDirLabel := _rkBlockedConf")]
bad = shown_vetoed = 0
for _ in range(5000):
    sb = rng.random() < .3
    ss = (not sb) and rng.random() < .3
    env = P.Env(shouldBuy=sb, shouldSell=ss, useRiskLimits=rng.random() < .8, riskLock=rng.random() < .2,
                tqVeto=rng.random() < .4, _statsWarm=rng.random() < .8, _confDirLabel="")
    rk = (sb or ss) and env["useRiskLimits"] and env["riskLock"]
    tq = (sb or ss) and env["tqVeto"]
    want = "RISK LOCK" if rk else "NO TRADE" if tq else "BUY" if sb else "SELL" if ss else "WARMUP" if not env["_statsWarm"] else "WAIT"
    P.run(dec, env)
    bad += env["_confDirLabel"] != want
    shown_vetoed += env["_confDirLabel"] in ("BUY", "SELL") and env["tqVeto"]
check(bad == 0, f"DECISION precedence RISK LOCK > NO TRADE > BUY > SELL > WARMUP > WAIT: 5000 cases, mismatches {bad}")
check(shown_vetoed == 0, f"BUY/SELL never shown on a vetoed bar: {shown_vetoed}")
print("RESULT: " + ("PASS" if fails == 0 else f"FAIL ({fails})") + " -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
