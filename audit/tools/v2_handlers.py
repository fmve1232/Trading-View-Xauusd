"""Every broad exception handler in the production Python, with what its body does (read-only).

  python3 -I audit/tools/v2_handlers.py <checkout> <out.csv>

Broad = `except Exception`, `except BaseException` or a bare `except`. For each: file:line, the guarded call (first line
of the try body), and the handler body, so each can be judged: does the failure become visible (status / report field /
note), fall back to another value, or vanish?"""
import ast
import csv
import os
import sys

root, out = sys.argv[1], sys.argv[2]
files = [os.path.join(root, "quantum", f) for f in sorted(os.listdir(os.path.join(root, "quantum"))) if f.endswith(".py")] + \
        [os.path.join(root, "quantum", "data", f) for f in sorted(os.listdir(os.path.join(root, "quantum", "data"))) if f.endswith(".py")]
rows = []
for p in files:
    s = open(p, encoding="utf-8").read()
    lines = s.splitlines()
    for node in ast.walk(ast.parse(s)):
        if isinstance(node, ast.Try):
            for h in node.handlers:
                t = h.type
                name = t.id if isinstance(t, ast.Name) else (t.attr if isinstance(t, ast.Attribute) else ("bare" if t is None else "tuple"))
                if name in ("Exception", "BaseException", "bare"):
                    guarded = lines[node.body[0].lineno - 1].strip()
                    body = " / ".join(lines[b.lineno - 1].strip() for b in h.body)
                    rows.append({"file": os.path.relpath(p, root), "line": h.lineno, "guarded": guarded[:110], "handler": body[:160]})
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["file", "line", "guarded", "handler"])
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print(f"{r['file']}:{r['line']} | {r['guarded'][:70]} -> {r['handler'][:110]}")
print(len(rows), "broad handlers")
