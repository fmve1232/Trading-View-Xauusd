"""Mutation test of the P-0 notification delivery layer (read-only on the repo).

Usage: python audit/tools/mutation_notify_delivery.py <empty scratch dir>
Each mutant is applied to a COPY of quantum/notify.py in the scratch dir; tests/test_notify_delivery.py must fail on
it. D01-D10 are the specification's list (docs/deploy/P0_NOTIFICATION_INTEGRITY_SPEC.md §10); D11-D31 break the rest of
the design one piece at a time (idempotency across runs, the reconcile, the warnings, the records, the line references,
the redaction, the per-run budget); D32-D38 undo the fixes of the independent review of 2026-11-14. A mutant is a list of (old, new) replacements, each of which must occur exactly once.
No request leaves the tests (their transport is a stand-in). Exit status 1 if any mutant survives."""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
W = sys.argv[1]
TESTS = ["tests/test_notify_delivery.py"]

M = {
    # --- the specification's list ---
    "D01 no retry": [('    skip = ("retry off (DELIVERY_RETRY=0)" if not retry_on()',
                      '    skip = "mutant" or ("retry off (DELIVERY_RETRY=0)" if not retry_on()')],
    "D02 retry on 401 (any non-2xx retried)": [('rec["retryable"], rec["uncertain"] = rec["http"] in RETRY_HTTP, rec["http"] in (502, 504)',
                                                'rec["retryable"], rec["uncertain"] = not ok, rec["http"] in (502, 504)')],
    "D03 resend without the cache check": [("        if tags is not None and tag in tags:               # attempt 1 had arrived: nothing is sent twice",
                                            "        if False and tags is not None and tag in tags:")],
    "D04 the resend carries a different tag": [("    a2 = _timed(R, _attempt, name, post, text2, tag)", '    a2 = _timed(R, _attempt, name, post, text2, tag + "-r")')],
    "D05 no tag on ntfy messages": [('headers={"Title": "XAUUSD Quantum", "Tags": tag}', 'headers={"Title": "XAUUSD Quantum"}')],
    "D06 an accepted message called DELIVERED": [('FINAL_OK = "DELIVERY_UNCONFIRMED"', 'FINAL_OK = "DELIVERED"')],
    "D07 undelivered block dropped": [('                out += undelivered_block(und[str(pid)], off, R["t_run"])', "                pass")],
    "D08 block levels recomputed from the current settings": [
        ('    n = u["attempts"]\n    fail = ',
         '    pc = plan_cfg()\n    u = {**u, "sl": u["entry"] + (1 if u["side"] == "SELL" else -1) * pc["sl_px"], "sl_usd": pc["sl_usd"],\n'
         '         "tp": u["entry"] - (1 if u["side"] == "SELL" else -1) * pc["tp_px"], "tp_usd": pc["tp_usd"]}\n'
         '    n = u["attempts"]\n    fail = ')],
    "D09a warning never cleared": [('        ns["pending_warnings"] = [w for w in ns["pending_warnings"] if w["id"] not in gone and w.get("notif_key") != key]',
                                    "        pass")],
    "D09b warning never shown": [("    body = warn + lines\n", "    body = lines\n")],
    "D10a _EVENTS not cleared by _say": [("        _EVENTS = None\n        if out is not None and ctx.get(\"outcome\"):",
                                          "        if out is not None and ctx.get(\"outcome\"):")],
    "D10b Discord truncation restored (no split)": [('"discord": (2000, False)}', '"discord": (10 ** 9, False)}'),
                                                    ('json={"content": text}', 'json={"content": text[:1900]}')],
    # --- the rest of the design ---
    "D11 ntfy bodies not split (> 4,096 bytes become attachments)": [('"ntfy": (4096, True)', '"ntfy": (10 ** 9, True)')],
    "D11b no room kept for the RESENT line (a resend can pass 4,096 bytes)": [
        ('    mark = RESENT_MAX + 1 + (0 if channel == "ntfy" else REF_MAX + 1)', "    mark = 0")],
    "D12 an earlier run's acceptance ignored (duplicate re-sent)": [("    if pr and pr[\"accepted\"]:", "    if False and pr and pr[\"accepted\"]:")],
    "D13 the store's own record ignored": [("    loc = _local(R).get((tag, name))", "    loc = None")],
    "D14 no reconcile (a failure that arrived still claimed lost)": [('    if R["reconciled"]:\n        return', "    if True:\n        return")],
    "D15 no Actions annotation": [('    print(f"::warning title=phone alert not delivered::{m}", flush=True)', "    pass")],
    "D16 a failed opening not registered": [('    if oc.get("final_state") in ("SEND_FAILED", "RETRY_FAILED") and not oc.get("no_channel"):',
                                              "    if False:")],
    "D17 UNDELIVERED PLAN prefix dropped": [("        out.append(UNDELIVERED_PREFIX.format(pid=hit) + ln if hit is not None else ln)",
                                             "        out.append(ln)")],
    "D18 the block put on an opening's own lines": [('            if kind not in ("OPEN", "OPEN_BODY", "SIGNAL") and pid is not None',
                                                     "            if pid is not None")],
    "D19 per-run budget removed": [('        R["down"].add(name)                                # per-run budget', "        pass  #")],
    "D20 one 15 s timeout again": [("SEND_TIMEOUT = (5, 10)", "SEND_TIMEOUT = 15")],
    "D21 block only until one message is accepted (D3 = every message)": [
        ('            if u is not None and not u.get("redelivered_utc"):',
         '            und.pop(str(pid), None)\n            if False:')],
    "D22 secrets not redacted": [('        out = out.replace(v, "***")', "        pass")],
    "D23 full text not kept in the ledger (D1)": [
        ('f.write("".join(json.dumps(json_safe(r), sort_keys=True) + "\\n" for r in rs))',
         'f.write("".join(json.dumps(json_safe({k: v for k, v in r.items() if k != "text"}), sort_keys=True) + "\\n" for r in rs))')],
    "D24 resend not marked RESENT": [("    return [f\"RESENT ({'; '.join(notes)})\"[:RESENT_MAX]] + lines + ", "    return lines + ")],
    "D25 any HTTP answer counts as accepted": [("        ok = rec[\"http\"] is not None and 200 <= rec[\"http\"] < 300\n",
                                                "        ok = rec[\"http\"] is not None\n")],
    "D26 line references not shifted by the NOT ACTIONABLE line": [
        ("            refs[:] = [(i + (i >= stale_at), k, m) for i, k, m in refs]", "            refs[:] = [(i, k, m) for i, k, m in refs]")],
    "D27 the retry pause skipped": [("    _sleep(RETRY_PAUSE_SEC)\n", "")],
    "D28 a reopened plan's entry not cleared when its opening is accepted": [("            und.pop(str(pid), None)\n        for pid in blocked:",
                                                                             "            pass\n        for pid in blocked:")],
    "D29 undelivered entries never expire": [("            del und[pid]\n", "            pass\n")],
    "D31 content keys not unique to the run (identical later messages suppressed)": [
        ("""[f"CONTENT:{stream}:{R['t_run']}:{_sha(base, 10)}"]""", """[f"CONTENT:{stream}:{trading_day(R['t_run'])}:{_sha(base, 10)}"]"""),
        ("""events.add(f"CONTENT:LINES:{tf}:{R['t_run']}:""", """events.add(f"CONTENT:LINES:{tf}:{int(last_t)}:""")],
    # --- the independent review of 2026-11-14 (findings 1-7), one mutant per fix ---
    "D32 a warning cleared by a message that was only skipped": [("        gone = set(wids) if shown else set()", "        gone = set(wids)")],
    "D33 a message warns about itself": [
        ('    pw = [w for w in (R["state"].get("pending_warnings") or []) if w.get("notif_key") != key]',
         '    pw = list(R["state"].get("pending_warnings") or [])')],
    "D34 a cache-hit acceptance missing from the store's record": [
        ('                    if not r.get("request") and r.get("state") not in ACCEPTED:',
         '                    if not r.get("request") and r.get("state") != "SERVER_ACCEPTED":')],
    "D35 a split opening whose first part arrived called undelivered": [
        ('            if pl is None or any(heads.get(pid, "\\0") in t for t in oc.get("accepted_texts") or []):', "            if pl is None:")],
    "D36 the run's delivery time budget ignored": [('    return R.get("spent", 0.0) >= DELIVERY_BUDGET_SEC', "    return False")],
    "D37 phone-facing state built with no channel at all": [
        ("    elif chans:                                            # no channel at all", "    else:  # mutant"),
        ('    if oc.get("final_state") in ("SEND_FAILED", "RETRY_FAILED") and not oc.get("no_channel"):',
         '    if oc.get("final_state") in ("SEND_FAILED", "RETRY_FAILED"):')],
    "D38 one record file per month again": [('    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%d")',
                                              '    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m")')],
    "D30 the kill switch ignored": [('    return os.environ.get("DELIVERY_RETRY", "1").strip() != "0"', "    return True")],
}


