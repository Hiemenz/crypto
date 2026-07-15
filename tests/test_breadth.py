import pandas as pd

import db
from conftest import make_ohlcv
from crypto_signal_station import breadth


def _seed_history(sym, cat, days, closes):
    end = pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=days, freq="D").strftime("%Y-%m-%d")
    db.replace_ohlcv(make_ohlcv(dates, closes), sym, cat)


def test_compute_breadth_counts_above_ma200(lake):
    days = 260
    # UP ends far above its 200d mean; DOWN far below
    _seed_history("UP", "stocks", days, [100.0 + i for i in range(days)])
    _seed_history("DOWN", "stocks", days, [400.0 - i for i in range(days)])

    row = breadth.compute_breadth("stocks")
    assert row["n_active"] == 2
    assert row["pct_above_ma200"] == 0.5
    assert row["regime"] == "Neutral"
    assert row["new_highs_52w"] == 1  # UP closes at its 52w max
    assert row["new_lows_52w"] == 1   # DOWN closes at its 52w min


def test_compute_breadth_excludes_stale_symbols(lake):
    days = 260
    _seed_history("LIVE", "stocks", days, [100.0 + i for i in range(days)])
    old = pd.date_range(end=pd.Timestamp.now() - pd.Timedelta(days=90), periods=days, freq="D")
    db.replace_ohlcv(make_ohlcv(old.strftime("%Y-%m-%d"), [50.0] * days), "DEAD", "stocks")

    row = breadth.compute_breadth("stocks")
    assert row["n_active"] == 1
    assert row["pct_above_ma200"] == 1.0
    assert row["regime"] == "Risk-On"


def test_short_history_excluded_from_ma_ratios(lake):
    # 30 bars: active, but too young for a 200d MA — counted active, not in ratios
    _seed_history("YOUNG", "stocks", 30, [10.0 + i for i in range(30)])
    row = breadth.compute_breadth("stocks")
    assert row["n_active"] == 1
    assert pd.isna(row["pct_above_ma200"])
    assert row["regime"] == "Unknown"


def test_record_daily_appends_history_idempotently(lake):
    days = 260
    _seed_history("UP", "stocks", days, [100.0 + i for i in range(days)])
    breadth.record_daily(categories=("stocks",))
    breadth.record_daily(categories=("stocks",))  # same day: upsert, not append
    hist = breadth.load_history("stocks")
    assert len(hist) == 1
    assert hist["regime"].iloc[0] == "Risk-On"


def test_breadth_line_and_empty_history(lake):
    assert breadth.latest_breadth_line("stocks") == ""
    row = {
        "category": "stocks", "pct_above_ma200": 0.62, "regime": "Risk-On",
        "new_highs_52w": 12, "new_lows_52w": 3,
    }
    line = breadth.breadth_line(row)
    assert "62%" in line and "Risk-On" in line and "12/3" in line


def test_compute_breadth_empty_lake(lake):
    assert breadth.compute_breadth("stocks") is None
