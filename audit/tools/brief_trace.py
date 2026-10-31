#!/usr/bin/env python3
"""Execute the Market Brief panel AS WRITTEN in Brief.pine (pine_exec.py) against the WEBSITE's own code.

The references are not re-typed: they are read, unchanged, from the default branch (the system of
record, A7) with `git show`, and only executed here, never edited.
  1. playbook (sell / buy: trigger, name, stop, TP1, TP2, names, R:R) vs quantum/arm_h4.py playbook()
     -- the level list is built by the panel's own f_brAdd lines, so their order and names are tested too
  2. "fired" (the bar that trades the previous bar's playbook) vs quantum/arm_h4.py evaluate()
  3. next target / then / opposite liquidity vs site/app.js nextLevels(), run in Node
  4. last liquidity taken: pool named vs site/app.js lastSweep(), run in Node
  5. gate row: 7/7 on the bias side <=> the engine's shouldBuy / shouldSell (Treatment lines executed)
Not covered: the TradingView runtime, table rendering, string formatting, and that the Pine
variables (cdh, activeResistance, vahPrice ...) are the engine quantities the site's rows name --
that mapping is by name and by reading engine.py, not executed. Usage: python3 audit/tools/brief_trace.py
"""
import json
import math
import os
import random
import re
import subprocess
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

BR = 'artefacts/XAUUSD_Quantum_5_0_Brief.pine'
TW = 'artefacts/XAUUSD_Quantum_5_0_Strategy.pine'
REF = 'origin/claude/audit-prompt-real-artefacts-nekqv6'
NA = float('nan')
rng = random.Random(52)
fails = 0
N_PLAY, N_NEAR, N_SWEEP, N_GATE = 3000, 2000, 2000, 4000


def report(name, bad, detail):
    global fails
    fails += bad > 0
    print(f"  {'PASS' if bad == 0 else 'FAIL'}  {name}: {detail}, mismatches {bad}")


def show(path):
    return subprocess.run(['git', 'show', f'{REF}:{path}'], capture_output=True, text=True, check=True).stdout


SRC = open(BR, encoding='utf-8').read().split('\n')


def func(name):
    a = next(i for i, l in enumerate(SRC) if l.startswith(name + '('))
    b = next(i for i in range(a + 1, len(SRC)) if SRC[i] and not SRC[i].startswith(' '))
    return SRC[a:b], a + 1


def block(start, end):
    return P.extract(BR, start, end)


env = P.Env()
for f in ('f_brAdd', 'f_brSplit', 'f_brSide', 'f_brNear'):
    P.define(func(f)[0], env)

# ---- the website's arm H4, unchanged, loaded as a module (numpy and backtest are not used by playbook/evaluate)
h4src = show('quantum/arm_h4.py')
sys.modules.setdefault('numpy', types.ModuleType('numpy'))
pkg = types.ModuleType('qpkg')
pkg.__path__ = []
sys.modules['qpkg'] = pkg
sys.modules['qpkg.backtest'] = types.ModuleType('qpkg.backtest')
H4 = types.ModuleType('qpkg.arm_h4')
H4.__package__ = 'qpkg'
H4.__file__ = os.devnull
exec(compile(h4src, 'arm_h4.py', 'exec'), H4.__dict__)
print(f"reference: {REF}:quantum/arm_h4.py (GAP {H4.GAP_ATR}, MERGE {H4.MERGE_ATR}, MIN_TP_R {H4.MIN_TP_R}, FALLBACK_R {H4.FALLBACK_R})")

PINE2SITE = {'poolPdH': ('rows', 'pdh'), 'poolPdL': ('rows', 'pdl'), 'poolPwH': ('rows', 'pwh'), 'poolPwL': ('rows', 'pwl'),
             'poolPmH': ('F', 'pm_high'), 'poolPmL': ('F', 'pm_low'), 'poolEqH': ('rows', 'eqh'), 'poolEqL': ('rows', 'eql'),
             'cdh': ('rows', 'cdh'), 'cdl': ('rows', 'cdl'), 'activeResistance': ('rows', 'active_res'),
             'activeSupport': ('rows', 'active_sup'), 'vahPrice': ('rows', 'vah'), 'valPrice': ('rows', 'val'), 'vpocPrice': ('rows', 'vpoc')}
