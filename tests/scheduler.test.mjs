// node --test tests/scheduler.test.mjs  (run by tests/test_relay.py)
import test from "node:test";
import assert from "node:assert/strict";
import worker, { goldShut, dispatch } from "../scheduler/worker.js";

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
    assert.ok(logs.every((l) => !l.includes("secret-tok")));
  } finally { globalThis.fetch = orig; console.log = log; }
});
