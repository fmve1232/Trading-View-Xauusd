# Reproducibility guide (2026-11-26)

Every number in `docs/final_audit/` can be reproduced with the commands below. Expected outputs are those measured on
2026-11-26.

A passing test suite shows that the code does what its tests say. It does not show that any strategy is profitable.

## 1. Environment

| Item | Version used |
|---|---|
| Python | 3.11.18 (venv created from `requirements.lock`) |
| numpy / pandas / pytest | 2.4.6 / 3.1.1 / 9.2.0 (pinned in `requirements.lock`) |
| Node | v22.23.4 (`node --test`) |
| OS | Linux 6.18 x86_64, glibc 2.39 |
| actionlint | installed binary |
| Research-only extras (not pinned) | `hmmlearn`, `scikit-learn`: without them 2 B22 tests skip |

## 2. Code checks

```sh
git clone https://github.com/fmve1232/Trading-View-Xauusd && cd Trading-View-Xauusd
git checkout claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-remediation
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.lock
.venv/bin/python -m pytest -q tests            # aad2af48d: 1092 passed, 2 skipped (7 min 45 s)
node --test tests/*.mjs                        # 20 pass, 0 fail
.venv/bin/python -c "from quantum import holdout, config; print(holdout.freeze_key(config.Config()))"
                                               # 1f88aad357497da4:4440d52587f5cc6b
sha256sum -c audit/MANIFEST.sha256             # 7 x OK
for t in precheck undeclared order deadcode pinelimits; do python3 audit/tools/$t.py artefacts/*.pine; done
python3 audit/tools/diag_parity.py             # PASS (3291 code lines)
python3 audit/tools/inventory.py               # 41 production modules; 47 switches; none unreferenced
actionlint .github/workflows/*.yml             # no output
mkdir -p /tmp/mut && python3 audit/tools/mutation_notify_delivery.py /tmp/mut   # 42 of 42 mutants killed
```

**On GitHub.** The repository's `pr-checks` workflow can be started by hand on any branch.
- Run 45810883836 on `aad2af48d` (2026-11-26 11:28 UTC) ended **success**, covering the full test suite with `requirements.lock`, the Pine checkers and the manifest.
- The final commit of this round is run the same way; its result is in `FINAL_AUDIT_REPORT.md`.

## 3. Records and data (read-only)

```sh
git fetch origin forward-ledger market-data research-data
mkdir fl md && git archive origin/forward-ledger | tar -x -C fl \
  && git archive origin/market-data XAU_USD_5m XAU_USD_15m XAU_USD_30m XAU_USD_60m alerts_state.json | tar -x -C md
python3 audit/tools/ledger_check.py fl                         # problems: 0; H6 final record 13 trades
python3 audit/tools/forward_report.py --ledger fl --bars md --json fr.json
python3 audit/tools/levels_check.py --state md/alerts_state.json --bars md          # 8 checked, 8 agree
python3 audit/tools/lineage.py --repo . --out /tmp/lineage     # 4045 distinct trial records; 38 registrations
python3 audit/tools/weighted_score.py                          # production 45.9 %, branch 68.0 %
```

**Differences to expect on a later date:**
- The ledger and the alert state grow every 15 minutes. Counts later than `forward-ledger` `c8a99d64e` and the
  `market-data` state of 11:04 UTC will differ.
- To reproduce exactly, check out those commits: `git archive c8a99d64e`.
- `market-data` is replaced every run, so its 11:04 state cannot be fetched later (that is GA-03). Its SHA-256 is in
  `CHANGELOG_AND_APPROVAL_REGISTER.md`.
- `forward_report.py` uses seed 20261126. The random baseline is identical for identical inputs.

**The durable outcome log (GA-03) on real records:**

```sh
mkdir -p st && cp md/alerts_state.json st/
python3 -m quantum.outcomes --append st
python3 -m quantum.outcomes --merge-ledger st/outcomes led/outcomes
python3 -m quantum.outcomes --verify led/outcomes --state st/alerts_state.json   # problems: []
```

## 4. Research results

The W-series results reproduce from their branches with `research-data` (development partition only). The commands
are in `docs/AUDIT_PACK.md` §5. W13's run reproduced the committed counts of W3, W7, W8 and W12 exactly (see
`research/B31B_W13_RESULTS.md` on the W13 branch).

**Limit:** the research input data is a single force-pushed commit (GA-15), so an exact rerun depends on the vendor
returning the same bars. The recorded data hash (`f113f97ad2105ff9`) shows whether it did.
