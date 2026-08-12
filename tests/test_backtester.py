#!/usr/bin/env python3
"""Tests for the backtester module using synthetic data."""

import sys
import os
import tempfile
import duckdb
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crypto_signal_station"))

from backtester import run_backtest, _compute_metrics, save_csv, save_html


def _make_synthetic_parquet(tmpdir, symbol="TEST-USD", timeframe="1d"):
    """Create a synthetic parquet file with known signals."""
    dates = pd.date_range("2024-01-01", periods=20, freq="D")
    signals = ["Hold"] * 20
    # Buy at index 2, Sell at index 8 → positive trade
    signals[2] = "Good Buy"
    signals[8] = "Good Sell"
    # Buy at index 12, Sell at index 17 → negative trade
    signals[12] = "Excellent Buy"
    signals[17] = "Great Sell"

    closes = [100.0] * 20
    closes[2] = 100.0
    closes[8] = 120.0   # +20%
    closes[12] = 115.0
    closes[17] = 110.0  # -4.35%

    df = pd.DataFrame({
        "Date": dates,
        "Close": closes,
        "Open": closes,
        "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes],
        "Volume": [1000.0] * 20,
        "signal": signals,
        "rsi": [50.0] * 20,
        "mfi": [50.0] * 20,
        "stoch_rsi": [0.5] * 20,
        "ma_50": [105.0] * 20,
        "ma_200": [100.0] * 20,
        "is_bull": [True] * 20,
    })

    tf_dir = os.path.join(tmpdir, "crypto", timeframe)
    os.makedirs(tf_dir, exist_ok=True)
    path = os.path.join(tf_dir, f"{symbol}_with_signals.parquet")
    # Coerce pandas 3.0 str-backed columns to object so DuckDB can register them
    for col in df.columns:
        if isinstance(df[col].dtype, pd.StringDtype) or str(df[col].dtype) == "str":
            df[col] = df[col].astype(object)
    con = duckdb.connect()
    try:
        con.register("_df", df)
        con.execute(f"COPY _df TO '{path}' (FORMAT PARQUET)")
    finally:
        con.close()
    return path, df


def test_trade_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch BASE_DATA in backtester
        import backtester
        original = backtester.BASE_DATA
        backtester.BASE_DATA = tmpdir

        _make_synthetic_parquet(tmpdir, "TEST-USD", "1d")

        metrics, trades = run_backtest("TEST-USD", "1d")
        backtester.BASE_DATA = original

        closed = [t for t in trades if t["status"] == "closed"]
        assert len(closed) == 2, f"Expected 2 closed trades, got {len(closed)}"


def test_win_rate():
    with tempfile.TemporaryDirectory() as tmpdir:
        import backtester
        original = backtester.BASE_DATA
        backtester.BASE_DATA = tmpdir

        _make_synthetic_parquet(tmpdir, "TEST-USD", "1d")
        metrics, trades = run_backtest("TEST-USD", "1d")
        backtester.BASE_DATA = original

        # First trade: +20%, second trade: negative → 50% win rate
        assert metrics["win_rate"] == 50.0, f"Expected 50.0% win rate, got {metrics['win_rate']}"


def test_positive_trade_return():
    with tempfile.TemporaryDirectory() as tmpdir:
        import backtester
        original = backtester.BASE_DATA
        backtester.BASE_DATA = tmpdir

        _make_synthetic_parquet(tmpdir, "TEST-USD", "1d")
        metrics, trades = run_backtest("TEST-USD", "1d")
        backtester.BASE_DATA = original

        closed = [t for t in trades if t["status"] == "closed"]
        first_trade = closed[0]
        assert first_trade["pct_return"] > 0, f"First trade should be profitable"


def test_metrics_zero_trades():
    metrics, trades = _compute_metrics("X", "1d", [], [])
    assert metrics["total_trades"] == 0
    assert metrics["win_rate"] is None


