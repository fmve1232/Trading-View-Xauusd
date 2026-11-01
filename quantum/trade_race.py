""""Your trade" panel data: how often price reached the operator's TP before the SL (display only).

Not in holdout.ENGINE_SOURCES and not in any arm's code hash: it reads the engine's signals and the stored bars and
changes nothing. The site turns the operator's SL / TP in account dollars into price distances (lot x 100 oz) and
reads the matching cell; the break-even win rate and the cost come from the selected cost profile in the browser.

Event, for a decision at price P (the trigger bar's close) in direction d, with TP distance a and SL distance b:
    WIN   price reaches P + d*a before P - d*b
    LOSS  P - d*b first. A bar reaching both levels is a LOSS unless it OPENED beyond the target (no ticks; conservative)
    OPEN  neither within one trading day (288 five-minute bars); its mark at the horizon close is kept
The path is walked on stored 5-minute bars from the first bar opening at or after the trigger bar's close; a trigger
before the stored 5-minute window, or whose horizon runs past it, or whose next stored bar is more than 3 days
away (a hole in the data), is not counted. Same rules as audit/tools/target_move_study.py.

Random baseline: a systematic sample of 5-minute closes (every k-th bar, no random numbers), long and short
separately; the site weights the two by each source's long / short mix, so a source is compared with random entries
taken in the same directions over the same window.

The sources' triggers are in-sample: they were produced on the stored window the page shows. The rules were not
fitted to it, but it is seen data. The recorded forward trades (the ledgers) are the out-of-sample row.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

from . import arm_h2, arm_h3, arm_h4, arm_h5, arm_h6, ta
from .data import sources, store

TP_GRID = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0)   # price $
SL_GRID = (2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0)    # price $
HORIZON_SEC = 86400        # one trading day (288 five-minute bars)
BAR_SEC = 300
RANDOM_MAX = 4000          # entries per direction in the random baseline
CHUNK = 1000               # paths per block (bounds memory as the store grows)
MAX_WAIT_SEC = 3 * 86400   # a trigger whose next stored bar is further away sits on a data hole: not counted


def bars_5m(market, store_dir: str | None) -> tuple[pd.DataFrame, int, str]:
    """The finest stored bars of this page's instrument, cut at the page's last confirmed close."""
    end = market.base.index[-1] + pd.Timedelta(seconds=market.tf_sec)
    if market.tf_sec == BAR_SEC:
        return market.base, BAR_SEC, "5-minute bars"
    sym = (market.price_source or "").split(":", 1)[-1]
    df = None
    if store_dir and sym and not market.synthetic:
        df = store.load(store_dir, f"{sym}_5m")
        if df is not None:                              # the same cleaning the download pass applies
            df = sources.trading_week_only(sources.drop_offgrid(df))
            if df is not None and market.price_source.startswith("twelvedata"):
                df = sources.repair_reopen(df, BAR_SEC)
    if df is not None and len(df):
        df = df[df.index + pd.Timedelta(seconds=BAR_SEC) <= end]
        if len(df) > HORIZON_SEC // BAR_SEC:
            return df, BAR_SEC, "5-minute bars"
    return market.base, market.tf_sec, f"this chart's {market.tf} bars (no 5-minute store: more bars touch both levels, counted as losses)"


def _first(cm: np.ndarray, x: float) -> np.ndarray:
    hit = cm >= x - 1e-9
    return np.where(hit.any(axis=1), hit.argmax(axis=1), cm.shape[1])


def race(path: dict, t_close: np.ndarray, price: np.ndarray, d: np.ndarray) -> dict:
    """WIN / LOSS counts and the summed horizon mark of OPEN paths, for every (TP, SL) cell."""
    t, o, h, l, c, H = path["t"], path["o"], path["h"], path["l"], path["c"], path["H"]
    t_close, price, d = (np.asarray(x) for x in (t_close, price, d))
    t_close = t_close.astype(np.int64)
    j = np.searchsorted(t, t_close) if len(t_close) and len(t) else np.zeros(len(t_close), int)
    nxt = t[np.minimum(j, len(t) - 1)] if len(t) else np.zeros(len(t_close), np.int64)
    # inside the stored window, the whole horizon stored, and the next bar not across a data hole (a weekend is 2 days)
    ok = (len(t) > 0) & (t_close >= (t[0] if len(t) else 0)) & (j + H <= len(t)) & (nxt - t_close <= MAX_WAIT_SEC) \
        & np.isfinite(price) & (d != 0)
    j, p, d = j[ok], price[ok].astype(float), np.sign(d[ok]).astype(float)
    nt, ns = len(TP_GRID), len(SL_GRID)
    win, loss, mark = np.zeros((nt, ns), np.int64), np.zeros((nt, ns), np.int64), np.zeros((nt, ns))
    steps = np.arange(H)
    for s0 in range(0, len(j), CHUNK):
        jj, pp, dd = j[s0:s0 + CHUNK], p[s0:s0 + CHUNK, None], d[s0:s0 + CHUNK, None]
        rows = jj[:, None] + steps[None, :]
        hh, ll = h[rows], l[rows]
        up = dd > 0
        cf = np.maximum.accumulate(np.where(up, hh - pp, pp - ll), axis=1)   # running best move in the trade's favour
        ca = np.maximum.accumulate(np.where(up, pp - ll, hh - pp), axis=1)   # running worst move against it
        od = (o[rows] - pp) * dd                                             # each bar's open, signed
        mk = (c[jj + H - 1] - pp[:, 0]) * dd[:, 0]
        r = np.arange(len(jj))
        ib_all = [_first(ca, b) for b in SL_GRID]
        for x, a in enumerate(TP_GRID):
            ia = _first(cf, a)
            opened_beyond = od[r, np.minimum(ia, H - 1)] >= a - 1e-9
            for y, ib in enumerate(ib_all):
                tie = (ia == ib) & (ia < H)
                win[x, y] += int(np.sum((ia < ib) | (tie & opened_beyond)))
                loss[x, y] += int(np.sum((ib < ia) | (tie & ~opened_beyond)))
                mark[x, y] += float(np.sum(mk[(ia >= H) & (ib >= H)]))
    return {"n": len(j), "long": int(np.sum(d > 0)), "short": int(np.sum(d < 0)),
            "win": win.tolist(), "loss": loss.tolist(), "mark": np.round(mark, 2).tolist()}


def _signals(ev: dict) -> tuple[np.ndarray, np.ndarray]:
    eb, es = np.asarray(ev["exec_buy"], float), np.asarray(ev["exec_sell"], float)
    i = np.flatnonzero((eb == 1) | (es == 1))
    return i, np.where(eb[i] == 1, 1, -1)


def forward_triggers(store_dir: str | None, tf: str, tf_sec: int, keys: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Recorded forward trades of this timeframe (every arm, current ledgers and archive) under the given engine keys,
    one per (entry time, direction): the same decision taken by two arms is one decision."""
    if not store_dir or not keys:
        return np.zeros(0, np.int64), np.zeros(0), np.zeros(0), 0
    seen = {}
    for f in glob.glob(os.path.join(store_dir, "holdout", f"{tf}_*.json")) + glob.glob(os.path.join(store_dir, "holdout", "archive", f"{tf}_*.json")):
        try:
            with open(f) as fh:
                led = json.load(fh)
        except (OSError, ValueError):
            continue
        for tr in led if isinstance(led, list) else []:
            fk = str(tr.get("freeze_key") or "") if isinstance(tr, dict) else ""
            if not fk or not any(fk == k or fk.startswith(k + ":") for k in keys):
                continue
            try:
                ts = int(pd.Timestamp(tr["entry_time"]).timestamp()) + tf_sec
                seen[(ts, 1 if tr["dir"] == "LONG" else -1)] = float(tr["entry"])
            except (KeyError, TypeError, ValueError):
                continue
    ks = sorted(seen)
    return (np.array([k[0] for k in ks], np.int64), np.array([seen[k] for k in ks]), np.array([k[1] for k in ks]), len(ks))


