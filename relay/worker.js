// XAU/USD tick relay -- Cloudflare Worker + one Durable Object hub. DISPLAY ONLY.
//
// Browsers connect to wss://<worker>/stream. The hub keeps ONE upstream WebSocket to Finnhub
// (opened while at least one viewer is connected, closed when the last one leaves), and fans the
// ticks out, throttled to at most 4 messages a second per hub: {type:"tick", p, t, h, l, n}
// = last price, its time (ms), high / low / count since the previous message.
//
// The Finnhub key lives only in the Worker secret FINNHUB_KEY; it never reaches a browser.
// ALLOWED_ORIGINS (comma-separated) limits which sites may connect, so nobody else can spend
// the key's quota. Messages from browsers are ignored. Nothing here feeds the engine.
//
// MT5 bridge (optional): the operator's MT5 Expert Advisor (mt5/XauBridge.mq5) POSTs batches of
// broker ticks to /mt5 with the header X-Push-Key = the Worker secret MT5_PUSH_KEY. The hub keeps
// the last tick, 1-minute bars (persisted) and the last ticks for a footprint, streams
// {type:"mt5"} to viewers (at most 4 a second), and serves GET /mt5/snapshot to the site and
// the pipeline. Without the secret, /mt5 refuses every push.

const MAX_CLIENTS = 200;
const SEND_EVERY_MS = 250;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ ok: true, symbol: env.SYMBOL || "OANDA:XAU_USD", key: Boolean(env.FINNHUB_KEY) }),
        { headers: { "content-type": "application/json" } });
    }
    if (url.pathname === "/mt5" && req.method === "POST") {
      if (!env.MT5_PUSH_KEY || !safeEqual(req.headers.get("X-Push-Key") || "", env.MT5_PUSH_KEY)) return new Response("forbidden", { status: 403 });
      return env.HUB.get(env.HUB.idFromName("xau")).fetch(req);
    }
    if (url.pathname === "/mt5/snapshot") {
      const origin = req.headers.get("Origin") || "";
      if (origin && !originAllowed(origin, env.ALLOWED_ORIGINS)) return new Response("origin not allowed", { status: 403 });
      const r = await env.HUB.get(env.HUB.idFromName("xau")).fetch(req);
      const h = new Headers(r.headers);
      if (origin) { h.set("Access-Control-Allow-Origin", origin); h.set("Vary", "Origin"); }
      h.set("Cache-Control", "no-store");
      return new Response(r.body, { status: r.status, headers: h });
    }
    if (url.pathname !== "/stream") return new Response("not found", { status: 404 });
    if ((req.headers.get("Upgrade") || "").toLowerCase() !== "websocket") return new Response("expected a WebSocket", { status: 426 });
    if (!originAllowed(req.headers.get("Origin") || "", env.ALLOWED_ORIGINS)) return new Response("origin not allowed", { status: 403 });
    return env.HUB.get(env.HUB.idFromName("xau")).fetch(req);
  },
};

export function originAllowed(origin, list) {
  const allowed = String(list || "").split(",").map((s) => s.trim()).filter(Boolean);
  return allowed.length === 0 || allowed.includes(origin);
}

// Constant-time comparison for the push key.
export function safeEqual(a, b) {
  a = String(a); b = String(b);
  let d = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) d |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return d === 0;
}

// ---- MT5 bridge -------------------------------------------------------------------------------
export const MT5_BARS = 1500;          // 1-minute bars kept (about a trading day)
export const MT5_TICKS = 3000;         // recent ticks kept for the footprint
const TICK_FLAG_BUY = 32, TICK_FLAG_SELL = 64;   // MQL5 flags: set only by exchange instruments

// EA payload -> validated ticks [t_ms, bid, ask, last, volume, flags]. A tick is rejected if it is
// not finite, crossed (ask < bid), older than the last accepted one, or more than 5% from it
// (a feed glitch must not look like a market move). Nothing is ever repaired or filled in.
export function cleanTicks(ticks, lastT = 0, lastMid = null) {
  const out = []; let rej = 0;
  for (const k of Array.isArray(ticks) ? ticks : []) {
    const [t, b, a, l = 0, v = 0, f = 0] = Array.isArray(k) ? k.map(Number) : [];
    const mid = (b + a) / 2;
    if (![t, b, a].every(Number.isFinite) || b <= 0 || a < b || t < lastT || (lastMid && Math.abs(mid / lastMid - 1) > 0.05)) { rej++; continue; }
    out.push([t, b, a, Number.isFinite(l) ? l : 0, Number.isFinite(v) ? v : 0, Number.isFinite(f) ? f : 0]);
    lastT = t; lastMid = mid;
  }
  return { ticks: out, rejected: rej };
}