def test_csv_output():
    with tempfile.TemporaryDirectory() as tmpdir:
        import backtester
        original_base = backtester.BASE_DATA
        original_reports = backtester.REPORTS_DIR
        backtester.BASE_DATA = tmpdir
        backtester.REPORTS_DIR = os.path.join(tmpdir, "reports", "backtests")

        _make_synthetic_parquet(tmpdir, "TEST-USD", "1d")
        metrics, trades = run_backtest("TEST-USD", "1d")
        csv_path = save_csv("TEST-USD", "1d", trades)

        backtester.BASE_DATA = original_base
        backtester.REPORTS_DIR = original_reports

        assert os.path.exists(csv_path), "CSV file not created"
        df_out = pd.read_csv(csv_path)
        assert len(df_out) == len(trades), "CSV row count mismatch"


def test_trailing_stop_triggers():
    """Trailing stop should exit a trade when price drops below peak by threshold."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import backtester
        original = backtester.BASE_DATA
        backtester.BASE_DATA = tmpdir

        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        signals = ["Hold"] * 10
        signals[0] = "Good Buy"     # enter at 100
        closes = [100.0, 110.0, 120.0, 115.0, 108.0, 100.0, 90.0, 85.0, 80.0, 75.0]
        # Peak is 120.0; 10% trailing stop triggers at 108.0 (120 * 0.90 = 108)

        df = pd.DataFrame({
            "Date": dates, "Close": closes, "Open": closes,
            "High": [c * 1.01 for c in closes], "Low": [c * 0.99 for c in closes],
            "Volume": [1000.0] * 10, "signal": signals,
            "rsi": [50.0] * 10, "mfi": [50.0] * 10, "stoch_rsi": [0.5] * 10,
            "ma_50": [100.0] * 10, "ma_200": [100.0] * 10, "is_bull": [True] * 10,
        })
        tf_dir = os.path.join(tmpdir, "crypto", "1d")
        os.makedirs(tf_dir, exist_ok=True)
        path = os.path.join(tf_dir, "TEST-USD_with_signals.parquet")
        for col in df.columns:
            if isinstance(df[col].dtype, pd.StringDtype) or str(df[col].dtype) == "str":
                df[col] = df[col].astype(object)
        con = duckdb.connect()
        try:
            con.register("_df", df)
            con.execute(f"COPY _df TO '{path}' (FORMAT PARQUET)")
        finally:
            con.close()

        metrics, trades = run_backtest("TEST-USD", "1d", trailing_stop_pct=10.0)
        backtester.BASE_DATA = original

        closed = [t for t in trades if t["status"] == "closed"]
        assert len(closed) == 1, f"Expected 1 closed trade (stop hit), got {len(closed)}"
        assert closed[0]["exit_signal"] == "Trailing Stop"
        # Exit at 108 or next bar at or below stop: peak=120, stop=108, closes[4]=108.0
        assert closed[0]["exit_price"] <= 108.0


def test_trailing_stop_not_triggered_before_sell():
    """When price never drops past the stop, the signal-based sell should still close."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import backtester
        original = backtester.BASE_DATA
        backtester.BASE_DATA = tmpdir

        _make_synthetic_parquet(tmpdir, "TEST-USD", "1d")
        # Default synthetic data: Good Buy at 100, Good Sell at 120 (+20%), 50% dip never > 8%
        metrics, trades = run_backtest("TEST-USD", "1d", trailing_stop_pct=50.0)
        backtester.BASE_DATA = original

        closed = [t for t in trades if t["status"] == "closed"]
        # Both trades should close via signal, not stop
        assert all(t["exit_signal"] != "Trailing Stop" for t in closed)


if __name__ == "__main__":
    test_trade_count()
    test_win_rate()
    test_positive_trade_return()
    test_metrics_zero_trades()
    test_csv_output()
    test_trailing_stop_triggers()
    test_trailing_stop_not_triggered_before_sell()
    print("All backtester tests passed.")
