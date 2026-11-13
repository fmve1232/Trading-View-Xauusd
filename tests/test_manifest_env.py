"""Each run's manifest line records the Python / NumPy / pandas versions used, without touching the freeze key
(operator approval 2026-11-13, audit F-03)."""
import json
import os
import platform

import numpy as np
import pandas as pd

from quantum import holdout, manifest
from quantum.config import DEFAULT

FROZEN_KEY = "5e4630924d663fc5:a6f2be58c74887ed"
FROZEN_SOURCES = ("ta.py", "sessions.py", "features.py", "analog.py", "engine.py", "backtest.py",
                  "config.py", "pipeline.py", "data/sources.py", "data/market.py", "data/store.py")


def _store(tmp_path):
    store, ledger = str(tmp_path / "store"), str(tmp_path / "ledger")
    os.makedirs(os.path.join(store, "XAU_USD_60m"))
    with open(os.path.join(store, "XAU_USD_60m", "2026-11.csv"), "w") as f:
        f.write("t,open,high,low,close,volume\n2026-11-02 10:00:00+00:00,4000,4001,3999,4000.5,0\n")
    return store, ledger


def test_env_versions_are_the_running_interpreter_and_libraries():
    env = manifest.env_versions()
    assert env == {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    assert all(isinstance(v, str) and v for v in env.values())


def test_every_run_line_carries_env(tmp_path):
    store, ledger = _store(tmp_path)
    line = manifest.record(store, ledger, "7", "abc", FROZEN_KEY)
    assert line["env"] == manifest.env_versions()
    path = os.path.join(ledger, "manifests", "runs-" + pd.Timestamp.now("UTC").strftime("%Y-%m") + ".jsonl")
    on_disk = json.loads(open(path).read().splitlines()[-1])
    assert on_disk["env"] == line["env"] and on_disk["freeze_key"] == FROZEN_KEY


def test_existing_fields_unchanged(tmp_path):
    """The new field is additive: every field the line had before is still written, with the same meaning."""
    store, ledger = _store(tmp_path)
    line = manifest.record(store, ledger, "7", "abc", FROZEN_KEY)
    assert set(line) == {"run_utc", "run_id", "commit", "freeze_key", "tree_sha256", "n_files", "changed", "removed",
                         "revised_closed_bars", "revised_files", "forming_bar_updates", "env"}
    assert line["run_id"] == "7" and line["commit"] == "abc" and line["n_files"] == 1


def test_freeze_key_and_engine_sources_unchanged():
    """Recording versions must not change what the holdout is frozen on."""
    assert holdout.ENGINE_SOURCES == FROZEN_SOURCES
    assert "manifest.py" not in holdout.ENGINE_SOURCES
    assert holdout.freeze_key(DEFAULT) == FROZEN_KEY


def test_manifest_is_still_outside_the_pipeline():
    """Bookkeeping only: the pipeline never imports it, so it cannot influence a decision."""
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "..", "quantum", "pipeline.py"), encoding="utf-8").read()
    assert "manifest" not in src