SNAP, sline = block(r'^    array\.clear\(brV\)', r'f_brAdd\(brV, brN, "POC", vpocPrice\)')

# the panel's level list must be arm_h4.LEVELS: same order, same names, mapped to the same fields
adds = [re.search(r'f_brAdd\(brV, brN, "([^"]+)", (\w+)\)', l) for l in SNAP]
adds = [(m.group(1), m.group(2)) for m in adds if m]
want = [(n, PINE2SITE_k) for n, w, k in H4.LEVELS for PINE2SITE_k, v in PINE2SITE.items() if v == (w, k)]
report("level list == arm_h4.LEVELS (order, names, fields)", 0 if adds == want else 1, f"L{sline}, {len(adds)} levels")


def scenario():
    p = rng.uniform(3900, 4300)
    a = rng.choice([rng.uniform(0.5, 3), rng.uniform(3, 12), rng.uniform(12, 40)])   # low / normal / high vol
    m = rng.uniform(1.0, 2.2)
    vals = {}
    for k in PINE2SITE:
        r = rng.random()
        vals[k] = NA if r < 0.15 else p + rng.uniform(-8, 8) * a
    ks = list(PINE2SITE)
    for _ in range(rng.randint(0, 3)):                 # near-duplicates (merge rule) and exact ties
        x, y = rng.sample(ks, 2)
        if not math.isnan(vals[x]):
            vals[y] = vals[x] + rng.choice([0.0, rng.uniform(-0.06, 0.06) * a])
    if rng.random() < 0.1:                             # a level inside the GAP band
        vals[rng.choice(ks)] = p + rng.uniform(-0.1, 0.1) * a
    return p, a, m, vals


def pine_play(p, a, m, vals):
    e = P.Env(funcs=env.funcs, brV=[], brN=[], brNv=[], brNn=[], **vals,
              swingActiveResistance=NA, swingActiveSupport=NA)
    P.run(SNAP, e)
    d = m * a
    return e, [P.evaluate(f"f_brSide(brV, brN, {p!r}, {a!r}, {d!r}, {s})", e) for s in (-1, 1)]


def site_play(p, a, m, vals, c_next=None):
    n = 1 if c_next is None else 2
    rows, F = {}, {'c': [p] * n, 'aatr': [a] * n, 'reg_sl_mult': [m] * n}
    for k, (w, key) in PINE2SITE.items():
        (rows if w == 'rows' else F)[key] = [vals[k]] * n
    if c_next is not None:
        F['c'][1] = c_next
    return types.SimpleNamespace(rows=rows, F=F)


def same(x, y):
    if isinstance(x, str) or isinstance(y, str):
        return x == y
    return (math.isnan(x) and math.isnan(y)) or abs(x - y) <= 1e-9 * max(1.0, abs(y))


bad = n = fired_bad = fired_n = 0
for _ in range(N_PLAY):
    p, a, m, vals = scenario()
    e, sides = pine_play(p, a, m, vals)
    ref = H4.playbook(site_play(p, a, m, vals), 0)
    for (tv, tn, st, t1, t1n, t2, t2n, rr), key in zip(sides, ('sell', 'buy')):
        r = ref[key]
        n += 1
        if r is None:
            bad += 0 if math.isnan(tv) else 1
            continue
        got = (tv, tn, st, t1, t1n, t2, t2n, rr)
        exp = (r['trigger'], r['tname'], r['stop'], r['tp1'], r['tp1n'], r['tp2'], r['tp2n'], r['rr'])
        if not all(same(x, y) for x, y in zip(got, exp)):
            bad += 1
            if bad <= 3:
                print("    got", got, "\n    exp", exp)
    # 2. fired: the next bar's close against this playbook, the panel's own lines vs arm_h4.evaluate
    c1 = p + rng.uniform(-6, 6) * a
    fl, _ = block(r'^        bool fS = ', r'^        bool fB = ')
    fe = P.Env(close=c1, sT=sides[0][0], s1=sides[0][3], bT=sides[1][0], b1=sides[1][3])
    P.run(fl, fe)
    ev = H4.evaluate(site_play(p, a, m, vals, c_next=c1))
    fired_n += 1
    fired_bad += (bool(fe['fS']), bool(fe['fB'])) != (bool(ev['exec_sell'][1]), bool(ev['exec_buy'][1]))
