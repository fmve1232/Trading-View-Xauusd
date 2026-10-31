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

## 4. How a profile becomes VERIFIED — exact MT5 evidence (specified 2026-11-01)

A profile is marked VERIFIED only after the evidence below has been received **for that firm and account type**. One
firm's evidence never verifies another firm, and one account type never verifies another. Until then every firm
profile stays **UNVERIFIED**, and the frozen engine keeps $7 per lot round turn.

### 4.1 What to send for each account

Per account means each login, for example a FundingPips 2-Step and a FundedNext Stellar 2-Step separately.

| # | Evidence | Where in MT5 (desktop) | What it establishes |
|---|---|---|---|
| E1 | **Symbol specification** of the exact XAUUSD symbol traded, including any suffix such as `XAUUSD.r` | Market Watch → right-click the symbol → *Specification* | contract size (expected 100 oz), digits, tick size and tick value, the spread mode (floating or fixed), the stops level, swaps, and the commission row if the broker shows one |
| E2 | **The account type**, as named by the firm | firm dashboard, or *File → Login* account name | which profile the evidence belongs to |
| E3 | **Two closed XAUUSD trades of different volume**, for example 0.10 and 1.00 lot, ideally on different days | *Toolbox → History*, right-click → **Deals** view (not Positions), with the **Commission**, **Fee** and **Swap** columns visible | each trade's **IN** deal and **OUT** deal; see §4.2 |
| E4 | **The same two trades in the Orders view** | *Toolbox → History* → *Orders* | the order type (market, limit, stop), the requested price and the filled price, giving the real slippage |
| E5 | **At least one trade closed by its stop loss**, if available | History, Deals and Orders | the SL order price against the fill: the real stop slippage, and a gap fill if one happened |
| E6 | **A report export**, optional but complete | *History → right-click → Report → HTML* or *Open XML* | all of the above in one file |

Send screenshots or the export only. **Never send a password, investor or trading.** No login is needed for any
of this.

### 4.2 How each quantity is derived (written now, before any evidence is seen)

| Quantity | Rule |
|---|---|
| **Charged per side** | the commission is non-zero on **both** the IN and the OUT deal → basis `per_side`; rate per side = the deal's commission ÷ its volume in lots |
| **Charged on opening only (or a round turn charged at entry)** | non-zero on the IN deal only → basis `open_only` / `round_turn`; round trip per lot = IN commission ÷ volume |
| **Fixed or percentage** | compare the two trades of different volume and price: fixed if commission ÷ lots is equal; a percentage if commission ÷ (lots × 100 × price) is equal |
| **Round-trip commission per lot** | sum of the IN and OUT commission ÷ lots, for one trade |
| **Contract size** | E1 *Contract size*. Cross-check: the profit on the OUT deal = (exit − entry) × lots × contract size, for a USD account |
| **Fees other than commission** | the *Fee* column, recorded separately; added to the profile only if non-zero |
| **Spread** | E1 says whether the spread is floating. The measured spread is the ask − bid at entry, when the deal or the chart shows both. Otherwise the profile keeps `spread: engine` (0.30 / 0.50) and says so |
| **Slippage** | E4 / E5: \|filled price − requested price\| per market or stop order. One trade is anecdote: recorded, not used to set a parameter |
| **Swap** | E1 swap long and short, and the *Swap* column. Swap is **not** in the engine's cost model (trades rarely cross rollover on 5m–1h). It is recorded as an unmodelled cost, not added silently |

### 4.3 What happens with the evidence

1. **Each profile it confirms is updated** with `status: VERIFIED`, the evidence date and a short source note
   ("MT5 deals 2026-11-xx, IN and OUT both charged"). This is a display-only change; it does not touch the freeze key.
2. **If the evidence contradicts the published figure**, the profile takes the evidenced figure, and the discrepancy
   is written into §3.
3. **The frozen engine's $7 round turn is not changed by this.** Changing it needs its own written amendment
   (cost model, before/after impact, restart procedure) and the operator's explicit approval, in the same way as
   Amendment 14.
4. **Spread and slippage observations are recorded, not fitted.** Changing the engine's spread or slippage
   assumptions also needs an amendment.

## 5. What stays frozen

- `config.commission_l` stays **7.0 round turn**, `slippage_pts` 0.20, `spread_cost` 0.30.
- If your verified main account differs materially, the change can go into the same written amendment as the
  gap-stop fix (Amendment 14), so that the forward test restarts only once. That amendment is not written into
  `PREREGISTRATION.md` until you approve it.
- The Kelly % on the site is still computed from the engine's statistics under the frozen costs. Only the $-risk per
  lot (and so the lot size) follows the selected profile.
