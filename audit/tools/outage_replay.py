"""Before / after replay of the outage notice over the real production runs of quantum-site (read-only).

Usage: python audit/tools/outage_replay.py <cache dir> [--fetch]
  --fetch  download every run of the workflow and the jobs of each run that did not succeed (plus every 25th
           success, as a control) from the public GitHub API into <cache dir>; without it the cache is reused.
For each run, in time order, it evaluates the three versions of the notice on that run's real step outcomes:
  deployed   `failure() && vars.OUTAGE_NOTICE != '0'` with the variable unset (null): never true (probe 43125115555)
  pra_first  commit d5f221338: failure() + the outcome clause; de-duplicated against ANY failed run in 60 min
  pra_final  this PR: (failure() || cancelled()) + the outcome clause; quantum/outage_notice.run() with a fake ntfy
             that remembers what this replay "sent" (its de-duplication reads delivered notices only)
Nothing is sent anywhere. Prints a per-run table of every run where any version differs from "no notice"."""
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from quantum import outage_notice as on  # noqa: E402

API = "https://api.github.com/repos/fmve1232/Trading-View-Xauusd/actions"


def _get(url):
    return json.loads(subprocess.run(["curl", "-sS", url], capture_output=True, text=True, check=True).stdout)


def fetch(cache):
    os.makedirs(os.path.join(cache, "jobs"), exist_ok=True)
    runs, page = [], 1
    while True:
        d = _get(f"{API}/workflows/quantum-site.yml/runs?per_page=100&page={page}")
        rs = d.get("workflow_runs") or []
        if not rs:
            break
        runs += rs
        page += 1
    json.dump(runs, open(os.path.join(cache, "runs.json"), "w"))
    ok = sorted((r for r in runs if r["conclusion"] == "success"), key=lambda r: r["run_number"])
    want = [r for r in runs if r["conclusion"] != "success"] + ok[::25]
    for r in want:
        p = os.path.join(cache, "jobs", f"{r['id']}.json")
        if not os.path.exists(p):
            json.dump(_get(f"{API}/runs/{r['id']}/jobs?filter=all&per_page=10"), open(p, "w"))


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def build_vector(cache, run):
    p = os.path.join(cache, "jobs", f"{run['id']}.json")
    if not os.path.exists(p):
        return None
    for j in json.load(open(p)).get("jobs") or []:
        if j["name"] != "build" or j["conclusion"] in (None, "skipped"):
            continue
        st = {s["name"]: s["conclusion"] for s in j["steps"]}
        pipe = st.get("Run pipeline", "skipped")
        save = next((v for k, v in st.items() if k.startswith("Save the market-data store")), "skipped")
        first_bad = next((k for k, v in st.items() if v == "failure"), None)
        return {"failure": j["conclusion"] == "failure", "cancelled": j["conclusion"] == "cancelled",
                "pipeline": pipe or "skipped", "savestore": save or "skipped", "first_bad": first_bad}
    return None


def main():
    cache = sys.argv[1]
    if "--fetch" in sys.argv:
        fetch(cache)
    runs = sorted(json.load(open(os.path.join(cache, "runs.json"))), key=lambda r: r["created_at"])
    failed_created = [ts(r["created_at"]) for r in runs if r["conclusion"] == "failure"]
    sent_final = []

    class Fake:
        def poll(self, topic, window):
            return "\n".join(json.dumps({"event": "message", "time": t, "tags": [on.OUTAGE_TAG]}) for t in sent_final)

        def post(self, topic, body):
            sent_final.append(self.now)
            return 200

    fake, rows, totals = Fake(), [], {"deployed": 0, "pra_first": 0, "pra_final": 0}
    for r in runs:
        v = build_vector(cache, r)
        now = ts(r["updated_at"])
        rec = {"run": r["run_number"], "created": r["created_at"][:16], "conclusion": r["conclusion"],
               "first_bad": (v or {}).get("first_bad"), "pipeline": (v or {}).get("pipeline"),
               "savestore": (v or {}).get("savestore"), "deployed": False, "pra_first": False, "pra_final": False}
        if v:
            affected = v["pipeline"] != "success" or v["savestore"] != "success"
            if v["failure"] and affected:
                others = [t for t in failed_created if t != ts(r["created_at"]) and 0 <= now - t < 3600]
                rec["pra_first"] = not others
            if (v["failure"] or v["cancelled"]) and affected:
                fake.now = now
                res = on.run({"PIPELINE": v["pipeline"], "SAVESTORE": v["savestore"], "NTFY_TOPIC": "replay"},
                             now=now, poll=fake.poll, post=fake.post)
                rec["pra_final"] = res["sent"]
                rec["kind"] = res["kind"]
        for k in totals:
            totals[k] += rec[k]
        if r["conclusion"] != "success" or any(rec[k] for k in totals):
            rows.append(rec)
    print("| run | created (UTC) | conclusion | first failing step | pipeline | store save | deployed | first PR-A | this PR |")
    print("|---|---|---|---|---|---|---|---|---|")
    for x in rows:
        yn = lambda b: "**SEND**" if b else "-"   # noqa: E731
        print(f"| {x['run']} | {x['created']} | {x['conclusion']} | {(x['first_bad'] or '')[:40]} | {x['pipeline'] or ''} | "
              f"{x['savestore'] or ''} | {yn(x['deployed'])} | {yn(x['pra_first'])} | {yn(x['pra_final'])}"
              + (f" ({x.get('kind')})" if x["pra_final"] else "") + " |")
    print()
    print(json.dumps({"runs": len(runs), "not_success": sum(r["conclusion"] != "success" for r in runs), "notices": totals}))


if __name__ == "__main__":
    main()
