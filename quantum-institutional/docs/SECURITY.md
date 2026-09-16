# Security

Master prompt §66.

## Never committed

API keys · database passwords · broker credentials · tokens · private keys ·
`.env` files.

Enforced in three places, because convention alone fails:

1. `.gitignore` covers `.env`, `.env.*` (allowing `.env.example`), `*.pem`,
   `*.key`, `credentials.json`.
2. CI job `secrets` fails the build if a `.env` file or key material is
   **tracked** — `.gitignore` does not protect a file already added.
3. No secret has a default in `config.py`. A missing credential raises
   `DataUnavailable` at the point of use rather than falling back to an
   anonymous or demo endpoint.

If a credential is ever committed: **rotate it first**, then remove it from
history. A rotated key in git history is an embarrassment; an un-rotated one
removed from history is still compromised.

## Provider keys never reach the browser

Frontend JavaScript is readable by anyone who loads the page. Provider
credentials live server-side; the dashboard talks to this API, and this API
talks to providers. §66.

The corollary from §42: the dashboard must not recompute financial logic, which
also means it has no reason to hold a data-provider key.

## Execution safety

§63 and §65. `EXECUTION_MODE` defaults to `PAPER`. `LIVE` requires the exact
string. An unrecognised value **raises** rather than defaulting — a typo in a
deploy config stops the deploy instead of quietly changing what the system does.
Tested in `test_safety.py`.

## This repository is public

The Quantum 5.0 Pine source is vendored under `reference/quantum_5_0/` and is
therefore world-readable, including the gate logic, the evidence composite and
the calibration design. That was a deliberate choice. Anyone relying on the
strategy's confidentiality should treat that assumption as void.

Nothing else in the repository is sensitive: there are no credentials, no
broker details, no account identifiers, and no market data.

## Dependencies

Lower-bound pins today; a lockfile lands in Phase 21. Dependabot and a
vulnerability scan belong in the same phase.
