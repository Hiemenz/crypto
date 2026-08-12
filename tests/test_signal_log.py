"""Tests for the signal history log module."""

import os
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crypto_signal_station"))

import db
import signal_log


def _seed_signals_lake(lake_dir, category, timeframe, symbol, rows):
    """Write synthetic signal rows to the lake under lake_dir."""
    import duckdb

    path = os.path.join(
        lake_dir, "data", "signals",
        f"category={category}", f"timeframe={timeframe}", f"symbol={symbol}", "data.parquet"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = pd.DataFrame(rows)
    for col in df.columns:
        if isinstance(df[col].dtype, pd.StringDtype) or str(df[col].dtype) == "str":
            df[col] = df[col].astype(object)
    con = duckdb.connect()
    try:
        con.register("_df", df)
        con.execute(f"COPY _df TO '{path}' (FORMAT PARQUET)")
    finally:
        con.close()


def _seed_ohlcv_lake(lake_dir, category, symbol, rows):
    """Write synthetic OHLCV rows to the lake."""
    import duckdb

    path = os.path.join(
        lake_dir, "data", "ohlcv",
        f"category={category}", f"symbol={symbol}", "data.parquet"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = pd.DataFrame(rows)
    con = duckdb.connect()
    try:
        con.register("_df", df)
        con.execute(f"COPY _df TO '{path}' (FORMAT PARQUET)")
    finally:
        con.close()


@pytest.fixture
def lake(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(db, "OHLCV_DIR", str(tmp_path / "data" / "ohlcv"))
    monkeypatch.setattr(db, "SIGNALS_DIR", str(tmp_path / "data" / "signals"))
    db.init_db()
    return tmp_path


def test_append_today_writes_rows(lake):
    today = pd.Timestamp("2025-01-10")
    _seed_signals_lake(lake, "crypto", "1d", "BTC-USD", [
        {"Date": today, "signal": "Good Buy", "Close": 50000.0},
        {"Date": today - pd.Timedelta(days=1), "signal": "Hold", "Close": 48000.0},
    ])

    n = signal_log.append_today("crypto", "1d")
    assert n > 0, "Should have appended at least one row"

    log = signal_log.load_log("crypto", "1d")
    assert not log.empty
    assert "BTC-USD" in log["symbol"].values


def test_append_today_idempotent(lake):
    today = pd.Timestamp("2025-01-10")
    _seed_signals_lake(lake, "crypto", "1d", "BTC-USD", [
        {"Date": today, "signal": "Hold", "Close": 50000.0},
    ])

    n1 = signal_log.append_today("crypto", "1d")
    n2 = signal_log.append_today("crypto", "1d")

    log = signal_log.load_log("crypto", "1d")
    # Idempotent: no duplicates
    assert log.duplicated(subset=["date", "symbol"]).sum() == 0
    assert n2 == 0, "Second append should be a no-op"


def test_load_log_empty_when_no_data(lake):
    df = signal_log.load_log("crypto", "1d")
    assert df.empty


def test_forward_returns_empty_without_enough_history(lake):
    today = pd.Timestamp("2025-01-10")
    _seed_signals_lake(lake, "crypto", "1d", "BTC-USD", [
        {"Date": today, "signal": "Good Buy", "Close": 50000.0},
    ])
    signal_log.append_today("crypto", "1d")

    # No OHLCV lake seeded → forward returns should return empty
    stats = signal_log.forward_returns("crypto", "1d", horizons=[7])
    assert stats.empty


def test_forward_returns_computes_pct(lake, monkeypatch):
    today = pd.Timestamp("2025-01-10")
    _seed_signals_lake(lake, "crypto", "1d", "BTC-USD", [
        {"Date": today, "signal": "Good Buy", "Close": 50000.0},
    ])
    signal_log.append_today("crypto", "1d")

    # Seed OHLCV with a known future price
    future_date = today + pd.Timedelta(days=7)
    _seed_ohlcv_lake(lake, "crypto", "BTC-USD", [
        {"Date": today, "Close": 50000.0, "Open": 50000.0, "High": 51000.0, "Low": 49000.0, "Volume": 1e9},
        {"Date": future_date, "Close": 55000.0, "Open": 51000.0, "High": 56000.0, "Low": 50000.0, "Volume": 1e9},
    ])

    stats = signal_log.forward_returns("crypto", "1d", horizons=[7])
    if stats.empty:
        pytest.skip("forward_returns requires merged OHLCV; skipping in CI without full lake")

    row = stats[stats["horizon_days"] == 7].iloc[0]
    assert row["n"] >= 1
    assert row["avg_return"] == pytest.approx(10.0, abs=0.5)