report("playbook sides vs arm_h4.playbook", bad, f"L{func('f_brSide')[1]}, {n} sides over {N_PLAY} level sets (3 volatility bands, ties, merges, gap band)")
report("fired vs arm_h4.evaluate", fired_bad, f"{fired_n} next-bar closes")

# ---- 3 / 4. the site's JavaScript, unchanged, run in Node
js = show('site/app.js')


def jsfunc(name):
    a = js.index(f'function {name}(')
    depth, i = 0, js.index('{', a)
    while True:
        depth += {'{': 1, '}': -1}.get(js[i], 0)
        i += 1
        if depth == 0:
            return js[a:i]


cases, near_cases = [], []
NEARK = ['poolPdH', 'poolPdL', 'poolPwH', 'poolPwL', 'poolPmH', 'poolPmL', 'poolEqH', 'poolEqL', 'cdh', 'cdl',
         'swingActiveResistance', 'swingActiveSupport']
for _ in range(N_NEAR):
    p, a = rng.uniform(3900, 4300), rng.uniform(1, 20)
    v = {k: (NA if rng.random() < 0.15 else round(p + rng.uniform(-6, 6) * a, 2)) for k in NEARK}
    if rng.random() < 0.2:
        x, y = rng.sample(NEARK, 2)
        v[y] = v[x]
    near_cases.append((p, v))
sweeps = []
for _ in range(N_SWEEP):
    dn = rng.random() < 0.5
    px = rng.uniform(3900, 4300)
    lv = {k: (NA if rng.random() < 0.2 else px + rng.uniform(-3, 1) * (1 if dn else -1)) for k in ('d', 'w', 'm')}
    if rng.random() < 0.15:
        lv['w'] = lv['d']
    sweeps.append((dn, px, lv))

nodejs = (
    "const isNum = (x) => typeof x === 'number' && isFinite(x);\n" + jsfunc('nextLevels') + "\n" + jsfunc('lastSweep') + "\n"
    "const inp = JSON.parse(require('fs').readFileSync(0, 'utf8')); const out = {near: [], sweep: []};\n"
    "for (const [price, P, up] of inp.near) {\n"
    "  const D = {dashboard: {liquidity: {pools: {PDH: P[0], PDL: P[1], PWH: P[2], PWL: P[3], PMH: P[4], PML: P[5], EQH: P[6], EQL: P[7]}, cdh: P[8], cdl: P[9]}, struct: {swing_res: P[10], swing_sup: P[11]}}};\n"
    "  const nl = nextLevels(D, price), s = up ? nl.above : nl.below, o = up ? nl.below : nl.above;\n"
    "  out.near.push([s[0] || null, s[1] || null, o[0] || null]); }\n"
    "for (const [dn, px, d, w] of inp.sweep) {\n"
    "  const D = {chart: {t: [1], pdh: [d], pwh: [w], pdl: [d], pwl: [w]}, markers: [{type: 'SWEEP', t: 1, dir: dn ? -1 : 1, px}]};\n"
    "  const r = lastSweep(D); out.sweep.push([r.pool, r.lvl]); }\n"
    "console.log(JSON.stringify(out));\n")
num = lambda x: None if isinstance(x, float) and math.isnan(x) else x  # noqa: E731
payload = {'near': [], 'sweep': []}
for p, v in near_cases:
    for up in (True, False):
        payload['near'].append([p, [num(v[k]) for k in NEARK], up])
for dn, px, lv in sweeps:
    payload['sweep'].append([dn, px, num(lv['d']), num(lv['w'])])
res = json.loads(subprocess.run(['node', '-e', nodejs], input=json.dumps(payload), capture_output=True, text=True, check=True).stdout)

