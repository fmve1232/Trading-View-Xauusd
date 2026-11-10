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

1. **Before the merge, hold the recorder off.** In GitHub, Settings → Secrets and variables → Actions → Variables, set
   `FWD_B24` = `0`. Leave `CONFIRM_PANEL` unset; unset means on.
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
4. **Start B24** (stage 2): delete the `FWD_B24` variable, or set it to `1`.
   - The next run is B24's start: `started_utc` in `B24-CONFIRM-FWD.json`.
   - Re-run step 3 without `--b24-off`; it must pass again.
5. **Watch** at least weekly:
   - re-run the check;
   - read B24's weekly report (in its record file, after each Friday New York close).
   - Every figure stays PRELIMINARY until a registered look (30 / 50 / 75 / 100 decided results). Nothing is called
     profitable or accurate before then.

## Rollback

- **Fast, no code change:**
  - `CONFIRM_PANEL` = `0` removes the card and stops the event log;
  - `FWD_B24` = `0` stops the recorder.
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
