"""IA-12 (audit 2026-11-14): closed bars are revised by the vendor and payloads were not kept, so a past decision could
not be replayed exactly as it was seen. Each run now archives site/data/*.json as an Actions artifact and the run's
manifest line records every payload's SHA-256 and size. Digests in these tests are computed independently (hashlib on the
bytes), not with the module's helper."""
import hashlib
import json
import os
import re
import subprocess
import sys

from quantum import holdout, manifest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _store(tmp_path):
    store, ledger, data = tmp_path / "store", tmp_path / "ledger", tmp_path / "data"
    for d in (store / "XAU_USD_15m", ledger, data):
        d.mkdir(parents=True)
    (store / "XAU_USD_15m" / "2026-11.csv").write_text("datetime,open,high,low,close,volume\n2026-11-13 21:45:00+00:00,1,2,0.5,1.5,\n")
    (data / "15m.json").write_bytes(b'{"meta":{"tf":"15m"}}')
    (data / "index.json").write_bytes(b'{"generated_utc":"2026-11-14T15:00:00+00:00"}')
    (data / "notes.txt").write_text("not a payload")
    return str(store), str(ledger), str(data)


def test_the_run_line_records_every_payload_digest_and_the_artifact(tmp_path):
    store, ledger, data = _store(tmp_path)
    line = manifest.record(store, ledger, "43606137153", "abc", "k", payload_dir=data, artifact="payloads-43606137153-1")
    want = {n: [hashlib.sha256(open(os.path.join(data, n), "rb").read()).hexdigest(), os.path.getsize(os.path.join(data, n))]
            for n in ("15m.json", "index.json")}
    assert line["payloads"] == want and line["payload_artifact"] == "payloads-43606137153-1"
    rows = [json.loads(x) for f in os.listdir(os.path.join(ledger, "manifests")) if f.startswith("runs-")
            for x in open(os.path.join(ledger, "manifests", f))]
    assert rows[-1]["payloads"] == want                                   # persisted in the ledger


def test_without_a_payload_dir_the_line_is_as_before(tmp_path):
    store, ledger, _ = _store(tmp_path)
    line = manifest.record(store, ledger, "1", "abc", "k")
    assert "payloads" not in line and "payload_artifact" not in line


def test_the_check_tool_accepts_the_copy_and_rejects_a_changed_byte(tmp_path):
    store, ledger, data = _store(tmp_path)
    manifest.record(store, ledger, "77", "abc", "k", payload_dir=data, artifact="payloads-77-1")
    tool = os.path.join(ROOT, "audit", "tools", "payload_archive_check.py")
    ok = subprocess.run([sys.executable, "-I", tool, ledger, "77", data], capture_output=True, text=True)
    assert ok.returncode == 0 and "2 of 2 payloads verified" in ok.stdout
    with open(os.path.join(data, "15m.json"), "ab") as f:
        f.write(b" ")
    bad = subprocess.run([sys.executable, "-I", tool, ledger, "77", data], capture_output=True, text=True)
    assert bad.returncode == 1 and "CHANGED  15m.json" in bad.stdout
    os.remove(os.path.join(data, "index.json"))
    gone = subprocess.run([sys.executable, "-I", tool, ledger, "77", data], capture_output=True, text=True)
    assert gone.returncode == 1 and "MISSING  index.json" in gone.stdout


def _steps():
    """The workflow's steps as text blocks (plain parsing: PyYAML is not a dependency of the production test gate)."""
    with open(os.path.join(ROOT, ".github", "workflows", "quantum-site.yml")) as f:
        src = f.read()
    return ["      - " + b for b in re.split(r"\n      - ", src)[1:]]


def test_the_workflow_archives_before_the_manifest_and_never_fails_the_run():
    steps = _steps()
    idx = {k: next(i for i, b in enumerate(steps) if k in b.split("\n", 1)[0])
           for k in ("name: Run pipeline", "name: Archive this run's payloads", "name: Data-versioning manifest")}
    ip, ia, im = idx["name: Run pipeline"], idx["name: Archive this run's payloads"], idx["name: Data-versioning manifest"]
    a, m = steps[ia], steps[im]
    assert ip < ia == im - 1                                              # after every writer, right before the manifest
    assert "uses: actions/upload-artifact@v4" in a and "continue-on-error: true" in a
    assert "path: site/data/*.json" in a and "name: payloads-${{ github.run_id }}-${{ github.run_attempt }}" in a
    assert "retention-days: ${{ vars.PAYLOAD_RETENTION_DAYS || 90 }}" in a
    assert '--payloads site/data --artifact "payloads-${{ github.run_id }}-${{ github.run_attempt }}"' in m
    assert "continue-on-error: true" in m
    assert "manifest.py" not in holdout.ENGINE_SOURCES                     # bookkeeping: outside the freeze key
