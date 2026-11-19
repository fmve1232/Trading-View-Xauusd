# B31b-W7 results — M15 / M30 breakouts: detection, false breakouts and shadow entry prices (development 2020-23)

**Registration:** `research/registrations/B31b-W7.json` and amendment A1. Both were committed before any code was merged and before any replay or study run.

**Code:** `quantum/research/w7breakout.py` (sha256 `1059ccb06c561f2e…`), committed with its tests before the run. It measures the live detector `quantum/breakouts.py` (sha256 `e45abeaad1d02d9e…`), the code deployed in production since PR #133.

**Data:**
- Development partition only: Twelve Data XAU/USD 15 min, 2020-01-24 → 2023-01-24, data hash `f113f97ad2105ff9` (the same data as B31b-W3 … W5).
- Scoring starts after a 45-day warm-up, from 2020-03-09.
- M30 bars are resampled from M15 (45 incomplete M30 bars).
- M5 bars cover 95.2% of the scored span.
- **Validation (2023-01 → 2024-07) and holdout (2024-07 → 2026-01) were not opened.**

**Distances** are $ at a gold price of $4,000 (scaled by price / 4,000), as in W3–W5.

**Reproduce:**

```
python -m quantum.research.w7breakout --part development --rd <research-data clone> --out dev.json --csv trades.csv
```

Two runs gave byte-identical results JSON and trades CSV. Output: `research/results/b31b_w7_development_2026-11-19.json`, trades `research/results/b31b_w7_trades_development_2026-11-19.csv.gz`.

## Answer in one paragraph

**Detection is exact.** An independent re-implementation of the registered rules reproduces every one of the 12,110 production breakouts (8,005 M15, 4,105 M30): every field and every stage, with no difference.

**Detection is not trading success.**
- Of 11,655 breakouts whose 16-bar watch ended:
  - 28.8% failed before confirmation (false breakouts);
  - 45.6% failed after confirming;
  - only 25.6% did not close back inside the level within the watch.
- None of the registered ENTRY READY prices (E0–E4) has positive net expectancy after costs on either timeframe: **NO CANDIDATE**.
- One variant beat the matched-random control on the +$10-first rate: E0 on M15 (market at the breakout close), +3.5 points, Holm p = 0.04. Its net expectancy is still −0.027 R per trade (95% CI −0.085 … +0.032), so the registered rule correctly rejects it.

ENTRY READY stays in shadow; the phone keeps only the monitoring messages.

## (a) Detection accuracy

| TF | bars | events (production) | events (reference) | only production | only reference | field / stage differences | identical |
|---|---|---|---|---|---|---|---|
| M15 | 70,173 | 8,005 | 8,005 | 0 | 0 | 0 | yes |
| M30 | 35,064 | 4,105 | 4,105 | 0 | 0 | 0 | yes |


**How the reference was built.** It was written again from the registration text. It shares only the registered primitives (`sessions.calendar`, `shadow.build_pools`, `shadow.session_label`, `ta.atr`, `ta.pivothigh` / `pivotlow`) and models each level as an instance with its own lifetime. Any difference would have been a defect to fix before reporting; there were none.

**How its power was checked.** The study tests show the check fails when production is altered: a different range height, displacement threshold, watch length or swing life each breaks it. The reference also catches a level that appears with price already beyond it.

**Two registered rules that never bind:**
- *The 4-bar gap for equal highs / lows.* Two 3/3 pivots of the same side can never be fewer than 4 bars apart.
- *The bar on which a swing becomes known.* That bar's own close can never cross the swing.

## (b) Breakout quality: what happened after each breakout

A breakout here is a close beyond the level; a wick through it is not one. The stage rates use only events whose 16-bar watch ended (Wilson 95% intervals). "Failed" means a close back inside the level within the watch.


