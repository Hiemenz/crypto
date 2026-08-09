import pandas as pd
import pytest

import db
from conftest import make_ohlcv
from crypto_signal_station import sectors


def _seed_history(sym, cat, days, closes):
    end = pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=days, freq="D").strftime("%Y-%m-%d")
    db.replace_ohlcv(make_ohlcv(dates, closes), sym, cat)


def test_load_sector_map_missing_returns_empty(lake):
    assert sectors.load_sector_map() == {}


def test_save_and_load_sector_map_roundtrip(lake):
    mapping = {"AAPL": "Information Technology", "XOM": "Energy"}
    sectors.save_sector_map(mapping)
    assert sectors.load_sector_map() == mapping


def test_compute_and_save_without_sector_map_returns_empty(lake):
    assert sectors.compute_and_save().empty


def test_compute_and_save_empty_lake_returns_empty(lake):
    sectors.save_sector_map({"AAPL": "Technology"})
    assert sectors.compute_and_save().empty


def test_compute_and_save_excludes_short_history_and_stale(lake):
    sectors.save_sector_map({"AAPL": "Technology", "OLD": "Technology", "NEW": "Technology"})
    _seed_history("AAPL", "stocks", 205, [100.0 + i for i in range(205)])
    _seed_history("NEW", "stocks", 30, [100.0] * 30)  # < MIN_HISTORY
    stale_end = pd.Timestamp.now().normalize() - pd.Timedelta(days=30)
    stale_dates = pd.date_range(end=stale_end, periods=205, freq="D").strftime("%Y-%m-%d")
    db.replace_ohlcv(make_ohlcv(stale_dates, [100.0] * 205), "OLD", "stocks")

    result = sectors.compute_and_save()
    assert result["n"].iloc[0] == 1  # only AAPL qualifies


def test_compute_and_save_computes_breadth_per_sector(lake):
    days = 205
    sectors.save_sector_map({"AAA": "Tech", "BBB": "Tech", "CCC": "Health"})
    _seed_history("AAA", "stocks", days, [100.0 + i for i in range(days)])  # ends high: above MA
    _seed_history("BBB", "stocks", days, [300.0 - i for i in range(days)])  # ends low: below MA
    _seed_history("CCC", "stocks", days, [100.0 + i for i in range(days)])  # ends high: above MA

    result = sectors.compute_and_save()

    by_sector = result.set_index("sector")
    assert by_sector.loc["Tech", "n"] == 2
    assert by_sector.loc["Tech", "pct_above_ma200"] == pytest.approx(0.5)
    assert by_sector.loc["Health", "n"] == 1
    assert by_sector.loc["Health", "pct_above_ma200"] == pytest.approx(1.0)
    assert list(result["sector"]) == ["Health", "Tech"]  # sorted desc by pct_above_ma200


def test_compute_and_save_averages_ret_30d_from_momentum_table(lake):
    days = 205
    sectors.save_sector_map({"AAA": "Tech", "BBB": "Tech"})
    _seed_history("AAA", "stocks", days, [100.0 + i for i in range(days)])
    _seed_history("BBB", "stocks", days, [100.0 + i for i in range(days)])
    db.save_table(
        pd.DataFrame({"symbol": ["AAA", "BBB"], "ret_30d": [0.10, -0.02]}),
        db.table_path("momentum", "latest.parquet"),
    )

    result = sectors.compute_and_save()
    assert result.loc[result["sector"] == "Tech", "ret_30d"].iloc[0] == pytest.approx(0.04)


def test_compute_and_save_counts_todays_buy_sell_signals(lake):
    days = 205
    sectors.save_sector_map({"AAA": "Tech", "BBB": "Tech"})
    _seed_history("AAA", "stocks", days, [100.0 + i for i in range(days)])
    _seed_history("BBB", "stocks", days, [100.0 + i for i in range(days)])
    today = pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
    db.replace_signals(
        pd.DataFrame({"Date": pd.to_datetime([today]), "signal": ["Good Buy"]}),
        "AAA", "stocks", "1d",
    )
    db.replace_signals(
        pd.DataFrame({"Date": pd.to_datetime([today]), "signal": ["Great Sell"]}),
        "BBB", "stocks", "1d",
    )

    result = sectors.compute_and_save()
    row = result.set_index("sector").loc["Tech"]
    assert row["buy_signals"] == 1
    assert row["sell_signals"] == 1


def test_load_returns_empty_if_not_computed(lake):
    assert sectors.load().empty
