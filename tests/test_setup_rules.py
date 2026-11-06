"""SETUP: the operator's level rules (research/registrations/B16.json), as quantum.notify.setup_levels / setup_events."""
from quantum import notify

T0 = 1793973600          # 2026-11-06 14:00 UTC (Friday, trading day 2026-11-06)


def test_levels_today_last_1h_4h_and_previous_month():
    t = [T0 + k * 900 for k in range(6)]
    h = [10.0, 12.0, 11.0, 15.0, 9.0, 9.5]
    lo = [5.0, 6.0, 4.0, 7.0, 3.0, 4.5]
    h1 = {"t": [T0 - 3600, T0, T0 + 3600], "h": [20.0, 21.0, 22.0], "l": [1.0, 2.0, 3.0]}
    h4 = {"t": [T0 - 14400, T0], "h": [30.0, 31.0], "l": [0.5, 0.6]}
    lv = notify.setup_levels(t, h, lo, h1, h4)
    assert lv["TDH"][:4] == [None, 10.0, 12.0, 12.0] and lv["TDL"][3] == 4.0           # bars before, same trading day
    assert lv["1HH"][:5] == [20.0, 20.0, 20.0, 20.0, 21.0]                            # the 1h bar closed by the bar's open
    assert lv["4HH"][0] == 30.0 and lv["4HL"][5] == 0.5
    oct_ = {"t": [1793361600 + k * 3600 for k in range(3)], "h": [50.0, 52.0, 51.0], "l": [40.0, 41.0, 42.0]}   # 30 Oct
    sep = {"t": [1790683200], "h": [60.0], "l": [30.0]}                                                      # 29 Sep (first month)
    both = {k: sep[k] + oct_[k] for k in ("t", "h", "l")}
    lv2 = notify.setup_levels(t, h, lo, both, h4)
    assert (lv2["PMH"][0], lv2["PML"][0]) == (52.0, 40.0)                             # October for a November bar
    assert notify.setup_levels(t, h, lo, oct_, h4)["PMH"][0] is None                  # the first month may be partial


def _lv(n, **kw):
    out = {k: [None] * n for k in notify.SETUP_HI + notify.SETUP_LO}
    out.update(kw)
    return out


def test_sweep_needs_a_zone_and_counts_once_per_day():
    n = 3
    t = [T0 + k * 900 for k in range(n)]
    h, lo, c = [4070.0, 4066.0, 4066.0], [4062.0, 4055.0, 4054.0], [4065.0, 4061.0, 4060.0]
    lv = _lv(n, PDL=[4058.44] * n)
    z = {"ob_bull_lo": [None] * n, "ob_bull_hi": [None] * n, "vpoc": [4059.0] * n, "vah": [4075.0] * n, "val": [4040.0] * n}
    seen: dict = {}
    ev = notify.setup_events(t, h, lo, c, lv, z, range(n), seen)
    assert [(e["i"], e["kind"], e["dir"], e["levels"], e["zones"]) for e in ev] == [(1, "SWEEP", 1, [("PDL", 4058.44)], ["POC 4059.00"])]
    assert notify.setup_events(t, h, lo, c, lv, z, range(n), {}, scale=False)[0]["close"] == 4061.0
    far = {**z, "vpoc": [4070.0] * n}                                                  # no zone within $3: no setup
    assert notify.setup_events(t, h, lo, c, lv, far, range(n), {}) == []
    ob = {**far, "ob_bull_lo": [4050.0] * n, "ob_bull_hi": [4057.0] * n}               # level within $3 of the order block
    assert notify.setup_events(t, h, lo, c, lv, ob, range(n), {})[0]["zones"] == ["bull order block 4050.00-4057.00"]


def test_breakout_needs_the_value_area_and_no_opposing_order_block():
    n = 2
    t = [T0, T0 + 900]
    h, lo, c = [4072.0, 4080.0], [4065.0, 4069.0], [4070.0, 4078.75]
    lv = _lv(n, PDH=[4070.46] * n, TDH=[4071.0, 4072.0])
    z = {"vah": [4074.0] * n, "val": [4040.0] * n, "vpoc": [4060.0] * n}
    ev = notify.setup_events(t, h, lo, c, lv, z, range(n), {})
    assert [(e["kind"], e["dir"], sorted(e["levels"])) for e in ev] == [("BREAKOUT", 1, [("PDH", 4070.46), ("TDH", 4072.0)])]
    assert notify.setup_events(t, h, lo, c, lv, {**z, "vah": [4079.0] * n}, range(n), {}) == []          # inside value
    bear = {**z, "ob_bear_lo": [4076.0] * n, "ob_bear_hi": [4082.0] * n}
    assert notify.setup_events(t, h, lo, c, lv, bear, range(n), {}) == []                                 # into a bear block
    dn = notify.setup_events([T0, T0 + 900], [4062.0, 4060.0], [4059.0, 4050.0], [4059.0, 4052.0],
                             _lv(2, PDL=[4058.44] * 2), {"val": [4055.0] * 2, "vah": [4080.0] * 2}, range(2), {})
    assert [(e["kind"], e["dir"]) for e in dn] == [("BREAKOUT", -1)]
