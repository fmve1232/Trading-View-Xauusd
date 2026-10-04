// node --test tests/relay.test.mjs  (run by tests/test_relay.py)
import test from "node:test";
import assert from "node:assert/strict";
import worker, { originAllowed, pickTicks, Hub, safeEqual, cleanTicks, addToBars, footprint } from "../relay/worker.js";

const SYM = "OANDA:XAU_USD";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function client() { const c = { sent: [], send: (s) => c.sent.push(JSON.parse(s)) }; return c; }
function fakeUpstream() {
  const ws = { sent: [], closed: false, handlers: {}, accept() {}, send(s) { ws.sent.push(JSON.parse(s)); },
    addEventListener(k, f) { ws.handlers[k] = f; }, close() { ws.closed = true; } };
  return ws;
}

test("origin allow-list", () => {
  assert.ok(originAllowed("https://fmve1232.github.io", "https://fmve1232.github.io"));
  assert.ok(!originAllowed("https://evil.example", "https://fmve1232.github.io, https://x.y"));
  assert.ok(originAllowed("anything", ""));                        // unset = open (documented)
});

test("tick parsing keeps the newest valid tick and the batch range", () => {
  const k = pickTicks({ type: "trade", data: [
    { s: SYM, p: 4286.1, t: 3, v: 1 }, { s: SYM, p: 4287.4, t: 5, v: 1 }, { s: SYM, p: 4285.9, t: 4, v: 1 },
    { s: "OANDA:EUR_USD", p: 1.1, t: 9 }, { s: SYM, p: 0, t: 10 }, { s: SYM, p: "x", t: 11 } ] }, SYM);
  assert.deepEqual(k, { p: 4287.4, t: 5, h: 4287.4, l: 4285.9, n: 3 });
  assert.equal(pickTicks({ type: "ping" }, SYM), null);
  assert.equal(pickTicks({ type: "trade", data: [{ s: "OANDA:EUR_USD", p: 1, t: 1 }] }, SYM), null);
});

test("throttle: a burst becomes one message with the burst's high and low", async () => {
  const hub = new Hub({}, { SYMBOL: SYM }); const c = client(); hub.clients.add(c);
  for (const [p, t] of [[4286, 1], [4290, 2], [4281, 3], [4288, 4]]) hub.onUpstream(JSON.stringify({ type: "trade", data: [{ s: SYM, p, t }] }));
  await sleep(120);
  const ticks = c.sent.filter((m) => m.type === "tick");
  assert.equal(ticks.length, 1);
  assert.deepEqual(ticks[0], { type: "tick", p: 4288, t: 4, h: 4290, l: 4281, n: 4 });
  hub.onUpstream(JSON.stringify({ type: "trade", data: [{ s: SYM, p: 4289, t: 5 }] }));
  await sleep(20);
  assert.equal(c.sent.filter((m) => m.type === "tick").length, 1, "second message waits for the 250 ms spacing");
  await sleep(500);
  assert.equal(c.sent.filter((m) => m.type === "tick").length, 2);
});

test("one upstream, subscribed; closed when the last viewer leaves; key never echoed", async () => {
  const up = fakeUpstream(); let calls = 0, calledUrl = "";
  globalThis.fetch = async (url) => { calls++; calledUrl = url; return { status: 101, webSocket: up }; };
  const hub = new Hub({}, { SYMBOL: SYM, FINNHUB_KEY: "SECRET123" });
  const a = client(), b = client(); hub.clients.add(a); hub.clients.add(b);
  await hub.openUpstream(); await hub.openUpstream();
  assert.equal(calls, 1);
  assert.ok(calledUrl.includes("token=SECRET123"));
  assert.deepEqual(up.sent, [{ type: "subscribe", symbol: SYM }]);
  assert.equal(hub.status, "live");
  assert.ok(!JSON.stringify(a.sent).includes("SECRET123"));
  hub.clients.clear(); hub.closeUpstream();
  assert.ok(up.closed); assert.equal(hub.status, "idle");
});

test("missing key and upstream errors are reported, not thrown", async () => {
  const hub = new Hub({}, { SYMBOL: SYM }); const c = client(); hub.clients.add(c);
  await hub.openUpstream();
  assert.equal(c.sent.at(-1).status, "no Finnhub key configured");
  hub.onUpstream(JSON.stringify({ type: "error", msg: "Subscribing to too many symbols" }));
  assert.match(c.sent.at(-1).status, /^upstream: Subscribing/);
  globalThis.fetch = async () => { throw new Error("connect failed https://ws.finnhub.io?token=SECRET123"); };
  const h2 = new Hub({}, { SYMBOL: SYM, FINNHUB_KEY: "SECRET123" }); const d = client(); h2.clients.add(d);
  await h2.openUpstream();
  h2.clients.clear();                                               // stop the retry loop
  assert.match(d.sent.at(-1).status, /^error: /);
  assert.ok(!JSON.stringify(d.sent).includes("SECRET123"), "the key is redacted from error text");
});

