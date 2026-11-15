"""Deployment smoke test: after GitHub Pages reports success, the live site must answer and serve THIS run's files.

  python -m quantum.smoke --url https://<owner>.github.io/<repo>/ --site site

Every file this run built (index.html, app.js, style.css, costs.js, method.html and data/*.json) is fetched from the live
URL and must answer 200 and be byte-identical to the built file; the root URL must serve index.html; data/index.json
must have been generated within the last 45 minutes. Byte identity is valid because site runs never overlap (the
workflow's concurrency group), so nothing else deploys between this run's deploy and this check.

Pages can take a few seconds to serve a new deployment, so the whole check is retried. If it still fails, the step fails
and the run goes red: a site that does not serve the run's data is a real failure and is not hidden. Alerts are not
affected (they were sent, and the records saved, before the deploy). Standard library only.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

PAGES = ("index.html", "app.js", "style.css", "costs.js", "method.html")
MAX_AGE_SEC = 45 * 60


def fetch(url: str, timeout: float = 20.0) -> tuple[int, bytes]:
    """(HTTP status, body); status 0 = no answer (DNS, TLS, timeout), with the reason as the body."""
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "quantum-smoke"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.status), r.read()
    except urllib.error.HTTPError as e:
        return int(e.code), b""
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e).encode()[:200]


def built_files(site_dir: str) -> list[str]:
    rel = [p for p in PAGES if os.path.exists(os.path.join(site_dir, p))]
    rel += sorted("data/" + os.path.basename(p) for p in glob.glob(os.path.join(site_dir, "data", "*.json")))
    return rel


def check(base: str, site_dir: str, get=fetch, now: datetime | None = None, bust: str = "") -> list[str]:
    """The problems found (empty = healthy)."""
    base = base if base.endswith("/") else base + "/"
    now = now or datetime.now(timezone.utc)
    out = []
    files = built_files(site_dir)
    if "index.html" not in files or "data/index.json" not in files:
        return [f"the build has no index.html or data/index.json in {site_dir}"]
    for rel in ["", *files]:
        with open(os.path.join(site_dir, rel or "index.html"), "rb") as f:
            want = f.read()
        status, body = get(f"{base}{rel}?v={bust}" if bust else f"{base}{rel}")
        name = rel or "(root URL)"
        if status != 200:
            out.append(f"{name}: HTTP {status}" + (f" ({body.decode(errors='replace')})" if status == 0 else ""))
        elif hashlib.sha256(body).digest() != hashlib.sha256(want).digest():
            out.append(f"{name}: the live file differs from this run's ({len(body)} bytes live, {len(want)} built)")
    try:
        with open(os.path.join(site_dir, "data", "index.json")) as f:
            gen = datetime.fromisoformat(json.load(f)["generated_utc"])
        age = (now - gen).total_seconds()
        if not 0 <= age <= MAX_AGE_SEC:
            out.append(f"data/index.json: generated {gen.isoformat()}, {age / 60:.0f} min before this check (limit {MAX_AGE_SEC // 60})")
    except (OSError, ValueError, KeyError, TypeError) as e:
        out.append(f"data/index.json: cannot read generated_utc ({type(e).__name__}: {e})")
    return out


def main(argv=None, get=fetch, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--site", default="site")
    ap.add_argument("--attempts", type=int, default=8)
    ap.add_argument("--wait", type=float, default=15.0)
    a = ap.parse_args(argv)
    problems: list[str] = []
    for k in range(1, a.attempts + 1):
        problems = check(a.url, a.site, get, bust=f"{os.environ.get('GITHUB_RUN_ID', 'local')}-{k}")
        if not problems:
            break
        if k < a.attempts:
            sleep(a.wait)
    n = len(built_files(a.site)) + 1
    line = (f"smoke test: {a.url} serves this run's {n} files, byte-identical (attempt {k})" if not problems else
            f"smoke test FAILED after {a.attempts} attempts: " + "; ".join(problems[:6]) + (f"; and {len(problems) - 6} more" if len(problems) > 6 else ""))
    print(line if not problems else "::error title=deployment smoke test::" + line)
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as f:
            f.write(line + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