| group | events | displacement | accepted | confirmed | retest held | failed before confirmation (false breakout) | failed after confirmation | not failed in the watch |
|---|---|---|---|---|---|---|---|---|
| all | 11,655 | 42.0% (4896/11655; 41.1%–42.9%) | 29.2% (3404/11655; 28.4%–30.0%) | 71.2% (8300/11655; 70.4%–72.0%) | 26.6% (3095/11655; 25.8%–27.4%) | 28.8% (3355/11655; 28.0%–29.6%) | 45.6% (5313/11655; 44.7%–46.5%) | 25.6% (2987/11655; 24.8%–26.4%) |
| tf: M15 | 7,709 | 42.3% (3259/7709; 41.2%–43.4%) | 28.6% (2208/7709; 27.6%–29.7%) | 70.9% (5467/7709; 69.9%–71.9%) | 26.2% (2021/7709; 25.2%–27.2%) | 29.1% (2242/7709; 28.1%–30.1%) | 45.6% (3512/7709; 44.4%–46.7%) | 25.4% (1955/7709; 24.4%–26.3%) |
| tf: M30 | 3,946 | 41.5% (1637/3946; 40.0%–43.0%) | 30.3% (1196/3946; 28.9%–31.8%) | 71.8% (2833/3946; 70.4%–73.2%) | 27.2% (1074/3946; 25.9%–28.6%) | 28.2% (1113/3946; 26.8%–29.6%) | 45.6% (1801/3946; 44.1%–47.2%) | 26.2% (1032/3946; 24.8%–27.5%) |
| dir: BUY | 6,038 | 40.2% (2429/6038; 39.0%–41.5%) | 31.3% (1889/6038; 30.1%–32.5%) | 71.5% (4318/6038; 70.4%–72.6%) | 27.1% (1635/6038; 26.0%–28.2%) | 28.5% (1720/6038; 27.4%–29.6%) | 44.5% (2686/6038; 43.2%–45.7%) | 27.0% (1632/6038; 25.9%–28.2%) |
| dir: SELL | 5,617 | 43.9% (2467/5617; 42.6%–45.2%) | 27.0% (1515/5617; 25.8%–28.1%) | 70.9% (3982/5617; 69.7%–72.1%) | 26.0% (1460/5617; 24.9%–27.2%) | 29.1% (1635/5617; 27.9%–30.3%) | 46.8% (2627/5617; 45.5%–48.1%) | 24.1% (1355/5617; 23.0%–25.3%) |
| session: ASIAN | 3,673 | 39.3% (1442/3673; 37.7%–40.8%) | 32.6% (1196/3673; 31.1%–34.1%) | 71.8% (2638/3673; 70.3%–73.3%) | 29.2% (1073/3673; 27.8%–30.7%) | 28.2% (1035/3673; 26.7%–29.7%) | 46.6% (1710/3673; 44.9%–48.2%) | 25.3% (928/3673; 23.9%–26.7%) |
| session: LONDON | 4,719 | 53.7% (2533/4719; 52.3%–55.1%) | 22.3% (1052/4719; 21.1%–23.5%) | 76.0% (3585/4719; 74.7%–77.2%) | 28.4% (1342/4719; 27.2%–29.7%) | 24.0% (1134/4719; 22.8%–25.3%) | 50.7% (2393/4719; 49.3%–52.1%) | 25.3% (1192/4719; 24.0%–26.5%) |
| session: LONDON+NY | 1,002 | 45.2% (453/1002; 42.2%–48.3%) | 29.5% (296/1002; 26.8%–32.4%) | 74.8% (749/1002; 72.0%–77.3%) | 23.5% (235/1002; 20.9%–26.2%) | 25.2% (253/1002; 22.7%–28.0%) | 39.1% (392/1002; 36.1%–42.2%) | 35.6% (357/1002; 32.7%–38.6%) |
| session: NEW YORK | 1,426 | 22.4% (319/1426; 20.3%–24.6%) | 39.6% (565/1426; 37.1%–42.2%) | 62.0% (884/1426; 59.4%–64.5%) | 19.8% (283/1426; 17.9%–22.0%) | 38.0% (542/1426; 35.5%–40.6%) | 35.9% (512/1426; 33.5%–38.4%) | 26.1% (372/1426; 23.9%–28.4%) |
| session: OFF | 835 | 17.8% (149/835; 15.4%–20.6%) | 35.3% (295/835; 32.2%–38.6%) | 53.2% (444/835; 49.8%–56.5%) | 19.4% (162/835; 16.9%–22.2%) | 46.8% (391/835; 43.5%–50.2%) | 36.6% (306/835; 33.4%–40.0%) | 16.5% (138/835; 14.2%–19.2%) |
| primary: AS | 1,584 | 55.4% (877/1584; 52.9%–57.8%) | 22.6% (358/1584; 20.6%–24.7%) | 78.0% (1235/1584; 75.9%–79.9%) | 28.5% (451/1584; 26.3%–30.7%) | 22.0% (349/1584; 20.1%–24.1%) | 51.6% (818/1584; 49.2%–54.1%) | 26.3% (417/1584; 24.2%–28.5%) |
| primary: EQ | 981 | 46.4% (455/981; 43.3%–49.5%) | 31.1% (305/981; 28.3%–34.1%) | 77.5% (760/981; 74.8%–80.0%) | 31.0% (304/981; 28.2%–34.0%) | 22.5% (221/981; 20.0%–25.2%) | 49.7% (488/981; 46.6%–52.9%) | 27.7% (272/981; 25.0%–30.6%) |
| primary: LO | 656 | 30.6% (201/656; 27.2%–34.3%) | 35.2% (231/656; 31.7%–38.9%) | 65.9% (432/656; 62.1%–69.4%) | 22.4% (147/656; 19.4%–25.8%) | 34.1% (224/656; 30.6%–37.9%) | 38.3% (251/656; 34.6%–42.0%) | 27.6% (181/656; 24.3%–31.1%) |
| primary: NY | 842 | 32.9% (277/842; 29.8%–36.1%) | 31.8% (268/842; 28.8%–35.1%) | 64.7% (545/842; 61.4%–67.9%) | 24.1% (203/842; 21.3%–27.1%) | 35.3% (297/842; 32.1%–38.6%) | 39.7% (334/842; 36.4%–43.0%) | 25.1% (211/842; 22.3%–28.1%) |
| primary: PD | 1,142 | 61.3% (700/1142; 58.4%–64.1%) | 20.1% (229/1142; 17.8%–22.5%) | 81.3% (929/1142; 79.0%–83.5%) | 28.7% (328/1142; 26.2%–31.4%) | 18.7% (213/1142; 16.5%–21.0%) | 48.9% (558/1142; 46.0%–51.8%) | 32.5% (371/1142; 29.8%–35.3%) |
| primary: PW | 276 | 68.8% (190/276; 63.1%–74.0%) | 16.7% (46/276; 12.7%–21.5%) | 85.5% (236/276; 80.9%–89.2%) | 23.9% (66/276; 19.3%–29.3%) | 14.5% (40/276; 10.8%–19.1%) | 40.9% (113/276; 35.3%–46.8%) | 44.6% (123/276; 38.8%–50.5%) |
| primary: RG | 106 | 19.8% (21/106; 13.3%–28.4%) | 41.5% (44/106; 32.6%–51.0%) | 61.3% (65/106; 51.8%–70.0%) | 23.6% (25/106; 16.5%–32.5%) | 38.7% (41/106; 30.0%–48.2%) | 41.5% (44/106; 32.6%–51.0%) | 19.8% (21/106; 13.3%–28.4%) |
| primary: SW | 6,068 | 35.8% (2175/6068; 34.6%–37.1%) | 31.7% (1923/6068; 30.5%–32.9%) | 67.5% (4098/6068; 66.3%–68.7%) | 25.9% (1571/6068; 24.8%–27.0%) | 32.5% (1970/6068; 31.3%–33.7%) | 44.6% (2707/6068; 43.4%–45.9%) | 22.9% (1391/6068; 21.9%–24.0%) |
| tf_x_dir: M15:1 | 3,957 | 40.2% (1591/3957; 38.7%–41.7%) | 30.6% (1212/3957; 29.2%–32.1%) | 70.8% (2803/3957; 69.4%–72.2%) | 26.6% (1051/3957; 25.2%–28.0%) | 29.2% (1154/3957; 27.8%–30.6%) | 44.2% (1748/3957; 42.6%–45.7%) | 26.7% (1055/3957; 25.3%–28.1%) |
| tf_x_dir: M15:-1 | 3,752 | 44.5% (1668/3752; 42.9%–46.1%) | 26.5% (996/3752; 25.2%–28.0%) | 71.0% (2664/3752; 69.5%–72.4%) | 25.9% (970/3752; 24.5%–27.3%) | 29.0% (1088/3752; 27.6%–30.5%) | 47.0% (1764/3752; 45.4%–48.6%) | 24.0% (900/3752; 22.6%–25.4%) |
| tf_x_dir: M30:1 | 2,081 | 40.3% (838/2081; 38.2%–42.4%) | 32.5% (677/2081; 30.6%–34.6%) | 72.8% (1515/2081; 70.8%–74.7%) | 28.1% (584/2081; 26.2%–30.0%) | 27.2% (566/2081; 25.3%–29.2%) | 45.1% (938/2081; 42.9%–47.2%) | 27.7% (577/2081; 25.8%–29.7%) |
| tf_x_dir: M30:-1 | 1,865 | 42.8% (799/1865; 40.6%–45.1%) | 27.8% (519/1865; 25.8%–29.9%) | 70.7% (1318/1865; 68.6%–72.7%) | 26.3% (490/1865; 24.3%–28.3%) | 29.3% (547/1865; 27.3%–31.4%) | 46.3% (863/1865; 44.0%–48.5%) | 24.4% (455/1865; 22.5%–26.4%) |


