#!/usr/bin/env python3
"""End-to-end value traceability (v47). For every value the operator acts on, find its defining line in the
Master by an exact anchor, and write audit/VALUE_TRACEABILITY.md: on-screen name -> variable -> file:line ->
formula -> how it is verified. Fails (exit 1) if any anchor is missing or ambiguous, so the table cannot go
stale silently when code moves. Usage: python3 audit/tools/value_map.py [--check]"""
import re
import sys

M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
BRF = "artefacts/XAUUSD_Quantum_5_0_Brief.pine"
L = open(M, encoding="utf-8").read().split("\n")
LB = open(BRF, encoding="utf-8").read().split("\n")

# (stage, on screen, variable, anchor (line start, after indentation), formula, verified by)
ROWS = [
    ("1 Data", "all higher-timeframe values", "htf1hClose ... htf1dEma200", r"\[htf1hClose, htf1hEma20",
     "request.security(TF, close[1] / EMA20/100/200 of close[1], lookahead_on): the last COMPLETED bar, same live and in history (F-A41)",
     "pinelimits G10; Diagnostics Math probes (=1d back on every bar)"),
    ("1 Data", "volatility unit", "adaptiveATR", r"adaptiveATR = math\.max\(",
     "max(adaptive ATR, 0.01% of price): never 0 after the first bar", "regime_check.py"),
    ("2 Regime", "regime (RANGE / STRONG TR / ...) , LV/NV/HV", "mktRegime, volTag", r"string mktRegime = regAbnormal",
     "percentile-based: ABNORMAL (news window, |z|>3 or ATR > 2.5x its 100-bar mean) > COMPRESS > EXPANSION > STRONG > WEAK > RANGE; LV <= 20th, HV >= 80th ATR percentile",
     "regime_check.py (20,000 states, all ATR percentiles)"),
    ("2 Regime", "SL multiple", "regSLMult", r"float regSLMult = \(regAbnormal",
     "regime base x (0.9 + ATRpct/500), clamped [1.0, 2.2]", "regime_check.py (bounds, monotone)"),
    ("2 Regime", "size haircut", "regSizeMult", r"float regSizeMult = regAbnormal",
     "0.5 ABNORMAL / 0.75 HV / 1.0", "regime_check.py; sizing lines executed (v46)"),
    ("3 Evidence", "MTF arrows / confluence", "mtfConfluenceScore", r"int mtfAvail = ",
     "votes normalised by the layers available on the chart's timeframe (F-A40)", "formula_trace.py test_mtf"),
    ("3 Evidence", "volume profile POC / VAH / VAL", "vpocPrice, vahPrice, valPrice", r"float bucketSize = \(vpHigh - vpLow\) / vpBuckets",
     "100 bars x 40 bins, typical price, 70% value area; rebuilt every confirmed bar (F-A46)", "h2_trace.py (engine VP == spec)"),
    ("3 Evidence", "MACRO verdict (Macro BULL / bull-ish / MIX / bear-ish / BEAR + score)", "macroStrengthScore", r"macroStrengthScore = int\(math\.max\(",
     "sum of DXY, yields, SPX, EURUSD, silver, TIPS votes weighted by |correlation| (normalised to 100) + DXY momentum +/-10 + rate pressure +/-10, clamped -100..+100; >= 40 BULL, 15..39 bull-ish, <= -40 BEAR (F-A53 label)",
     "read from code (v50); inputs are completed 1H bars (F-A41)"),
    ("3 Evidence", "macro arrows DXY / 10Y / EUR / XAG / SPX / TIP (▲ ▼ ≈ —)", "_arrowStr", r"_arrowStr\(bool valid, bool up, bool dn",
     "IMPACT on gold: ▲ / ▲▲ supports up, ▼ / ▼▼ down by |corr| > 0.25 / > 0.5; flat or weak = ≈; no data = — (F-A54: flat was ▼)",
     "brief_trace.py §6 (executed, 4000 states)"),
    ("4 Scores", "L / S / R % (SIGNAL)", "bullScore, bearScore, rangeScore", r"\[nb2_, nbe2_, nr2_\] = normalizeScores",
     "evidence -> analog blend -> forecast engine -> normalisation to 100", "sequence.py; diag_parity.py (stats engine)"),
    ("6 Plan", "SIGNAL cell: analog evidence, calibration, IS WR, feature edges (wired v59)", "oPdh1stPct, oBosCont, oMaxAdverseATR, oCalDetail, __cg, __cb, __iw, __in, __fs..__fc", r"string _evConf = _evDisp",
     "stats-engine outputs (held identical to the twin, diag_parity.py): PDH/PDL-first %, BOS continue / fail %, MAE (ATR), calibration grade + Brier, in-sample WR + n, per-feature edges (c / (c + w) - 50 over resolved analogs, F-A45)",
     "diag_parity.py (stats engine); formula_trace.py; read from code"),
    ("4 Scores", "BIAS", "biasLabel", r"biasLabel = bullScore >= 62",
     ">= 62 BULL/BEAR/RANGE, else the larger score -ISH, on the FINAL scores", "sequence.py (F-A35)"),
    ("4 Scores", "mP= / S%", "_calibratedProb", r"calProbStr := ",
     "constrained weighted least-squares Platt fit on observed outcomes, clamped [0.05, 0.95] (F-A38)", "formula_trace.py test_platt"),
    ("5 Gates", "entry rule", "shouldBuy / shouldSell", r"shouldBuy = buyPreFilters",
     "trend + HTF not against + session >= 30 + no news/DD + recent bar, then structure or displacement", "decision_check.py (every condition necessary; BUY/SELL exclusive)"),
    ("6 Plan", "PLAN side / entry / SL / TP1-3", "f_tradePlan()", r"\[tpIsLong, tpEntry, tpSL.*\] = f_tradePlan\(\)",
     "built on the FINAL scores (F-A48); SL = nearest structure +/- 0.15 ATR inside [0.6 ATR, 1.6 x regime ATR]; TPs = liquidity targets >= 0.8R, R-multiple fallback",
     "order.py; sequence.py"),
    ("6 Plan", "EV (R)", "planExpectancy", r"planExpectancy := _pW \* tpRR1",
     "P(win) x RR - P(loss) + E[timeout] - cost, from the race probabilities", "formula_trace.py test_race; expectancy_check.py"),
    ("6 Plan", "TQ", "tradeQuality", r"float _tqTrend = tpIsLong",
     "trend / zone / macro / history / EV (50 + 50 tanh(EV/0.75)) components on the plan side", "formula_trace.py test_tanh"),
    ("7 Veto", "NO TRADE", "tqVeto", r"bool tqVeto = ",
     "TQ below floor OR EV < 0 OR calibrated P below minimum; + risk lock", "decision_check.py (truth table)"),
    ("8 Decision", "DECISION", "_confDirLabel", r"_confDirLabel := _rkBlockedConf",
     "RISK LOCK > NO TRADE > BUY / SELL > WARMUP > WAIT", "decision_check.py (precedence; never BUY/SELL while vetoed)"),
    ("9 MT5", "Entry / SL / TP prices", "tpEntryStr ... tp3Str", r"string tpEntryStr = _m\(tpEntry\)",
     "_m(x) = TradingView price + MT5 Price Offset, 2 decimals (one helper for every order price)", "v46 review (offset applied everywhere an order price is shown)"),
    ("9 MT5", "Risk %", "_kellyPct", r"_kellyPct := math\.min\(riskPercent",
     "half-Kelly on the Wilson 95% LOWER win probability at effective N, capped at Risk %, x skew/kurtosis/drawdown haircuts", "formula_trace.py test_kelly"),
    ("9 MT5", "$ risk / lots", "_riskUSD, _lots", r"float _riskUSD = accountSize",
     "account x Risk % x regime haircut; lots = floor(risk $ / (SL distance x 100 oz), 0.01); '<min' below the broker minimum (F-A52)",
     "sizing lines executed, 3000 cases (v46)"),
    ("9 MT5", "structure / sweep / H2 alert", "_evS", r"string _evS = _ev\(bosLabelBull",
     "first bar of BOS / CHoCH / MSS / liquidity sweep (engine flags = STRUCTURE cell) + H2 SETUP text; info only", "decision_check.py (alert edge test)"),
    ("9 MT5", "BUY / SELL alert text", "_mt5Plan", r"string _mt5Plan = ",
     "the same strings as the PLAN box", "v46 review"),
    ("10 H2", "H2 SETUP", "h2Long / h2Short, h2Plan", r"string h2Plan = ",
     "sweep of the last unswept 5-bar swing + 2-of-3 RAW 1H/4H/1D trend scores (not TF-gated, = H2 arm, F-A60) + value side of POC; SL wick +/- 0.15 ATR; TP1 max(POC,1R), TP2 max(VAH,2R)",
     "h2_parity.py (block + inputs); h2_trace.py"),
]
# v52: the Market Brief companion (Treatment engine verbatim, diag_parity.py); display only
BROWS = [
    ("11 Brief", "PLAYBOOK SELL / BUY: trigger, stop, TP1, TP2, R:R", "f_brSide", r"f_brSide\(float\[\] v",
     "the website's arm H4 rule: nearest level beyond 0.1 ATR (levels merged within 0.05 ATR); stop = trigger -/+ regSLMult x ATR; TP = next levels >= 1 stop beyond, else 2 stops; built at a bar close, applies to the next",
     "brief_trace.py (vs the site's arm_h4.py, executed)"),
    ("11 Brief", "playbook fired (and its alert)", "fS / fB", r"bool fS = ",
     "the next bar's close beyond the trigger and short of TP1 (sell checked first)", "brief_trace.py (vs arm_h4.evaluate)"),
    ("11 Brief", "TARGET / then / opposite liquidity", "f_brNear", r"f_brNear\(float\[\] v",
     "nearest pool / day / swing level beyond price on the side of the lean (bull >= bear), from the last closed bar", "brief_trace.py (vs the site's nextLevels, Node)"),
    ("11 Brief", "LIQ TAKEN", "brSwPx, brSwPool", r"brSwPool := \(k == 0",
     "the engine's liqSweepBull / liqSweepBear on a confirmed bar; pool = PDx/PWx the wick crossed, closest, else the month", "brief_trace.py (vs the site's lastSweep, Node)"),
    ("11 Brief", "GATES n/7", "g", r"bool\[\] g = array\.from",
     "the seven conditions of shouldBuy / shouldSell on the bias side", "brief_trace.py (7/7 <=> engine signal)"),
    ("11 Brief", "DO NOW", "doNow", r"string doNow = sig",
     "the engine DECISION (_confDirLabel, the Master's line, diag_parity.py): BUY/SELL now > risk lock > wait for a playbook trigger > stay flat > no trade",
     "brief_trace.py (vs the site's doNow, Node); diag_parity.py (22 DECISION/gate/veto lines Master == twin)"),
    ("11 Brief", "ENGINE / DATA rows (moved from the Master's cross-check line, v57)", "_xT.._xQ, tradeQuality, confidenceScore, gcState ...", r"f_brC\(brT, 10, \"ENGINE\"",
     "T/S/L/M arrows, Q veto state, TQ / C scores, value-area position, structure, risk lock, VIX, climax; GC / OI / COT / 2s10s and the feed status codes",
     "diag_parity.py (same engine); read from code"),
    ("11 Brief", "GOLD ARROWS grid (24 cells)", "f_brA / f_brM", r"f_brA\(int i, string nm",
     "green = supports gold up, red = down, grey = neutral, dim = no data; macro = impact on gold (DXY/yields/TIPS falling = up), weak |r| <= 0.25 = neutral",
     "brief_trace.py (grid == Master _arrowStr; colour == direction)"),
]


