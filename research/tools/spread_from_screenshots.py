"""The broker's live bid / ask spread read from the operator's MT5 phone screenshots (B31b-W8 cost amendment).

MT5 draws the bid (teal) and the ask (red) as full-width horizontal lines. Each line's centre is found to sub-pixel
precision (the colour-weighted centroid over its anti-aliased rows, on the median of the chart width so candles do not
move it) and converted to a price with a straight-line fit of the chart's own price-axis gridlines. The axis labels
(first label and step) and the bid label are read from the screenshot by eye and listed below; the fit's residual and
the bid line's agreement with the bid label are reported as the check.

The screenshots are NOT in the repository (they show the account balance). Run it on the operator's files:

  python research/tools/spread_from_screenshots.py --dir <folder with the screenshots> [--out readings.json]
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

# id: (file name, timeframe, first axis label, step between labels, bid label, phone time PKT, UTC)
SHOTS = {
    "19nov_M15": ("nov19_1.jpg", "M15", 3743.24, -3.65, 3679.05, "19 Nov 11:25 PKT", "2026-11-19T06:25Z"),
    "19nov_M30": ("nov19_2.jpg", "M30", 3788.14, -5.80, 3678.63, "19 Nov 11:24 PKT", "2026-11-19T06:24Z"),
    "19nov_H1": ("nov19_3.jpg", "H1", 3887.36, -10.55, 3678.40, "19 Nov 11:24 PKT", "2026-11-19T06:24Z"),
    "25nov_M15": ("nov25_1.jpg", "M15", 3589.76, -4.30, 3519.29, "25 Nov 11:53 PKT", "2026-11-25T06:53Z"),
    "25nov_M30": ("nov25_2.jpg", "M30", 3644.30, -6.15, 3519.42, "25 Nov 11:54 PKT", "2026-11-25T06:54Z"),
    "25nov_H1": ("nov25_3.jpg", "H1", 3686.08, -8.15, 3519.41, "25 Nov 11:54 PKT", "2026-11-25T06:54Z"),
    "25nov_H4": ("nov25_4.jpg", "H4", 3898.59, -18.95, 3519.61, "25 Nov 11:54 PKT", "2026-11-25T06:54Z"),
}
CHART_X = (20, 580)          # the plot area, left of the price axis
CHART_Y = (180, 1300)


def grid_rows(a: np.ndarray) -> list[float]:
    """Centres of the dashed light-grey gridlines (one per axis label), top to bottom."""
    R, G, B = (a[..., k] for k in range(3))
    gray = ((abs(R - G) < 8) & (abs(G - B) < 8) & (R > 200) & (R < 242))[:, 5:590].sum(1)
    rows = [y for y in range(*CHART_Y) if gray[y] > 120]
    groups: list[list[int]] = []
    for y in rows:
        if groups and y - groups[-1][-1] <= 2:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [sum(g) / len(g) for g in groups]


def line_centre(a: np.ndarray, kind: str) -> float | None:
    """Sub-pixel row of the full-width ask (red) or bid (teal) line, or None when it cannot be separated."""
    med = np.median(a[:, CHART_X[0]:CHART_X[1]], axis=1)
    R, G = med[:, 0], med[:, 1]
    w = np.clip((R - G) - 5, 0, None) * (R > 150) if kind == "ask" else np.clip((G - R) - 5, 0, None) * (G > 120)
    y0 = int(np.argmax(w[CHART_Y[0]:CHART_Y[1]])) + CHART_Y[0]
    ys = np.arange(y0 - 3, y0 + 4)
    tot = float(w[ys].sum())
    return float((ys * w[ys]).sum() / tot) if tot > 0 else None


def read(path: str, first: float, step: float) -> dict:
    a = np.asarray(Image.open(path).convert("RGB")).astype(float)
    g = grid_rows(a)
    vals = [first + step * k for k in range(len(g))]
    k, c = np.polyfit(g, vals, 1)
    resid = float(np.abs(np.array(vals) - (k * np.array(g) + c)).max())
    ya, yb = line_centre(a, "ask"), line_centre(a, "bid")
    ask = None if ya is None else k * ya + c
    bid = None if yb is None else k * yb + c
    return {"usd_per_px": -k, "axis_fit_max_err": resid, "ask_line": ask, "bid_line": bid,
            "spread_lines": None if ask is None or bid is None else ask - bid}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    out = {}
    for sid, (fname, tf, first, step, bid_label, local, utc) in SHOTS.items():
        r = read(os.path.join(a.dir, fname), first, step)
        r.update(tf=tf, time_local=local, time_utc=utc, bid_label=bid_label,
                 spread_ask_minus_bid_label=None if r["ask_line"] is None else r["ask_line"] - bid_label,
                 bid_line_minus_label=None if r["bid_line"] is None else r["bid_line"] - bid_label)
        out[sid] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
        s = r["spread_lines"]
        print(f"{sid:10} $/px {r['usd_per_px']:.4f}  spread (lines) " + ("not separable" if s is None else f"${s:.2f}")
              + ("" if r["spread_ask_minus_bid_label"] is None else f"  (ask line - bid label ${r['spread_ask_minus_bid_label']:.2f})"))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
