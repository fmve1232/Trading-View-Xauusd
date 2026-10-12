// XAU/USD tick relay -- Cloudflare Worker + one Durable Object hub. DISPLAY ONLY.
//
// Browsers connect to wss://<worker>/stream. The hub keeps ONE upstream WebSocket to Finnhub
// (opened while at least one viewer is connected, closed when the last one leaves), and fans the
// ticks out, throttled to at most 4 messages a second per hub: {type:"tick", p, t, h, l, n}
// = last price, its time (ms), high / low / count since the previous message.
// The macro panel's instruments (MACRO_SYMBOLS: the six DXY currency pairs, USD/JPY, WTI and the
// US 10Y T-note) ride on the same upstream connection and go out once a second as
// {type:"macro", q:{symbol:{p,t}}} -- only the symbols that changed.
//
// The Finnhub key lives only in the Worker secret FINNHUB_KEY; it never reaches a browser.
// ALLOWED_ORIGINS (comma-separated) limits which sites may connect, so nobody else can spend
// the key's quota. Messages from browsers are ignored. Nothing here feeds the engine.

const MAX_CLIENTS = 200;
const SEND_EVERY_MS = 250;
const MACRO_EVERY_MS = 1000;
export const macroSymbols = (env) => String((env && env.MACRO_SYMBOLS) || "").split(",").map((s) => s.trim()).filter(Boolean);

// Finnhub trade message -> the newest valid price per macro symbol in the batch.
export function pickMacro(msg, symbols) {
  if (!msg || msg.type !== "trade" || !Array.isArray(msg.data)) return null;
  const out = {};
  for (const x of msg.data) {
    if (!x || !symbols.includes(x.s) || !Number.isFinite(x.p) || x.p <= 0 || !Number.isFinite(x.t)) continue;
    if (!out[x.s] || x.t >= out[x.s].t) out[x.s] = { p: x.p, t: x.t };
  }
  return Object.keys(out).length ? out : null;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ ok: true, symbol: env.SYMBOL || "OANDA:XAU_USD", macro: macroSymbols(env), key: Boolean(env.FINNHUB_KEY) }),
        { headers: { "content-type": "application/json" } });
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
    this.mlast = {}; this.mpend = {}; this.mtimer = null;
  }
  sym() { return this.env.SYMBOL || "OANDA:XAU_USD"; }

  async fetch() {
    if (this.clients.size >= MAX_CLIENTS) return new Response("too many viewers", { status: 503 });
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();
    this.clients.add(server);
    const bye = () => { this.clients.delete(server); if (this.clients.size === 0) this.closeUpstream(); };
    server.addEventListener("close", bye);
    server.addEventListener("error", bye);
    server.send(JSON.stringify({ type: "hello", symbol: this.sym(), status: this.status, last: this.last, macro: this.mlast }));
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
      for (const m of macroSymbols(this.env)) ws.send(JSON.stringify({ type: "subscribe", symbol: m }));
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
    const mq = pickMacro(m, macroSymbols(this.env));
    if (mq) { Object.assign(this.mpend, mq); this.macroSoon(); }
    const k = pickTicks(m, this.sym());
    if (!k) return;
    this.batch = this.batch ? { p: k.t >= this.batch.t ? k.p : this.batch.p, t: Math.max(k.t, this.batch.t),
      h: Math.max(this.batch.h, k.h), l: Math.min(this.batch.l, k.l), n: this.batch.n + k.n } : k;
    this.flushSoon();
  }
  macroSoon() {
    if (this.mtimer) return;
    this.mtimer = setTimeout(() => {
      this.mtimer = null;
      if (!Object.keys(this.mpend).length) return;
      Object.assign(this.mlast, this.mpend);
      this.broadcast({ type: "macro", q: this.mpend }); this.mpend = {};
    }, MACRO_EVERY_MS);
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
