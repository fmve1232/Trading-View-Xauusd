#!/usr/bin/env python3
"""Dead-code / wiring check for the Pine artefacts (built on trace.py).

Flags, per file:
  UNREAD            declared or assigned, never read
  SELF-ONLY         read only inside its own update statements (x += ..., x := x ...)
  WRITE-ONLY-ARRAY  only ever the target of array.set/fill/push/...
  UNCALLED-FUNC     defined, never called

Mechanical screen, like trace.py: every hit must be judged by hand. Known STRUCTURAL
hits that are correct and must stay:
  * __xx names in the strategy twins -- slots of the shared stats-engine tuple; Pine
    requires every tuple element to be named, and the Master reads them all.
  * _diPV / _diMV in Visuals -- ta.dmi's 3-tuple, only ADX is needed there.
  * bull/bearStructActive (Control arm) and regimeConfHigh (Treatment arm) -- read by
    the OTHER arm's entry gate; kept so the two arms stay identical except for the gate.

RETAINED: names listed in audit/tools/retained.txt were restored on operator instruction
(v18) and are reported separately. They do not fail the check; anything dead and NOT listed does.

DRAWING HANDLES: a line / label / box / table variable re-assigned through a function that
deletes and redraws it (x := f(x, ...)) is a live chart object, not a self-only accumulator.

COMPANION: the strategy twins and Diagnostics.pine run the same engine verbatim
(diag_parity.py). A twin symbol that the twin never reads but Diagnostics DOES read is wired
through Diagnostics, and is reported as such.
The Master is included since v37: its analog-evidence readout (oPdh1stPct, oCalDetail, ...)
moved to the Diagnostics "Analog evidence" row (token ceiling); the same engine computes them.

Usage: python3 audit/tools/deadcode.py [--all] artefacts/*.pine   (--all also lists structural / companion-wired names)
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import trace as T

WR = re.compile(r'array\.(set|fill|push|clear|unshift|insert|remove|shift|pop)\s*\(\s*([A-Za-z_]\w*)')
_rt = os.path.join(os.path.dirname(__file__), 'retained.txt')
RETAINED = set(l.strip() for l in open(_rt) if l.strip() and not l.startswith('#')) if os.path.exists(_rt) else set()
# v67 (operator, 2026-10-17: "don't delete anything, look for its purpose and wire it up"): no exemptions left. The
# tuple slots (__xx), DI+ / DI- in Visuals and the cross-arm gate inputs are all displayed now, so a STRUCTURAL hit is
# a failure like any other unread value. A companion-wired value (computed here, displayed by Diagnostics / Visuals,
# which run the same code) is still accepted, because the companion is checked to read it.
STRUCTURAL = set()

total = 0
SHOW_ALL = '--all' in sys.argv
for p in [a for a in sys.argv[1:] if a != '--all']:
    via = []
    res = T.analyze(p)
    raw = open(p, encoding='utf-8').read().split('\n')
    lines = T.strip(open(p, encoding='utf-8').read())
    hits = []
    for r in res['rows']:
        nm = r['name']
        if r['is_param']:
            continue
        tag = None
        if r['nreads'] == 0:
            tag = 'UNREAD'
        elif all(re.match(r'^\s*' + re.escape(nm) + r'\s*(:=|\+=|-=|\*=|/=)', lines[i - 1]) for i in r['reads']):
            decl_src = raw[(r['decl'] or [1])[0] - 1] if r['decl'] else ''
            if not re.search(r'\b(line|label|box|table|linefill|polyline)\b', decl_src):
                tag = 'SELF-ONLY'
        else:
            real = False
            for i in r['reads']:
                ln = lines[i - 1]
                tot = len(re.findall(r'(?<![\w.])' + re.escape(nm) + r'(?!\w)', ln))
                w = sum(1 for m in WR.finditer(ln) if m.group(2) == nm)
                if tot > w:
                    real = True
                    break
            decl_src = raw[(r['decl'] or [1])[0] - 1] if r['decl'] else ''
            if not real and not re.search(r'\b(line|label|box|linefill|polyline)\[\]', decl_src):
                tag = 'WRITE-ONLY-ARRAY'
        if tag:
            structural = nm in STRUCTURAL
            hits.append((tag, nm, (r['decl'] or r['assign'] or [0])[0], structural))
    for f, ln in res['funcs'].items():
        n = sum(len(re.findall(r'(?<![\w.])' + re.escape(f) + r'\s*\(', l)) for l in lines)
        if n <= 1:
            hits.append(('UNCALLED-FUNC', f, ln, False))
    if any(k in os.path.basename(p) for k in ('Strategy', 'Master', 'Brief')):
        # companion that runs the same code: Diagnostics for the engine arms and Brief (v52, the
        # same engine verbatim, diag_parity.py); Visuals for the H2
        # arm, whose H2 block is byte-identical there (h2_parity.py) -- only h2* names qualify
        _h2 = 'Strategy_H2' in os.path.basename(p)
        _dp = os.path.join(os.path.dirname(p), 'XAUUSD_Quantum_5_5_Visuals.pine' if _h2 else 'XAUUSD_Quantum_5_0_Diagnostics.pine')
        if os.path.exists(_dp):
            _dr = {r['name']: r['nreads'] for r in T.analyze(_dp)['rows']}
            _df = set(T.analyze(_dp)['funcs'])
            _dl = T.strip(open(_dp, encoding='utf-8').read())
            def _wired(nm):
                if nm in _df:
                    return sum(len(re.findall(r'(?<![\w.])' + re.escape(nm) + r'\s*\(', l)) for l in _dl) > 1
                return _dr.get(nm, 0) > 0
            via = [h for h in hits if not h[3] and _wired(h[1]) and (not _h2 or h[1].startswith('h2'))]
            hits = [h for h in hits if h not in via]
            # v57: in the MASTER, a value only a companion reads is a value the Master computes and never shows.
            # v59 (operator: "every value was added with a purpose -- wire it up"): no exceptions.
            if 'Master' in os.path.basename(p):
                MASTER_VIA_OK = set()          # v59: none -- the six analog outputs are wired in the SIGNAL cell
                extra = sorted(h[1] for h in via if h[1] not in MASTER_VIA_OK)
                if extra:
                    print(f"FAIL  Master computes values it never shows (read only by a companion): {extra}")
                    hits += [h for h in via if h[1] in extra]
            if via:
                print(f"{os.path.basename(p)}: {len(via)} symbols wired through {'Visuals (same H2 block)' if _h2 else 'Diagnostics (same engine)'}")
    kept = [h for h in hits if not h[3] and h[1] in RETAINED]
    real = [h for h in hits if not h[3] and h[1] not in RETAINED]
    print(f"{os.path.basename(p)}: {len(real)} dead, {len(kept)} retained (operator instruction), {len(hits) - len(real) - len(kept)} structural")
    for h in real:
        print(f"    {h[0]:17s} {h[1]}  L{h[2]}")
    if SHOW_ALL:                     # v67: list the structural and companion-wired names too, for review
        for h in hits:
            if h[3]:
                print(f"    structural {h[0]:17s} {h[1]}  L{h[2]}")
        for h in via:
            print(f"    via-companion {h[0]:17s} {h[1]}  L{h[2]}")
    total += len(real)
raise SystemExit(1 if total else 0)
