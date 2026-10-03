"""The MT5 broker feed via MetaApi (quantum/mt5.py), with the HTTP layer replaced by fakes shaped
like the SDK's REST responses (provisioning account, domain, market-data candles and ticks)."""
import json

import pandas as pd

from quantum import holdout, mt5

T0 = pd.Timestamp("2026-10-05 12:00", tz="UTC")


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j

    def raise_for_status(self):
        pass


def _fake(state="DEPLOYED", conn="CONNECTED", side=None):
    calls = []

    def get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        assert headers == {"auth-token": "tok-secret"}
        if url.endswith("/servers/mt-client-api"):
            return _R({"domain": "agiliumtrade.ai", "hostname": "mt-client-api-v1"})
        if "/users/current/accounts/acc1" in url and "historical" not in url:
            return _R({"name": "demo", "server": "Broker-Demo", "platform": "mt5", "region": "london", "state": state,
                       "connectionStatus": conn, "type": "cloud-g2"})
        assert url.startswith("https://mt-market-data-client-api-v1.london.agiliumtrade.ai/users/current/accounts/acc1/historical-market-data/symbols/XAUUSD")
        if "/candles" in url:
            tf = url.split("/timeframes/")[1].split("/")[0]
            sec = mt5.TIMEFRAMES[tf]
            return _R([{"time": (T0 - pd.Timedelta(seconds=sec * k)).isoformat().replace("+00:00", "Z"), "open": 4300.0 + k,
                        "high": 4301.0 + k, "low": 4299.0 + k, "close": 4300.5 + k, "tickVolume": 100 + k, "spread": 20} for k in range(5, -1, -1)])
        if url.endswith("/ticks"):
            px = [4300.0, 4300.2, 4300.4, 4300.4, 4300.1, 4299.9, 4300.6]
            return _R([{"time": (T0 + pd.Timedelta(milliseconds=250 * i)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                        "bid": p - 0.1, "ask": p + 0.1, **({"side": side[i % 2], "volume": 2.0} if side else {})} for i, p in enumerate(px)])
        raise AssertionError(url)
    return get, calls


def test_without_credentials_it_says_so_and_fills_nothing():
    out = mt5.build(None, "XAUUSD")
    assert out["status"] == "UNAVAILABLE" and out["tick"] is None and "METAAPI_TOKEN" in out["note"]


def test_disconnected_account_is_reported_not_filled():
    get, _ = _fake(state="UNDEPLOYED", conn="DISCONNECTED")
    out = mt5.build(mt5.MetaApi("tok-secret", "acc1", get), "XAUUSD")
    assert out["status"] == "DISCONNECTED" and out["tick"] is None and "UNDEPLOYED" in out["note"]


def test_broker_tick_candles_comparison_and_store(tmp_path):
    get, calls = _fake()
    sec = 3600
    t = [int((T0 - pd.Timedelta(seconds=sec * k)).timestamp()) for k in range(5, -1, -1)]
    primary = {"1h": {"t": t, "c": [4300.5 + k for k in range(5, -1, -1)]}}
    primary["1h"]["c"][-1] += 0.4                                    # engine $0.40 above the broker on the last bar
    out = mt5.build(mt5.MetaApi("tok-secret", "acc1", get), "XAUUSD", primary, str(tmp_path))
    assert out["status"] == "OK" and out["broker"]["server"] == "Broker-Demo" and out["api_calls"] == 6
    k = out["tick"]
    assert (round(k["bid"], 2), round(k["ask"], 2)) == (4300.5, 4300.7) and k["timestamp_precision"] == "MILLISECOND"
    v = out["vs_primary"]["1h"]
    assert v["n"] == 6 and v["diff"] == 0.4 and v["status"] == "CONSISTENT" and v["median_diff"] == 0.0
    assert out["candles"]["1h"]["tick_volume"] == 100.0
    stored = pd.read_csv(tmp_path / "MT5_XAUUSD_1h" / "2026-10.csv", index_col=0)
    assert len(stored) == 6 and "volume" in stored.columns
    assert "tok-secret" not in json.dumps(out, default=float)


def test_footprint_tick_rule_is_labelled_proxy_and_real_side_is_used_when_present():
    get, _ = _fake()
    out = mt5.build(mt5.MetaApi("tok-secret", "acc1", get), "XAUUSD")
    fp = out["footprint"]
    assert fp["method"] == "TICK_RULE_PROXY" and fp["n"] == 7
    # mids 4300.0 -> .2 up, .4 up, .4 zero (keeps up), .1 down, -0.1 down, .6 up: 4 buys, 2 sells
    assert (fp["buy"], fp["sell"], fp["delta"]) == (4.0, 2.0, 2.0)
    get, _ = _fake(side=["buy", "sell"])
    fp = mt5.build(mt5.MetaApi("tok-secret", "acc1", get), "XAUUSD")["footprint"]
    assert fp["method"] == "DEAL_SIDE_VOLUME" and fp["buy"] + fp["sell"] == 12.0


def test_errors_never_carry_the_token():
    def boom(url, headers=None, params=None, timeout=None):
        raise OSError("401 Unauthorized for tok-secret")
    out = mt5.build(mt5.MetaApi("tok-secret", "acc1", boom), "XAUUSD")
    assert out["status"] == "ERROR" and "tok-secret" not in out["note"]


def test_mt5_is_outside_the_freeze_key_and_never_loaded_by_the_engine():
    assert "mt5.py" not in holdout.ENGINE_SOURCES
    for rel in holdout.ENGINE_SOURCES:
        src = open("quantum/" + rel).read()
        assert "MT5_" not in src and "from .mt5" not in src and "from ..mt5" not in src
