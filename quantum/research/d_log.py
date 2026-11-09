"""Phase D's append-only trial log (research/phase_d_trials.jsonl). Research only.

Every record carries seq (1, 2, ...) and prev (the SHA-256 of the previous line's bytes; the first record's prev is
GENESIS). Editing, deleting or reordering any earlier line breaks the chain, and verify() names the first broken
record. Phase C's research/trials.jsonl is left as it is (append-only, pinned by tests/test_phase_c_frozen.py).
Records are written for EVERY registered trial run, whatever its result; nothing is ever removed.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

GENESIS = "GENESIS"
REQUIRED = ("phase", "kind", "id")


def _sha(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def _lines(path: str) -> list[bytes]:
    if not os.path.exists(path):
        return []
    with open(path, "rb") as fh:
        data = fh.read()
    if data and not data.endswith(b"\n"):
        raise ValueError(f"{path}: the last record is incomplete (no newline); not appending")
    return [ln for ln in data.split(b"\n") if ln]


def append(path: str, record: dict) -> dict:
    """Append one record (needs phase, kind, id). Returns the record as written."""
    missing = [k for k in REQUIRED if k not in record]
    if missing:
        raise ValueError(f"a Phase D record needs {missing}")
    if "seq" in record or "prev" in record:
        raise ValueError("seq / prev are assigned by the log")
    lines = _lines(path)
    ok, why = verify_lines(lines)
    if not ok:
        raise ValueError(f"{path}: chain broken before appending ({why})")
    rec = {"seq": len(lines) + 1, "prev": _sha(lines[-1]) if lines else GENESIS,
           "logged_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    line = json.dumps(rec, sort_keys=False, default=_default, allow_nan=False).encode("utf-8")
    with open(path, "ab") as fh:
        fh.write(line + b"\n")
    return rec


def _default(x):
    try:
        import numpy as np
        if isinstance(x, np.integer):
            return int(x)
        if isinstance(x, np.floating):
            return None if np.isnan(x) else float(x)
        if isinstance(x, np.ndarray):
            return x.tolist()
    except ImportError:                                      # numpy is always present here; kept for a bare reader
        pass
    return str(x)


def verify_lines(lines: list[bytes]) -> tuple[bool, str]:
    prev = GENESIS
    for i, ln in enumerate(lines, 1):
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            return False, f"record {i} is not JSON"
        if rec.get("seq") != i:
            return False, f"record {i} has seq {rec.get('seq')}"
        if rec.get("prev") != prev:
            return False, f"record {i}: prev does not match the previous line"
        prev = _sha(ln)
    return True, f"{len(lines)} records, chain intact"


def verify(path: str) -> tuple[bool, str]:
    return verify_lines(_lines(path))


def sanitize(x):
    """NaN / inf -> None, recursively (the log refuses non-JSON numbers)."""
    import math
    if isinstance(x, float):
        return None if (math.isnan(x) or math.isinf(x)) else x
    if isinstance(x, dict):
        return {k: sanitize(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [sanitize(v) for v in x]
    return x
