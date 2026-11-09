"""Phase C is frozen evidence (Phase D rule 1): its reports, results, registrations and the code that produced them
must stay byte-identical to commit c0496c13c, and the trial log may only grow (its first 3,808 lines never change)."""
import hashlib
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
MANIFEST = os.path.join(ROOT, "research", "PHASE_C_FROZEN.sha256")
TRIALS = os.path.join(ROOT, "research", "trials.jsonl")
TRIALS_PHASE_C_LINES = 3808
TRIALS_PHASE_C_SHA256 = "647c1cc27010992f8f7202e02e023bddc470bdc8645803ba38630eb0ede80c2a"


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def test_phase_c_evidence_is_unchanged():
    with open(MANIFEST) as fh:
        rows = [ln.split(maxsplit=1) for ln in fh if ln.strip() and not ln.startswith("#")]
    assert len(rows) >= 70
    changed = [p.strip() for h, p in rows if _sha(os.path.join(ROOT, p.strip())) != h]
    assert not changed, f"Phase C evidence changed: {changed}"


def test_trial_log_is_append_only_over_phase_c():
    with open(TRIALS, "rb") as fh:
        lines = fh.read().split(b"\n")
    assert len(lines) - 1 >= TRIALS_PHASE_C_LINES
    prefix = b"\n".join(lines[:TRIALS_PHASE_C_LINES]) + b"\n"
    assert hashlib.sha256(prefix).hexdigest() == TRIALS_PHASE_C_SHA256
