#!/usr/bin/env python3
"""Bug-class scan for Pine trading scripts (v83). Each class is a mechanical screen: a hit is a question, triaged in
audit/BUG_CATALOGUE.md; the classes other tools already cover are listed there with their tool.

  R1 look-ahead  request.security(..., lookahead_on) whose expression has no [1] (or larger) offset = future data on
                 historical bars (the classic gold-indicator repaint). Expressions in a [tuple] are checked one by one.
  R2 repaint     request.security on a HIGHER timeframe with lookahead_off and no offset is fine only if it is not
                 used to decide on the forming bar; listed for triage (pinelimits.py G10 checks the [1] + off case).
  R3 varip       varip state (intrabar memory) -- repaints on reload by construction.
  R4 timenow     timenow in logic -- differs between history and realtime.
  A1 alerts      alert() / alertcondition() not gated by barstate.isconfirmed and not freq_once_per_bar_close.
  T1 time zone   hour / minute / dayofweek / dayofmonth / time(...) session calls with no time-zone argument =
                 exchange time zone (OANDA XAUUSD: America/New_York), not UTC -- listed for triage.
  P1 positions   two table.new() in one script that can take the same position at the same time (F-A69 class).
  S1 strategy    strategy() without explicit commission / slippage, or with calc_on_every_tick / fill-on-close
                 settings that flatter a backtest.
  D1 division    "/" whose denominator is a bare variable or difference not guarded (math.max, nz, safeDiv, != 0,
                 > 0 in the same line) -- a possible divide by zero / na; listed for triage.
Usage: python3 audit/tools/bug_scan.py [files]"""
import glob
import re
import sys

files = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted(glob.glob("artefacts/*.pine"))


def code_lines(text):
    out = []
    for i, l in enumerate(text.split("\n"), 1):
        s = l.strip()
        if s.startswith("//"):
            continue
        c = l.split("//")[0] if '"' not in l else l
        out.append((i, c))
    return out


def call_spans(line, name):
    for m in re.finditer(re.escape(name) + r"\(", line):
        d, j = 0, m.end() - 1
        q = False
        while j < len(line):
            ch = line[j]
            if ch == '"':
                q = not q
            elif not q and ch == "(":
                d += 1
            elif not q and ch == ")":
                d -= 1
                if d == 0:
                    yield line[m.end():j]
                    break
            j += 1


def split_args(s):
    out, d, cur, q = [], 0, "", False
    for ch in s:
        if ch == '"':
            q = not q
        if not q and ch in "([":
            d += 1
        if not q and ch in ")]":
            d -= 1
        if ch == "," and d == 0 and not q:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()]


report = {}
for p in files:
    t = open(p, encoding="utf-8").read()
    lines_all = t.split("\n")
    L = code_lines(t)
    hits = {k: [] for k in ("R1", "R2", "R3", "R4", "A1", "T1", "P1", "S1", "D1")}
    for i, l in L:
        for a in call_spans(l, "request.security"):
            args = split_args(a)
            look_on = "lookahead_on" in a
            expr = args[2] if len(args) > 2 else ""
            parts = split_args(expr[1:-1]) if expr.startswith("[") else [expr]
            if look_on:
                bad = [x for x in parts if not re.search(r"\[\s*[1-9]\d*\s*\]", x)]
                if bad:
                    hits["R1"].append((i, "lookahead_on without [1]: " + ", ".join(bad)[:80]))
            else:
                tf = args[1] if len(args) > 1 else ""
                if tf not in ("timeframe.period", '""') and not any(re.search(r"\[\s*[1-9]", x) for x in parts):
                    hits["R2"].append((i, f"tf {tf}: {expr[:70]}"))
        if re.search(r"\bvarip\b", l):
            hits["R3"].append((i, l.strip()[:90]))
        if re.search(r"\btimenow\b", l):
            hits["R4"].append((i, l.strip()[:90]))
        for nm in ("alert", "alertcondition"):
            for a in call_spans(l, nm):
                if nm == "alert" and "freq_once_per_bar_close" in a:
                    continue
                hits["A1"].append((i, f"{nm}(" + a[:70]))
        for fn in ("hour", "minute", "dayofweek", "dayofmonth"):
            for a in call_spans(l, fn):
                if len(split_args(a)) < 2:
                    hits["T1"].append((i, f"{fn}({a[:40]}) no time zone"))
        for a in call_spans(l, "time"):
            ar = split_args(a)
            if len(ar) >= 2 and len(ar) < 3 and "session" not in ar[0]:
                hits["T1"].append((i, f"time({a[:50]}) session without time zone"))
        m = re.search(r"\bstrategy\((.*)", l)
        if m and l.lstrip().startswith("strategy("):
            s = m.group(1)
            if "commission_value" not in s or "slippage" not in s:
                hits["S1"].append((i, "strategy() without explicit commission_value and slippage"))
            for bad in ("calc_on_every_tick=true", "calc_on_every_tick = true", "process_orders_on_close=true", "process_orders_on_close = true"):
                if bad in s:
                    hits["S1"].append((i, bad))
        nostr = re.sub(r'"[^"]*"', '""', l)            # divisions inside text are not divisions
        for m in re.finditer(r"/\s*(\(?[A-Za-z_][\w.]*(?:\[\d+\])?(?:\s*-\s*[A-Za-z_][\w.]*(?:\[\d+\])?)?\)?)", nostr):
            den = m.group(1)
            core = den.strip("()").split("-")[0].strip().split("[")[0]
            if re.fullmatch(r"[A-Z_][A-Z_0-9]*", core) or core in ("timeframe.in_seconds", "math.sqrt", "math.log", "math.exp", "math.pow"):
                continue                               # constants and functions whose result is checked below
            # guarded on this line or on an enclosing if / ternary condition up to 8 lines above at a smaller indent
            ctx = [nostr]
            ind = len(l) - len(l.lstrip())
            for j in range(i - 1, max(0, i - 9), -1):
                pl = lines_all[j - 1]
                pind = len(pl) - len(pl.lstrip())
                if pl.strip() and pind < ind:
                    ctx.append(pl)
                    ind = pind
            g = re.escape(core)
            guard = re.compile(rf"(math\.max\([^)]*{g}|{g}[^\n]{{0,40}}(>\s*0|!=\s*0|>=\s*1|>\s*1e-|> 0\.|>\s*\d)|nz\({g}|na\({g}\)|safeDiv)")
            if not any(guard.search(c) for c in ctx):
                hits["D1"].append((i, "/ " + den + "   " + l.strip()[:90]))
    # P1: table positions that can coincide (same literal position, or a ternary branch naming the same one)
    pos = {}
    for i, l in L:
        for a in call_spans(l, "table.new"):
            ps = set(re.findall(r"position\.(\w+)", split_args(a)[0]))
            for q in ps:
                pos.setdefault(q, []).append(i)
    for q, ls in pos.items():
        if len(ls) > 1:
            hits["P1"].append((ls[0], f"position.{q} named by table.new at lines {ls}"))
    report[p] = hits

for p, hits in report.items():
    print(f"== {p.split('/')[-1]}: " + "  ".join(f"{k} {len(v)}" for k, v in hits.items()))
    for k, v in hits.items():
        for i, msg in v[: (12 if "--all" not in sys.argv else 999)]:
            print(f"   {k} L{i}: {msg}")
