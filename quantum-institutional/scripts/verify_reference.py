#!/usr/bin/env python3
"""Verify the vendored Quantum 5.0 artefacts against their manifest.

Exits non-zero on any mismatch. Runs in CI on every push and is the same check
the upstream audit repository uses as its stop rule: a finding written against
different bytes is a false record.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "quantum_5_0"


def main() -> int:
    manifest = REFERENCE / "MANIFEST.sha256"
    if not manifest.exists():
        print(f"FAIL: {manifest} is missing", file=sys.stderr)
        return 2

    expected = {}
    for line in manifest.read_text().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            expected[name.strip()] = digest

    on_disk = {p.name for p in REFERENCE.glob("*.pine")}
    failures = 0

    for extra in sorted(on_disk - set(expected)):
        print(f"FAIL {extra}: present on disk but absent from the manifest")
        failures += 1

    for name, digest in sorted(expected.items()):
        path = REFERENCE / name
        if not path.exists():
            print(f"FAIL {name}: listed in the manifest but missing")
            failures += 1
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            print(f"FAIL {name}\n  expected {digest}\n  actual   {actual}")
            failures += 1
        else:
            print(f"OK   {name}")

    if failures:
        print(f"\n{failures} artefact(s) do not match. The reference is read-only.", file=sys.stderr)
        return 1
    print(f"\nAll {len(expected)} artefacts match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
