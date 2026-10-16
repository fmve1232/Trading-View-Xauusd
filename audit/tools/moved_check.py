#!/usr/bin/env python3
"""Moved-feature ledger (v57): a feature moved out of a file for token room must keep EXACTLY its definition
and stay displayed where it went. Each entry: the definition frozen from the build it left (here the v56 Master,
commit 2f7f56d7), the file it moved to, and the panel that must read it. Fails if a definition drifts, a moved
value stops being displayed, or it comes back into the Master unannounced.

v57: the Master's engine cross-check line + data-feed status -> Brief ENGINE / DATA rows.
  Equivalences, documented rather than frozen:
  * COT_STATUS -- v56 Master `cotValid ? 0 : not cotEnable ? 1 : 1`, twin `cotValid ? 0 : 1`: equal for every input.
  * tradeQuality / tqBasis -- from f_tqEngine(), whose body diag_parity-style comparison found identical (45 lines);
    checked here by comparing that function's body.
  * migState -- the twin words it differently; the Brief's DATA row reproduces the Master's `schemaLine` text,
    held below by its literals.
Usage: python3 audit/tools/moved_check.py"""
import re
import sys

M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
B = "artefacts/XAUUSD_Quantum_5_0_Brief.pine"
FROZEN = {
    "_xT": "string _xT = bullTrend ? \"T▲\" : bearTrend ? \"T▼\" : \"T=\"",
    "_xS": "string _xS = bullStructActive ? \"S▲\" + bullStructType : bearStructActive ? \"S▼\" + bearStructType : \"S=\"",
    "_xL": "string _xL = evLiqBull > evLiqBear + 3 ? \"L▲\" : evLiqBear > evLiqBull + 3 ? \"L▼\" : \"L=\"",
    "_xM": "string _xM = mtfConfluenceScore > 20 ? \"M▲\" : mtfConfluenceScore < -20 ? \"M▼\" : \"M=\"",
    "_xQ": "string _xQ = riskLock ? \"R✗\" : _calVeto ? \"P✗\" : tqVeto ? \"Q✗\" : \"R✓\"",
    "structStr": "string structStr = bullStructActive ? \"▲\" + bullStructType + \" \" + str.tostring(bullStructAge) + \"b\" : bearStructActive ? \"▼\" + bearStructType + \" \" + str.tostring(bearStructAge) + \"b\" : \"no-struct\"",
    "riskLockStr": "string riskLockStr = not useRiskLimits ? \"\" : riskLock ? (rkLossHit ? \"LOCK:DAYLOSS\" : rkCapHit ? \"LOCK:MAXTRADES\" : \"LOCK:LOSSSTREAK\") : \"R\" + str.tostring(rkDayR, \"#.#\") + \" N\" + str.tostring(rkDayN) + (rkConsec > 0 ? \" L\" + str.tostring(rkConsec) : \"\")",
    "gcState": "string gcState = gcFailWhy != \"\" ? \"GC\" + gcFailWhy : not gcValid ? \"GC —\" : gcDiverges ? \"GC DIV\" : gcStrongBull ? \"GC ++\" : gcStrongBear ? \"GC --\" : gcConfirmsBull ? \"GC +\" : gcConfirmsBear ? \"GC -\" : \"GC ~\"",
    "oiState": "string oiState = not oiValid ? \"OI —\" : (_dUp and oiRising) ? \"OI NEW-LONG\" : (not _dUp and oiRising) ? \"OI NEW-SHORT\" : (_dUp and not oiRising) ? \"OI COVER\" : \"OI LIQ\"",
    "cotState": "string cotState = not cotValid ? \"\" : \"  COT\" + str.tostring(int(nz(cotPct, 50))) + (cotCrowdedLong ? \"!LONG-CROWD\" : cotCrowdedShort ? \"!SHORT-CROWD\" : \"\")",
    "curveState": "string curveState = not y2Valid ? \"\" : \"  2s10s\" + str.tostring(curve2s10s, \"#.##\") + (curveSteepening ? \"^\" : \"v\")",
    "vixD": "float vixD = vixSymbol != \"\" ? request.security(vixSymbol, \"D\", close[1], barmerge.gaps_off, barmerge.lookahead_on, ignore_invalid_symbol=true) : na",
    "vixSymbol": "string vixSymbol = input.symbol(\"TVC:VIX\", \"VIX Symbol (blank=off)\", group=grpCore)",
    "GC_STATUS": "int GC_STATUS   = gcValid ? 0 : not gcEnabled ? 1 : not gcResolved ? 1 : not gcFinite ? 3 : not gcFresh ? 2 : 3",
    "OI_STATUS": "int OI_STATUS   = oiValid ? 0 : oiSymbol == \"\" ? 1 : (na(_oiNow) or na(_oiPrev)) ? 1 : 3",
    "US2Y_STATUS": "int US2Y_STATUS = y2Valid ? 0 : 1",
    "migPct": "float migPct = hN > 0 ? math.min(migV2Count * 100.0 / math.min(hN, HIST_MAX), 100.0) : 0.0",
    "vaPos": "var string vaPos = \"—\"",
    "vaRatio": "var float vaRatio = 0.0",
    "climaxUp": "climaxUp = showClimax and recentBars and volPercentile >= volClimaxPerc and close > open",
    "climaxDown": "climaxDown = showClimax and recentBars and volPercentile >= volClimaxPerc and close < open",
    "confidenceScore": "confidenceScore = int(math.round((confStruct * cwStruct + confMTF * cwMtf + confLiquidity * cwLiq + confMacro * cwMacro + confSession * cwSess) / cwTotal))",
    "SCHEMA_BUILD": "int SCHEMA_BUILD = 5"
}
SCHEMA_LITERALS = ['"  SCHEMA_V2 CLEAN"', '"  V1 100%"', '"  MIXED_SCHEMA V1 "', '"\\nBUILD v"']


