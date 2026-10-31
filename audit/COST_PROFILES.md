# Per-account cost profiles — FundingPips and FundedNext (proposal and status, 2026-11-01)

**Scope:** position sizing on the site only (Risk & sizing card).

The forward test, every arm, every ledger and every backtest keep the **frozen** engine cost model in `config.py`:

| Component | Frozen value |
|---|---|
| Session spread | 0.30 in session, 0.50 off session |
| Slippage | 2 × 0.20 |
| Commission | $7 per lot round turn |

That model is not changed here. Changing it would need a pre-registration amendment and would restart the forward
test.

Code: `quantum/cost_profiles.py` (Python, the source of truth) and `site/costs.js` (the site's mirror). Neither is in
`holdout.ENGINE_SOURCES`. Tests:

- `tests/test_cost_profiles.py`: the engine profile equals the frozen model; hand-worked fixed and percentage fees;
  no double counting; nothing is marked verified.
- `tests/costs.test.mjs`: the JavaScript equals the Python on every profile.

## 1. What a profile holds

| Field | Values | Meaning |
|---|---|---|
| `commission.type` | `fixed` / `pct` | USD per lot, or percent of notional (lots × 100 oz × price) |
| `commission.rate` | number | the published figure |
| `commission.basis` | `per_side` / `round_turn` / `open_only` / `unconfirmed` | how often the fee is paid per round trip: 2 / 1 / 1 / **2 for sizing** (the higher reading) |
| `spread` | `engine` or a fixed value | `engine` = the session spread the engine charges at that bar |
| `slippage` | points per side | default 0.20, the engine's value |
| `status` | `FROZEN` / `UNVERIFIED` / `VERIFIED` / `USER` | **no profile is `VERIFIED` yet** |

**Cost per ounce, round trip:**

```
spread + 2 × slippage + commission per lot ÷ 100 oz
```

This is the engine's own formula, with each part counted once.

**Loss at the stop per lot:**

```
(stop distance + that cost) × 100
```

## 2. The profiles

All rates are as published by the firms, read from their help centres on 2026-11-01. Round-trip figures are per lot.

| ID | Firm and account | Published rate | Basis used for sizing | Round trip, 1 lot at $4,000 | Status |
|---|---|---|---|---|---|
| `engine` | Engine (frozen) | $7 per lot round turn | round turn | $7.00 | **FROZEN** (forward test) |
| `fp_standard` | FundingPips Standard (1-Step / 2-Step / Flex) | $5 per lot | **unconfirmed → per side** | $10.00 (or $5.00) | UNVERIFIED |
| `fp_zero` | FundingPips Zero | $7 per lot | unconfirmed → per side | $14.00 (or $7.00) | UNVERIFIED |
| `fp_swapfree` | FundingPips Swap-free (MT5) | $10 per lot | unconfirmed → per side | $20.00 (or $10.00) | UNVERIFIED |
| `fp_prime` | FundingPips Prime | $10 per lot flat | unconfirmed → per side | $20.00 (or $10.00) | UNVERIFIED |
| `fn_stellar_1step` | FundedNext Stellar 1-Step | 0.0016% of notional | per side (symbols page) | $12.80 | UNVERIFIED |
| `fn_stellar_2step` | FundedNext Stellar 2-Step | 0.0016% of notional | per side (symbols page) | $12.80 | UNVERIFIED |
| `fn_stellar_instant` | FundedNext Stellar Instant | 0.0016% of notional | on opening only (help article) | $6.40 | UNVERIFIED |
| `fn_stellar_lite` | FundedNext Stellar Lite | 0.0018% of notional | per side | $14.40 | UNVERIFIED |
| `custom` | any other account | entered by the viewer | entered by the viewer | — | USER |

Every profile uses `spread: engine` and slippage 0.20 per side until your MT5 evidence gives a measured spread.

**Contract:** 1 lot = 100 oz, so $1 of price movement = $100 per lot, on both firms' published specifications. That
is not yet checked against your MT5 symbol specification.

**FundedNext's worked example:** 1 lot at 4466.22 × 100 oz × 0.0016% = **$7.15** per side. FundedNext prints
$7.14, a rounding slip; `test_cost_profiles.py` checks the formula.

**Why "unconfirmed" sizes on the higher reading:** sizing on the lower reading could make the real loss at the stop
larger than the chosen risk %. The higher reading can only make the position smaller.

## 3. Conflicts and gaps in the published sources

1. **FundingPips** publishes a rate per lot, but nowhere says whether it is per side or round turn.
2. **FundedNext** contradicts itself. The symbols page says "commission charged per side". The Stellar Instant help
   article says commission is charged on the opening price and "no commission is applied at trade closing". A
   percentage fee charged per side would price the closing leg at the exit price; the code prices both legs at
   entry, a difference under 0.01% of the fee for a normal move.
3. FundedNext announces a new commission schedule from **12/01/2026**.
4. **Third-party reviews disagree** with both firms' own pages: commission-free metals, $2.50, $3, $5 round lot.
   They are not used.
5. **How these pages were read:** this session's network blocks `help.fundingpips.com` and `intercom.help`. The
   figures come from search-engine extracts of the official pages, not from the pages loaded directly.

## 4. How a profile becomes VERIFIED

Send the following for **each** account, firm and type:

1. **MT5 symbol specification:** right-click XAUUSD → Specification. It gives the contract size, digits and
   commission fields if shown.
2. **One closed XAUUSD trade, in the History tab's "Deals" view**, with the Commission column visible on both the
   **in** deal and the **out** deal. A screenshot or CSV is enough; never send passwords.

Then:

| What the deals show | Basis |
|---|---|
| Commission on both the in and the out deal | `per_side`; the rate per side = the shown fee ÷ lots |
| Commission on the in deal only | `open_only`, or `round_turn` charged at entry; the shown fee is the whole round trip |

Also:

- If one closed deal shows a percentage fee, its size compared with price × 100 × lots confirms the rate.
- A trade's bid / ask at entry and exit (or the spread column, if your MT5 shows it) gives a measured spread to
  replace `engine`.

Each confirmed profile gets `status: VERIFIED`, with the evidence date in `source`. That is a display-only edit; it
does not touch the freeze key.

## 5. What stays frozen

- `config.commission_l` stays **7.0 round turn**, `slippage_pts` 0.20, `spread_cost` 0.30.
- If your verified main account differs materially, the change can go into the same written amendment as the
  gap-stop fix (Amendment 14), so that the forward test restarts only once. That amendment is not written into
  `PREREGISTRATION.md` until you approve it.
- The Kelly % on the site is still computed from the engine's statistics under the frozen costs. Only the $-risk per
  lot (and so the lot size) follows the selected profile.