**What the table shows.** These are descriptive differences on development data. They are not tuned rules, and none of them is a filter on the phone.

**Most breakouts do not hold.** Across all events, 74.4% close back inside within 16 bars. That is 4 h on M15 and 8 h on M30.

**Confirmed is not safe.** Of the 8,300 confirmed breakouts, 5,313 (64%) failed later inside the watch.

**By timeframe and direction:** M15 and M30 behave alike, and so do buy and sell breakouts.

**By session:**
- London breakouts confirm most often (76.0%) and fail before confirmation least often (24.0%).
- New York and off-session breakouts are the weakest: 38.0% and 46.8% false breakouts.
- Asia sits in between (28.2% false), and it was monitored like every other session.

**By the highest-ranked level crossed:**
- Previous-week (PW) and previous-day (PD) levels hold best: 14.5% and 18.7% false; 44.6% and 32.5% not failed in the watch.
- Asia session levels and equal highs / lows come next (22.0% and 22.5% false).
- Swing, London-session, New-York-session and range levels fail most (32.5%, 34.1%, 35.3% and 38.7% false).

**Not run:** volume or tick volume (the feed carries none), the bid / ask spread and executable-price deviation (there is no bid / ask feed; costs are the cost model), and the broker's contract size (100 oz per lot is assumed).

