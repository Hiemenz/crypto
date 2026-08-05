import pandas as pd
import pytest

import db
from conftest import make_ohlcv
from crypto_signal_station import momentum


def _seed_history(sym, cat, days, closes):
    end = pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=days, freq="D").strftime("%Y-%m-%d")
    db.replace_ohlcv(make_ohlcv(dates, closes), sym, cat)


def test_compute_returns_trailing_returns_for_active_symbol(lake):
    days = 200
    closes = [100.0 + i for i in range(days)]
    _seed_history("BTC-USD", "crypto", days, closes)

    df = momentum.compute(categories=("crypto",))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "BTC-USD"
    assert row["last_close"] == pytest.approx(299.0)
    assert row["ret_30d"] == pytest.approx(299.0 / 269.0 - 1)
    assert row["ret_90d"] == pytest.approx(299.0 / 209.0 - 1)
    assert row["ret_180d"] == pytest.approx(299.0 / 119.0 - 1)


def test_compute_excludes_stale_symbols(lake):
    days = 200
    _seed_history("LIVE-USD", "crypto", days, [100.0 + i for i in range(days)])
    stale_end = pd.Timestamp.now().normalize() - pd.Timedelta(days=30)
    stale_dates = pd.date_range(end=stale_end, periods=days, freq="D").strftime("%Y-%m-%d")
    db.replace_ohlcv(make_ohlcv(stale_dates, [50.0] * days), "DEAD-USD", "crypto")

    df = momentum.compute(categories=("crypto",))
    assert list(df["symbol"]) == ["LIVE-USD"]


def test_compute_short_history_leaves_horizons_none(lake):
    days = 10  # too young for any of the 30/90/180d horizons
    _seed_history("NEW-USD", "crypto", days, [100.0] * days)

    df = momentum.compute(categories=("crypto",))
    row = df.iloc[0]
    assert pd.isna(row["ret_30d"])
    assert pd.isna(row["ret_90d"])
    assert pd.isna(row["ret_180d"])


def test_compute_empty_lake_returns_empty(lake):
    assert momentum.compute(categories=("crypto",)).empty


def test_compute_persists_and_load_roundtrips(lake):
    days = 200
    _seed_history("BTC-USD", "crypto", days, [100.0 + i for i in range(days)])
    momentum.compute(categories=("crypto",))

    loaded = momentum.load()
    assert list(loaded["symbol"]) == ["BTC-USD"]
    assert loaded["ret_90d"].iloc[0] == pytest.approx(299.0 / 209.0 - 1)


def test_load_returns_empty_when_not_computed(lake):
    assert momentum.load().empty


def test_load_altcoin_season_missing_file_returns_empty_dict(lake):
    assert momentum.load_altcoin_season() == {}


@pytest.mark.parametrize(
    "beating, total, expected_label",
    [
        (3, 4, "Altcoin Season"),  # 75% beating BTC
        (2, 4, "Neutral"),         # 50% beating BTC
        (1, 4, "BTC Season"),     # 25% beating BTC
    ],
)
def test_altcoin_season_label_thresholds(lake, beating, total, expected_label):
    btc_ret = 0.10
    rows = [{"category": "crypto", "symbol": "BTC-USD", "ret_90d": btc_ret}]
    rows += [
        {"category": "crypto", "symbol": f"WIN{i}", "ret_90d": btc_ret + 0.05}
        for i in range(beating)
    ]
    rows += [
        {"category": "crypto", "symbol": f"LOSE{i}", "ret_90d": btc_ret - 0.05}
        for i in range(total - 1 - beating)
    ]
    df = pd.DataFrame(rows)

    momentum._compute_and_store_altcoin_season(df)

    result = momentum.load_altcoin_season()
    assert result["label"] == expected_label
    assert result["btc_ret_90d"] == pytest.approx(btc_ret)
    assert result["n_total"] == total
    assert result["n_beating"] == beating


def test_altcoin_season_skips_without_btc(lake):
    df = pd.DataFrame([{"category": "crypto", "symbol": "ALT-USD", "ret_90d": 0.2}])
    momentum._compute_and_store_altcoin_season(df)
    assert momentum.load_altcoin_season() == {}
