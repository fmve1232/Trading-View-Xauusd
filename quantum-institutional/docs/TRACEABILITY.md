# Traceability

Master prompt §79 and §84. Every production number must answer: what, why, when,
from which data, using which formula, which model, which version, with what
probability, uncertainty and risk.

## The chain

```
raw data ──► feature ──► formula ──► engine ──► model ──► probability ──► risk ──► decision
   │           │           │           │          │            │            │          │
 source     formula_    formula_    engine_    model_    calibration_   engine_    git_commit
 timestamp  version     version     version    version   version        version
 data_version
```

Every arrow is a stored row, not a computation repeated on demand. `/trace`
(§47) walks it backwards from a `signal_id`.

## What is built

- `version.py` — `Stamp` carrying engine / formula / schema / model / data
  versions and the git commit.
- Every analytical table in migration 0001 carries those columns from the start,
  rather than having them retrofitted.
- `GET /version` exposes the current stamp.

## What is not

`/trace` itself, and the `audit_logs` writer. Phase 18.

## The commit is read, never guessed

`_git_commit()` prefers `GIT_COMMIT`, then `GITHUB_SHA`, then `git rev-parse`.
If none resolves, the value is `None` and `Stamp.is_reproducible` is `False`.

A fabricated hash would make an irreproducible result look reproducible, which
is worse than admitting the gap. CI injects `github.sha` because a build
artefact has no `.git` directory.

## Reference traceability

The vendored Quantum 5.0 artefacts are hash-pinned and verified in CI before
anything else runs. Every parity fixture and line citation is written against
those exact bytes; if they move, nothing downstream is meaningful, so the build
fails first rather than producing a result nobody can place.
