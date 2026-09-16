"""The vendored Quantum 5.0 artefacts must stay byte-identical.

The parity plan, every line citation and every finding in the upstream audit
are written against these exact bytes. A silent edit would invalidate all of
them, and the failure would surface much later as an unexplained parity
mismatch.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "quantum_5_0"
MANIFEST = REFERENCE / "MANIFEST.sha256"


def manifest_entries() -> list[tuple[str, str]]:
    entries = []
    for line in MANIFEST.read_text().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            entries.append((digest, name.strip()))
    return entries


def test_manifest_lists_all_five_artefacts() -> None:
    assert len(manifest_entries()) == 5
    assert len(list(REFERENCE.glob("*.pine"))) == 5


@pytest.mark.parametrize(("digest", "name"), manifest_entries(), ids=[n for _, n in manifest_entries()])
def test_artefact_matches_its_recorded_hash(digest: str, name: str) -> None:
    actual = hashlib.sha256((REFERENCE / name).read_bytes()).hexdigest()
    assert actual == digest, (
        f"{name} has changed. The vendored reference is read-only: if Quantum 5.0 "
        "genuinely moved to a new build, re-vendor it and re-derive every line "
        "citation in quantum_parity/ in the same commit."
    )
