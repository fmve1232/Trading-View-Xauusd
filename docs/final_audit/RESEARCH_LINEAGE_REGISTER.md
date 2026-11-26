# Research lineage register (2026-11-26)

**Finding: no historical period is untouched.**
- The 2023–24 validation partition was read by 8 studies.
- The 2024–25 holdout was read by 3.
- The only data no study has seen is the live forward period from the 15 Nov 2026 freeze onward.
- No result in this programme may be described as "sealed out-of-sample" unless it comes from that period.

**Sources**
- `research/lineage/` on the remediation branch, written by `audit/tools/lineage.py`. The tool reads every research branch through `git show` and changes none.
- 4,045 distinct trial records across 16 branches.
- 38 registration files: 25 on production, 13 on branches only (B26–B29, B5C, PHASE_D, B31b-W3, W4, W5, W8, W8-cost, W12, W13).

## 1. Partitions

The split is from `audit/PREREGISTRATION.md` Amendment 13, written before any research data was opened.

| Partition | Dates (UTC) | Registered use |
|---|---|---|
| Development | 2020-01-24 02:00 → 2023-01-24 02:00 | explore; parameters may be chosen, with walk-forward and purging |
| Validation | 2023-01-24 → 2024-07-01 | one evaluation per registered variant |
| Holdout | 2024-07-01 → 2026-01-01 | once per hypothesis that passed validation; its result is final |
| Recent / live | 2026 onward | descriptive; the forward ledger from each freeze is the only prospective test |

**Leakage at the boundaries: none found.**
- `quantum/research/harness.py` `partition()` and W3's `run_part` slice the bars to the partition (`lo <= t < hi`), so an outcome cannot read a bar from the next partition. A trade near the end is left undecided (censored), not completed with future prices.
- Check: the W4 development trade file has 8,018 rows. Its last decision is at 2023-01-23 20:00 UTC, and 0 recorded target times fall after the end.
- Purged walk-forward (`harness.purged_folds`, purge plus embargo) is used by the B-studies that fit models (B19–B22). W13 uses 6 chronological folds with no model fitted.

## 2. Who read which partition

The table lists trial records per study and partition. "Other periods" are the 2026 or live windows, which are not sealed.

