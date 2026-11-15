"""Check an archived run's payloads against the run's manifest line (read-only; audit IA-12).

  python3 -I audit/tools/payload_archive_check.py <forward-ledger checkout> <run id> <unzipped artifact dir>

Download the run's artifact `payloads-<run id>-<attempt>` from the Actions run page (or `gh run download`), unzip it, and
point this tool at it. It finds the run's line in manifests/runs-*.jsonl and compares every payload's SHA-256 and size.
Exit 0 only when every recorded payload is present and identical (extra files are reported, not accepted). Payloads are
vendor-derived market data: keep the downloaded copy out of the repository."""
import glob
import hashlib
import json
import os
import sys


def main() -> int:
    ledger, run_id, adir = sys.argv[1], sys.argv[2], sys.argv[3]
    line = None
    for path in sorted(glob.glob(os.path.join(ledger, "manifests", "runs-*.jsonl"))):
        with open(path) as f:
            for raw in f:
                if raw.strip():
                    r = json.loads(raw)
                    if str(r.get("run_id")) == str(run_id) and "payloads" in r:
                        line = r
    if line is None:
        print(f"no manifest line with payload digests for run {run_id}")
        return 2
    bad = 0
    for name, (sha, size) in sorted(line["payloads"].items()):
        p = os.path.join(adir, name)
        if not os.path.isfile(p):
            print(f"MISSING  {name}")
            bad += 1
            continue
        with open(p, "rb") as f:
            got = hashlib.sha256(f.read()).hexdigest()
        ok = got == sha and os.path.getsize(p) == size
        bad += not ok
        print(f"{'OK      ' if ok else 'CHANGED '} {name} {size} bytes")
    extra = sorted(set(n for n in os.listdir(adir) if n.endswith(".json")) - set(line["payloads"]))
    for n in extra:
        print(f"EXTRA    {n} (not in the manifest)")
    print(f"run {run_id} ({line.get('run_utc')}, commit {str(line.get('commit'))[:9]}): "
          f"{len(line['payloads']) - bad} of {len(line['payloads'])} payloads verified; artifact {line.get('payload_artifact') or '?'}")
    return 1 if bad or extra else 0


if __name__ == "__main__":
    sys.exit(main())
