# XAU/USD tick relay (display only)

Streams XAU/USD ticks to the website's live chip and forming candle, at most 4 updates a second.
The engine never reads them: signals come from closed bars, and the forward test is unaffected.

```
Finnhub WebSocket ──(one connection, key in a Worker secret)──► Cloudflare Worker + Durable Object hub
                                                                 └──► every open browser tab (wss://…/stream)
```

- **One** upstream connection, opened while someone is watching and closed when the last viewer leaves.
- **Only your site may connect** (`ALLOWED_ORIGINS` in `wrangler.toml`), so nobody else can spend your key.
- The **key never reaches a browser**. Messages from browsers are ignored.
- Cost: Cloudflare Workers free plan (Durable Objects included); Finnhub free plan.

## Setup (about 10 minutes, one time)

1. **Finnhub:** sign up at https://finnhub.io and copy your API key.
2. **Cloudflare:** sign up at https://dash.cloudflare.com (free), then:
   - *My Profile → API Tokens → Create Token →* template **Edit Cloudflare Workers** → copy the token;
   - copy your **Account ID** (shown on the Workers & Pages overview page).
3. **GitHub:** go to *Settings → Secrets and variables → Actions → New repository secret*. Add three secrets:
   `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and `FINNHUB_KEY`.
4. **Deploy:** go to *Actions → stream-relay → Run workflow*. The run summary prints the stream address,
   `wss://xau-stream.<your-subdomain>.workers.dev/stream`.
5. **Connect the site:** go to *Settings → Secrets and variables → Actions → **Variables** → New variable*,
   name it `STREAM_URL`, and paste that address. The site picks it up on its next run (within 15 minutes).

Check it at `https://xau-stream.<your-subdomain>.workers.dev/health`. It should show `{"ok":true,…,"key":true}`.
The live chip shows **stream** when ticks are arriving. Hover over it to see the relay status.

## If no ticks arrive

The chip keeps using the 60-second gold-api price, and its tooltip shows the relay status:

| Status | Meaning |
|---|---|
| `no Finnhub key configured` | The `FINNHUB_KEY` secret is missing: add it and run the workflow again. |
| `upstream: …` | Finnhub refused (e.g. the symbol is not on your plan). Try another symbol in `wrangler.toml`, e.g. `SYMBOL = "FXCM:XAU/USD"`. |
| `live`, but no ticks | The market is closed, or Finnhub sends no gold ticks on the free plan. |

Streaming gold on Finnhub's free plan has **not been verified** yet. The first deploy will show whether it works.