## Shadow entry prices E0–E4 against matched random entries

**Variants:**
- E0: market at the breakout close;
- E1: market at the confirmation close;
- E2: a limit at the level, placed at the confirmation close, valid 8 bars;
- E3: an M5 resume after a pullback, within 4 bars;
- E4: a limit at the middle of a displacement bar's body, valid 4 bars.

**Trade rules:**
- stop at the opposite extreme of the breakout structure − 0.2 ATR;
- targets +$10 / +$15 / +$20, each raced on its own against the stop on 15m bars refined on M5, with a 24 h time stop;
- size from $650 at the stop including the modelled cost.

**Counted trades:** ENTRY READY only: lot ≥ 0.01, cost ≤ 15% of the stop, entry ≤ 1 ATR beyond the level, and no same-side level within $10 ahead. One position at a time per variant and timeframe.

**Controls:**
- R1 = 20 market entries at random closes in the same watch window, same direction, stop distance and targets;
- R2 = the same moment, stop distance and targets in the opposite direction.

**Test (registered):** the paired difference of the +$10-first rate vs R1, with a day-clustered bootstrap, Holm-adjusted over the 10 variant × timeframe tests. A CANDIDATE needs Holm p < 0.05 **and** mean net R > 0 with its bootstrap lower bound > 0.


