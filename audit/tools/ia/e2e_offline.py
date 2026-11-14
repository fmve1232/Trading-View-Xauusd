"""End-to-end offline run of the production pipeline (download -> engine x3 -> report -> notify -> index.json) on a store
COPY. Every network call raises; no channel is configured, so nothing is sent."""
import os, sys, time
prod, store, out = sys.argv[1], sys.argv[2], sys.argv[3]
for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL", "GITHUB_STEP_SUMMARY"):
    os.environ.pop(k, None)
os.environ["TWELVEDATA_API_KEY"] = "offline-placeholder-not-a-key"
os.environ["ALERT_TFS"] = "15m,30m,1h,4h"
sys.path.insert(0, prod)
from quantum.data import sources
def _off(*a, **k): raise sources.FetchError("offline e2e")
sources._get = _off
import requests
def _block(*a, **k): raise requests.exceptions.ConnectionError("offline e2e: network blocked")
requests.post = requests.get = _block
from quantum import pipeline
t0 = time.time()
rc = pipeline.main(["--store", store, "--out", out, "--tfs", "15m,30m,1h,4h,5m"])
print("pipeline rc", rc, "in", round(time.time() - t0), "s")