def build(market, res, res_chal, cfg, man: dict, store_dir: str | None) -> dict:
    df, bar_sec, bars_label = bars_5m(market, store_dir)
    H = HORIZON_SEC // bar_sec
    path = {"t": ta.epoch_s(df.index), "o": df["open"].to_numpy(float), "h": df["high"].to_numpy(float),
            "l": df["low"].to_numpy(float), "c": df["close"].to_numpy(float), "H": H}
    F = res.F
    n = len(F["c"])
    t_close = ta.epoch_s(F["index"]) + market.tf_sec
    c = np.asarray(F["c"], float)
    evs = [("engine", "Engine signal (treatment)", res.rows), ("challenger", "Challenger (H1)", res_chal.rows if res_chal is not None else None),
           ("h2", "H2 Sweep and Value", lambda: arm_h2.evaluate(res)), ("h3", "H3 Sweep-to-Value", lambda: arm_h3.evaluate(res, market)),
           ("h4", "H4 Playbook (level break)", lambda: arm_h4.evaluate(res)), ("h5", "H5 High confidence", lambda: arm_h5.evaluate(res, market.tf_sec)),
           ("h6", "H6 No score veto", lambda: arm_h6.evaluate(res, cfg))]
    out = []
    for key, label, ev in evs:
        if ev is None:
            continue
        try:
            ev = ev() if callable(ev) else ev
            i, d = _signals(ev)
        except Exception as e:  # noqa: BLE001 - one source must never break the panel
            out.append({"key": key, "label": label, "error": f"{type(e).__name__}: {e}"[:160]})
            continue
        out.append({"key": key, "label": label, "sample": "in-sample",
                    "now": int(d[-1]) if len(i) and i[-1] == n - 1 else 0, **race(path, t_close[i], c[i], d)})
    hist = [h for h in (man.get("history") or []) if h.get("freeze_key")]
    keys = [k for k in (man.get("freeze_key"), hist[-1]["freeze_key"] if hist else None) if k]
    vers = [v for v in (man.get("engine_version"), hist[-1].get("engine_version") if hist else None) if v]
    ft, fp, fd, _ = forward_triggers(store_dir, market.tf, market.tf_sec, keys)
    out.append({"key": "forward", "label": "Recorded forward trades (every arm, real time)", "sample": "out-of-sample (recorded)",
                "versions": vers, "now": 0, **race(path, ft, fp, fd)})
    step = max(3, len(path["t"]) // RANDOM_MAX)
    k = np.arange(0, len(path["t"]), step)
    rt, rp = path["t"][k] + bar_sec, path["c"][k]
    rnd = {nm: race(path, rt, rp, np.full(len(k), s)) for nm, s in (("long", 1), ("short", -1))}
    return {"tp_grid": list(TP_GRID), "sl_grid": list(SL_GRID), "horizon_bars": H, "bar_sec": bar_sec, "bars": bars_label,
            "window": [pd.Timestamp(int(path["t"][0]), unit="s", tz="UTC").isoformat(),
                       pd.Timestamp(int(path["t"][-1]) + bar_sec, unit="s", tz="UTC").isoformat()] if len(path["t"]) else None,
            "random_step": int(step), "sources": out, "random": rnd}