def main() -> int:
    res, survived, invalid = {}, [], []
    for name, reps in M.items():
        d = os.path.join(W, "r")
        shutil.rmtree(d, ignore_errors=True)
        for sub in ("quantum", "tests"):
            shutil.copytree(os.path.join(REPO, sub), os.path.join(d, sub), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(REPO, ".github"), os.path.join(d, ".github"))      # the workflow test reads it
        p = os.path.join(d, "quantum", "notify.py")
        s = open(p).read()
        for a, b in reps:
            assert s.count(a) == 1, (name, a[:60], s.count(a))
            s = s.replace(a, b)
        open(p, "w").write(s)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", *TESTS],
                           cwd=d, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        failed = [ln.split("::")[1].split(" ")[0] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        killed = r.returncode == 1 and bool(failed)          # a test failed; a collection / syntax error is no kill
        verdict = "KILLED  " if killed else "SURVIVED" if r.returncode == 0 else "INVALID "
        if not killed:
            (survived if r.returncode == 0 else invalid).append(name)
        res[name] = {"killed": killed, "failing_tests": failed, "rc": r.returncode, "verdict": verdict.strip()}
        print(verdict, name, "->", len(failed), "failing test(s)", flush=True)
    json.dump(res, open(os.path.join(W, "mutation_notify_delivery.json"), "w"), indent=1)
    print(f"{len(M) - len(survived) - len(invalid)} of {len(M)} mutants killed; {len(survived)} survived; {len(invalid)} invalid")
    return 1 if survived or invalid else 0


if __name__ == "__main__":
    sys.exit(main())
