"""Version stamping. Master prompt sections 44, 57 and 84.

Every analytical result must be reproducible, which means every result carries
the identity of the code, formulas, models and data that produced it.

The git commit is READ, never guessed. If it cannot be determined the value is
``None`` and the caller reports it as unknown -- a fabricated commit hash would
make a result look reproducible when it is not.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

__all__ = ["ENGINE_VERSION", "FORMULA_REGISTRY_VERSION", "SCHEMA_VERSION", "Stamp", "current_stamp"]

#: Bumped when engine BEHAVIOUR changes. Not tied to the package version.
ENGINE_VERSION: Final[str] = "0.1.0"

#: Bumped when any formula in docs/FORMULA_REGISTRY.md changes.
FORMULA_REGISTRY_VERSION: Final[str] = "0.1.0"

#: Highest applied migration in migrations/.
SCHEMA_VERSION: Final[str] = "0001"


@dataclass(frozen=True, slots=True)
class Stamp:
    """Identity of the code that produced a result.

    ``git_commit`` is ``None`` when it could not be determined. Consumers must
    render that as "unknown" and must not treat the result as reproducible.
    """

    engine_version: str
    formula_registry_version: str
    schema_version: str
    git_commit: str | None
    model_version: str | None = None
    data_version: str | None = None

    @property
    def is_reproducible(self) -> bool:
        """False when the commit is unknown -- the result cannot be re-derived."""
        return self.git_commit is not None


@lru_cache(maxsize=1)
def _git_commit() -> str | None:
    """Resolve the current commit, preferring an injected value.

    CI and containers set ``GIT_COMMIT`` (GitHub Actions provides ``GITHUB_SHA``)
    because the build artefact usually has no ``.git`` directory. Falling back
    to ``git rev-parse`` covers local development.
    """
    for env_var in ("GIT_COMMIT", "GITHUB_SHA"):
        value = os.environ.get(env_var)
        if value:
            return value.strip()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def current_stamp(model_version: str | None = None, data_version: str | None = None) -> Stamp:
    """Build the stamp for a result produced now."""
    return Stamp(
        engine_version=ENGINE_VERSION,
        formula_registry_version=FORMULA_REGISTRY_VERSION,
        schema_version=SCHEMA_VERSION,
        git_commit=_git_commit(),
        model_version=model_version,
        data_version=data_version,
    )
