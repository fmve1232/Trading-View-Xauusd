"""Progressive replay of one tree's alert code on real payloads, one run every 15 minutes (read-only; never sends).

  python audit/tools/alert_replay.py <tree> <payload dir> <store copy> <out.json> <t_start> <t_end> [skip_from skip_to]...

<tree> is a checkout whose quantum/notify.py is replayed (e.g. the deployed commit, or this branch); <payload dir> holds
the site's {15m,30m,1h,4h,5m}.json from one production run; <store copy> is a COPY of a store (its alerts_state.json and
records are rewritten). Each run sees only the bars closed by its step (payloads cut at the step; markers and decisions
of closed bars only), generated 4 minutes after the step and sent 5 minutes after it, as in production. Runs whose step
falls in [skip_from, skip_to) are skipped (an outage). Dumps every phone message, the report keys and the final records.
Compare two trees' outputs with audit/tools/alert_replay_check.py. Payloads and stores are vendor-derived market data:
keep them out of the repository.
"""
import json
import os
import sys
from bisect import bisect_right
from datetime import UTC, datetime

tree, pdir, store, out = sys.argv[1:5]
t0, t1 = int(sys.argv[5]), int(sys.argv[6])
skips = [(int(a), int(b)) for a, b in zip(sys.argv[7::2], sys.argv[8::2], strict=True)]
sys.path.insert(0, tree)
os.chdir(tree)
from quantum import notify  # noqa: E402

assert os.path.abspath(notify.__file__).startswith(os.path.abspath(tree)), notify.__file__
TFS = ("15m", "30m", "1h", "4h", "5m")
full = {}
for tf in TFS:
    with open(os.path.join(pdir, f"{tf}.json")) as fh:
        full[tf] = json.load(fh)


def cut(p, tf, step):
    sec = notify.TF_SEC[tf]
    t = p["chart"]["t"]
    k = bisect_right(t, step - sec)
    ch = {key: (v[:k] if isinstance(v, list) and len(v) == len(t) else v) for key, v in p["chart"].items()}
    c = ch.get("c") or []
    live = {"t": t[k - 1] + sec, "c": c[k - 1]} if k and c and c[k - 1] is not None else None    # this download's live price
    meta = {**p["meta"], "generated_utc": datetime.fromtimestamp(step + 240, UTC).isoformat(), "forming": live}
    return {**p, "meta": meta, "chart": ch, "markers": [m for m in p["markers"] if m["t"] + sec <= step],
            "decisions": [d for d in p["decisions"] if d["t"] + sec <= step]}


st_path = os.path.join(store, notify.STATE)
with open(st_path) as fh:
    st = json.load(fh)
for tf in TFS:                                              # the position at the start: the last bar closed by t0
    t = full[tf]["chart"]["t"]
    k = bisect_right(t, t0 - notify.TF_SEC[tf])
    st[tf] = t[k - 1]
with open(st_path, "w") as fh:
    json.dump(st, fh)

phone, runs = [], []
for step in range(t0, t1 + 1, 900):
    if any(a <= step < b for a, b in skips):
        continue
    msgs = []
    notify.send = lambda lines, msgs=msgs: msgs.append(list(lines)) or (["cap"] if lines else [])
    rep = notify.run(store, {tf: cut(full[tf], tf, step) for tf in TFS}, ["15m", "30m", "1h", "4h"], sent_t=step + 300)
    phone += [{"step": step, "lines": m} for m in msgs if m]
    runs.append({"step": step, "keys": sorted(rep)})
with open(st_path) as fh:
    state = json.load(fh)
files = {}
for root, _, names in os.walk(store):
    for nm in names:
        if nm.endswith((".json", ".jsonl")) and ".git" not in root:
            p = os.path.join(root, nm)
            with open(p) as fh:
                files[os.path.relpath(p, store)] = fh.read()
with open(out, "w") as fh:
    json.dump({"phone": phone, "runs": runs, "state": state, "files": files, "notify_file": notify.__file__}, fh, default=str)
print("ok", len(runs), "runs", len(phone), "phone messages", sum(len(m["lines"]) for m in phone), "lines")
