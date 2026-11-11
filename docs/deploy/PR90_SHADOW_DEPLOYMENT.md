# PR #90: controlled shadow-only deployment

**Prepared, not executed.** Nothing here runs until the operator approves the merge in writing. The operator has not
authorised unrestricted production deployment, and has not authorised any trade execution.

## What shadow mode is

- **The website shows the two-stage card, marked SHADOW TEST.**
  - The card reads "recording and testing only. Not a trading recommendation."
  - Its headline is always NO TRADE — INSUFFICIENT CONFIRMATION.
  - All six trigger types are NOT VALIDATED. The flags are hard-coded; only a reviewed code change can alter them.
  - The confirmation rule is amendment B24-CONFIRM-FWD-A1: the first 15m close $15 beyond the trigger price confirms
    only if it is no more than $20 beyond; beyond $20 it is EXPIRED.
- **Records are append-only**, in `research_forward/`, copied to `forward-ledger` every run:
  - `CONFIRM-EVENTS.jsonl`: every stage event, hash-chained and anchored;
  - `CONFIRM-LIVE.json`: finished panel rows;
  - `B24-CONFIRM-FWD.json`: the registered forward test. It starts with the first run that carries its recorder, with
    no backfill.
- **Nothing is sent and nothing is executed.**
  - The panel and the recorder send no phone message.
  - No order code exists in production.
  - The frozen engine, `config.py`, the holdout and the freeze key `5e4630924d663fc5:a6f2be58c74887ed` are untouched.
- **Existing production alerts and plans are not modified.** The phone keeps receiving what it receives today: the
  deployed alert mode, its plans and their records. This deployment adds no phone alert and removes none.

## Steps (operator)

1. **The recorder is off unless `FWD_B24` = `1`** (amendment A2's fail-safe). Unset, empty, `0`, or a value saved as
   a Secret instead of a Variable all mean off. Leave `CONFIRM_PANEL` unset; unset means on.
   - **Incident, 2026-11-10:** the PR #90 code treated an unset `FWD_B24` as on. The hold-off value did not reach the
     workflow (the run log printed `FWD_B24:` empty), so B24 started by mistake at 21:35:34 UTC with 0 rows. The
     operator declared that start void; A2 moves it aside once and made off the default.
2. **Merge PR #90** into `claude/audit-prompt-real-artefacts-nekqv6`, then run `quantum-site.yml`, or wait for the
   15-minute scheduler.
   - The workflow's `pytest` step gates the deploy: a red suite deploys nothing.
3. **Check the first run** (stage 1: panel only):

   ```sh
   git clone --depth 1 --branch market-data   https://github.com/fmve1232/Trading-View-Xauusd.git store
   git clone --depth 1 --branch forward-ledger https://github.com/fmve1232/Trading-View-Xauusd.git ledger
   python docs/deploy/shadow_check.py --index <site URL>/data/index.json --store store --ledger ledger --b24-off
   ```

   It must print `SHADOW CHECK PASSED`. Look at the card: SHADOW TEST banner, NO TRADE, stages named.
   Where the site's `index.json` cannot be fetched, audit the records instead. Take a snapshot of both branches before
   the merge, and save the log of the last run before the merge and of the first run after it:

   ```sh
   python docs/deploy/shadow_store_check.py --store store --ledger ledger --before-store store_before \
       --before-ledger ledger_before --log first_run.log --log-before last_run_before.log --b24-off
   ```

   It must print `SHADOW STORE AUDIT PASSED`.
4. **Before B24 starts: amendment A2.** `research/registrations/B24-CONFIRM-FWD-A2.json` replaces the 2029-12-31
   deadline with a maximum administrative horizon (12 years after the start) and adds the INSUFFICIENT EVIDENCE end
   state. The recorder that implements it must be merged and deployed (a separate reviewed change) while `FWD_B24`
   is off (unset or `0`).
   - Check: the deployed `quantum/fwd_b24.py` has `HORIZON_YEARS = 12`, no `DEADLINE`, and `on()` true only for `1`.
   - Re-run step 3 with `--b24-off`; it must pass.
5. **Start B24** (stage 2), only with the operator's separate approval: set the repository **Variable** `FWD_B24` = `1`
   (Settings → Secrets and variables → Actions → **Variables** tab).
   - Check the next run's log: the "Run pipeline" env must print `FWD_B24: 1`.
   - The next run is B24's start: `started_utc` and `horizon_end_utc` in `B24-CONFIRM-FWD.json`.
   - Re-run step 3 without `--b24-off`; it must pass again.
6. **Watch** at least weekly:
   - re-run the check;
   - read B24's weekly report (in its record file, after each Friday New York close).
   - Every figure stays PRELIMINARY until a registered look (30 / 50 / 75 / 100 decided results). Nothing is called
     profitable or accurate before then.
   - Once a year, read the schedule report (`annual` in the record). It is descriptive and changes nothing.
   - If the horizon comes before a decision, the result is INSUFFICIENT EVIDENCE. That is not a measure of accuracy.

## Rollback

- **Fast, no code change:**
  - `CONFIRM_PANEL` = `0` removes the card and stops the event log;
  - `FWD_B24` unset or `0` stops the recorder.
  - Each switch is independent. With both at 0 the run's output is byte-identical to the deployed `2b782dbab` (tested).
  - Records already written stay, unchanged.
- **Full:** revert the merge commit (`git revert -m 1 <merge sha>`) and push; the next run deploys the previous code.
  - The previous code runs on the state and files this PR leaves behind and ignores them (tested).
  - A later re-deploy resumes from them.
- **Neither path moves the freeze key.**

## What would make it more than shadow (never without a new approval)

- marking any trigger type validated;
- sending the panel's stages to the phone;
- any order placement;
- changing the confirmation rule without a registered amendment.

`docs/deploy/shadow_check.py` fails on the first three and on a confirmation outside $15–$20.
