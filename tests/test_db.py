import pandas as pd

import db
from conftest import make_ohlcv


def test_upsert_ohlcv_merges_newest_wins(lake):
    db.upsert_ohlcv(make_ohlcv(["2026-01-01", "2026-01-02"], [1.0, 2.0]), "X", "crypto")
    db.upsert_ohlcv(make_ohlcv(["2026-01-02", "2026-01-03"], [5.0, 6.0]), "X", "crypto")
    out = db.load_ohlcv("X", "crypto")
    assert list(out["Date"].dt.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert out["Close"].tolist() == [1.0, 5.0, 6.0]


def test_replace_ohlcv_drops_rows_absent_from_new_history(lake):
    db.upsert_ohlcv(make_ohlcv(["2026-01-01", "2026-01-02"]), "X", "crypto")
    db.replace_ohlcv(make_ohlcv(["2026-01-02"], [7.0]), "X", "crypto")
    out = db.load_ohlcv("X", "crypto")
    assert len(out) == 1
    assert out["Close"].iloc[0] == 7.0


def test_replace_signals_removes_phantom_rows(lake):
    old = pd.DataFrame({"Date": pd.to_datetime(["2026-01-04", "2026-01-11"]), "signal": ["Hold", "Good Buy"]})
    db.upsert_signals(old, "X", "crypto", "1wk")
    # Rebinned recompute: the old dates no longer exist and must not survive
    rebinned = pd.DataFrame({"Date": pd.to_datetime(["2026-01-05", "2026-01-12"]), "signal": ["Hold", "Hold"]})
    db.replace_signals(rebinned, "X", "crypto", "1wk")
    out = db.load_signals("X", "crypto", "1wk")
    assert list(out["Date"].dt.strftime("%Y-%m-%d")) == ["2026-01-05", "2026-01-12"]


def test_missing_symbol_returns_empty(lake):
    assert db.get_latest_ohlcv_date("NOPE", "crypto") is None
    assert db.get_signals_date_range("NOPE", "crypto", "1d") == (None, None)
    assert db.load_ohlcv("NOPE", "crypto").empty
    assert db.load_signals("NOPE", "crypto", "1d").empty


def test_get_latest_ohlcv_date(lake):
    db.upsert_ohlcv(make_ohlcv(["2026-01-01", "2026-01-03"]), "X", "stocks")
    assert db.get_latest_ohlcv_date("X", "stocks") == pd.Timestamp("2026-01-03")
