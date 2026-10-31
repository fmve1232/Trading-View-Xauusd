"""Forward-ledger consistency check (read-only). Usage: python audit/tools/ledger_check.py <forward-ledger checkout>

Checks every live ledger and every archive file for: attribution (each trade's freeze key matches its file's arm and
the key that was active when it was entered), duplicates, entry inside its key's window, and each trade's own
arithmetic (pts = gross - cost, R = pts / initial risk, level order, exit price consistent with the exit label)."""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

B = sys.argv[1]
man = json.load(open(os.path.join(B, "holdout_manifest.json")))
windows = {h["freeze_key"]: (h["freeze_utc"], h["ended_utc"]) for h in man["history"] if h.get("freeze_key")}
windows[man["freeze_key"]] = (man["freeze_utc"], "9999")
arm_hash = {}
for f in glob.glob(os.path.join(B, "holdout", "manifest_*.json")):
    a = os.path.basename(f)[9:-5]
    m = json.load(open(f))
    arm_hash[a] = {m["freeze_key"].rsplit(":", 1)[1]} | {h["freeze_key"].rsplit(":", 1)[1] for h in m.get("history", []) if h.get("freeze_key")}
ENGINE_ARMS = {"treatment", "control", "challenger"}
problems, counts = [], Counter()
seen = defaultdict(set)


def check(path, live):
    tf, arm = os.path.basename(path)[:-5].split("_", 1)
    L = json.load(open(path))
    for t in L:
        k = t.get("freeze_key", "")
        parts = k.split(":")
        main = ":".join(parts[:2])
        where = f"{'live' if live else 'archive'} {tf}_{arm} {t.get('entry_time')}"
        counts[(main, live)] += 1
        if live and main != man["freeze_key"]:
            problems.append(f"{where}: live trade under a non-current key {k}")
        if arm in ENGINE_ARMS and len(parts) != 2:
            problems.append(f"{where}: engine arm carries an arm suffix {k}")
        if arm not in ENGINE_ARMS and (len(parts) != 3 or (arm in arm_hash and parts[2] not in arm_hash[arm])):
            problems.append(f"{where}: arm suffix {k} is not one of {arm}'s keys")
        if main in windows:
            a, b = windows[main]
            if not (a[:19] <= t["entry_time"][:19] < b[:19]):
                problems.append(f"{where}: entry outside its key window {a[:19]}..{b[:19]}")
        dup = (tf, arm, k, t["entry_time"], t["dir"])
        if dup in seen["x"]:
            problems.append(f"{where}: duplicate")
        seen["x"].add(dup)
        risk = abs(t["entry"] - t["sl"])
        if abs(t["pts"] - (t["gross_pts"] - t["cost_pts"])) > 2e-3:
            problems.append(f"{where}: pts != gross - cost")
        if risk > 0 and abs(t["r"] - t["pts"] / risk) > 2e-3 * max(1, abs(t["r"])):
            problems.append(f"{where}: r != pts / risk ({t['r']} vs {t['pts'] / risk:.4f})")
        lg = t["dir"] == "LONG"
        if not ((t["sl"] < t["entry"] < t["tp1"] <= t["tp2"]) if lg else (t["sl"] > t["entry"] > t["tp1"] >= t["tp2"])):
            problems.append(f"{where}: level order broken sl {t['sl']} entry {t['entry']} tp1 {t['tp1']} tp2 {t['tp2']}")
        why = t["exit_reason"]
        if why == "SL" and abs(t["exit"] - t["sl"]) > 1e-3:
            problems.append(f"{where}: SL exit not at the stop")
        if why == "BE" and abs(t["exit"] - t["entry"]) > 1e-3:
            problems.append(f"{where}: BE exit not at entry")
        if why == "TP2" and main.endswith("6f3964ad97813cc9") and abs(t["exit"] - t["tp2"]) > 1e-3:
            problems.append(f"{where}: web.6 TP2 exit not at TP2")
        if why in ("SL_GAP", "BE_GAP") and main.endswith("6f3964ad97813cc9"):
            problems.append(f"{where}: web.6 trade carries a web.7 label")
        if why not in ("SL", "BE", "TP2", "FLIP", "SL_GAP", "BE_GAP"):
            problems.append(f"{where}: unexpected exit label {why}")
        if t["exit_time"] < t["entry_time"] or t.get("bars", 0) < 0 or t.get("open"):
            problems.append(f"{where}: time order / open flag")
        if t.get("recorded_utc") and t["recorded_utc"][:19] < t["exit_time"][:19]:
            problems.append(f"{where}: recorded before its exit")


for f in sorted(glob.glob(os.path.join(B, "holdout", "*_*.json"))):
    if not os.path.basename(f).startswith("manifest"):
        check(f, True)
for f in sorted(glob.glob(os.path.join(B, "holdout", "archive", "*.json"))):
    check(f, False)
print("keys:", {f"{k[0][-16:]} ({'live' if k[1] else 'archive'})": v for k, v in sorted(counts.items())})
print("current key:", man["freeze_key"], man["engine_version"], man["freeze_utc"])
print(f"problems: {len(problems)}")
for p in problems[:40]:
    print("  ", p)