def find(pat, src=L):
    hits = [i + 1 for i, l in enumerate(src) if re.match(r"^\s*" + pat, l)]
    return hits


out, bad = [], []
for rows, src, fn in ((ROWS, L, "Master.pine"), (BROWS, LB, "Brief.pine")):
    for stage, screen, var, pat, formula, ver in rows:
        h = find(pat, src)
        if len(h) != 1:
            bad.append((screen, pat, h))
            continue
        out.append(f"| {stage} | {screen} | `{var}` | `{fn}:{h[0]}` | {formula} | {ver} |")
if bad:
    for b in bad:
        print("FAIL  anchor for", b[0], "matched", b[2] or "nothing", "pattern", b[1])
    sys.exit(1)
doc = ["# Value traceability — XAUUSD Quantum Master",
       "",
       "Generated by `audit/tools/value_map.py` from the current Master; the line numbers are found, not typed.",
       "Every value the operator acts on is listed in the order the engine computes it: data -> regime -> evidence -> scores ->",
       "gates -> plan -> veto -> decision -> MT5 order values, then the Market Brief (Brief.pine, v52). Re-run the tool after any change; it fails if a value's code moved",
       "or disappeared. 'Verified by' names the tool or chart readout that checks it; every tool in it executes the Pine text,",
       "none exercises the TradingView runtime (that is the operator's compile and chart).",
       "",
       "| Stage | On screen | Variable | Defined at | Formula | Verified by |",
       "|---|---|---|---|---|---|"] + out + [
       "",
       "Not listed: chart drawings and reference levels (PDH/PDL, VWAP, FVG, OB). They are TradingView prices for orientation,",
       "not order prices; order prices come only from the PLAN box and the alerts. The Brief's playbook prices are",
       "conditional levels (MT5 offset applied), not a DECISION."]
if "--check" in sys.argv:
    cur = open("audit/VALUE_TRACEABILITY.md", encoding="utf-8").read()
    if cur.strip() != "\n".join(doc).strip():
        sys.exit("FAIL  audit/VALUE_TRACEABILITY.md is stale; run python3 audit/tools/value_map.py")
    print(f"PASS  value traceability table current ({len(out)} values)")
else:
    open("audit/VALUE_TRACEABILITY.md", "w", encoding="utf-8").write("\n".join(doc) + "\n")
    print(f"wrote audit/VALUE_TRACEABILITY.md ({len(out)} values, every anchor found exactly once)")
