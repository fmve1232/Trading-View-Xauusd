"""Intra-package import graph of quantum/ (AST, read-only)."""
import ast, os, sys, json
root = sys.argv[1]
G = {}
for dp, _, fs in os.walk(os.path.join(root, "quantum")):
    if "__pycache__" in dp: continue
    for f in fs:
        if not f.endswith(".py"): continue
        p = os.path.join(dp, f); mod = os.path.relpath(p, root)[:-3].replace("/", ".").replace(".__init__", "")
        t = ast.parse(open(p).read())
        deps = set()
        pkg = mod if f == "__init__.py" else mod.rsplit(".", 1)[0]
        for n in ast.walk(t):
            if isinstance(n, ast.ImportFrom):
                if n.level:
                    base = pkg.split(".")
                    base = base[:len(base) - (n.level - 1)]
                    tgt = ".".join(base + ([n.module] if n.module else []))
                    if n.module is None:
                        for a in n.names: deps.add(tgt + "." + a.name)
                    else: deps.add(tgt)
                elif n.module and n.module.startswith("quantum"): deps.add(n.module)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith("quantum"): deps.add(a.name)
        G[mod] = sorted(deps)
mods = set(G)
G = {m: sorted(d for d in ds if d in mods or any(x.startswith(d + ".") for x in mods)) for m, ds in G.items()}
json.dump(G, open(sys.argv[2], "w"), indent=1)
# cycles (Tarjan)
idx, low, st, on, out, i = {}, {}, [], set(), [], [0]
def sc(v):
    idx[v] = low[v] = i[0]; i[0] += 1; st.append(v); on.add(v)
    for w in G.get(v, []):
        if w not in G: continue
        if w not in idx: sc(w); low[v] = min(low[v], low[w])
        elif w in on: low[v] = min(low[v], idx[w])
    if low[v] == idx[v]:
        c = []
        while True:
            w = st.pop(); on.discard(w); c.append(w)
            if w == v: break
        if len(c) > 1: out.append(c)
sys.setrecursionlimit(10000)
for v in G:
    if v not in idx: sc(v)
print("modules", len(G), "| import cycles:", out or "none")
imported = {d for ds in G.values() for d in ds}
print("never imported by another quantum module:", sorted(m for m in G if m not in imported and not m.endswith("__init__")))
