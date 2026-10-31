#!/usr/bin/env python3
"""v90 independent audit, Stage 3: do the checkers catch REAL defects? (mutation testing, read-only on the baseline)

Each mutant is ONE realistic defect seeded into a scratch COPY of the repository (never into artefacts/ here). The
checker suite runs on the copy; a mutant is KILLED when at least one checker exits non-zero. A SURVIVING mutant is a
class of defect the suite cannot see. Usage: python3 audit/tools/v90_mutation.py <scratch_dir> [mutant ids]"""
import os, re, shutil, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
M, V, S, H2 = ("artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_5_Visuals.pine",
               "artefacts/XAUUSD_Quantum_5_0_Strategy.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy_H2.pine")
# id: (description, [(file, old, new)])  -- old must occur exactly once
MUT = {
 "m01": ("repaint: daily close request without [1] (live bar's close leaks into history)",
         [(M, 'float _dC1 = request.security(syminfo.tickerid, "D", close[1], barmerge.gaps_off, barmerge.lookahead_on)',
              'float _dC1 = request.security(syminfo.tickerid, "D", close, barmerge.gaps_off, barmerge.lookahead_on)')]),
 "m02": ("Kelly: wrong sign of the loss term",
         [(M, "float _rawKelly = (p * b - (1.0 - p)) / b * 100.0", "float _rawKelly = (p * b + (1.0 - p)) / b * 100.0")]),
 "m03": ("lot size rounds to NEAREST (risk can exceed the ceiling)",
         [(M, "float _lotsFloored = math.floor(_rawLots / 0.01) * 0.01", "float _lotsFloored = math.round(_rawLots / 0.01) * 0.01")]),
 "m04": ("outcome race off by one bar (scan stops one bar early)",
         [(M, "int _oScan = math.max(OUTCOME_N - 60, 0)", "int _oScan = math.max(OUTCOME_N - 60, 1)")]),
 "m05": ("DST: US DST starts on the FIRST Sunday of March",
         [(M, "usDstStartDom := _firstSunDom + 7 // 2nd Sunday of March", "usDstStartDom := _firstSunDom // 2nd Sunday of March")]),
 "m06": ("entry gate: session floor 30 -> 20 (Master only)",
         [(M, "bool buyPreFilters = bullTrend and not htfBearScoreGate and recentBars and sessionQuality >= 30",
              "bool buyPreFilters = bullTrend and not htfBearScoreGate and recentBars and sessionQuality >= 20")]),
 "m07": ("regime size haircut 0.5 -> 0.6 (engine constant, all four engine copies? no: Master only)",
         [(M, "float regSizeMult = regAbnormal ? 0.5 :", "float regSizeMult = regAbnormal ? 0.6 :")]),
 "m08": ("dashboard: L and S scores swapped in the SIGNAL cell",
         [(M, '"\\nscore L " + _si(na(fBullScore) ? 50 : fBullScore) + " S " + _si(na(fBearScore) ? 50 : fBearScore)',
              '"\\nscore L " + _si(na(fBearScore) ? 50 : fBearScore) + " S " + _si(na(fBullScore) ? 50 : fBullScore)')]),
 "m09": ("PDH pool reads the previous day's LOW",
         [(M, "poolPdH := _tfAboveD ? na : prevNyDailyHigh", "poolPdH := _tfAboveD ? na : prevNyDailyLow")]),
 "m10": ("alert fires mid-candle (barstate.isconfirmed dropped from BUY alertcondition)",
         [(M, "alertcondition(shouldBuy and not tqVeto and not perfMode and barstate.isconfirmed,",
              "alertcondition(shouldBuy and not tqVeto and not perfMode,")]),
 "m11": ("plan expectancy ignores the cost term",
         [(M, "planExpectancy := _pW * tpRR1 - _pL + _pT - _cR", "planExpectancy := _pW * tpRR1 - _pL + _pT")]),
 "m12": ("Visuals EMA20 colour no longer white",
         [(V, "cFast   = #FFFFFF", "cFast   = #FFEB3B")]),
 "m13": ("engine change applied to ALL engine copies consistently: abnormal ATR multiple 2.5 -> 2.0",
         [(f, "(atrSma100R > 0 and adaptiveATR > atrSma100R * 2.5)", "(atrSma100R > 0 and adaptiveATR > atrSma100R * 2.0)")
          for f in (M, S, "artefacts/XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine",
                    "artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine", "artefacts/XAUUSD_Quantum_5_0_Brief.pine")]),
 "m14": ("Visuals cost row drops commission",
         [(V, "float ckCost = (ckSpread + 2.0 * slippagePts) + commissionL / math.max(pointValue, 1.0)",
              "float ckCost = (ckSpread + 2.0 * slippagePts)")]),
 "m15": ("scorecard PF rule 1.2 -> 1.0 in the three twins identically",
         [(f, "bool _fwpfOk = _fwgl > 0 ? _fwpf >= 1.2 : _fwgw > 0", "bool _fwpfOk = _fwgl > 0 ? _fwpf >= 1.0 : _fwgw > 0")
          for f in (S, "artefacts/XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine")]),
 "m16": ("H2 sweep uses close >= level (identical in all three H2 copies)",
         [(f, "bool h2SweepL = barstate.isconfirmed and not na(h2SwL) and low < h2SwL and close > h2SwL",
              "bool h2SweepL = barstate.isconfirmed and not na(h2SwL) and low < h2SwL and close >= h2SwL") for f in (M, V, H2)]),
 "m17": ("CDH resets on the wrong boundary (never resets: running max of all history)",
         [(M, "if crossedNYDay\n    cdh := high\n    cdl := low", "if false\n    cdh := high\n    cdl := low")]),
 "m18": ("Wilson lower bound uses z = 1.645 instead of 1.96 in Kelly",
         [(M, "float _zWK = 1.96", "float _zWK = 1.645")]),
}
SUITE = ["precheck", "undeclared", "order", "deadcode", "pinelimits", "diag_parity", "decision_check", "regime_check",
         "expectancy_check", "formula_trace", "h2_parity", "h2_trace", "h2_age_check", "panel_check", "v88_check",
         "refactor_check", "inputs_check", "bug_scan", "pine_web_parity", "macro_check", "moved_check", "edgecase_cites",
         "value_map --check", "v86_check", "compile_est", "brief_trace", "v91_check"]