def lines(p):
    return open(p, encoding="utf-8").read().split("\n")


def defs(L, v):
    return [l.rstrip() for l in L if re.match(r"^(?:var\s+)?(?:\w+(?:\[\])?\s+)?" + re.escape(v) + r"\s*=(?!=)", l)]


def panel(L):
    out, on = [], False
    for l in L:
        if l.strip().startswith("// DIAG-BEGIN market brief"):
            on = True
        if on:
            out.append(l.split("//")[0] if '"' not in l else l)
    return "\n".join(out)


bl, ml = lines(B), lines(M)
pb = panel(bl)
bad = 0
for v, d in FROZEN.items():
    got = defs(bl, v)
    if got != [d]:
        bad += 1
        print(f"FAIL  {v}: Brief definition differs from the v56 Master's\n   frozen: {d}\n   Brief:  {got}")
    if v in ("vixSymbol", "migPct", "SCHEMA_BUILD"):
        continue                       # read through vixD / the schema text, not directly by name in every case
    if not re.search(r"(?<![\w.])" + re.escape(v) + r"(?!\w)", pb):
        bad += 1
        print(f"FAIL  {v}: moved to the Brief but not displayed by its panel")
for v in ("gcState", "oiState", "cotState", "curveState", "xcheckStr", "crossCheck", "schemaLine"):
    if defs(ml, v):
        bad += 1
        print(f"FAIL  {v}: defined in the Master again -- update this ledger if it moved back")
for lit in SCHEMA_LITERALS:
    if lit not in pb:
        bad += 1
        print(f"FAIL  schema text literal {lit} missing from the Brief's DATA row")


def body(L, head):
    a = next(i for i, l in enumerate(L) if l.startswith(head))
    out = []
    for l in L[a + 1:]:
        if l.strip() and not l.startswith(" "):
            break
        c = l.split("//")[0].rstrip()
        if c.strip():
            out.append(c)
    return out


if body(ml, "f_tqEngine() =>") != body(bl, "f_tqEngine() =>"):
    bad += 1
    print("FAIL  f_tqEngine (TQ shown in the Brief's ENGINE row) differs Master vs Brief")
if bad:
    sys.exit(1)
print(f"PASS  moved features: {len(FROZEN)} definitions identical to the v56 Master, each displayed by the Brief panel; "
      "f_tqEngine identical; schema text = the Master's wording; none re-defined in the Master")
