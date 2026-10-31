#!/usr/bin/env python3
"""v90 independent audit, Stage 3: machine-generated register of every declared symbol in the nine files.

Written for the 2026-10-31 independent audit; it does NOT reuse deadcode.py / value_map.py, so it can disagree with them.
For each file, every GLOBAL declaration (input, var, typed or untyped assignment, tuple slot, user function) with:
line, kind, input default / first expression, number of reads in the file (word matches outside comments and strings,
minus the declaration and := writes), number of other files that also declare it. Output: CSV per file in
audit/v90_audit/register/ and a summary to stdout. Reads counted lexically: a symbol shadowed by a local of the same
name is over-counted (pinelimits G12 lists those)."""
import csv, glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "audit", "v90_audit", "register")
os.makedirs(OUT, exist_ok=True)
TYPES = r"(?:float|int|bool|string|color|line|label|box|table|linefill|polyline|chart\.point|array<[^>]+>|float\[\]|int\[\]|bool\[\]|string\[\]|color\[\]|map<[^>]+>|matrix<[^>]+>)"
DECL = re.compile(rf"^(var\s+|varip\s+)?(?:{TYPES}\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)(.*)$")
TUP = re.compile(r"^\[([^\]]+)\]\s*=(?!=)(.*)$")
FUN = re.compile(r"^(?:method\s+)?([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\)\s*=>(.*)$")
KW = {"if", "for", "while", "switch", "else", "var", "varip", "import", "export", "type", "method"}


def strip(l):
    out, q = [], None
    i = 0
    while i < len(l):
        c = l[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
            out.append(" ")
        elif c in "\"'":
            q = c
            out.append(" ")
        elif l.startswith("//", i):
            break
        else:
            out.append(c)
        i += 1
    return "".join(out)


files = sorted(glob.glob(os.path.join(ROOT, "artefacts", "*.pine")))
decls = {}
for f in files:
    L = open(f, encoding="utf-8").read().split("\n")
    code = [strip(l) for l in L]
    rows = []
    for i, (raw, c) in enumerate(zip(L, code), 1):
        if not c.strip() or c[0] in " \t":
            continue
        s = c.rstrip()
        m = FUN.match(s)
        if m and m.group(1) not in KW:
            rows.append((m.group(1), i, "function", raw.split("=>", 1)[1].strip()[:120]))
            continue
        m = TUP.match(s)
        if m:
            for nm in m.group(1).split(","):
                nm = nm.strip()
                if re.fullmatch(r"[A-Za-z_]\w*", nm) and nm != "_":
                    rows.append((nm, i, "tuple", raw.split("=", 1)[1].strip()[:120]))
            continue
        m = DECL.match(s)
        if m and m.group(2) not in KW:
            rhs = raw.split("=", 1)[1].strip()
            kind = "input" if re.match(r"input(\.\w+)?\(", rhs) else ("var" if m.group(1) else "value")
            rows.append((m.group(2), i, kind, rhs[:120]))
    words = re.compile(r"\b[A-Za-z_]\w*\b")
    cnt = {}
    for c in code:
        for w in words.findall(c):
            cnt[w] = cnt.get(w, 0) + 1
    writes = {}
    for c in code:
        for w in re.findall(r"\b([A-Za-z_]\w*)\s*(?::=|\+=|-=|\*=|/=)", c):
            writes[w] = writes.get(w, 0) + 1
    seen = {}
    for r in rows:
        seen.setdefault(r[0], r)
    decls[f] = (seen, cnt, writes)
summary = []
for f in files:
    seen, cnt, writes = decls[f]
    others = {n: sum(1 for g in files if g != f and n in decls[g][0]) for n in seen}
    path = os.path.join(OUT, os.path.basename(f).replace(".pine", ".csv"))
    unread = 0
    with open(path, "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["symbol", "line", "kind", "reads", "writes", "declared_in_other_files", "definition"])
        for n, (nm, ln, kind, rhs) in sorted(seen.items(), key=lambda kv: kv[1][1]):
            rd = cnt.get(n, 0) - 1 - writes.get(n, 0)
            unread += rd <= 0
            w.writerow([n, ln, kind, rd, writes.get(n, 0), others[n], rhs])
    k = {}
    for v in seen.values():
        k[v[2]] = k.get(v[2], 0) + 1
    summary.append((os.path.basename(f), len(seen), k, unread))
tot = 0
for b, n, k, u in summary:
    tot += n
    print(f"{b:44s} symbols {n:5d}  " + " ".join(f"{a} {c}" for a, c in sorted(k.items())) + f"  lexically-unread {u}")
print(f"TOTAL {tot} global symbols; CSVs in audit/v90_audit/register/ (lexical count: triage hits by hand)")
