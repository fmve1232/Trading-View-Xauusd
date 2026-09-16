"""Every source file is actually tracked by git.

WHY THIS EXISTS
---------------
`.gitignore` carried an unanchored `data/` rule, intended for a top-level data
directory. It also matched `src/quantum_institutional/data/`, so the entire data
package -- contracts, validation, aggregation, point-in-time -- was silently
excluded from the first commit.

Nothing caught it locally, because the files were on disk and every test passed.
It would have surfaced as `ModuleNotFoundError` on the first clone.

A `.gitignore` pattern without a leading slash matches at every level. That is
easy to write and invisible afterwards, so it is checked rather than remembered.
"""

from __future__ import annotations

import pathlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def tracked_files() -> set[str]:
    """Files git tracks, as paths relative to ROOT.

    Skips unless ROOT is itself the repository root. When this tree is copied
    inside another repository -- which is how it is transported -- `git ls-files`
    resolves to the OUTER repository and returns paths relative to that root, so
    every path would appear untracked. That is an artefact of where the copy
    sits, not a defect in this repository, and a test that reported it as a
    failure would be lying about the copy it can actually see.
    """
    toplevel = _git("rev-parse", "--show-toplevel")
    if toplevel.returncode != 0:
        pytest.skip("not a git working tree")
    if pathlib.Path(toplevel.stdout.strip()).resolve() != ROOT:
        pytest.skip(f"ROOT is not the git root (nested inside {toplevel.stdout.strip()})")
    listing = _git("ls-files")
    if listing.returncode != 0:
        pytest.skip("git ls-files failed")
    return set(listing.stdout.split())


def source_files() -> list[Path]:
    return sorted(
        p
        for p in ROOT.glob("**/*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts and "build" not in p.parts
    )


def test_every_python_file_is_tracked() -> None:
    tracked = tracked_files()
    untracked = [str(p.relative_to(ROOT)) for p in source_files() if str(p.relative_to(ROOT)) not in tracked]
    assert not untracked, (
        "these Python files exist on disk but are not tracked by git, so a fresh "
        f"clone would not have them: {untracked}. Check .gitignore for an "
        "unanchored directory pattern."
    )


def test_every_package_directory_has_an_init() -> None:
    """A missing __init__.py is the other way a package vanishes on install."""
    package_root = ROOT / "src" / "quantum_institutional"
    missing = [
        str(d.relative_to(ROOT))
        for d in package_root.glob("**/")
        if "__pycache__" not in d.parts and not (d / "__init__.py").exists()
    ]
    assert not missing, f"package directories without __init__.py: {missing}"


def test_gitignore_data_rule_is_root_anchored() -> None:
    """The specific rule that caused the outage, pinned.

    Asserted on the text rather than on behaviour because the behaviour is only
    observable through git, and the point is that the pattern itself is wrong.
    """
    lines = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()]
    assert "data/" not in lines, (
        "an unanchored `data/` rule also matches src/quantum_institutional/data/; "
        "use `/data/` to limit it to the repository root"
    )
