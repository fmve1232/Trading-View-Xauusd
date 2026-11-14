"""Compare a send-captured replay (audit/tools/alert_replay.py, e.g. of the deployed tree) with a transport replay
(audit/tools/alert_replay_transport.py) of the same payloads and store (read-only).

  python audit/tools/alert_replay_transport_check.py <alert_replay out.json> <alert_replay_transport out.json>

Every captured message must have been POSTed byte for byte, at the same step and in the same order, except a message
over the channel's split limit, which must appear as consecutive (1/n) ... (n/n) parts of that step that rejoin to it
(nothing cut off). The final alert state, plan_validation.json and every research_forward / holdout file must be
identical. Prints a JSON summary; exit status 1 on any unexplained difference. Use it on a transport replay WITHOUT
injected failures (with --fail / --arrive the bodies differ by design)."""
import json
import sys

d, t = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))


def prot(f):
    return {k: v for k, v in f.items() if k in ("alerts_state.json", "plan_validation.json") or k.startswith(("research_forward", "holdout"))}


dep = [(m["step"], "\n".join(m["lines"])) for m in d["phone"]]
posts = [(p["step"], p["text"]) for p in t["posts"]]
i, same, split, bad, sizes = 0, 0, 0, [], []
for step, txt in dep:
    if i < len(posts) and posts[i] == (step, txt):
        same, i = same + 1, i + 1
        continue
    if i < len(posts) and posts[i][0] == step and posts[i][1].startswith("(1/"):
        n = int(posts[i][1].split("/", 1)[1].split(")", 1)[0])
        group = posts[i:i + n]
        body = "\n".join(p.split(" ", 1)[1] for _, p in group)
        if len(group) == n and all(s == step for s, _ in group) and body.replace("\n", "") == txt.replace("\n", ""):
            split, i = split + 1, i + n
            sizes.append(len(txt.encode()))
            continue
    bad.append(step)
out = {"captured_messages": len(dep), "posted_identical": same, "split_into_parts": split, "split_sizes_bytes": sorted(sizes),
       "unexplained_steps": bad, "posts_left_over": len(posts) - i, "state_identical": d["state"] == t["state"],
       "protected_files_identical": prot(d["files"]) == prot(t["files"]), "new_files": sorted(set(t["files"]) - set(d["files"]))}
print(json.dumps(out, indent=1))
sys.exit(0 if not bad and out["posts_left_over"] == 0 and out["state_identical"] and out["protected_files_identical"] else 1)