| variant : TF | orders → ready (funnel) | n decided | +$10 first | stop first (+$10 race) | +$15 first | +$20 first | mean net R (+$10) [day-boot 95%] | vs R1: rate − R1 rate [boot 95%], p | Holm p | vs R2 (opposite) mean R diff | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E0:M15 | 7711 → 1059 | 1031 | 51.3% (529/1031; 48.3%–54.3%) | 48.5% (500/1031; 45.5%–51.5%) | 39.7% (409/1031; 36.7%–42.7%) | 31.7% (327/1031; 28.9%–34.6%) | -0.027 [-0.085, +0.032] | +0.035 [+0.008, +0.063], p=0.004 | 0.04 | +0.115 | no |
| E0:M30 | 3950 → 1014 | 973 | 47.6% (463/973; 44.5%–50.7%) | 52.1% (507/973; 49.0%–55.2%) | 38.0% (370/973; 35.0%–41.1%) | 31.8% (309/973; 28.9%–34.7%) | -0.159 [-0.215, -0.102] | -0.018 [-0.047, +0.013], p=0.872 | 1.0 | -0.137 | no |
| E1:M15 | 5468 → 787 | 754 | 51.5% (388/754; 47.9%–55.0%) | 48.4% (365/754; 44.9%–52.0%) | 39.3% (296/754; 35.8%–42.8%) | 31.7% (239/754; 28.5%–35.1%) | -0.061 [-0.125, +0.007] | +0.034 [+0.007, +0.064], p=0.0085 | 0.07650000000000001 | +0.040 | no |
| E1:M30 | 2837 → 688 | 659 | 52.0% (343/659; 48.2%–55.8%) | 47.5% (313/659; 43.7%–51.3%) | 43.1% (284/659; 39.4%–46.9%) | 35.8% (236/659; 32.2%–39.5%) | -0.112 [-0.178, -0.045] | -0.005 [-0.041, +0.029], p=0.5945 | 1.0 | -0.087 | no |
| E2:M15 | 5468 → 655 | 646 | 43.8% (283/646; 40.0%–47.7%) | 56.0% (362/646; 52.2%–59.8%) | 36.2% (234/646; 32.6%–40.0%) | 30.0% (194/646; 26.6%–33.7%) | -0.127 [-0.208, -0.046] | +0.008 [-0.030, +0.043], p=0.332 | 1.0 | -0.074 | no |
| E2:M30 | 2837 → 642 | 640 | 47.3% (303/640; 43.5%–51.2%) | 52.5% (336/640; 48.6%–56.3%) | 40.3% (258/640; 36.6%–44.2%) | 32.8% (210/640; 29.3%–36.5%) | -0.122 [-0.193, -0.047] | +0.013 [-0.022, +0.047], p=0.24 | 1.0 | -0.047 | no |
| E3:M15 | 4382 → 621 | 598 | 48.0% (287/598; 44.0%–52.0%) | 52.0% (311/598; 48.0%–56.0%) | 37.6% (225/598; 33.8%–41.6%) | 29.9% (179/598; 26.4%–33.7%) | -0.104 [-0.182, -0.031] | +0.025 [-0.007, +0.057], p=0.0595 | 0.4165 | -0.029 | no |
| E3:M30 | 2717 → 691 | 655 | 49.8% (326/655; 46.0%–53.6%) | 49.9% (327/655; 46.1%–53.7%) | 39.4% (258/655; 35.7%–43.2%) | 32.2% (211/655; 28.7%–35.9%) | -0.123 [-0.191, -0.054] | +0.008 [-0.027, +0.042], p=0.333 | 1.0 | -0.101 | no |
| E4:M15 | 3260 → 543 | 541 | 41.4% (224/541; 37.3%–45.6%) | 58.4% (316/541; 54.2%–62.5%) | 32.0% (173/541; 28.2%–36.0%) | 26.2% (142/541; 22.7%–30.1%) | -0.167 [-0.252, -0.079] | -0.013 [-0.053, +0.027], p=0.731 | 1.0 | -0.124 | no |
| E4:M30 | 1638 → 497 | 496 | 49.2% (244/496; 44.8%–53.6%) | 50.2% (249/496; 45.8%–54.6%) | 41.1% (204/496; 36.9%–45.5%) | 33.5% (166/496; 29.5%–37.7%) | -0.084 [-0.169, +0.007] | +0.036 [-0.003, +0.078], p=0.0375 | 0.3 | +0.030 | no |