bad = k = 0
NAMES = dict(zip(NEARK, ['PDH', 'PDL', 'PWH', 'PWL', 'PMH', 'PML', 'EQH', 'EQL', 'Day high', 'Day low', 'Swing high', 'Swing low']))
SNAPN, _ = block(r'^    for \[k, x\] in brV', r'"Swing low", swingActiveSupport\)')
for (p, v), up in [(c, u) for c in near_cases for u in (True, False)]:
    e = P.Env(funcs=env.funcs, brN=[], brNv=[], brNn=[])
    e['brV'] = [v[x] for x in NEARK[:10] if not math.isnan(v[x])]
    e['brN'] = [NAMES[x] for x in NEARK[:10] if not math.isnan(v[x])]
    e['swingActiveResistance'], e['swingActiveSupport'] = v['swingActiveResistance'], v['swingActiveSupport']
    P.run(SNAPN, e)
    d = 1 if up else -1
    tX, tN = P.evaluate(f"f_brNear(brNv, brNn, {p!r}, {d}, na)", e)
    e['tX'] = tX
    nX, nN = P.evaluate(f"f_brNear(brNv, brNn, {p!r}, {d}, tX)", e)
    oX, oN = P.evaluate(f"f_brNear(brNv, brNn, {p!r}, {-d}, na)", e)
    exp = res['near'][k]
    k += 1
    got = [None if math.isnan(x) else [nm, x] for x, nm in ((tX, tN), (nX, nN), (oX, oN))]
    if got != exp:
        bad += 1
        if bad <= 3:
            print("    got", got, "\n    exp", exp)
report("next target / then / opposite vs site nextLevels()", bad, f"L{func('f_brNear')[1]}, {k} cases (Node)")

SW, swl = block(r'^    bool _dn = liqSweepBear', r'^            _first := false')
bad = 0
for (dn, px, lv), (pool, lvl) in zip(sweeps, res['sweep']):
    e = P.Env(liqSweepBear=dn, high=px, low=px, bar_index=0.0, time=0.0,
              poolPdH=lv['d'], poolPdL=lv['d'], poolPwH=lv['w'], poolPwL=lv['w'], poolPmH=lv['m'], poolPmL=lv['m'],
              brSwDir=0.0, brSwPx=NA, brSwBar=NA, brSwT=NA, brSwPool='', brSwLvl=NA)
    P.run(SW, e)
    ok = e['brSwPool'] == pool and (lvl is None and e['brSwPool'][:2] == 'PM' or lvl is not None and same(e['brSwLvl'], lvl))
    bad += not ok
report("last liquidity taken: pool vs site lastSweep()", bad, f"L{swl}, {len(sweeps)} sweeps (Node); the panel also prints the month level the site leaves blank")

# ---- 5. gate row agrees with the engine's own signal
G, gl = block(r'^    bool\[\] g = array\.from', r'^        need \+= ')
pre = [l.strip() for l in open(TW, encoding='utf-8').read().split('\n')
       if l.startswith(('bool buyPreFilters =', 'bool sellPreFilters =', 'shouldBuy =', 'shouldSell ='))]
bad = 0
for _ in range(N_GATE):
    e = P.Env(**{x: rng.random() < 0.7 for x in ('bullTrend', 'bearTrend', 'htfBearScoreGate', 'htfBullScoreGate', 'recentBars',
                                                 'inNewsWindow', '_ddBreach', 'bullStructActive', 'bearStructActive',
                                                 'displacementUp', 'displacementDown')})
    e['htfBearScoreGate'] = rng.random() < 0.3
    e['htfBullScoreGate'] = rng.random() < 0.3
    e['inNewsWindow'] = rng.random() < 0.1
    e['_ddBreach'] = rng.random() < 0.1
    e['sessionQuality'] = float(rng.choice([0, 13, 29, 30, 31, 75]))
    e['bullBiasScore'], e['bearBiasScore'] = rng.uniform(0, 130), rng.uniform(0, 130)
    e.update(gl_='', need='', gp=0.0, gn=['Trend', 'HTF not against', 'Fresh bar', 'Session', 'No news', 'No DD', 'Trigger bar'])
    e['gl'] = ''
    e['bs'] = e['bullBiasScore'] >= e['bearBiasScore']
    P.run(G, e)
    P.run(pre, e)
    bad += (e['gp'] == 7) != bool(e['shouldBuy'] if e['bs'] else e['shouldSell'])
report("gate row 7/7 <=> engine shouldBuy / shouldSell on the bias side", bad, f"L{gl}, {N_GATE} gate states")

