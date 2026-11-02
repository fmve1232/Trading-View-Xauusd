#!/usr/bin/env python3
"""Display wiring: does each label the operator trades from show ITS OWN value? (v99; v90 mutation gap m08)

  A  label rules, every display string in every file: wherever a trading label is printed and followed by a value
     (`"SL " + tpSLStr`, `"score L " + _si(fBullScore)` ...), the expression after it must name that label's quantity:
         L -> bull, S -> bear, R -> range / rng          (the SIGNAL / TREND score triplets)
         SL / stop -> a stop (sl / stop, or f_brSide's stop slot sS / bS), TPn -> the n-th target (tpn, or an unnumbered tp), entry -> an entry (entry / close)
     This is a rule about MEANING, not a frozen copy of the text: any legitimate rewrite keeps passing, a swap fails.
  B  the plan's MT5 strings (f_tradePlan) EXECUTED with distinct sentinel prices: each must print its own price + the
     MT5 offset, rounded as Pine's "#.##" does.
  C  tuples: for every user function that returns a list of names and every call site that destructures it into names,
     each name the two share sits at the SAME position (a reordered tuple shows one value under another's name).
  D  Visuals' NOT A GATE row (v99, B-14): every Master item it names is OUTSIDE the DECISION slice (v90_slice.py, a
     lexical over-approximation: outside = provably no influence on shouldBuy / shouldSell / tqVeto / _confDirLabel),
     and every name in the row has a mapping here (the row cannot gain an unchecked item).
Positive controls (each must be detected): m08 (L / S swapped in the SIGNAL cell), TP1 <-> TP2 in the DECISION cell,
SL <-> entry in the plan strip, the plan builders' SL / TP1 sentinels swapped, a reordered f_tradePlan call site.
Usage: python3 audit/tools/dash_wiring.py"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

FILES = sorted(glob.glob("artefacts/*.pine"))
MASTER = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def code_lines(src):
    return [(i + 1, l) for i, l in enumerate(src.split("\n")) if l.strip() and not l.lstrip().startswith("//")]


def next_expr(s, k):
    """the expression after `+` at position k, up to the next top-level `+`, `,` or closing bracket"""
    depth, j, out = 0, k, []
    in_str = False
    while j < len(s):
        ch = s[j]
        if ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and (ch == "," or (ch == "+" and j > k)):
                break
        out.append(ch)
        j += 1
    return "".join(out).strip()


IDENT = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")
SCORE = {"L": ("bull",), "S": ("bear",), "R": ("rng", "range")}


def check_label(label, expr):
    ids = [x.lower() for x in IDENT.findall(re.sub(r'"[^"]*"', "", expr))
           if x not in ("str", "tostring", "math", "round", "na", "nz", "_si", "mt5Offset")]
    if not ids or "format_time" in ids:
        return None                                   # a literal or a time follows (e.g. "first entry <date>"): no price
    if label in SCORE:
        return any(any(k in x for k in SCORE[label]) for x in ids)
    if label in ("SL", "stop"):                     # stop: the Brief's word; sS / bS = f_brSide's stop slot
        return any("sl" in x or "stop" in x or re.fullmatch(r"[sb]s", x) for x in ids)
    if label == "entry":
        return any("entry" in x or x == "close" for x in ids)
    n = label[2]                                      # TP1 / TP2 / TP3
    # a target's number: from tpN (tp1Str, h2Tp1), else a trailing digit (the Brief's f_brSide s1 / b1 / s2 / b2)
    # (and its name slot: s1n / b2n = the level's name, f_brSide)
    nums = [(re.search(r"tp(\d)", x) or re.search(r"(\d)n?$", x)).group(1) for x in ids
            if re.search(r"tp\d", x) or re.search(r"^[a-z]{1,2}\dn?$", x)]
    if nums:
        return all(d == n for d in nums)
    return any("tp" in x for x in ids)


# a label at the END of a string literal that is followed by `+ value`; the label starts the literal, or follows a
# space / '·' / ':' / the two source characters of "\n"
_B = r'"(?:[^"]*?(?:[\s·:]|\\n))?'
PAT = [(re.compile(_B + r'score L "\s*\+\s*'), "L"), (re.compile(_B + r'(?:/ )?S "\s*\+\s*'), "S"),
       (re.compile(_B + r'R "\s*\+\s*'), "R"), (re.compile(_B + r'SL "\s*\+\s*'), "SL"),
       (re.compile(_B + r'TP1 "\s*\+\s*'), "TP1"), (re.compile(_B + r'TP2 "\s*\+\s*'), "TP2"),
       (re.compile(_B + r'TP3 "\s*\+\s*'), "TP3"), (re.compile(_B + r'stop "\s*\+\s*'), "stop"), (re.compile(_B + r'(?:MT5 )?[Ee]ntry "\s*\+\s*'), "entry")]


def layer_a(src):
    sites, bad = {}, []
    for n, l in code_lines(src):
        score_line = "score L " in l
        for rx, label in PAT:
            if label in ("S", "R") and not score_line:
                continue                              # " S " / " R " are score labels only on a score line
            for m in rx.finditer(l):
                expr = next_expr(l, m.end())
                ok = check_label(label, expr)
                if ok is None:
                    continue
                sites[label] = sites.get(label, 0) + 1
                if not ok:
                    bad.append((n, label, expr[:60]))
    return sites, bad


def fn_body(L, head):
    a = next(i for i, l in enumerate(L) if l.startswith(head))
    out = []
    for l in L[a + 1:]:
        if l.startswith("    ") or not l.strip():
            out.append(l)
        else:
            break
    return out


SENT = {"tpEntry": 4123.456, "tpSL": 4100.111, "tp1": 4150.004, "tp2": 4175.995, "tp3": 4201.505}
BUILD = {"tpEntryStr": "tpEntry", "tpSLStr": "tpSL", "tp1Str": "tp1", "tp2Str": "tp2", "tp3Str": "tp3"}


def layer_b(src):
    L = src.split("\n")
    body = fn_body(L, "f_tradePlan() =>")
    lines = [l.strip() for l in body if re.match(r"\s+string (tpEntryStr|tpSLStr|tp1Str|tp2Str|tp3Str) = ", l)]
    assert len(lines) == 5, lines
    env = P.Env(mt5Offset=0.25, **SENT)
    P.run(lines, env)
    bad = [(k, env[k], P._tostr(SENT[v] + 0.25, "#.##")) for k, v in BUILD.items() if env[k] != P._tostr(SENT[v] + 0.25, "#.##")]
    return bad


def layer_c(src):
    L = src.split("\n")
    rets = {}
    for i, l in enumerate(L):
        m = re.match(r"^([A-Za-z_]\w*)\(.*\)\s*=>\s*$", l)
        if m:
            body = fn_body(L, l)
            last = next((x.strip() for x in reversed(body) if x.strip() and not x.strip().startswith("//")), "")
            if re.fullmatch(r"\[[\w\s,]+\]", last):
                rets[m.group(1)] = [x.strip() for x in last[1:-1].split(",")]
    bad, n = [], 0
    for i, l in enumerate(L):
        m = re.match(r"^\s*\[([\w\s,]+)\]\s*=\s*([A-Za-z_]\w*)\(", l)
        if m and m.group(2) in rets:
            got = [x.strip() for x in m.group(1).split(",")]
            ret = rets[m.group(2)]
            n += 1
            for k, name in enumerate(got):
                if name in ret and ret.index(name) != k:
                    bad.append((i + 1, m.group(2), name, k, ret.index(name)))
            if len(got) != len(ret):
                bad.append((i + 1, m.group(2), "arity", len(got), len(ret)))
    return n, bad


NOT_A_GATE = {"BIAS": ["biasLabel"], "EI conf": ["confLabel"], "sweeps": ["liqSweepBull", "liqSweepBear"],
              "RSI div": ["bullRsiDiv", "bearRsiDiv"], "SMT": ["smtBullPair", "smtBearPair"], "CVD": ["cvd", "cvdBull", "cvdBear"],
              "value area": ["vaPos"], "VIX": ["vixD"], "2s10s": ["curve2s10s", "curveState"], "H2 SETUP": ["h2Long", "h2Short"]}


def dslice(master_src):
    """the DECISION slice of a Master text, computed by v90_slice.py as written (its file path pointed at a copy)"""
    import contextlib
    import io
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".pine", delete=False, encoding="utf-8") as t:
        t.write(master_src)
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "v90_slice.py"), encoding="utf-8").read()
    src = src.replace('F = "artefacts/XAUUSD_Quantum_5_0_Master.pine"', f"F = {t.name!r}", 1)
    g = {"__name__": "__main__", "__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "v90_slice.py")}
    argv, sys.argv = sys.argv, ["v90_slice.py"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(src, "v90_slice.py", "exec"), g)
    finally:
        sys.argv = argv
        os.unlink(t.name)
    return g["seen"]


def layer_d(master_src, visuals_src):
    row = next(l for l in visuals_src.split("\n") if '_tmRow(r, "NOT A GATE", ' in l)
    text = re.search(r'"NOT A GATE", "([^"]*)"', row).group(1).replace("\\n", " · ").replace(": context only", "")
    items = [x.strip() for x in text.split("·") if x.strip()]
    unmapped = [x for x in items if x not in NOT_A_GATE]
    seen = dslice(master_src)
    reach = [(x, v) for x in items if x in NOT_A_GATE for v in NOT_A_GATE[x] if v in seen]
    missing = [(x, v) for x in items if x in NOT_A_GATE for v in NOT_A_GATE[x] if not re.search(rf"\b{v}\b", master_src)]
    return items, unmapped, reach, missing


if __name__ == "__main__":
    print("== A  label -> value rules (every display string)")
    tot = {}
    for f in FILES:
        sites, bad = layer_a(open(f, encoding="utf-8").read())
        for k, v in sites.items():
            tot[k] = tot.get(k, 0) + v
        if bad or sites:
            report(not bad, f"{f.split('/')[-1]}: {sum(sites.values())} labelled values ({', '.join(f'{k} {v}' for k, v in sorted(sites.items()))})"
                   + ("" if not bad else f": {bad[:4]}"))
    report(all(tot.get(k, 0) > 0 for k in ("L", "S", "R", "SL", "stop", "TP1", "TP2", "TP3", "entry")),
           f"every rule exercised at least once: {dict(sorted(tot.items()))}")
    print("== B  the plan's MT5 strings executed with sentinel prices (+ offset 0.25)")
    msrc = open(MASTER, encoding="utf-8").read()
    bad = layer_b(msrc)
    report(not bad, "tpEntryStr / tpSLStr / tp1Str / tp2Str / tp3Str each print their own price + mt5Offset" + ("" if not bad else f": {bad}"))
    print("== C  tuple returns vs destructuring call sites, by position")
    for f in FILES:
        n, bad = layer_c(open(f, encoding="utf-8").read())
        if n:
            report(not bad, f"{f.split('/')[-1]}: {n} call sites" + ("" if not bad else f": {bad[:4]}"))
    print("== D  Visuals' NOT A GATE row: each named Master item is outside the DECISION slice")
    vsrc = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
    items, unmapped, reach, missing = layer_d(msrc, vsrc)
    report(not unmapped and not reach and not missing and len(items) == len(NOT_A_GATE),
           f"{len(items)} items ({', '.join(items)}): unmapped {unmapped}, reaching the DECISION {reach}, not in the Master {missing}")
    print("== positive controls (each must be detected)")
    ctl = {
        "m08 L / S swapped in the SIGNAL cell": ('"\\nscore L " + _si(na(fBullScore) ? 50 : fBullScore) + " S " + _si(na(fBearScore) ? 50 : fBearScore)',
                                                 '"\\nscore L " + _si(na(fBearScore) ? 50 : fBearScore) + " S " + _si(na(fBullScore) ? 50 : fBullScore)', "a"),
        "TP1 <-> TP2 in the DECISION cell": ('"\\nTP1 " + tp1Str + "\\nTP2 " + tp2Str', '"\\nTP1 " + tp2Str + "\\nTP2 " + tp1Str', "a"),
        "SL <-> entry in the plan strip": ('tpDirStr + " " + tpEntryStr + " · SL " + tpSLStr', 'tpDirStr + " " + tpSLStr + " · SL " + tpEntryStr', "a"),
        "plan builder: SL string reads tp1": ("string tpSLStr = str.tostring(tpSL + mt5Offset", "string tpSLStr = str.tostring(tp1 + mt5Offset", "b"),
        "f_tradePlan call site reordered (tpSL <-> tpEntry)": ("[tpIsLong, tpEntry, tpSL, tpDist,", "[tpIsLong, tpSL, tpEntry, tpDist,", "c"),
    }
    for name, (o, n_, layer) in ctl.items():
        if layer == "c":                              # the anchor is in the return AND the call: mutate the call only
            ML_ = msrc.split("\n")
            k = [i for i, l in enumerate(ML_) if o in l and "= f_tradePlan(" in l]
            assert len(k) == 1, name
            ML_[k[0]] = ML_[k[0]].replace(o, n_)
            mut = "\n".join(ML_)
        else:
            assert msrc.count(o) == 1, (name, msrc.count(o))
            mut = msrc.replace(o, n_)
        hit = bool(layer_a(mut)[1]) if layer == "a" else bool(layer_b(mut)) if layer == "b" else bool(layer_c(mut)[1])
        report(hit, f"control {name}: detected")
    wired = msrc.replace("shouldBuy = buyPreFilters and (bullStructActive or displacementUp)",
                         "shouldBuy = buyPreFilters and (bullStructActive or displacementUp) and biasLabel != \"\"")
    assert wired != msrc
    report(bool(layer_d(wired, vsrc)[2]), "control D: biasLabel wired into the BUY gate is detected")
    print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- A / C / D read the Pine as written, B executes it; "
          "TradingView runtime NOT exercised")
    sys.exit(1 if fails else 0)