// 1-minute bars on the mid: [open_s, o, h, l, c, ticks, spread_sum].
export function addToBars(bars, ticks) {
  for (const [t, b, a] of ticks) {
    const m = (b + a) / 2, open = Math.floor(t / 60000) * 60, last = bars[bars.length - 1];
    if (last && last[0] === open) { last[2] = Math.max(last[2], m); last[3] = Math.min(last[3], m); last[4] = m; last[5]++; last[6] += a - b; }
    else if (!last || open > last[0]) bars.push([open, m, m, m, m, 1, a - b]);
  }
  if (bars.length > MT5_BARS) bars.splice(0, bars.length - MT5_BARS);
  return bars;
}

// Ticks per $step price level. Real buy/sell when >= 80% of ticks carry the exchange's deal flags
// and a volume; otherwise the tick rule on the mid (up-tick = buy), labelled a PROXY.
export function footprint(ticks, step = 0.5) {
  if (ticks.length < 2) return { n: ticks.length, levels: [], method: "UNAVAILABLE" };
  const real = ticks.filter((k) => (k[5] & (TICK_FLAG_BUY | TICK_FLAG_SELL)) && k[4] > 0).length >= 0.8 * ticks.length;
  const lv = new Map(); let prev = (ticks[0][1] + ticks[0][2]) / 2, dir = 0;
  for (const k of ticks.slice(1)) {
    const m = (k[1] + k[2]) / 2; let d, w = 1;
    if (real) { d = k[5] & TICK_FLAG_BUY ? 1 : k[5] & TICK_FLAG_SELL ? -1 : 0; w = k[4]; }
    else d = m > prev ? 1 : m < prev ? -1 : dir;
    prev = m; if (!d) continue; dir = d;
    const p = Math.round(Math.floor(m / step) * step * 100) / 100;
    const e = lv.get(p) || [0, 0]; e[d > 0 ? 0 : 1] += w; lv.set(p, e);
  }
  const levels = [...lv.entries()].sort((x, y) => y[0] - x[0]).map(([price, [buy, sell]]) => ({ price, buy, sell, delta: buy - sell }));
  const buy = levels.reduce((s, x) => s + x.buy, 0), sell = levels.reduce((s, x) => s + x.sell, 0);
  const poc = levels.length ? levels.reduce((m, x) => (x.buy + x.sell > m.buy + m.sell ? x : m)).price : null;
  return { n: ticks.length, from_ms: ticks[0][0], to_ms: ticks[ticks.length - 1][0], step, levels, buy, sell, delta: buy - sell, poc,
           method: real ? "DEAL_SIDE_VOLUME" : "TICK_RULE_PROXY" };
}

// Finnhub trade message -> the newest valid tick for `symbol` plus the batch's high/low/count.
export function pickTicks(msg, symbol) {
  if (!msg || msg.type !== "trade" || !Array.isArray(msg.data)) return null;
  const ok = msg.data.filter((x) => x && x.s === symbol && Number.isFinite(x.p) && x.p > 0 && Number.isFinite(x.t));
  if (!ok.length) return null;
  let last = ok[0], h = -Infinity, l = Infinity;
  for (const x of ok) { if (x.t >= last.t) last = x; h = Math.max(h, x.p); l = Math.min(l, x.p); }
  return { p: last.p, t: last.t, h, l, n: ok.length };
}

export class Hub {
  constructor(state, env) {
    this.state = state; this.env = env;
    this.clients = new Set(); this.up = null; this.status = "idle"; this.backoff = 1000;
    this.last = null; this.batch = null; this.timer = null; this.lastSent = 0;
    this.mt5 = null; this.mt5Ticks = []; this.mt5Saved = 0; this.mt5Timer = null; this.mt5SentAt = 0;
  }
  async loadMt5() {
    if (this.mt5) return this.mt5;
    let saved = null;
    try { saved = this.state.storage ? await this.state.storage.get("mt5") : null; } catch (e) { saved = null; }
    this.mt5 = saved || { sym: "", server: "", digits: 2, last: null, rx: 0, bars: [], rejected: 0 };
    return this.mt5;
  }
  async ingestMt5(body, now = Date.now()) {
    const s = await this.loadMt5();
    const lastMid = s.last ? (s.last.b + s.last.a) / 2 : null;
    const { ticks, rejected } = cleanTicks(body && body.ticks, s.last ? s.last.t : 0, lastMid);
    s.rejected += rejected;
    if (body && body.sym) s.sym = String(body.sym).slice(0, 32);
    if (body && body.server) s.server = String(body.server).slice(0, 64);
    if (body && Number.isFinite(Number(body.digits))) s.digits = Number(body.digits);
    s.rx = now;
    if (ticks.length) {
      addToBars(s.bars, ticks);
      const k = ticks[ticks.length - 1];
      s.last = { t: k[0], b: k[1], a: k[2] };
      this.mt5Ticks.push(...ticks);
      if (this.mt5Ticks.length > MT5_TICKS) this.mt5Ticks.splice(0, this.mt5Ticks.length - MT5_TICKS);
      this.mt5Flush(ticks.length);
    }
    if (this.state.storage && now - this.mt5Saved > 60000) {            // persist at most once a minute
      this.mt5Saved = now;
      try { await this.state.storage.put("mt5", s); } catch (e) { /* the next push retries */ }
    }
    return { accepted: ticks.length, rejected };
  }
  mt5Flush(n) {
    if (this.mt5Timer) return;
    const wait = Math.max(0, this.mt5SentAt + SEND_EVERY_MS - Date.now());
    this.mt5Timer = setTimeout(() => {
      this.mt5Timer = null; this.mt5SentAt = Date.now();
      const s = this.mt5; if (!s || !s.last) return;
      this.broadcast({ type: "mt5", sym: s.sym, server: s.server, b: s.last.b, a: s.last.a, t: s.last.t, n });
    }, wait);
  }
  async mt5Snapshot(now = Date.now()) {
    const s = await this.loadMt5();
    return { sym: s.sym, server: s.server, digits: s.digits, last: s.last, rx: s.rx, now,
             age_ms: s.last ? now - s.last.t : null, rejected: s.rejected, bars1m: s.bars,
             footprint: footprint(this.mt5Ticks), volume_kind: "TICK_VOLUME (count of price changes; not traded volume)" };
  }
  sym() { return this.env.SYMBOL || "OANDA:XAU_USD"; }

