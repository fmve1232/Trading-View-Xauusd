"""The terminal band at the top of the site (site/bbg.js; mandate 2026-11-28, Parts 18-19). The rules are tested in
tests/bbg.test.mjs (run here); this file adds the field-map document check, the page wiring, and one end-to-end run on
a real pipeline payload (built offline from the pipeline's synthetic market) so every field path is exercised on the
structure the pipeline actually writes."""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


@node
def test_bbg_node_suite():
    r = subprocess.run(["node", "--test", os.path.join(ROOT, "tests", "bbg.test.mjs")], capture_output=True, text=True, timeout=120, check=False)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]


@node
def test_field_map_document_matches_the_code():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "audit", "tools", "dashboard_field_map.py"), "--check"],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_band_comes_first_and_loads_before_app_js():
    html = _read("site", "index.html")
    main = html[html.index("<main>"):]
    assert main.index('id="bbg"') < main.index('id="terminal"') < main.index('id="brief"')
    assert html.index('src="costs.js"') < html.index('src="bbg.js"') < html.index('src="app.js"')


def test_app_js_hands_its_own_helpers_and_no_ledger():
    s = _read("site", "app.js")
    fn = s[s.index("function renderBbg("):s.index("function renderAll(")]
    for name in ("fresh: freshness()", "verdict: recordVerdict", "why: whyPlain", "htfDir", "px, tfmt, ago", "QCosts.newsState", "QCosts.specValidate", "ledger: null"):
        assert name in fn, name
    assert "safe(renderBbg)" in s[s.index("function renderAll("):]


@node
def test_end_to_end_on_a_pipeline_payload(tmp_path):
    out = tmp_path / "data"
    r = subprocess.run([sys.executable, "-m", "quantum.pipeline", "--synthetic", "--out", str(out), "--tfs", "15m", "--bars", "2500"],
                       cwd=ROOT, capture_output=True, text=True, timeout=600, check=False)
    assert r.returncode == 0, r.stderr[-3000:]
    js = r"""
const fs = require("fs"), path = require("path"), [root, dir] = process.argv.slice(1);
const B = require(path.join(root, "site", "bbg.js")), src = fs.readFileSync(path.join(root, "site", "app.js"), "utf8");
const cut = (a, b) => { const i = src.indexOf(a); return src.slice(i, src.indexOf(b, i)); };
const H = new Function(`const isNum = (x) => typeof x === "number" && isFinite(x);
${cut("const t975 = ", "// Visuals f_glNear")}${cut("function whyPlain(", "/* ---------- Playbook")}${cut("const htfDir = ", "function lastSweep(")}
return { recordVerdict, whyPlain, htfDir };`)();
const D = JSON.parse(fs.readFileSync(path.join(dir, "15m.json"))), I = JSON.parse(fs.readFileSync(path.join(dir, "index.json")));
const x = { nowMs: Date.parse(D.meta.last_bar_close) + 60000, closed: false, fresh: { behind: 0 }, live: null, verdict: H.recordVerdict,
  why: H.whyPlain, htfDir: H.htfDir, px: (v) => (typeof v === "number" ? v.toFixed(2) : "—"), tfmt: (s) => new Date(s * 1000).toISOString(),
  ago: () => "1 min ago", news: null, mt5: null, spec: null, specOk: false, account: null, ledger: null };
const m = B.model(D, I, x), html = B.render(m);
console.log(JSON.stringify({ cells: Object.values(m.sections).flat(), final: m.final, html_len: html.length }));
"""
    res = json.loads(subprocess.run(["node", "-e", js, ROOT, str(out)], capture_output=True, text=True, check=True).stdout)
    spec = json.loads(subprocess.run(["node", "-e", "console.log(JSON.stringify(Object.keys(require(process.argv[1]).FIELDS)))",
                                      os.path.join(ROOT, "site", "bbg.js")], capture_output=True, text=True, check=True).stdout)
    cells = {c["id"]: c for c in res["cells"]}
    assert sorted(cells) == sorted(spec)
    assert cells["A.source"]["v"] == "SYNTHETIC" and "SYNTHETIC" in cells["A.warn"]["v"]
    assert cells["B.engine"]["v"] in ("BUY", "SELL", "WAIT", "NO TRADE", "WARMUP", "RISK LOCK")
    assert cells["A.tf"]["v"] == "15m" and cells["E.ema"]["v"].count("/") == 2
    for k in ("I.open", "I.single", "I.blocked"):
        assert cells[k]["v"] == "UNAVAILABLE"
    assert res["final"]["v"] in ("NO TRADE / INSUFFICIENT EVIDENCE", "UNAVAILABLE", "BUY", "SELL", "WAIT", "NO TRADE")
    assert all(c["v"] for c in res["cells"]), "an empty cell"
