"""Mutation test of site/bbg.js against tests/bbg.test.mjs, on a scratch copy (the repository is not touched).
Each mutant breaks one display rule (evidence gate, STALE, no score, UNAVAILABLE, no lot without a spec ...); a
mutant is killed when the Node suite fails on it.
  python audit/tools/bbg_mutation.py <repo> <scratch dir> <out json>
"""
import json
import os
import shutil
import subprocess
import sys

repo, work, out = sys.argv[1:4]
MUTANTS = [
    ("final verdict ignores the evidence", "const rv = x.verdict(hold), evOk = rv && rv.lv === 1;", "const rv = x.verdict(hold), evOk = true;"),
    ("STALE never set", "stale = isNum(fr.behind) && fr.behind >= 2", "stale = isNum(fr.behind) && fr.behind >= 99"),
    ("engine confidence shown as the score", 'cell("B.score", "NOT SHOWN"', 'cell("B.score", d.confidence'),
    ("invalid macro value shown", "if (!m || !m.valid || !isNum(m.value))", "if (!m || !isNum(m.value))"),
    ("failed feed shown", "if (r && r.ok === false) return cell(id, null", "if (false) return cell(id, null"),
    ("macro STALE threshold disabled", "nowS - (asof + sec) >= 2 * sec", "nowS - (asof + sec) >= 200 * sec"),
    ("macro STALE while the market is closed", "const old = !x.closed && isNum(asof)", "const old = isNum(asof)"),
    ("store fallback not DELAYED", 'const viaStore = r && /store/.test(String(r.source || ""));', "const viaStore = false;"),
    ("no ledger reads as no open trade", 'L ? cell("I.open", lopen', 'true ? cell("I.open", lopen'),
    ("developing / done swapped", '`${e0.done ? "done" : "DEVELOPING"}', '`${!e0.done ? "done" : "DEVELOPING"}'),
    ("engine plan shown without a signal", ": sig && d.plan && isNum(d.plan.entry)", ": d.plan && isNum(d.plan.entry)"),
    ("lot shown without an account", "const specOk = !!(x.spec && x.specOk && x.account > 0)", "const specOk = !!(x.spec && x.specOk)"),
    ("lot shown without a valid spec", "const specOk = !!(x.spec && x.specOk && x.account > 0)", "const specOk = !!(x.spec && x.account > 0)"),
    ("payload text not escaped", "const esc = (s) => String(s ?? \"\").replace(", "const esc = (s) => String(s ?? \"\"); const _e = (s) => String(s).replace("),
    ("old structure coloured as current", 'return cell(id, `last ${m.dir > 0 ? "▲" : m.dir < 0 ? "▼" : "·"} ${isNum(m.ago) ? bars(m.ago) + " ago" : ""}`.trim(), { c: "na"',
     'return cell(id, `last ${m.dir > 0 ? "▲" : m.dir < 0 ? "▼" : "·"} ${isNum(m.ago) ? bars(m.ago) + " ago" : ""}`.trim(), { c: m.dir > 0 ? "bull" : "bear"'),
    ("live price used when stale", 'const live = x.live && isNum(x.live.px) ? x.live : null;', 'const live = x.live && isNum(x.live.px) ? x.live : { px: 1, t: 0 };'),
    ("missing payload filled with zeros", 'if (!D || !D.meta || !D.dashboard) return unavailable("data/<tf>.json could not be read");',
     'if (!D || !D.meta || !D.dashboard) { const u = unavailable(""); for (const k in u.sections) u.sections[k].forEach((c) => (c.v = "0")); return u; }'),
    ("high-cost warning dropped", "cpa > chk.cost_amber_pct ? `HIGH COST", "cpa > 1e9 ? `HIGH COST"),
    ("news window dropped", "nw.in_window ? `NEWS WINDOW", "false ? `NEWS WINDOW"),
    ("phone decision ignored in the final line", ': word === "BUY" || word === "SELL" ? { v: word,', ': false ? { v: word,'),
    ("confirmed sweep flag ignored", "lq.sweep_bull || lq.sweep_bear\n", "false\n"),
    ("INDICATIVE dropped for a futures source", 'gc ? { st: "INDICATIVE"', 'false ? { st: "INDICATIVE"'),
]
results = []
MARK = ".bbg_mutation_scratch"
rp, wp = os.path.realpath(repo), os.path.realpath(work)
if wp == rp or rp.startswith(wp + os.sep):
    sys.exit("the scratch directory must not be the repository or contain it")
if os.path.exists(wp) and not os.path.exists(os.path.join(wp, MARK)):
    sys.exit(f"{wp} exists and was not made by this tool ({MARK} missing): give a new or empty path")


def fresh():
    """Recreate the scratch copy; only a directory this tool marked is ever removed."""
    if os.path.exists(os.path.join(wp, MARK)):
        shutil.rmtree(wp)
    os.makedirs(os.path.join(wp, "tests"))
    with open(os.path.join(wp, MARK), "w") as fh:
        fh.write("scratch copy for audit/tools/bbg_mutation.py\n")
    shutil.copytree(os.path.join(rp, "site"), os.path.join(wp, "site"))
    shutil.copy(os.path.join(rp, "tests", "bbg.test.mjs"), os.path.join(wp, "tests"))


for name, a, b in MUTANTS:
    fresh()
    p = os.path.join(wp, "site", "bbg.js")
    with open(p, encoding="utf-8") as fh:
        src = fh.read()
    n = src.count(a)
    if n != 1:
        results.append({"mutant": name, "applied": False, "count": n})
        continue
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(src.replace(a, b))
    r = subprocess.run(["node", "--test", os.path.join(wp, "tests", "bbg.test.mjs")], capture_output=True, text=True, timeout=120, check=False)
    results.append({"mutant": name, "applied": True, "killed": r.returncode != 0})
killed = sum(1 for x in results if x.get("killed"))
applied = sum(1 for x in results if x["applied"])
with open(out, "w") as fh:
    json.dump({"tool": "audit/tools/bbg_mutation.py (scratch copy; repository untouched)", "applied": applied, "killed": killed,
               "results": results}, fh, indent=1)
print(f"{killed} of {applied} applied mutants killed; not applied: {[x['mutant'] for x in results if not x['applied']]}")
print("survivors:", [x["mutant"] for x in results if x["applied"] and not x["killed"]])