  async fetch(req) {
    const path = req && req.url ? new URL(req.url).pathname : "/stream";
    if (path === "/mt5") {
      let body; try { body = await req.json(); } catch (e) { return new Response("bad json", { status: 400 }); }
      return new Response(JSON.stringify(await this.ingestMt5(body)), { headers: { "content-type": "application/json" } });
    }
    if (path === "/mt5/snapshot") return new Response(JSON.stringify(await this.mt5Snapshot()), { headers: { "content-type": "application/json" } });
    if (this.clients.size >= MAX_CLIENTS) return new Response("too many viewers", { status: 503 });
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();
    this.clients.add(server);
    const bye = () => { this.clients.delete(server); if (this.clients.size === 0) this.closeUpstream(); };
    server.addEventListener("close", bye);
    server.addEventListener("error", bye);
    server.send(JSON.stringify({ type: "hello", symbol: this.sym(), status: this.status, last: this.last,
      mt5: this.mt5 && this.mt5.last ? { sym: this.mt5.sym, server: this.mt5.server, ...this.mt5.last } : null }));
    if (!this.up) this.openUpstream();
    return new Response(null, { status: 101, webSocket: client });
  }

  broadcast(obj) {
    const s = JSON.stringify(obj);
    for (const c of this.clients) { try { c.send(s); } catch (e) { this.clients.delete(c); } }
  }
  setStatus(status) { this.status = status; this.broadcast({ type: "status", status }); }

  async openUpstream() {
    if (this.up || this.clients.size === 0) return;
    if (!this.env.FINNHUB_KEY) { this.setStatus("no Finnhub key configured"); return; }
    this.setStatus("connecting");
    try {
      const resp = await fetch("https://ws.finnhub.io?token=" + encodeURIComponent(this.env.FINNHUB_KEY), { headers: { Upgrade: "websocket" } });
      const ws = resp.webSocket;
      if (!ws) throw new Error("upstream refused (HTTP " + resp.status + ")");
      ws.accept();
      this.up = ws;
      ws.send(JSON.stringify({ type: "subscribe", symbol: this.sym() }));
      this.backoff = 1000;
      this.setStatus("live");
      ws.addEventListener("message", (ev) => this.onUpstream(ev.data));
      const lost = () => { if (this.up === ws) { this.up = null; this.setStatus("reconnecting"); this.retry(); } };
      ws.addEventListener("close", lost);
      ws.addEventListener("error", lost);
    } catch (e) {
      this.up = null;
      this.setStatus("error: " + String((e && e.message) || e).replace(/token=[^&\s]+/g, "token=***").slice(0, 120));
      this.retry();
    }
  }
  retry() {
    if (this.clients.size === 0) return;
    const d = this.backoff; this.backoff = Math.min(this.backoff * 2, 60000);
    setTimeout(() => this.openUpstream(), d);
  }
  closeUpstream() {
    if (this.up) { try { this.up.close(1000, "no viewers"); } catch (e) { /* already closed */ } }
    this.up = null; this.status = "idle";
  }

  onUpstream(data) {
    let m; try { m = JSON.parse(data); } catch (e) { return; }
    if (m.type === "error") { this.setStatus("upstream: " + String(m.msg || "error").slice(0, 120)); return; }
    const k = pickTicks(m, this.sym());
    if (!k) return;
    this.batch = this.batch ? { p: k.t >= this.batch.t ? k.p : this.batch.p, t: Math.max(k.t, this.batch.t),
      h: Math.max(this.batch.h, k.h), l: Math.min(this.batch.l, k.l), n: this.batch.n + k.n } : k;
    this.flushSoon();
  }
  flushSoon(now = Date.now()) {
    if (this.timer) return;
    const wait = Math.max(0, this.lastSent + SEND_EVERY_MS - now);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (!this.batch) return;
      this.last = this.batch; this.batch = null; this.lastSent = Date.now();
      this.broadcast({ type: "tick", ...this.last });
    }, wait);
  }
}
