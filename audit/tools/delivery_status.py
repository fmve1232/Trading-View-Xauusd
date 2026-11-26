"""Delivery-status report from the phone delivery log (operator decision B, 2026-11-26). READ ONLY.

  python3 audit/tools/delivery_status.py <notifications dir> [--json out.json]

<notifications dir> is forward-ledger/notifications (or <store>/notifications): one JSON line per send attempt.
Attempts are grouped into messages by (notif_key, t_run). Each message gets the five statuses, computed here from the
attempt fields alone and independently of quantum/notify.py:

  SENT_TO_NTFY     YES (ntfy's server accepted every part) / PARTLY / NO / NOT_CONFIGURED (no ntfy attempt)
  PHONE_DELIVERY   NOT_VERIFIABLE: ntfy reports only that its server accepted a message
  PHONE_DISPLAY    NOT_VERIFIABLE: nothing reports what the phone showed
  SEND_FAILED      YES when any attempt failed
  RETRY_ATTEMPTED  YES when a second request was sent (a cache check that found attempt 1 had arrived sends nothing)

Records written since decision B also carry the status the system computed when it sent; a message whose stored
status differs from the one computed here is listed as a disagreement. Server acceptance is never counted as delivery.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

NV = "NOT_VERIFIABLE"
NAMES = ("SENT_TO_NTFY", "PHONE_DELIVERY", "PHONE_DISPLAY", "SEND_FAILED", "RETRY_ATTEMPTED")


def read(d: str) -> list[dict]:
    rows = []
    for nm in sorted(os.listdir(d)):
        if nm.endswith(".jsonl"):
            with open(os.path.join(d, nm)) as f:
                rows += [json.loads(x) for x in f if x.strip()]
    return rows


def status(attempts: list[dict]) -> dict:
    ntfy_parts: dict = {}
    for a in attempts:
        if a.get("channel") == "ntfy":
            ntfy_parts.setdefault(str(a.get("part") or "1/1"), False)
            ntfy_parts[str(a.get("part") or "1/1")] |= a.get("ok") is True
    if not ntfy_parts:
        sent = "NOT_CONFIGURED"
    else:
        n_ok = sum(ntfy_parts.values())
        sent = "YES" if n_ok == len(ntfy_parts) else "NO" if n_ok == 0 else "PARTLY"
    return {"SENT_TO_NTFY": sent, "PHONE_DELIVERY": NV, "PHONE_DISPLAY": NV,
            "SEND_FAILED": "YES" if any(a.get("ok") is not True for a in attempts) else "NO",
            "RETRY_ATTEMPTED": "YES" if any(a.get("attempt") == 2 and a.get("request") is True for a in attempts) else "NO"}


def messages(rows: list[dict]) -> list[dict]:
    by: dict = collections.OrderedDict()
    for r in rows:
        by.setdefault((r.get("notif_key"), r.get("t_run")), []).append(r)
    out = []
    for (key, t_run), att in by.items():
        stored = [a["status"] for a in att if isinstance(a.get("status"), dict)]
        out.append({"notif_key": key, "t_run": t_run, "stream": att[0].get("stream"), "attempts": len(att),
                    "requests": sum(1 for a in att if a.get("request") is True),
                    "http_failures": sorted({a.get("http") for a in att if a.get("ok") is not True and a.get("http")}),
                    "status": status(att), "stored": stored[0] if stored else None,
                    "stored_consistent": len({json.dumps(s, sort_keys=True) for s in stored}) <= 1})
    return out


def report(rows: list[dict]) -> dict:
    ms = messages(rows)
    dist = {n: dict(collections.Counter(m["status"][n] for m in ms)) for n in NAMES}
    by_stream: dict = {}
    for m in ms:
        s = by_stream.setdefault(m["stream"] or "unlabelled", collections.Counter())
        s["messages"] += 1
        s["SENT_TO_NTFY=" + m["status"]["SENT_TO_NTFY"]] += 1
        s["SEND_FAILED=YES"] += m["status"]["SEND_FAILED"] == "YES"
        s["RETRY_ATTEMPTED=YES"] += m["status"]["RETRY_ATTEMPTED"] == "YES"
    dis = [m for m in ms if m["stored"] is not None and (m["stored"] != m["status"] or not m["stored_consistent"])]
    lost = [m for m in ms if m["status"]["SENT_TO_NTFY"] in ("NO", "PARTLY")]
    return {"attempt_records": len(rows), "messages": len(ms),
            "messages_with_stored_status": sum(1 for m in ms if m["stored"] is not None),
            "status_distribution": dist, "by_stream": {k: dict(v) for k, v in sorted(by_stream.items())},
            "not_fully_accepted": [{k: m[k] for k in ("notif_key", "t_run", "stream", "requests", "http_failures")}
                                   | {"SENT_TO_NTFY": m["status"]["SENT_TO_NTFY"]} for m in lost],
            "stored_vs_recomputed_disagreements": [{k: m[k] for k in ("notif_key", "t_run", "status", "stored")} for m in dis],
            "note": "SENT_TO_NTFY=YES means ntfy's server accepted the message; delivery to and display on the phone are "
                    "NOT_VERIFIABLE with the configured channels."}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rep = report(read(a.dir))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rep, f, indent=1)
    print(f"{rep['attempt_records']} attempt records, {rep['messages']} messages "
          f"({rep['messages_with_stored_status']} with a stored status)")
    for n in NAMES:
        print(f"  {n:16s} {rep['status_distribution'][n]}")
    for k, v in rep["by_stream"].items():
        print(f"  stream {k}: {v}")
    print(f"not fully accepted by ntfy: {len(rep['not_fully_accepted'])}")
    for m in rep["not_fully_accepted"]:
        print("  ", m)
    print(f"stored vs recomputed disagreements: {len(rep['stored_vs_recomputed_disagreements'])}")
    return 1 if rep["stored_vs_recomputed_disagreements"] else 0


if __name__ == "__main__":
    sys.exit(main())
