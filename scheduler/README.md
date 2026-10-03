# Site scheduler (free)

GitHub's own cron starts the site's runs late or skips them. On 1–2 Oct 2026 it delivered 100 of
153 runs, with a median gap of 23 minutes. On the NFP release of 2 Oct the site was 25 minutes
behind TradingView.

This Cloudflare Worker (free plan) starts the `quantum-site` workflow one minute after each
15-minute bar closes, and only while gold trades. It uses `workflow_dispatch`, which starts within
seconds. GitHub's cron stays as the backup, and its runs stand down when a dispatched run started
in the last 10 minutes, so Twelve Data's free 800 calls a day are not spent twice (about 384 a day
are used).

## Set-up

1. **GitHub token.** Go to github.com → Settings → Developer settings → Fine-grained tokens →
   Generate.
   - Repository access: **only** `fmve1232/Trading-View-Xauusd`.
   - Permissions: **Actions: Read and write**. Nothing else.
2. **Repository secrets** (Settings → Secrets and variables → Actions):
   - `GH_DISPATCH_TOKEN`: the token from step 1;
   - `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, the same as for `relay/`.
3. Run the **scheduler** workflow once. It deploys the Worker and stores the token as a Worker
   secret.

The token never reaches the site. Check it is working at `https://xau-scheduler.<you>.workers.dev/`,
which shows the time and whether gold is shut. The Actions tab then shows `workflow_dispatch`
runs at :01, :16, :31 and :46.
