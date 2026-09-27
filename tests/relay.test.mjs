// node --test tests/relay.test.mjs  (run by tests/test_relay.py)
import test from "node:test";
import assert from "node:assert/strict";
import { originAllowed, pickTicks, Hub } from "../relay/worker.js";

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
