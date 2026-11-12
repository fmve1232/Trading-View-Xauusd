"""Outage notice: one ntfy message when a site run may have lost or repeated the phone alerts.

The last step of `.github/workflows/quantum-site.yml`. The workflow runs it only after a failed step or a
cancellation (a timeout), with the outcomes of the two steps the alerts depend on:

  PIPELINE   outcome of "Run pipeline" (it builds AND sends the alerts)
  SAVESTORE  outcome of "Save the market-data store" (it holds the alert state: what was already sent)

Decision (`kind`):
  "down"   the pipeline did not succeed (failed, skipped after an earlier failure, or timed out): no alerts
           went out for this run, and they stay paused until a run succeeds;
  "state"  the pipeline succeeded but its state was not saved: the alerts went out, and the next run may
           show them again (marked DELAYED or NOT ACTIONABLE by the stale-signal gate);
  None     anything else, e.g. only the Pages publish or the ledger save failed: the alerts were
           unaffected, so nothing is sent.

De-duplication uses ntfy's own record of what was delivered: nothing is sent while ntfy.sh holds an outage
notice for the topic from the last REPEAT_MIN minutes (tag OUTAGE_TAG). A long outage therefore gets one
notice at its first failed run and at most one reminder every REPEAT_MIN minutes, whatever else fails in
between (a failed Pages deploy never blocks a later notice). When ntfy's record cannot be read, the notice
is sent: a missed outage costs more than a duplicate.

Stdlib only, so it still runs when `pip install` is what failed. It never raises, never fails the run and
never prints the topic (a repository secret). Outside the freeze key: it reads no market data and changes
no record. OUTAGE_NOTICE=0 (repository variable) turns it off in the workflow condition.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

NTFY = "https://ntfy.sh"
OUTAGE_TAG = "xau-outage"
REPEAT_MIN = 180
TITLE = "XAUUSD Quantum (site down)"
TIMEOUT_SEC = 15

MESSAGES = {
    "down": ("XAUUSD SITE DOWN: the site run of {hhmm} UTC failed, so alerts are paused until a run succeeds. "
             "When it is back, signals from the gap are re-checked against the live price or marked NOT ACTIONABLE. "
             "Do not act on old alerts."),
    "state": ("XAUUSD ALERT STATE NOT SAVED: the site run of {hhmm} UTC sent its alerts but could not save their state. "
              "The next run may show them again (marked DELAYED or NOT ACTIONABLE). "
              "Do not open a second trade for the same signal."),
}


def kind(pipeline: str, savestore: str) -> str | None:
    """Which notice a run needs, from the two step outcomes ('success', 'failure', 'cancelled', 'skipped')."""
    if (pipeline or "").strip() != "success":
        return "down"
    if (savestore or "").strip() != "success":
        return "state"
    return None


def message(k: str, now: float) -> str:
    return MESSAGES[k].format(hhmm=time.strftime("%H:%M", time.gmtime(now)))


def recent_notice(poll_body: str, now: float, window_min: int = REPEAT_MIN) -> bool:
    """True when ntfy's poll output holds an outage notice (OUTAGE_TAG) sent within the window."""
    for line in (poll_body or "").splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if not isinstance(m, dict) or m.get("event") != "message":
            continue
        if OUTAGE_TAG in (m.get("tags") or []) and now - float(m.get("time") or 0) < window_min * 60:
            return True
    return False


def _poll(topic: str, window_min: int) -> str:
    url = f"{NTFY}/{urllib.parse.quote(topic, safe='')}/json?poll=1&since={int(window_min)}m"
    with urllib.request.urlopen(url, timeout=TIMEOUT_SEC) as r:
        return r.read().decode("utf-8", "replace")


def _post(topic: str, body: str) -> int:
    req = urllib.request.Request(f"{NTFY}/{urllib.parse.quote(topic, safe='')}", data=body.encode("utf-8"), method="POST",
                                 headers={"Title": TITLE, "Tags": f"warning,{OUTAGE_TAG}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
        return r.status


def run(env: dict, now: float | None = None, poll=None, post=None) -> dict:
    """Decide and (maybe) send. Returns what happened; never raises, never contains the topic."""
    now = time.time() if now is None else now
    poll, post = poll or _poll, post or _post
    out = {"kind": kind(env.get("PIPELINE", ""), env.get("SAVESTORE", "")), "sent": False}
    topic = (env.get("NTFY_TOPIC") or "").strip()
    if out["kind"] is None:
        out["why"] = "alerts unaffected (pipeline and store save succeeded): no notice"
        return out
    if not topic:
        out["why"] = "NTFY_TOPIC not set: no notice"
        return out
    try:
        recent = recent_notice(poll(topic, REPEAT_MIN), now)
        out["dedupe"] = "checked"
    except Exception as e:  # noqa: BLE001 - fail open: a missed outage costs more than a duplicate
        recent = False
        out["dedupe"] = f"unavailable ({type(e).__name__}); sending"
    if recent:
        out["why"] = f"an outage notice was already sent in the last {REPEAT_MIN} min: no repeat"
        return out
    try:
        out["http"] = int(post(topic, message(out["kind"], now)))
        out["sent"] = 200 <= out["http"] < 300
    except Exception as e:  # noqa: BLE001
        out["http"] = getattr(e, "code", None)
        out["error"] = type(e).__name__
    out["why"] = "sent" if out["sent"] else "send failed"
    return out


def main() -> int:
    res = run(dict(os.environ))
    print("outage notice: " + json.dumps(res, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