# ---- 6. v53 gold arrows: Brief grid == Master macro arrows, and a FLAT market is never shown as gold-bearish (F-A54)
MS = open('artefacts/XAUUSD_Quantum_5_0_Master.pine', encoding='utf-8').read().split('\n')
a = next(i for i, l in enumerate(MS) if l.startswith('_arrowStr('))
P.define(MS[a:a + 2], env)
magl = next(l for l in MS if l.startswith('string dxyMag = '))
for f in ('f_brS', 'f_brM'):
    P.define(func(f)[0], env)
# v68: the grid is one table.cell in a loop (it was f_brA, called 28 times); read glyph / colour from that line
fal = next(i for i, l in enumerate(SRC) if l.lstrip().startswith('table.cell(brG, k % 4, 1 + int(k / 4), nm + '))
fa = [None, SRC[fal]]
fal += 1
glyph = re.search(r'\(na\(d\) \? "—" : .*?"≈"\)', fa[1]).group(0)
colr = re.search(r'text_color=(na\(d\) \? .*?color\.new\(#B2B5BE, 0\))', fa[1]).group(1)
GREEN, RED = 'color.new(#26A69A, 0)', 'color.new(#EF5350, 0)'
BUILTIN_COL = {GREEN: 'G', RED: 'R', 'color.new(#B2B5BE, 0)': 'N', 'color.new(#787B86, 0)': 'X'}
P.BUILTINS['color.new'] = lambda c, t: c
bad = spec = 0
for _ in range(N_GATE):
    v, up = rng.random() < 0.85, rng.random() < 0.4
    dn = (not up) and rng.random() < 0.6
    r = rng.choice([NA, rng.uniform(-1, 1), 0.25, -0.5, 0.5])
    e = P.Env(funcs=env.funcs, dxyValid=v, avgCorrDXY=r)
    P.run([magl], e)
    master = P.evaluate(f"_arrowStr({str(v).lower()}, {str(up).lower()}, {str(dn).lower()}, dxyMag)", e)
    e['d'] = P.evaluate(f"f_brM({str(v).lower()}, {str(up).lower()}, {str(dn).lower()}, avgCorrDXY)", e)
    brief = P.evaluate(glyph, e)
    col = P.evaluate(colr.replace(GREEN, '"G"').replace(RED, '"R"').replace('color.new(#B2B5BE, 0)', '"N"').replace('color.new(#787B86, 0)', '"X"'), e)
    bad += brief != master
    want_col = 'X' if not v else 'N' if brief == '≈' else 'G' if '▲' in brief else 'R'
    spec += col != want_col or (v and not up and not dn and brief != '≈') or (not v and brief != '—')
report("gold arrows: Brief grid glyph == Master _arrowStr (DXY lines, both executed)", bad, f"Brief L{fal}, Master L{a + 1}, {N_GATE} states incl. flat, weak |r|, na r, no data")
report("gold arrows: colour == direction for gold (green ▲ / red ▼ / grey ≈ / dim —); flat never ▼", spec, f"{N_GATE} states")

# ---- 7. v54 DO NOW == the site's doNow line (Node), driven by the engine DECISION, every state (F-A55); v90 (F-A77):
# with the site's h4Losing (its own line, run in Node on a D.h4.forward built like backtest.metrics: t_stat = mean /
# (sd / sqrt n), null when sd = 0 or n < 2) against the Brief's per-timeframe record lines, records above / below
# N = 50 and t = -2, every timeframe the Brief types a record for, and one it does not
dl = js[js.index('const doNow = '):]
dl = dl[:dl.index(';') + 1]
hl = js[js.index('const h4Losing = '):]
hl = hl[:hl.index('\n')]     # the whole one-line definition (its body has ';' inside)
DECS = ['RISK LOCK', 'NO TRADE', 'BUY', 'SELL', 'WARMUP', 'WAIT']
RECS = [(0, 0.0, 0.0), (49, -0.5, 0.6), (50, -0.5, 0.6), (50, -0.17, 0.6), (511, -0.1789, 0.8513), (171, -0.092, 0.8006),
        (60, 0.3, 0.7), (60, -0.2, 0.0), (1, -1.0, 0.5)]
TFS = ['5', '15', '60', '240', 'D']


