"""Mutation test of tests/test_pr_checks.py: every unsafe edit of .github/workflows/pr-checks.yml must make it fail.

Usage: python audit/tools/mutation_pr_checks.py <empty scratch dir>
Copies the repository's workflow + test into the scratch dir, applies one mutant at a time there, runs the test file,
and reports KILLED / SURVIVED. The repository itself is never modified."""
import os
import shutil
import subprocess
import sys

W = sys.argv[1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WF = ".github/workflows/pr-checks.yml"
SITE = ".github/workflows/quantum-site.yml"
TEST = "tests/test_pr_checks.py"

MUTANTS = {
    "M01 contents: write": ("permissions:\n  contents: read", "permissions:\n  contents: write"),
    "M02 id-token: write added": ("permissions:\n  contents: read", "permissions:\n  contents: read\n  id-token: write"),
    "M03 pull_request_target": ("  pull_request:\n", "  pull_request_target:\n"),
    "M04 push trigger added": ("  workflow_dispatch:\n", "  workflow_dispatch:\n  push:\n"),
    "M05 a secret in an env": ("run: pip install -r requirements.txt",
                               "run: pip install -r requirements.txt\n        env:\n          K: ${{ secrets.TWELVEDATA_API_KEY }}"),
    "M06 checkout keeps credentials": ("persist-credentials: false", "persist-credentials: true"),
    "M07 a Pages deploy step": ("      - name: Full test suite", "      - uses: actions/deploy-pages@v4\n      - name: Full test suite"),
    "M08 suite dropped": ("run: python -m pytest -q tests", "run: echo skipped"),
    "M09 order count ignored": ("': [1-9][0-9]* order violation'", "'NEVER'"),
    "M10 dead-code count ignored": ("': [1-9][0-9]* dead,'", "'NEVER'"),
    "M11 manifest check dropped": ("sha256sum -c audit/MANIFEST.sha256", "true"),
}


def main():
    for rel in (WF, SITE, TEST):
        os.makedirs(os.path.join(W, os.path.dirname(rel)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(W, rel))
    orig = open(os.path.join(W, WF), encoding="utf-8").read()
    killed = 0
    for name, (a, b) in MUTANTS.items():
        assert a in orig, name
        open(os.path.join(W, WF), "w", encoding="utf-8").write(orig.replace(a, b, 1))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=W,
                           capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        k = r.returncode != 0
        killed += k
        print(("KILLED   " if k else "SURVIVED ") + name)
    open(os.path.join(W, WF), "w", encoding="utf-8").write(orig)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=W,
                       capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    print(f"unmutated: {'PASS' if r.returncode == 0 else 'FAIL'}")
    print(f"{killed} of {len(MUTANTS)} mutants killed")
    sys.exit(0 if killed == len(MUTANTS) and r.returncode == 0 else 1)


if __name__ == "__main__":
    main()