| Study | Trial records | Development | Validation 2023-24 | Holdout 2024-25 | Other periods read | First record (UTC) | Branches |
|---|---|---|---|---|---|---|---|
| B1 | 96 | 96 | — | — | — | 2026-10-31T21:54 | production +15 |
| B1b | 28 | 28 | — | — | — | 2026-10-31T21:56 | production +15 |
| B2 | 54 | 54 | — | — | — | 2026-11-01T08:07 | production +15 |
| B2b | 18 | 18 | — | — | — | 2026-11-01T08:18 | production +15 |
| B2c | 18 | 18 | — | — | — | 2026-11-01T08:27 | production +15 |
| B3 | 210 | 210 | — | — | — | 2026-11-01T08:44 | production +15 |
| B4 | 48 | 48 | — | — | — | 2026-11-01T15:44 | production +15 |
| B4-V | 1 | — | **1** | — | — | 2026-11-01T16:14 | production +15 |
| B5 | 18 | 18 | — | — | — | 2026-11-01T21:55 | production +15 |
| B5-explore | 6 | — | — | — | live-window-2026 (6) | 2026-11-01T16:30 | production +15 |
| B6-explore | 10 | — | — | — | live-window-2026 (10) | 2026-11-01T22:44 | production +15 |
| B7 | 22 | 22 | — | — | — | 2026-11-03T06:29 | production +15 |
| B8 | 32 | 32 | — | — | — | 2026-11-03T06:25 | production +15 |
| B9-explore | 50 | — | — | — | live-window-2026 (50) | 2026-11-04T23:32 | production +15 |
| B10 | 18 | 18 | — | — | — | 2026-11-05T07:18 | production +15 |
| B12-explore | 18 | — | — | — | live-window-2026 (18) | 2026-11-05T10:03 | production +15 |
| B13 | 24 | 20 | **4** | — | — | 2026-11-05T10:20 | production +15 |
| B14 | 12 | 12 | — | — | — | 2026-11-06T11:47 | production +15 |
| B16 | 6 | 6 | — | — | — | 2026-11-06T17:40 | production +15 |
| B17 | 10 | 10 | — | — | — | 2026-11-06T20:52 | production +15 |
| B18 | 8 | 8 | — | — | — | 2026-11-06T21:26 | production +15 |
| B19 | 317 | 298 | **19** | — | — | 2026-11-06T23:01 | production +15 |
| B19-explore | 2 | 2 | — | — | — | 2026-11-06T22:37 | production +15 |
| B19-month | 22 | — | — | — | recent (22) | 2026-11-07T06:57 | production +15 |
| B20 | 58 | 58 | — | — | — | 2026-11-07T07:15 | production +15 |
| B21 | 32 | 32 | — | — | — | 2026-11-07T07:33 | production +15 |
| B22 | 42 | 42 | — | — | — | 2026-11-07T07:53 | production +15 |
| B23 | 6 | — | **6** | — | — | 2026-11-07T07:59 | production +15 |
| B24-A1 | 1 | — | — | — | none (registration amendment, no data read) (1) | 2026-11-10T07:45 | production +12 |
| B24-A2 | 1 | — | — | — | none (registration amendment; signal frequencies from research/results/cf_validation.json, no outcome read) (1) | 2026-11-11T07:01 | production +12 |
| B25 | 141 | 50 | — | — | recent (91) | 2026-11-07T12:06 | production +15 |
| B26 | 48 | 16 | — | — | unsealed P2 (16), unsealed P3 (16) | 2026-11-08T17:45 | claude/research-phase-c +2 |
| B27 | 1212 | 1192 | — | — | unsealed 2026 (frozen check) (20) | 2026-11-08T18:33 | claude/research-phase-c +2 |
| B27-fix | 90 | 70 | — | — | unsealed 2026 (frozen check) (20) | 2026-11-09T13:01 | claude/research-phase-c +1 |
| B28 | 330 | 320 | — | — | unsealed 2026 (frozen check) (10) | 2026-11-09T05:46 | claude/research-phase-c +1 |
| B29 | 674 | 644 | — | — | unsealed 2026 (frozen check) (30) | 2026-11-09T05:46 | claude/research-phase-c +1 |
| B29-fix | 119 | 84 | — | — | unsealed 2026 (frozen check) (35) | 2026-11-09T13:01 | claude/research-phase-c +1 |
| B30 | 128 | 32 | **32** | **32** | recent (32) | 2026-11-15T07:03 | production +12 |
| B31 | 56 | 14 | **14** | **14** | recent (14) | 2026-11-15T08:24 | production +11 |
| B31b-W1 | 1 | 1 | — | — | — | 2026-11-16T02:40 | production +10 |
| B31b-W12 | 1 | 1 | — | — | — | 2026-11-25T17:51 | w12-session-sweeps +1 |
| B31b-W13 | 1 | 1 | — | — | — | 2026-11-25T21:12 | w13-entry-precision |
| B31b-W2 | 8 | 2 | **2** | **2** | recent (2) | 2026-11-18T13:56 | production +9 |
| B31b-W3 | 4 | 3 | — | — | recent (1) | 2026-11-18T21:44 | w11-scoreboard +5 |
| B31b-W4 | 1 | 1 | — | — | — | 2026-11-19T04:28 | w11-scoreboard +4 |
| B31b-W5 | 3 | 3 | — | — | — | 2026-11-19T08:36 | w11-scoreboard +3 |
| B31b-W7 | 1 | 1 | — | — | — | 2026-11-19T16:59 | w11-scoreboard +2 |
| B31b-W8 | 1 | 1 | — | — | — | 2026-11-25T16:44 | w8-quality |
| CF-VALIDATION | 30 | 10 | **10** | — | recent (10) | 2026-11-10T07:14 | production +12 |
| PR90-audit | 8 | — | — | — | recent (2026-03-01 on, unsealed) (8) | 2026-11-07T09:53 | production +15 |