STATIC = {"precheck", "undeclared", "order", "deadcode", "pinelimits"}


BUG_BASE = 14   # baseline R1 + A1 + R4 hits, all triaged (Visuals A1 11, R4 3)
TRIPWIRE = {"refactor_check", "edgecase_cites", "value_map", "moved_check"}   # fail on ANY text change of their anchors


def run(work, t):
    a = t.split()
    cmd = ["python3", f"audit/tools/{a[0]}.py"] + a[1:] + (sorted(f"artefacts/{x}" for x in os.listdir(os.path.join(work, "artefacts"))) if a[0] in STATIC else [])
    env = dict(os.environ, GIT_DIR=os.path.join(REPO, ".git"), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=900, env=env)
    out = r.stdout + r.stderr
    if a[0] == "v86_check" and r.returncode:                  # section 9 = "only the stamp and that line differ": a tripwire
        fl = [l for l in out.split("\n") if l.strip().startswith("FAIL")]
        return "trip" if fl and all(l.strip().startswith("FAIL  9 ") for l in fl) else "sem"
    if a[0] == "bug_scan":                                     # exits 0 by design: read its R1 / A1 / R4 hit counts instead
        hit = sum(int(m) for m in re.findall(r"\b(?:R1|A1|R4) (\d+)", out)) > BUG_BASE   # more hits than the triaged baseline
        return "sem" if hit else "ok"
    if r.returncode == 0:
        return "ok"
    return "trip" if a[0] in TRIPWIRE else "sem"


def main():
    scratch = sys.argv[1]
    ids = sys.argv[2:] or sorted(MUT)
    base = os.path.join(scratch, "base")
    out = []
    for mid in ids:
        desc, edits = MUT[mid]
        work = os.path.join(scratch, mid)
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(base, work)
        for f, old, new in edits:
            p = os.path.join(work, f)
            s = open(p, encoding="utf-8").read()
            assert s.count(old) == 1, f"{mid}: anchor found {s.count(old)} times in {f}"
            open(p, "w", encoding="utf-8").write(s.replace(old, new))
        t0 = time.time()
        res = {t.split()[0]: run(work, t) for t in SUITE}
        shutil.rmtree(work)
        sem = [k for k, v in res.items() if v == "sem"]
        trip = [k for k, v in res.items() if v == "trip"]
        verdict = "CAUGHT" if sem else "TRIPWIRE-ONLY" if trip else "MISSED"
        print(f"{mid} {verdict:13s} {desc}\n      semantic: {', '.join(sem) or '-'} | tripwire: {', '.join(trip) or '-'}  ({time.time() - t0:.0f}s)", flush=True)
        out.append((mid, verdict))
    for v in ("CAUGHT", "TRIPWIRE-ONLY", "MISSED"):
        print(f"{v}: {sum(x == v for _, x in out)}/{len(out)}")
    print("RESULT: CAUGHT = a checker tested the behaviour; TRIPWIRE-ONLY = only a frozen-text anchor noticed the edit "
          "(it would pass once the anchor is refreshed); MISSED = nothing failed. bug_scan counted by its R1 / A1 / R4 hits. "
          "tf_check not in the suite (~25 min per run)")


main()
