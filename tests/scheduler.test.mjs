// node --test tests/scheduler.test.mjs  (run by tests/test_relay.py)
import test from "node:test";
import assert from "node:assert/strict";
import worker, { goldShut, dispatch, runSlot } from "../scheduler/worker.js";

test("gold hours match sources.gold_shut (EDT and EST)", () => {
  const shut = (iso) => goldShut(new Date(iso));
  assert.equal(shut("2026-10-02T12:31:00Z"), false);   // Fri 08:31 EDT: NFP, open
  assert.equal(shut("2026-10-02T21:01:00Z"), true);    // Fri 17:01 EDT
  assert.equal(shut("2026-10-03T12:00:00Z"), true);    // Saturday
  assert.equal(shut("2026-10-04T21:46:00Z"), true);    // Sun 17:46 EDT: still shut
  assert.equal(shut("2026-10-04T22:01:00Z"), false);   // Sun 18:01 EDT: reopen
  assert.equal(shut("2026-10-06T21:16:00Z"), true);    // Tue 17:16 EDT: daily break
  assert.equal(shut("2026-10-06T22:01:00Z"), false);   // Tue 18:01 EDT
  assert.equal(shut("2026-12-08T22:16:00Z"), true);    // Tue 17:16 EST: daily break in winter
  assert.equal(shut("2026-12-08T23:01:00Z"), false);
});

test("the slot right after the daily and weekly close runs; the rest of the shut hours do not", () => {
  const run = (iso) => runSlot(new Date(iso));
  assert.equal(run("2026-11-23T22:01:00Z"), true);    // Mon 17:01 EST: carries the 16:45-17:00 bar and the 4h close
  assert.equal(run("2026-11-23T22:16:00Z"), false);   // Mon 17:16 EST: daily break
  assert.equal(run("2026-11-23T22:46:00Z"), false);
  assert.equal(run("2026-11-23T23:01:00Z"), true);    // Mon 18:01 EST: reopen, as before
  assert.equal(run("2026-11-27T22:01:00Z"), true);    // Fri 17:01 EST: the week's last bar
  assert.equal(run("2026-11-27T22:16:00Z"), false);   // Fri 17:16 EST: weekend
  assert.equal(run("2026-11-28T12:01:00Z"), false);   // Saturday
  assert.equal(run("2026-11-29T22:01:00Z"), false);   // Sun 17:01 EST: still shut before and after
  assert.equal(run("2026-11-29T23:01:00Z"), true);    // Sun 18:01 EST: reopen
  assert.equal(run("2026-10-06T21:01:00Z"), true);    // Tue 17:01 EDT (summer)
  assert.equal(run("2026-10-06T21:16:00Z"), false);
  assert.equal(run("2026-10-02T12:31:00Z"), true);    // an ordinary open slot
});

test("dispatch posts to the workflow on the default branch", async () => {
  let seen;
  const st = await dispatch({ REPO: "o/r", WORKFLOW: "quantum-site.yml", REF: "main", GH_DISPATCH_TOKEN: "tok" },
    async (url, init) => { seen = { url, init }; return { status: 204 }; });
  assert.equal(st, 204);
  assert.equal(seen.url, "https://api.github.com/repos/o/r/actions/workflows/quantum-site.yml/dispatches");
  assert.equal(seen.init.method, "POST");
  assert.equal(seen.init.headers.Authorization, "Bearer tok");
  assert.deepEqual(JSON.parse(seen.init.body), { ref: "main" });
});

test("no dispatch while gold is shut or without a token; the token is never logged", async () => {
  const calls = [], logs = [];
  const orig = globalThis.fetch, log = console.log;
  globalThis.fetch = async (...a) => { calls.push(a); return { status: 204 }; };
  console.log = (m) => logs.push(String(m));
  try {
    const env = { REPO: "o/r", WORKFLOW: "w.yml", REF: "main", GH_DISPATCH_TOKEN: "secret-tok" };
    await worker.scheduled({ scheduledTime: Date.parse("2026-10-03T12:01:00Z") }, env);   // Saturday
    assert.equal(calls.length, 0);
    await worker.scheduled({ scheduledTime: Date.parse("2026-10-02T12:31:00Z") }, { ...env, GH_DISPATCH_TOKEN: "" });
    assert.equal(calls.length, 0);
    await worker.scheduled({ scheduledTime: Date.parse("2026-10-02T12:31:00Z") }, env);
    assert.equal(calls.length, 1);
    await worker.scheduled({ scheduledTime: Date.parse("2026-11-23T22:01:00Z") }, env);   // the slot after the close
    assert.equal(calls.length, 2);
    await worker.scheduled({ scheduledTime: Date.parse("2026-11-23T22:16:00Z") }, env);   // daily break
    assert.equal(calls.length, 2);
    assert.ok(logs.every((l) => !l.includes("secret-tok")));
  } finally { globalThis.fetch = orig; console.log = log; }
});

test("/check classifies the token without starting a run and never echoes it", async () => {
  const { check } = await import("../scheduler/worker.js");
  const env = { REPO: "o/r", WORKFLOW: "w.yml", REF: "main", GH_DISPATCH_TOKEN: "secret-tok" };
  const mk = (rd, wr) => async (url, init) => {
    const st = url.endsWith("/dispatches") ? wr : rd;
    if (url.endsWith("/dispatches")) assert.match(JSON.parse(init.body).ref, /no-such-branch/);
    return { status: st, headers: new Headers({ "x-accepted-github-permissions": "actions=write" }), json: async () => ({ message: "m" }) };
  };
  assert.match((await check(env, mk(200, 422))).verdict, /^OK/);
  assert.match((await check(env, mk(200, 403))).verdict, /^NO PERMISSION/);
  assert.match((await check(env, mk(404, 404))).verdict, /^NO PERMISSION/);
  assert.match((await check(env, mk(401, 401))).verdict, /^BAD TOKEN/);
  assert.deepEqual(await check({ ...env, GH_DISPATCH_TOKEN: "" }, mk(200, 422)), { token_set: false });
  assert.ok(!JSON.stringify(await check(env, mk(200, 403))).includes("secret-tok"));
});
