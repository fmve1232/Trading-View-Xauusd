#!/usr/bin/env python3
"""Engine constants == the system of record's (v99; v90 mutation gaps m13, and m06 / m07 semantically).

Every parity checker here compares Pine copies with EACH OTHER, so a constant changed in every copy at once passes them
all (v90 mutation m13: the abnormal-ATR multiple 2.5 -> 2.0 in all six engine copies was tripwire-only). The website's
engine (A7, read-only from its default branch) is the reference that a consistent edit cannot move. For each pair below
(a Pine line in the Master and the Treatment twin, the line that ports it on the website), the numeric literals must be
the same multiset. The pairs are the constants that decide the regime, the entry gates and the trade plan.
Positive controls: m13 (2.5 -> 2.0), m06 (session floor 30 -> 20), m07 (haircut 0.5 -> 0.6), SL band 1.6 -> 1.8.
Usage: python3 audit/tools/const_parity.py"""
import re
import subprocess
import sys

REF = "origin/claude/audit-prompt-real-artefacts-nekqv6"
FILES = ["artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy.pine"]
# name: (Pine line prefixes (stripped), website file, website line prefixes (stripped))
PAIRS = {
    "regime ABNORMAL (|z| > 3, ATR > 2.5 x its 100-bar mean)": (["bool regAbnormal = "], "quantum/features.py", ["reg_abn = news |"]),
    "position-size haircut (0.5 / 0.75 / 1.0)": (["float regSizeMult = "], "quantum/features.py", ['F["reg_size_mult"] = ']),
    "SL multiple by regime x (0.9 + ATR pct / 500)": (["float regSLMult = ("], "quantum/features.py", ["sl_mult = np.where(reg_abn"]),
    "SL multiple clamp [1.0, 2.2]": (["regSLMult := math.min("], "quantum/features.py", ['F["reg_sl_mult"] = np.clip']),
    "BOS volume scale (1.20 / 0.85)": (["float regBOSMult = "], "quantum/features.py", ['F["reg_bos_mult"] = ']),
    "liquidity window scale (1.30 / 0.80)": (["float regLiqMult = "], "quantum/features.py", ['F["reg_liq_mult"] = ']),
    "BUY entry gate (session >= 30)": (["bool buyPreFilters = "], "quantum/engine.py", ["buy_pre = bt and not hgs and recent"]),
    "SELL entry gate (session >= 30)": (["bool sellPreFilters = "], "quantum/engine.py", ["sell_pre = brt and not hgb and recent"]),
    "structure break buffer (0.15 ATR)": (["float breakBuffer = "], "quantum/engine.py", ["break_buf = a * "]),
    "SL acceptance band [0.6 ATR, 1.6 x regime ATR]": (["float _slLoB = ", "float _slHiB = "], "quantum/engine.py", ["sl_lo, sl_hi = "]),
    "SL candidate buffer (0.15 ATR)": (["float _dS = math.abs(close - _lv) + "], "quantum/engine.py", ["d = abs(close - lv) + a * "]),
    "TP minimum (0.8 R, 0.5 ATR)": (["float _tpMinD = "], "quantum/engine.py", ["tp_min = max("]),
    "TP maximum (12 R)": (["float _tpMaxD = "], "quantum/engine.py", ["tp_max = dist * "]),
}
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def nums(lines):
    out = []
    for l in lines:
        code = re.sub(r'"[^"]*"', "", l.split("//")[0] if not l.lstrip().startswith("#") else "")
        code = code.split(" #")[0]
        out += [float(x) for x in NUM.findall(code)]
    return sorted(out)


def find(lines, prefixes):
    hit = []
    for p in prefixes:
        h = [l.strip() for l in lines if l.strip().startswith(p)]
        assert len(h) >= 1, f"anchor not found: {p}"
        hit.append(h[0])
    return hit


def compare(pine_src, web):
    L = pine_src.split("\n")
    bad = []
    for name, (pp, wf, wp) in PAIRS.items():
        a, b = nums(find(L, pp)), nums(find(web[wf], wp))
        if a != b:
            bad.append((name, a, b))
    return bad


if __name__ == "__main__":
    web = {}
    for wf in {v[1] for v in PAIRS.values()}:
        r = subprocess.run(["git", "show", f"{REF}:{wf}"], capture_output=True, text=True)
        if r.returncode:
            print(f"NOT RUN  website {wf} not reachable")
            sys.exit(2)
        web[wf] = r.stdout.split("\n")
    rev = subprocess.run(["git", "log", "-1", "--format=%h", REF], capture_output=True, text=True).stdout.strip()
    for f in FILES:
        bad = compare(open(f, encoding="utf-8").read(), web)
        report(not bad, f"{f.split('/')[-1]}: {len(PAIRS)} constant groups == the website's engine @ {rev}"
               + ("" if not bad else ": " + "; ".join(f"{n}: Pine {a} vs web {b}" for n, a, b in bad)))
    print("== positive controls on the Master (each must be detected)")
    src = open(FILES[0], encoding="utf-8").read()
    for name, o, n in (("m13 abnormal ATR 2.5 -> 2.0", "adaptiveATR > atrSma100R * 2.5)", "adaptiveATR > atrSma100R * 2.0)"),
                       ("m06 session floor 30 -> 20 (BUY)", "recentBars and sessionQuality >= 30 and not inNewsWindow and not _ddBreach\nbool sellPreFilters",
                        "recentBars and sessionQuality >= 20 and not inNewsWindow and not _ddBreach\nbool sellPreFilters"),
                       ("m07 haircut 0.5 -> 0.6", "float regSizeMult = regAbnormal ? 0.5 :", "float regSizeMult = regAbnormal ? 0.6 :"),
                       ("SL band 1.6 -> 1.8", "float _slHiB = _slAtrBase * 1.6", "float _slHiB = _slAtrBase * 1.8")):
        assert src.count(o) == 1, (name, src.count(o))
        report(bool(compare(src.replace(o, n), web)), f"control {name}: detected")
    print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- literals read from the Pine and the website's Python as written; "
          "the behaviour around them is executed by regime_check / decision_check / pine_web_parity")
    sys.exit(1 if fails else 0)