**Overall: NO CANDIDATE**

**Reading the table:**
- The +$10-first rates sit around 41–52%, against a geometric break-even near 50% plus costs.
- Every mean net R is negative. Seven of the ten day-clustered 95% intervals lie wholly below zero. The other three (E0:M15, E1:M15, E4:M30) reach just above it; no lower bound is above zero.
- **E0 on M15** is the only variant whose +$10-first rate beats R1 after Holm (+3.5 points, Holm p = 0.04). It still loses −0.027 R per trade after costs (interval −0.085 … +0.032), so it is not a candidate. The edge over a random entry is smaller than the cost of trading it.
- Against R2 (the same moment, the opposite direction), the breakout direction did better only for E0:M15 (+0.115 R), E1:M15 (+0.040 R) and E4:M30 (+0.030 R). For the other seven the opposite direction did as well or better, consistent with most breakouts closing back inside. Whatever direction information exists does not pay for the costs.
- **Limits:**
  - Waiting for the retest at the level (E2) lowers the +$10-first rate (43.8% M15, 47.3% M30). It also misses the move in 31–32% of confirmations (limit not filled within 8 bars).
  - E4's mid-body limit is not filled in 37% (M15) and 40% (M30) of cases, and is the worst on M15.
- **Over-extension and room** are what block most ENTRY READY candidates. On M15, 69% of E0 orders have an unbroken same-side level less than $10 ahead. On M15, E1 fails the extension check (more than 1 ATR beyond the level) in 36% of orders.

**By direction, stop size, cost, lot and realised loss at the stop** (ENTRY READY trades, one position at a time):

| variant : TF | BUY n / +$10 first / mean R | SELL n / +$10 first / mean R | median stop $ (at $4,000) | mean cost $ | median lot | realised loss at stop: max $ / over $650 |
|---|---|---|---|---|---|---|
| E0:M15 | 533 / 49.3% / -0.033 | 498 / 53.4% / -0.021 | 8.90 | 0.81 | 0.66 | 779 / 4 of 502 |
| E0:M30 | 529 / 45.4% / -0.177 | 444 / 50.2% / -0.137 | 10.10 | 0.83 | 0.59 | 2423 / 4 of 508 |
| E1:M15 | 385 / 49.6% / -0.074 | 369 / 53.4% / -0.048 | 9.47 | 0.82 | 0.63 | 753 / 3 of 366 |
| E1:M30 | 368 / 50.3% / -0.128 | 291 / 54.3% / -0.092 | 11.74 | 0.84 | 0.51 | 715 / 2 of 313 |
| E2:M15 | 309 / 40.8% / -0.182 | 337 / 46.6% / -0.076 | 8.28 | 0.80 | 0.71 | 715 / 2 of 362 |
| E2:M30 | 324 / 44.4% / -0.162 | 316 / 50.3% / -0.080 | 9.25 | 0.81 | 0.64 | 670 / 1 of 336 |
| E3:M15 | 325 / 46.8% / -0.118 | 273 / 49.5% / -0.088 | 8.89 | 0.81 | 0.67 | 892 / 3 of 311 |
| E3:M30 | 348 / 47.7% / -0.161 | 307 / 52.1% / -0.080 | 10.70 | 0.82 | 0.56 | 840 / 2 of 328 |
| E4:M15 | 239 / 40.6% / -0.184 | 302 / 42.1% / -0.153 | 8.39 | 0.79 | 0.70 | 704 / 3 of 317 |
| E4:M30 | 254 / 44.5% / -0.141 | 242 / 54.1% / -0.025 | 9.48 | 0.80 | 0.63 | 2922 / 1 of 250 |