**Validation and holdout openings, in order** (first record time, UTC):

| Date | Study | Partitions | What was scored |
|---|---|---|---|
| 1 Nov 16:14 | B4-V (B4-RN-V1) | validation | the one frozen B4 lead (round-number crossings): failed (41.5% vs 40.3% random) |
| 5 Nov 10:23 | B13 | validation | the B10 lead and the engine's 15m signals, Holm over two |
| 6 Nov 23:06 | B19 | validation | the two-stage confirmation rules |
| 7 Nov 07:59 | B23 | validation | B22's frozen ML rule, opened once |
| 10 Nov 07:14 | CF-VALIDATION | validation | the confirmation-panel rules |
| 15 Nov 07:04 | B30 | validation and holdout, pooled | $0 / $10 / $15 / $20 confirmation thresholds |
| 15 Nov 08:26 | B31 | validation and holdout | liquidity-aware modules A–E |
| 18 Nov 13:57 | B31b-W2 | validation and holdout | setup counts and their fates (why few trades); descriptive |

**Correction to B31's registration (GA-27).**
- `research/registrations/B31.json` line 12 says validation and holdout "have been read by B10, B13, B19, B20-B23 and B30".
- The trial records and result documents show development only for B10, B20, B21 and B22. B22's rule was validated by B23.
- The same line omits CF-VALIDATION and B4-V, which did read validation.
- The registration is not rewritten (registrations are immutable); this register is the correction.

**The W-series wording.** The W3–W13 result documents say "validation and holdout were not opened". That is true of each W-study itself (each logged development only), not of the partitions. GA-01 tracks an erratum note on those documents.

## 3. Selection decisions and their influence

| Decision | Basis | Data it saw | Assessment |
|---|---|---|---|
| Engine parameters (`quantum/config.py`) | the Pine Master's input defaults (build v21); never tuned on this history | the Pine line's TradingView history before the web port (disclosed in `audit/AUDIT_PROMPT.md` §9) | frozen since 15 Nov by the freeze key; any change restarts the forward test |
| H2–H5 arms | each amendment written before the arm was run on any price history (Amendments 5, 7, 8, 10) | none before registration | forward-only evidence |
| Live breakout and sweep monitors | operator directives (W7, A2–A4) | built after W3 / W7 found no entry edge | non-directional monitoring; entries kept in shadow |
| B23 validating B22 | B22 selected on development; B23 opened validation once | development, then validation | the protocol as registered |
| B30 / B31 opening holdout | registered and approved 15 Nov | validation and holdout | holdout results are final for those hypotheses, and spent |
| W13 ranking 50 mechanisms on development | each study's own registered rule; no new rule | development only, already read by W3–W8 | can only reject (stated in its registration) |

No production rule, threshold or alert was changed because of a validation or holdout result. The frozen files and the freeze key have stayed the same since 15 Nov.

## 4. Trial counts and multiple testing

- **One line per run, many rules per line.** `trials.jsonl` records about 4,045 distinct results. Several runs log one line for many rules:
  - W13: 50 mechanisms on one line;
  - W4: 15;
  - W5: 20;
  - W3: discovery, 3 runs with changed code, each logged.
- **Within-study correction only.** Holm is applied within each study. No program-wide correction over everything tried has been computed (GA-02). It would need each rule's trade series, which many records summarise rather than store.
- **The burden of proof is therefore high.** Any future candidate must pass on data no study has seen, which today means the forward period only.

## 5. Registrations and the order of work

- **What exists:** `research/lineage/registrations.json` gives, for each registration on each branch, the commit that added it and its committer date.
- **What it can show:** committer dates are set by the author, so they show order only weakly (GA-06).
- **Server-side proof:** GitHub's push and pull-request times are server-side. They were not collected for the 38 registrations in this round, so this is UNVERIFIED.
