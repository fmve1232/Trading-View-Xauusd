"""Runs the relay's JavaScript unit tests (relay/worker.js) with Node's built-in test runner."""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_relay_worker_logic():
    r = subprocess.run(["node", "--test", os.path.join(HERE, "relay.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
