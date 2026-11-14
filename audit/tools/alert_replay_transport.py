"""Progressive replay of one tree's alert code on real payloads with its REAL send() and a stand-in transport
(read-only; never sends: requests.post / requests.get are replaced before the first run, and a request to any host
other than the stand-in's fails).

  python audit/tools/alert_replay_transport.py <tree> <payload dir> <store copy> <out.json> <t_start> <t_end>
         [--skip FROM TO]... [--fail STEP]... [--arrive STEP]... [--tfs 15m,30m,1h,4h]

The same runs as audit/tools/alert_replay.py (one every 15 minutes, payloads cut at the step, generated 4 minutes and
sent 5 minutes after it), but the tree's own send() runs: tags, cache checks, retries, records, undelivered blocks and
warnings included. The stand-in plays ntfy: a POST it accepts is cached with its tag at the simulated send time; a poll
(/json?poll=1&since=15m | 6h) returns the cached tags inside that window. --fail STEP: every ntfy POST of the run at STEP
raises ConnectionError and nothing arrives (both attempts of every message fail). --arrive STEP: the same, except the
server does receive them (the uncertain case: the client sees an error, ntfy has the message).
Dumps every POST (step, attempt, tag, the exact body), every poll, the report keys, the final alert state and every
record file of the store. <store copy> is a COPY (its files are rewritten). Payloads and stores are vendor-derived market
data: keep them out of the repository."""
import json
import os
import sys
from bisect import bisect_right
from datetime import UTC, datetime

args = sys.argv[1:]
tree, pdir, store, out = args[:4]
t0, t1 = int(args[4]), int(args[5])
skips, fails, arrives, tfs = [], set(), set(), ["15m", "30m", "1h", "4h"]
i = 6
while i < len(args):
    if args[i] == "--skip":
        skips.append((int(args[i + 1]), int(args[i + 2])))
        i += 3
    elif args[i] in ("--fail", "--arrive"):
        (fails if args[i] == "--fail" else arrives).add(int(args[i + 1]))
        i += 2
    elif args[i] == "--tfs":
        tfs = args[i + 1].split(",")
        i += 2
    else:
        sys.exit(f"unknown argument {args[i]}")
for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL", "GITHUB_STEP_SUMMARY"):
    os.environ.pop(k, None)
os.environ["NTFY_TOPIC"] = "replay-stand-in-topic-not-real"
sys.path.insert(0, tree)
os.chdir(tree)
from quantum import notify  # noqa: E402

assert os.path.abspath(notify.__file__).startswith(os.path.abspath(tree)), notify.__file__
NOW = {"t": 0, "step": 0}
POSTS, POLLS, CACHE = [], [], []                            # CACHE: (simulated time, tag)


class _R:
    def __init__(self, code, body=None, text=""):
        self.status_code, self._b, self.text = code, body, text

    def json(self):
        return self._b


def fake_post(url, data=None, json=None, headers=None, timeout=None, **kw):
    if not url.startswith("https://ntfy.sh/replay-stand-in-topic-not-real"):
        raise RuntimeError(f"replay: unexpected POST to {url[:40]}")
    tag = (headers or {}).get("Tags")
    POSTS.append({"step": NOW["step"], "tag": tag, "text": data.decode(), "timeout": timeout})
    if NOW["step"] in fails:
        raise notify.requests.exceptions.ConnectionError("replay: injected failure")
    CACHE.append((NOW["t"], tag))
    if NOW["step"] in arrives:
        raise notify.requests.exceptions.ReadTimeout("replay: injected timeout after the server received it")
    return _R(200, {"id": f"r{len(POSTS)}"})


def fake_get(url, timeout=None, **kw):
    if not url.startswith("https://ntfy.sh/replay-stand-in-topic-not-real/json?poll=1&since="):
        raise RuntimeError(f"replay: unexpected GET to {url[:40]}")
    since = url.rsplit("since=", 1)[1]
    sec = int(since[:-1]) * {"m": 60, "h": 3600}[since[-1]]
    POLLS.append({"step": NOW["step"], "since": since})
    rows = [{"event": "open"}] + [{"event": "message", "tags": [g]} for t, g in CACHE if g and NOW["t"] - sec <= t <= NOW["t"]]
    return _R(200, text="\n".join(__import__("json").dumps(r) for r in rows))


notify.requests.post, notify.requests.get, notify._sleep = fake_post, fake_get, (lambda s: None)
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
    live = {"t": t[k - 1] + sec, "c": c[k - 1]} if k and c and c[k - 1] is not None else None
    meta = {**p["meta"], "generated_utc": datetime.fromtimestamp(step + 240, UTC).isoformat(), "forming": live}
    return {**p, "meta": meta, "chart": ch, "markers": [m for m in p["markers"] if m["t"] + sec <= step],
            "decisions": [d for d in p["decisions"] if d["t"] + sec <= step]}


st_path = os.path.join(store, notify.STATE)
with open(st_path) as fh:
    st = json.load(fh)
for tf in TFS:
    t = full[tf]["chart"]["t"]
    k = bisect_right(t, t0 - notify.TF_SEC[tf])
    st[tf] = t[k - 1]
with open(st_path, "w") as fh:
    json.dump(st, fh)

runs = []
for step in range(t0, t1 + 1, 900):
    if any(a <= step < b for a, b in skips):
        continue
    NOW.update(t=step + 300, step=step)
    rep = notify.run(store, {tf: cut(full[tf], tf, step) for tf in TFS}, tfs, sent_t=step + 300)
    runs.append({"step": step, "keys": sorted(rep), "sent": {k: v.get("sent") for k, v in rep.items() if isinstance(v, dict) and "sent" in v}})
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
    json.dump({"posts": POSTS, "polls": POLLS, "runs": runs, "state": state, "files": files, "notify_file": notify.__file__,
               "fails": sorted(fails), "arrives": sorted(arrives)}, fh, default=str)
print("ok", len(runs), "runs", len(POSTS), "posts", len(POLLS), "polls")
