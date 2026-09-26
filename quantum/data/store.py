"""Append-only market-data store, partitioned by month.

Yahoo serves 60 days of 5- and 15-minute bars. The pipeline runs every 15 minutes and merges
each download into `<store>/<series>/<YYYY-MM>.csv`, so history accumulates beyond any single
request. Only the current month's file changes on a normal run, which keeps the data branch
small when it is pushed. The frozen forward holdout is built from this store.
"""
from __future__ import annotations

import os
import re

import pandas as pd


def _dir(store_dir: str, name: str) -> str:
    return os.path.join(store_dir, re.sub(r"[^A-Za-z0-9_.-]", "_", name))


def load(store_dir: str | None, name: str) -> pd.DataFrame | None:
    if not store_dir:
        return None
    d = _dir(store_dir, name)
    if not os.path.isdir(d):
        return None
    parts = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".csv"):
            df = pd.read_csv(os.path.join(d, fn), index_col=0)
            df.index = pd.to_datetime(df.index, utc=True)
            parts.append(df)
    if not parts:
        return None
    out = pd.concat(parts)
    return out[~out.index.duplicated(keep="last")].sort_index()


def merge(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return new.sort_index()
    both = pd.concat([old, new])
    both = both[~both.index.duplicated(keep="last")]  # the newer download wins on overlap
    return both.sort_index()


def save(store_dir: str, name: str, df: pd.DataFrame) -> None:
    d = _dir(store_dir, name)
    os.makedirs(d, exist_ok=True)
    idx = df.index.tz_convert("UTC")
    keys = idx.strftime("%Y-%m")
    for month in sorted(set(keys)):
        part = df[keys == month]
        path = os.path.join(d, f"{month}.csv")
        text = part.to_csv(float_format="%.6f")
        if os.path.exists(path):
            with open(path) as f:
                if f.read() == text:
                    continue           # unchanged month: leave the file (and its git blob) alone
        with open(path, "w") as f:
            f.write(text)
