// XAU/USD site scheduler: a Cloudflare Worker cron (free plan) that starts the quantum-site
// workflow one minute after each 15-minute bar closes.
//
// Why: GitHub's own cron starts scheduled runs late or drops them (1-2 Oct 2026: 100 of 153 runs,
// median gap 23 min), so on the NFP release of 2 Oct the site was 25 minutes behind. A
// workflow_dispatch call starts a run within seconds. GitHub's cron stays as the backup; its runs
// stand down when a dispatched run started in the last 10 minutes (the `gate` job).
//
// Secret (Worker): GH_DISPATCH_TOKEN, a fine-grained GitHub token for THIS repository only, with
// "Actions: Read and write" and nothing else. It never reaches the site or the repository.
// Every 15 minutes, not 5: four Twelve Data calls a run x 96 runs = 384 of the free 800 a day.

const DOW = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

// Gold is shut Friday 17:00 -> Sunday 18:00 New York and 17:00-18:00 Monday-Thursday: the same
// rule as quantum/data/sources.gold_shut. A run in the first minutes after a close still runs
// (the :01 slot after 17:00 falls inside the shut hour and is skipped; the backup cron covers it).
export function goldShut(d) {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "numeric", hourCycle: "h23" })
    .formatToParts(d).map((x) => [x.type, x.value]));
  const wd = DOW[p.weekday], h = Number(p.hour);
  return wd === 6 || (wd === 5 && h >= 17) || (wd === 0 && h < 18) || (wd >= 1 && wd <= 4 && h === 17);
}

export async function dispatch(env, fetchImpl = fetch) {
  const r = await fetchImpl(`https://api.github.com/repos/${env.REPO}/actions/workflows/${env.WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, Accept: "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "xau-scheduler" },
    body: JSON.stringify({ ref: env.REF }),
  });
  return r.status;      // 204 = started
}

export default {
  async scheduled(event, env, ctx) {
    const when = new Date(event.scheduledTime);
    if (goldShut(when)) { console.log(`${when.toISOString()} gold shut: no run`); return; }
    if (!env.GH_DISPATCH_TOKEN) { console.log("GH_DISPATCH_TOKEN not set"); return; }
    const st = await dispatch(env);
    console.log(`${when.toISOString()} dispatch -> HTTP ${st}`);   // never logs the token
  },
  async fetch() {
    return new Response(JSON.stringify({ service: "xau-scheduler", now: new Date().toISOString(), gold_shut: goldShut(new Date()) }),
      { headers: { "content-type": "application/json" } });
  },
};