**The planned loss is not a maximum.**
- In every variant, 1 to 4 stop-outs lost more than the $650 planned at the stop. The price gapped through the stop.
- The worst was $2,922 (E4 on M30) and the next $2,423 (E0 on M30).

**Sessions.** Each cell below is n: +$10-first rate / mean net R. These are descriptive subgroups. They were not separate registered tests, and their small sizes and multiple comparisons mean a positive cell is not evidence.

| variant : TF | ASIAN | LONDON | LONDON+NY | NEW YORK | OFF |
|---|---|---|---|---|---|
| E0:M15 | 175: 51% / -0.04 | 485: 50% / -0.05 | 146: 58% / +0.04 | 181: 51% / +0.02 | 44: 45% / -0.09 |
| E0:M30 | 235: 46% / -0.17 | 450: 49% / -0.15 | 109: 53% / -0.09 | 133: 46% / -0.13 | 46: 35% / -0.41 |
| E1:M15 | 159: 50% / -0.07 | 356: 51% / -0.07 | 84: 60% / +0.03 | 120: 52% / -0.03 | 35: 43% / -0.25 |
| E1:M30 | 191: 48% / -0.14 | 291: 54% / -0.10 | 75: 56% / -0.06 | 77: 55% / -0.07 | 25: 40% / -0.33 |
| E2:M15 | 75: 51% / -0.03 | 387: 43% / -0.14 | 89: 44% / -0.14 | 74: 47% / -0.03 | 21: 29% / -0.49 |
| E2:M30 | 107: 50% / -0.08 | 366: 46% / -0.14 | 78: 54% / -0.03 | 70: 41% / -0.20 | 19: 53% / -0.12 |
| E3:M15 | 124: 51% / -0.04 | 300: 48% / -0.09 | 61: 48% / -0.19 | 92: 46% / -0.16 | 21: 43% / -0.27 |
| E3:M30 | 165: 48% / -0.13 | 306: 48% / -0.14 | 80: 49% / -0.14 | 80: 58% / -0.02 | 24: 54% / -0.14 |
| E4:M15 | 45: 60% / +0.14 | 354: 38% / -0.21 | 75: 45% / -0.11 | 52: 44% / -0.11 | 15: 27% / -0.55 |
| E4:M30 | 66: 48% / -0.08 | 307: 50% / -0.06 | 60: 48% / -0.11 | 50: 44% / -0.14 | 13: 46% / -0.20 |

## Which features add information (walk-forward, out of sample)

**Method.** Section 4 features, each known at the breakout close or at the order. Six folds by time with purging, logistic models, and the gain in out-of-fold log-loss over the registered baseline. The baseline is stop distance, cost, ATR and session; positive gain = better.

**Two outcomes:**
- (A) the breakout does not fail within its watch (every event);
- (B) E1 reaches +$10 first (every E1 fill).

**(A) The breakout does not fail within its watch**

rows 11,655, out-of-fold 9,781, base rate 25.7%

| set | log-loss OOF | gain vs baseline per row [boot 95%] | Brier | AUC |
|---|---|---|---|---|
| baseline | 0.5490 | +0.00000 [+0.00000, +0.00000] | 0.1823 | 0.626 |
| +candle | 0.5320 | +0.01704 [+0.01260, +0.02163] | 0.1749 | 0.668 |
| +mtf_alignment | 0.5491 | -0.00006 [-0.00030, +0.00021] | 0.1823 | 0.625 |
| +room | 0.5501 | -0.00109 [-0.00245, +0.00025] | 0.1827 | 0.618 |
| +cost_stop | 0.5479 | +0.00111 [-0.00033, +0.00247] | 0.1818 | 0.631 |
| +regime | 0.5481 | +0.00096 [-0.00037, +0.00233] | 0.1819 | 0.625 |
| +level | 0.5490 | +0.00001 [-0.00167, +0.00178] | 0.1824 | 0.625 |
| +all | 0.5335 | +0.01558 [+0.01078, +0.02068] | 0.1755 | 0.666 |

**(B) E1 reaches +$10 first**

