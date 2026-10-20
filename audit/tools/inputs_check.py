#!/usr/bin/env python3
"""Every input and default setting, all nine files (v63).

  1. valid       -- each default lies inside its own minval / maxval, is one of its options, and sits on its step grid.
  2. consistent  -- an input with the same variable in two engine copies (Master, Treatment, Control, Challenger,
                    Diagnostics, Brief) has the same default, bounds and options; the H2 inputs are the same in Visuals,
                    Strategy_H2 and the Master. A difference is listed, never silently accepted.
  3. frozen      -- each default of the five pre-registered files equals the default in the build the forward test
                    froze (PREREGISTRATION.md §2: commit 98d9ab5f, H2 77992ec4). §2 forbids changing an input default
                    in those files; a change is reported, with the file it is in.
  4. stated      -- a tooltip that states a default ("default N", "N = default") states the real one.
  5. safe range  -- an integer input that reaches a ta.* length, an array size or a history offset has minval >= 1
                    (TradingView stops the script with a runtime error on a length of 0); what the operator can type
                    must not be able to stop the script.

No default is judged by the results it gives on this price history: that is tuning (AUDIT_PROMPT.md §9). The
defaults ARE the pre-registered rule. Usage: python3 audit/tools/inputs_check.py [--list]"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

A = "artefacts/XAUUSD_Quantum_5_0_"
ENGINE = {"Master": A + "Master.pine", "Treatment": A + "Strategy.pine", "Control": A + "Strategy_OLDGATES.pine",
          "Challenger": A + "Strategy_CHALLENGER.pine", "Diagnostics": A + "Diagnostics.pine", "Brief": A + "Brief.pine"}
OTHER = {"Visuals": "artefacts/XAUUSD_Quantum_5_5_Visuals.pine", "H2": A + "Strategy_H2.pine",
         "EdgeCases": A + "EdgeCases.pine"}
FROZEN = {"Master": "98d9ab5f", "Treatment": "98d9ab5f", "Control": "98d9ab5f", "Challenger": "98d9ab5f",
          "H2": "77992ec4"}
fails = 0
# Known, reviewed differences (v63): each prints as INFO with its reason; anything else FAILS.
KNOWN = {
    "trendThreshold step": "frozen default 60 with minval 51 / step 5: TradingView accepts an off-grid default (the step "
                           "only moves the spinner, to 55 / 65); 51 keeps the threshold strictly above the neutral 50",
    "dashMode.options": "the Master's layouts were redesigned (v55-v60: Mobile card / Strip); the arms' dashboards are "
                        "the display-only twins' and keep their own",
    "ema20Len.min": "same default (20); Visuals' tooltip asks to keep them matched; both bounds >= 1",
    "ema100Len.min": "same default (100); both bounds >= 1",
    "ema200Len.min": "same default (200); both bounds >= 1",
    "fvgMaxBars.default": "different features: Visuals projects each FVG box this many bars right (a chart aid, many "
                          "boxes, ATR(14) size filter); the Master expires its single engine FVG after 30 bars",
    "fvgMaxBars.min": "as fvgMaxBars.default", "fvgMaxBars.max": "as fvgMaxBars.default",
    "showSR.default": "Visuals draws S/R; the Master switch only annotates its dashboard (its tooltip says so)",
    "showFVG.default": "different features: Visuals' switch only DRAWS the FVG boxes (off by default since v81, clutter); "
                       "the Master's is the ENGINE input (F-A30) that feeds trade quality and the plan, unchanged ON",
    "showOB.default": "as showFVG.default: Visuals draws the OB boxes (off since v81); the Master's is the engine input (F-A30), ON",
}


def triage(items, key_of):
    hard, info = [], []
    for x in items:
        k = key_of(x)
        (info if k in KNOWN else hard).append(x + (f"\n          INFO: {KNOWN[k]}" if k in KNOWN else ""))
    return hard, info


def call_args(s, i):
    """The argument text of the call whose '(' is at s[i]."""
    d, j = 0, i
    while True:
        c = s[j]
        if c == '"':
            j = s.index('"', j + 1)
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return s[i + 1:j]
        j += 1


def lit(x):
    x = x.strip()
    if x.startswith('"') and x.endswith('"'):
        return x[1:-1]
    if x in ("true", "false"):
        return x == "true"
    try:
        return float(x)
    except ValueError:
        return x                                      # an expression (e.g. a constant or color) -- compared as text


def inputs(text):
    out = {}
    for ln, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("//"):
            continue
        for m in re.finditer(r"input\.(\w+)\(", line):
            pre = line[:m.start()]
            v = re.search(r"([A-Za-z_]\w*)\s*=\s*$", pre)
            args = P._split_args(call_args(line, m.end() - 1))
            pos = [a for a in args if not re.match(r"^\w+\s*=[^=]", a)]
            kw = dict(re.match(r"^(\w+)\s*=\s*(.*)$", a, re.S).groups() for a in args if re.match(r"^\w+\s*=[^=]", a))
            d = {"kind": m.group(1), "line": ln, "default": lit(kw.get("defval", pos[0] if pos else "")),
                 "title": lit(kw.get("title", pos[1] if len(pos) > 1 else "")),
                 "min": lit(kw["minval"]) if "minval" in kw else None, "max": lit(kw["maxval"]) if "maxval" in kw else None,
                 "step": lit(kw["step"]) if "step" in kw else None, "tooltip": lit(kw.get("tooltip", "")),
                 "options": [lit(o) for o in P._split_args(kw["options"].strip()[1:-1])] if "options" in kw else None}
            out[v.group(1) if v else f"<L{ln}>"] = d
    return out


def show(x):
    return ("%g" % x) if isinstance(x, float) else repr(x) if isinstance(x, str) else str(x).lower()


now = {k: inputs(open(p, encoding="utf-8").read()) for k, p in {**ENGINE, **OTHER}.items()}

# ---- 1 valid
bad = []
for f, ins in now.items():
    for v, d in ins.items():
        x = d["default"]
        if isinstance(x, float):
            if isinstance(d["min"], float) and x < d["min"] or isinstance(d["max"], float) and x > d["max"]:
                bad.append(f"{f} {v} = {show(x)} outside [{show(d['min'])}, {show(d['max'])}]")
            if isinstance(d["step"], float) and isinstance(d["min"], float):
                k = (x - d["min"]) / d["step"]
                if abs(k - round(k)) > 1e-9:
                    bad.append(f"{f} {v} = {show(x)} off its step grid ({show(d['min'])} + n x {show(d['step'])})")
        if d["options"] is not None and x not in d["options"]:
            bad.append(f"{f} {v} = {show(x)} not among its options")
n = sum(len(i) for i in now.values())
hard, info = triage(bad, lambda x: x.split()[1] + (" step" if "step grid" in x else ""))
seen = set()
info = [i for i in info if not (i.split()[1] in seen or seen.add(i.split()[1]))]
print(f"{'PASS' if not hard else 'FAIL'}  1 valid: {n} inputs, every default inside its bounds, on its step and among "
      f"its options" + "".join("\n      " + b for b in hard + info))
fails += bool(hard)

# ---- 2 consistent
FIELDS = ("default", "min", "max", "step", "options", "kind")
diffs = []
for group in (list(ENGINE), ["Visuals", "H2", "Master"]):
    names = sorted(set().union(*(now[f].keys() for f in group)))
    for v in names:
        have = {f: now[f][v] for f in group if v in now[f]}
        if len(have) < 2:
            continue
        for fld in FIELDS:
            vals = {f: show(d[fld]) for f, d in have.items()}
            if len(set(vals.values())) > 1:
                diffs.append(f"{v}.{fld}: " + ", ".join(f"{f}={x}" for f, x in vals.items()))
shared = sum(1 for v in set().union(*(now[f].keys() for f in ENGINE)) if sum(v in now[f] for f in ENGINE) > 1)
hard, info = triage(diffs, lambda x: x.split(":")[0])
print(f"{'PASS' if not hard else 'FAIL'}  2 consistent: {shared} inputs shared by engine copies (+ the H2 inputs in "
      f"Visuals / Strategy_H2 / Master): same default, bounds, step, options" + "".join("\n      " + x for x in hard + info))
fails += bool(hard)

# ---- 3 frozen
chg = []
for f, c in FROZEN.items():
    p = {**ENGINE, **OTHER}[f]
    old = inputs(subprocess.run(["git", "show", f"{c}:{p}"], capture_output=True, text=True, check=True).stdout)
    for v in sorted(set(old) | set(now[f])):
        if v not in now[f]:
            chg.append(f"{f}: {v} removed since the freeze")
        elif v not in old:
            chg.append(f"{f}: {v} added since the freeze (default {show(now[f][v]['default'])}, line {now[f][v]['line']})")
        elif show(old[v]["default"]) != show(now[f][v]["default"]):
            chg.append(f"{f}: {v} default {show(old[v]['default'])} -> {show(now[f][v]['default'])}")
real = [c for c in chg if "default" in c and "->" in c or "removed" in c]
print(f"{'PASS' if not real else 'FAIL'}  3 frozen: every input default in the five pre-registered files equals the "
      f"frozen build's ({', '.join(f'{f}@{c}' for f, c in FROZEN.items())})"
      + "".join("\n      " + x for x in chg))
fails += bool(real)

# ---- 4 stated
st = []
for f, ins in now.items():
    for v, d in ins.items():
        t = d["tooltip"] if isinstance(d["tooltip"], str) else ""
        for m in re.finditer(r"[Dd]efault[: ]+(?:is |= ?)?(-?\d+(?:\.\d+)?)\b|(-?\d+(?:\.\d+)?) ?(?:=|is the) default", t):
            q = float(m.group(1) or m.group(2))
            if isinstance(d["default"], float) and abs(q - d["default"]) > 1e-9:
                st.append(f"{f} {v}: tooltip says default {m.group(0)!r}, the default is {show(d['default'])}")
print(f"{'PASS' if not st else 'FAIL'}  4 stated: tooltips that quote a default quote the real one"
      + "".join("\n      " + x for x in st))
fails += bool(st)

# ---- 5 safe range: integer inputs that reach a length / size / offset argument
unsafe = []
LEN_CALL = re.compile(r"\b(?:ta\.\w+|array\.new(?:_\w+|<\w+>)?|math\.sum)\(")
for f, ins in now.items():
    text = open({**ENGINE, **OTHER}[f], encoding="utf-8").read()
    code = "\n".join(l.split("//")[0] if '"' not in l else l for l in text.split("\n") if not l.lstrip().startswith("//"))
    ints = {v: d for v, d in ins.items() if d["kind"] == "int"}
    used = set()
    for m in LEN_CALL.finditer(code):
        for a in P._split_args(call_args(code, m.end() - 1)):        # ta.atr / ta.dmi take the length first
            used |= {v for v in ints if re.fullmatch(rf"{v}(?:\s*[*+]\s*\d+)?", a.strip())}
    for m in re.finditer(r"\[(\w+)\]", code):
        if m.group(1) in ints:
            used.add(m.group(1))
    for v in sorted(used):
        mn = ints[v]["min"]
        if not isinstance(mn, float) or mn < 1:
            unsafe.append(f"{f} {v} (line {ints[v]['line']}, default {show(ints[v]['default'])}): minval "
                          f"{'missing' if mn is None else show(mn)}, reaches a length / size / offset")
print(f"{'PASS' if not unsafe else 'FAIL'}  5 safe range: every integer input that reaches a ta.* length, an array "
      f"size or a [offset] has minval >= 1" + "".join("\n      " + x for x in unsafe))
fails += bool(unsafe)

if "--list" in sys.argv:
    print("\nMaster inputs (variable | kind | default | bounds | title):")
    for v, d in now["Master"].items():
        b = "" if d["min"] is None and d["max"] is None else f"[{show(d['min'])}, {show(d['max'])}]"
        print(f"  L{d['line']:<5} {v:<22} {d['kind']:<9} {show(d['default']):<22} {b:<16} {d['title']}")
print(f"RESULT: {'PASS' if fails == 0 else 'FAIL'} -- static read of every input() call; defaults are the pre-registered "
      "rule, not tuned; TradingView NOT exercised")
sys.exit(1 if fails else 0)
