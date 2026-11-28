# G3-NEWS: run status

**BLOCKED (28 Nov 2026): the registered second timestamp source cannot be read from this session.**

- **The rule.** The registration (`research/registrations/G3-NEWS.json`) lets an event enter only when its date agrees in two sources:
  - B8's committed dates;
  - an independent reading of the official calendars.
- **What failed.** The reading was attempted through the web-fetch tool on 28 Nov 2026. Every host was refused by the session's network policy before any page was reached, so no date was read:

  | Host | Calendar |
  |---|---|
  | `www.bls.gov` | CPI and Employment Situation archives |
  | `www.federalreserve.gov` | FOMC historical pages, 2020–2022 |
  | `www.bea.gov` | PCE and GDP |
  | `www.census.gov` | Retail sales |

- **What was not done.** No date was filled from memory, and no study was run.
- **What remains possible.** The code (`quantum/research/g3_news.py`) and its tests are committed, so it runs as registered once the official calendars can be read and saved here as `official.json`, with each list's source address and fetch time.