rows 8,300, out-of-fold 6,977, base rate 46.7%

| set | log-loss OOF | gain vs baseline per row [boot 95%] | Brier | AUC |
|---|---|---|---|---|
| baseline | 0.6609 | +0.00000 [+0.00000, +0.00000] | 0.2341 | 0.644 |
| +candle | 0.6624 | -0.00151 [-0.00300, -0.00009] | 0.2347 | 0.638 |
| +mtf_alignment | 0.6609 | -0.00001 [-0.00031, +0.00028] | 0.2341 | 0.644 |
| +room | 0.6618 | -0.00093 [-0.00160, -0.00029] | 0.2345 | 0.642 |
| +cost_stop | 0.6598 | +0.00110 [+0.00025, +0.00192] | 0.2336 | 0.646 |
| +regime | 0.6618 | -0.00095 [-0.00188, -0.00007] | 0.2345 | 0.640 |
| +level | 0.6651 | -0.00418 [-0.00693, -0.00149] | 0.2358 | 0.635 |
| +all | 0.6664 | -0.00553 [-0.00886, -0.00223] | 0.2365 | 0.631 |

**Reading:**
- **Outcome A (does the breakout hold):**
  - The candle of the breakout bar adds real out-of-sample information: penetration beyond the level / ATR, body / range, wicks with and against, body / ATR. Gain +0.017 log-loss per event (+0.013 … +0.022); AUC 0.626 → 0.668.
  - M15–M30 alignment, room to the next level, cost / stop, regime (ATR percentile, efficiency ratio) and level kind add nothing measurable beyond it.
- **Outcome B (does E1 reach +$10 first):**
  - Nothing beyond the baseline helps except cost / stop, which adds a tiny +0.0011.
  - Adding the candle, room, regime or level groups makes the out-of-sample fit worse.
  - Knowing a breakout is more likely to hold therefore does not translate into a better +$10-before-stop entry.
- Nothing here is a probability shown to anyone, and nothing here was turned into a filter.

## Live forward record and replays (descriptive)

**Live since 19 Nov 12:22 UTC** (production 84326fb47). The first 4.5 hours recorded two breakouts of the Asia low (3695.08):
- M15: displacement CONFIRMED at the 15:30 close, then RETEST HELD at 15:45;
- M30: DETECTED at 15:30, CONFIRMED (accepted) at 16:30.

Four phone messages were accepted by the server (DELIVERY_UNCONFIRMED: not proof the phone showed them), with 0 LATE and 0 send failures. An independent re-detection on the same live bars gives the same two events, stages and messages.

**Replays:**
- Real payloads 9–13 Nov (472 runs): 78 breakouts, 170 messages (23–45 a day); 15 failed before confirmation and 33 after.
- Live-store bars 17–19 Nov: 41 breakouts and 100 messages; 35 failed within the watch.
- Shadow E1 ENTRY READY on 17–19 Nov (n = 12): +$10 first 6, stop first 6.
- These counts are far too small to estimate anything. The live record stays descriptive until each variant has 100 decided shadow trades (registered).

## Verification

- **Tests:** `tests/test_research_w7breakout.py` has 21 tests. `tests/test_breakouts.py` has 31 tests for the live module.
- **Mutation of the study code:** 16 of 18 mutants killed; both survivors are equivalent (above). The live module: 42 of 43, the survivor equivalent.
- **Determinism:** two runs gave byte-identical results.
- **Sealed partitions:** validation and holdout were not opened. `main()` refuses any partition other than development, and `harness.partition` refuses sealed ones without an approved registration.

## What this changes

Nothing in production. The monitoring messages stay as deployed: DETECTED / CONFIRMED / RETEST HELD / FAILED, every session, both directions, M15 and M30 independently. ENTRY READY stays in shadow on the website and is never sent, because no breakout entry has positive expectancy on development data.

**Possible next step (needs your approval).** A breakout-quality filter built from the outcome-A candle features, or from the session / level differences above, would be a **new** registered study. Its rule would be frozen on development and checked once on validation, which is sealed. Neither the development result nor the live counts justify sending ENTRY READY.
