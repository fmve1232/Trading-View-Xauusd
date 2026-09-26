#!/usr/bin/env python3
"""Static checks for Pine v6 compile errors that precheck / undeclared / order do not cover.

  G1  a function modifies a GLOBAL variable with := or += (Pine: "Cannot modify global
      variable in function"). Arrays are exempt -- array.set on a global array is allowed.
  G2  a name declared twice in the same scope (global scope, or the same block).
  G3  tuple arity: a function returning [a, b, ...] vs every [x, y, ...] = f() destructure.
  G4  a division inside an array index argument without int(...) (float index is an error).
  G5  variables per scope, reported as counts. The v14 strategy twin compiled and ran with
      1,102 globals, so any ceiling is above that; counts beyond it are unproven, not errors.
  G6  `bool x = na` (v6: bool can no longer hold na).
  G7  unique request.*() call sites (reported; the limit depends on plan / version).
  G8  an indicator()/strategy() with no output call (plot, bgcolor, fill, hline, alertcondition,
      strategy.entry ...): "Script must have at least one output function call". Tables and
      labels do not count.

A mechanical screen like the others: it cannot prove a file compiles. Calibrated against a
build that did compile on the operator's chart (v14 Strategy.pine): anything it flags there
is a false positive, and the tool's report says so.

Usage: python3 audit/tools/pinelimits.py artefacts/*.pine
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import trace as T  # noqa: E402  (string/comment stripper)

KW = {'if', 'else', 'for', 'while', 'switch', 'var', 'varip', 'and', 'or', 'not', 'to', 'by',
      'true', 'false', 'na', 'return', 'break', 'continue', 'import', 'export', 'method', 'type'}
TYPE = r'(?:float|int|bool|string|color|line|label|box|table|linefill|polyline|array<[^>]+>|matrix<[^>]+>|map<[^>]+>|\w+\[\])'
DECL = re.compile(r'^(\s*)(?:var\s+|varip\s+)?(?:' + TYPE + r'\s+)?([A-Za-z_]\w*)\s*=(?!=)')
TUPLE = re.compile(r'^(\s*)\[([^\]]+)\]\s*=(?!=)\s*([A-Za-z_]\w*)\s*\(')
FUNC = re.compile(r'^([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>')
MUT = re.compile(r'(?<![\w.])([A-Za-z_]\w*)\s*(?::=|\+=|-=|\*=|/=)')


def ind(s):
    return len(s) - len(s.lstrip(' '))


def analyse(path):
    raw = open(path, encoding='utf-8').read().split('\n')
    S = T.strip('\n'.join(raw))
    issues, info = [], {}

    # ---- scopes: a stack of (indent, names) -----------------------------------------
    globals_ = {}
    stack = [(-1, {}, 'global')]
    func_of_line = {}
    cur_func, func_indent, func_params = None, None, set()
    var_counts = {}
    for n, l in enumerate(S, 1):
        if not l.strip():
            continue
        i = ind(l)
        while len(stack) > 1 and i <= stack[-1][0]:
            stack.pop()
        if cur_func and i <= func_indent:
            cur_func = None
        m = FUNC.match(l)
        if m:
            cur_func, func_indent = m.group(1), 0
            func_params = {p.strip().split()[-1] for p in m.group(2).split(',') if p.strip()}
            stack.append((0, {p: n for p in func_params}, 'func ' + cur_func))
            continue
        if cur_func:
            func_of_line[n] = (cur_func, func_params)
        # block openers create a child scope for deeper lines
        opener = re.match(r'^\s*(if|else|for|while|switch)\b', l) or re.search(r'=>\s*$', l)
        names = []
        mt = TUPLE.match(l)
        if mt:
            names = [x.strip().split()[-1] for x in mt.group(2).split(',')]
        else:
            md = DECL.match(l)
            if md and md.group(2) not in KW:
                names = [md.group(2)]
        fm = re.match(r'^\s*for\s+([A-Za-z_]\w*)\s*=', l)
        scope = stack[-1][1]
        for nm in names:
            if nm in scope and not fm:
                issues.append(('G2', n, f"'{nm}' declared again in the same scope (first L{scope[nm]})"))
            scope.setdefault(nm, n)
            if len(stack) == 1:
                globals_.setdefault(nm, n)
            key = stack[-1][2] + '@' + str(id(scope))
            var_counts[key] = var_counts.get(key, 0) + 1
        if opener:
            child = {}
            if fm:
                child[fm.group(1)] = n
            stack.append((i, child, stack[-1][2]))

    # ---- G1: global modified inside a function ---------------------------------------
    for n, (fname, params) in func_of_line.items():
        l = S[n - 1]
        for m in MUT.finditer(l):
            nm = m.group(1)
            if nm in globals_ and nm not in params:
                # a local of the same name declared earlier in this function shadows the global
                local = any(DECL.match(S[k - 1]) and DECL.match(S[k - 1]).group(2) == nm
                            for k in range(max(1, n - 400), n) if func_of_line.get(k, (None,))[0] == fname)
                tup = any(TUPLE.match(S[k - 1]) and nm in S[k - 1] for k in range(max(1, n - 400), n)
                          if func_of_line.get(k, (None,))[0] == fname)
                if not local and not tup:
                    issues.append(('G1', n, f"function {fname} modifies global '{nm}'"))

    # ---- G3: tuple arity ------------------------------------------------------------
    ret = {}
    fname = None
    for n, l in enumerate(S, 1):
        m = FUNC.match(l)
        if m:
            fname = m.group(1)
            continue
        if fname and l.strip() and ind(l) == 0:
            fname = None
        if fname:
            mr = re.match(r'^\s+\[([^\]]*)\]\s*$', l)
            if mr:
                ret.setdefault(fname, set()).add(len(mr.group(1).split(',')))
    for n, l in enumerate(S, 1):
        mt = TUPLE.match(l)
        if mt and mt.group(3) in ret:
            k = len(mt.group(2).split(','))
            if ret[mt.group(3)] != {k}:
                issues.append(('G3', n, f"destructures {k} values from {mt.group(3)}(), which returns {sorted(ret[mt.group(3)])}"))
    for f, ks in ret.items():
        if len(ks) > 1:
            issues.append(('G3', 0, f"{f}() returns tuples of different sizes {sorted(ks)}"))

    # ---- G4: division inside an array index ------------------------------------------
    for n, l in enumerate(S, 1):
        for m in re.finditer(r'array\.(?:get|set)\(\s*[A-Za-z_]\w*\s*,\s*([^,()]*(?:\([^()]*\)[^,()]*)*)', l):
            idx = m.group(1)
            if '/' in idx and 'int(' not in idx and 'math.floor' not in idx and 'math.round' not in idx:
                issues.append(('G4', n, f"possible float index: {idx.strip()[:50]}"))

    # ---- G6: bool = na -----------------------------------------------------------------
    for n, l in enumerate(S, 1):
        if re.match(r'^\s*(?:var\s+)?bool\s+\w+\s*=\s*na\s*$', l):
            issues.append(('G6', n, 'bool initialised to na (not allowed in v6)'))

    outs = sum(len(re.findall(r'(?<![\w.])(plot|plotshape|plotchar|plotarrow|plotcandle|plotbar|bgcolor|barcolor|fill|hline|alertcondition|strategy\.entry|strategy\.order)\s*\(', l)) for l in S)
    if outs == 0:
        issues.append(('G8', 0, 'no output function call -- TradingView rejects the script'))
    info['globals'] = len(globals_)
    info['max_scope_vars'] = max(var_counts.values()) if var_counts else 0
    info['request_sites'] = sum(len(re.findall(r'request\.\w+\s*\(', l)) for l in S)
    return issues, info


if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        issues, info = analyse(p)
        print(f"{os.path.basename(p)}: {len(issues)} issue(s)  | global vars {info['globals']}, "
              f"largest scope {info['max_scope_vars']} (v14 twin ran with 1102), request.* call sites {info['request_sites']}")
        for code, n, msg in issues:
            print(f"    {code} L{n}: {msg}")
        bad += len(issues)
    sys.exit(1 if bad else 0)
