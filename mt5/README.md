# MT5 bridge: your broker's live price on the website (free)

`XauBridge.mq5` is a small **read-only** Expert Advisor. Every 2 seconds it sends the new ticks of the
chart it is attached to (bid, ask, millisecond time, tick flags) to your relay
(`xau-stream.fm-ve1232.workers.dev`). The website then shows:

- an **MT5 chip** in the top bar with your broker's live price and spread, on every device;
- the **MT5 broker feed** panel: bid/ask, tick volume, the same-bar difference from the engine's
  feed, and a footprint of the latest ticks per $0.50. The footprint is labelled PROXY: spot gold
  has no central traded volume.

It **never trades**: the code contains no order or position calls, and a test enforces that. It works
while MT5 and your PC are on. When they are off, the website shows the last data as offline.

## Setup (about 10 minutes, once)

### 1. Choose a push key and store it in GitHub
Make up a long random password of **at least 20 letters and numbers**, for example by mashing the
keyboard. It only stops strangers from sending fake prices to your relay.

GitHub → **Settings → Secrets and variables → Actions → New repository secret**:
- Name: `MT5_PUSH_KEY`
- Secret: your push key.

Then run **Actions → stream-relay → Run workflow**. It stores the key in the relay.

### 2. Install the EA in MT5 (on your PC)
1. Download `XauBridge.mq5` from this folder (open the file on GitHub, then **Download raw file**).
2. In MT5: **File → Open Data Folder** → open `MQL5` → `Experts` → copy `XauBridge.mq5` there.
3. In MT5: **Tools → MetaQuotes Language Editor** (or press F4). In the Navigator, open
   `Experts/XauBridge.mq5` and press **Compile** (F7). The bottom panel must say **0 errors**.
4. Back in MT5: **Tools → Options → Expert Advisors**:
   - tick **Allow WebRequest for listed URL** and add `https://xau-stream.fm-ve1232.workers.dev`.
   - You can leave **Allow algorithmic trading** off. That blocks all automated trading at the
     platform level, and the EA only sends prices.
5. Open an **XAUUSDm** chart. In the **Navigator → Expert Advisors**, drag **XauBridge** onto the chart.
6. In the **Inputs** tab, paste your push key into **PushKey**. Leave the other inputs as they are,
   then click **OK**.
7. The **Algo Trading** toolbar button can stay off (grey). Only if the Experts tab shows no
   "XauBridge: sending …" line, switch it on. The EA has no trading code either way.

### 3. Check
- MT5 **Experts** tab (bottom panel): `XauBridge: sending XAUUSDm ticks to … every 2000 ms (read-only).`
- Website: the **MT5** chip appears in the top bar within a few seconds while the market is open.

| Message in the Experts tab | Fix |
|---|---|
| `WebRequest failed (error 4014)` | The URL is not in Tools → Options → Expert Advisors → Allow WebRequest |
| `relay refused the PushKey (HTTP 403)` | PushKey ≠ the `MT5_PUSH_KEY` secret, or stream-relay was not re-run after adding it |
| `set PushKey …` | The PushKey input is empty or shorter than 16 characters |

## Limits (honest)
- **Updates every 2 seconds** (all ticks are sent, with their millisecond times). Faster would exceed
  Cloudflare's free daily request limit.
- **Only while the PC and MT5 are on.** For 24/7 operation without a PC you need a paid MT5 VPS
  (about $13–15 a month), or MetaApi (about $9 a month).
- **Display and validation only.** The engine and the forward test never read this feed.