// ---- MT5 bridge ----
test("push key: constant-time compare; /mt5 refuses without the secret or with a wrong key", async () => {
  assert.ok(safeEqual("abc", "abc")); assert.ok(!safeEqual("abc", "abd")); assert.ok(!safeEqual("abc", "abcd"));
  let reached = 0;
  const env = { MT5_PUSH_KEY: "k".repeat(24), HUB: { idFromName: () => 1, get: () => ({ fetch: async () => { reached++; return new Response("{}"); } }) } };
  const post = (key) => new Request("https://x/mt5", { method: "POST", headers: key ? { "X-Push-Key": key } : {}, body: "{}" });
  assert.equal((await worker.fetch(post(null), env)).status, 403);
  assert.equal((await worker.fetch(post("wrong"), env)).status, 403);
  assert.equal((await worker.fetch(post("k".repeat(24)), { ...env, MT5_PUSH_KEY: "" })).status, 403);
  assert.equal((await worker.fetch(post("k".repeat(24)), env)).status, 200);
  assert.equal(reached, 1);
});

test("ticks are validated, never repaired: crossed, stale, non-finite and >5% jumps are rejected", () => {
  const { ticks, rejected } = cleanTicks([
    [1000, 4300.1, 4300.3], [1500, 4300.2, 4300.1], [900, 4300, 4300.2], ["x", 1, 2],
    [2000, 2707, 2707.2], [2500, 4300.4, 4300.6, 0, 0, 0]], 0, null);
  assert.equal(ticks.length, 2); assert.equal(rejected, 4);
  assert.deepEqual(ticks.map((k) => k[0]), [1000, 2500]);
});

test("1-minute bars on the mid, and the footprint labels the tick rule as a proxy", () => {
  const t0 = 1790942400000;   // 2026-10-02 12:00 UTC
  const mids = [4300.0, 4300.2, 4300.4, 4300.4, 4300.1, 4299.9, 4300.6];
  const ticks = mids.map((m, i) => [t0 + i * 15000, m - 0.1, m + 0.1, 0, 0, 0]);
  const bars = addToBars([], ticks);
  assert.equal(bars.length, 2);                                   // 12:00 (4 ticks) and 12:01 (3 ticks)
  assert.deepEqual(bars[0].slice(0, 6).map((x) => Math.round(x * 100) / 100), [1790942400, 4300, 4300.4, 4300, 4300.4, 4]);
  const fp = footprint(ticks);
  assert.equal(fp.method, "TICK_RULE_PROXY");
  assert.deepEqual([fp.buy, fp.sell, fp.delta], [4, 2, 2]);      // same answer as quantum/mt5.py's footprint
  const real = footprint(ticks.map((k, i) => [k[0], k[1], k[2], 0, 2, i % 2 ? 64 : 32]));
  assert.equal(real.method, "DEAL_SIDE_VOLUME"); assert.equal(real.buy + real.sell, 12);
});

test("hub: ingest streams an mt5 message, persists, and serves a snapshot", async () => {
  const store = new Map();
  const hub = new Hub({ storage: { get: async (k) => store.get(k), put: async (k, v) => store.set(k, structuredClone(v)) } }, { SYMBOL: SYM });
  const c = client(); hub.clients.add(c);
  const t0 = 1790942400000;
  const r = await hub.ingestMt5({ sym: "XAUUSDm", server: "Exness-MT5Real32", digits: 3,
    ticks: [[t0, 4141.5, 4141.7, 0, 0, 6], [t0 + 400, 4141.6, 4141.8, 0, 0, 6]] }, t0 + 1000);
  assert.deepEqual(r, { accepted: 2, rejected: 0 });
  await sleep(30);
  const m = c.sent.filter((x) => x.type === "mt5");
  assert.equal(m.length, 1);
  assert.deepEqual([m[0].sym, m[0].server, m[0].b, m[0].a, m[0].t], ["XAUUSDm", "Exness-MT5Real32", 4141.6, 4141.8, t0 + 400]);
  assert.ok(store.get("mt5") && store.get("mt5").last.t === t0 + 400, "persisted");
  const snap = await hub.mt5Snapshot(t0 + 2400);
  assert.equal(snap.age_ms, 2000); assert.equal(snap.bars1m.length, 1); assert.equal(snap.footprint.n, 2);
  const again = await hub.ingestMt5({ ticks: [[t0 + 100, 4141, 4141.2]] }, t0 + 3000);   // older than the last tick
  assert.deepEqual(again, { accepted: 0, rejected: 1 });
  const fresh = new Hub({ storage: { get: async (k) => store.get(k), put: async () => {} } }, { SYMBOL: SYM });
  assert.equal((await fresh.mt5Snapshot(t0 + 5000)).last.t, t0 + 400, "state survives an eviction");
});