def tstat(n_, m_, s_):
    return m_ / (s_ / math.sqrt(n_)) if s_ > 0 and n_ > 1 else None


cases = [(d, s_, b_, n_, m_, sd_) for d in DECS for s_ in (True, False) for b_ in (True, False) for (n_, m_, sd_) in RECS]
nodejs2 = ("const isNum = (x) => typeof x === 'number' && isFinite(x); " + hl + " const out = []; for (const [dec, s, b, n, t] of "
           + json.dumps([(d, s_, b_, n_, tstat(n_, m_, sd_)) for d, s_, b_, n_, m_, sd_ in cases]) + ") { const D = {h4: {forward: {n: n, t_stat: t}}};"
           " const sig = dec === 'BUY' || dec === 'SELL'; const pb0 = !sig ? {sell: s ? {} : null, buy: b ? {} : null} : null; "
           + dl + " out.push(doNow); } console.log(JSON.stringify(out));")
site = json.loads(subprocess.run(['node', '-e', nodejs2], capture_output=True, text=True, check=True).stdout)
DN, dnl = block(r'^    bool sig = _confDirLabel', r'^    string doNow = ')
DN = [l for l in DN if l.startswith(('bool sig', 'string doNow'))]
RL = [l for l in SRC if l.startswith(('string brTf = ', 'int brH4N = ', 'float brH4M = ', 'float brH4S = ', 'float brH4T = ', 'bool h4Losing = '))]
bad = nst = 0
for tf in TFS:
    for (d, s_, b_, n_, m_, sd_), want in zip(cases, site):
        e = P.Env(_confDirLabel=d, pbOK=s_ or b_, **{"timeframe.period": tf})
        for k in ('5', '15', '60', '240'):     # the record typed for THIS timeframe; the others hold a different record
            on = k == tf
            e.update({f"brH4N{k}": float(n_ if on else 999), f"brH4M{k}": m_ if on else 1.0, f"brH4S{k}": sd_ if on else 0.5})
        P.run(RL + DN, e)
        exp = want if tf != 'D' else site[cases.index((d, s_, b_, 0, 0.0, 0.0))]     # no record typed for D: never losing
        bad += e['doNow'] != exp
        nst += 1
report("DO NOW == site doNow with its h4Losing (engine DECISION x playbook sides x live H4 record x timeframe)", bad,
       f"L{dnl}, {nst} states (Node)")
# the Brief's typed record defaults == the ledger files recomputed (as of the ledger update they name)
led_bad, led_note = 0, []
for k, f in (('5', '5m_h4'), ('15', '15m_h4'), ('60', '1h_h4'), ('240', '4h_h4')):
    dN = int(re.search(rf'brH4N{k} = input\.int\((\d+),', "\n".join(SRC)).group(1))
    dM = float(re.search(rf'brH4M{k} = input\.float\(([-\d.]+),', "\n".join(SRC)).group(1))
    dS = float(re.search(rf'brH4S{k} = input\.float\(([-\d.]+),', "\n".join(SRC)).group(1))
    try:
        rows = json.loads(subprocess.run(['git', 'show', f'origin/forward-ledger:holdout/{f}.json'], capture_output=True, text=True,
                                         check=True).stdout)
    except subprocess.CalledProcessError:
        led_note.append(f"{f} NOT RUN (ledger not reachable)")
        continue
    r_ = [t['r'] for t in rows if isinstance(t, dict) and not t.get('open') and t['recorded_utc'] <= '2026-10-31T00:58:10']
    mu = sum(r_) / len(r_)
    sdv = math.sqrt(sum((x - mu) ** 2 for x in r_) / (len(r_) - 1))
    ok = len(r_) == dN and abs(mu - dM) < 5e-5 and abs(sdv - dS) < 5e-5
    led_bad += not ok
    led_note.append(f"{f} N {len(r_)} mean {mu:.4f} sd {sdv:.4f} t {tstat(len(r_), mu, sdv):.2f}")
report("H4 live-record defaults == the ledger files recomputed", led_bad, "; ".join(led_note))

print(f"RESULT: {'PASS' if fails == 0 else 'FAIL'} -- Pine text executed in Python against the website's code "
      "(arm_h4.py in Python, app.js in Node); TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
