import pandas as pd
import pytest

import db
from conftest import make_ohlcv
from crypto_signal_station import cycle_forecast


def _daily(start, days, closes):
    dates = pd.date_range(start, periods=days, freq="D")
    return make_ohlcv(dates.strftime("%Y-%m-%d"), closes)


def _daily_ending_now(days, closes):
    """Like _daily, but anchored so the last bar is 'today' — needed for
    anything that goes through breadth.compute_breadth()'s staleness cutoff."""
    end = pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=days, freq="D")
    return make_ohlcv(dates.strftime("%Y-%m-%d"), closes)


def test_band_label_edges():
    # Boundaries mirror market_cycle.compute_crypto_cycle() exactly:
    # <= 0.25 → "≤25%", (0.25, 0.40] → "25-40%", (0.40, 0.60) → "40-60%",
    # [0.60, 0.75) → "60-75%", >= 0.75 → "≥75%"
    assert cycle_forecast._band_label(0.0) == "≤25%"
    assert cycle_forecast._band_label(0.24) == "≤25%"
    assert cycle_forecast._band_label(0.25) == "≤25%"   # <= 0.25, same as market_cycle
    assert cycle_forecast._band_label(0.26) == "25-40%"
    assert cycle_forecast._band_label(0.40) == "25-40%"  # <= 0.40, same as market_cycle
    assert cycle_forecast._band_label(0.41) == "40-60%"
    assert cycle_forecast._band_label(0.59) == "40-60%"
    assert cycle_forecast._band_label(0.60) == "60-75%"  # >= 0.60, same as market_cycle
    assert cycle_forecast._band_label(0.75) == "≥75%"   # >= 0.75, same as market_cycle
    assert cycle_forecast._band_label(0.99) == "≥75%"
    assert cycle_forecast._band_label(None) is None
    assert cycle_forecast._band_label(float("nan")) is None


def test_compute_breadth_timeseries_from_full_history(lake):
    # 260 days: first 200 needed just to seed the rolling MA200, so the
    # timeseries should start once symbols become mature, not from day 1.
    days = 260
    db.replace_ohlcv(_daily("2025-01-01", days, [100.0 + i for i in range(days)]), "UP", "stocks")
    db.replace_ohlcv(_daily("2025-01-01", days, [400.0 - i for i in range(days)]), "DOWN", "stocks")

    ts = cycle_forecast.compute_breadth_timeseries("stocks")
    assert not ts.empty
    assert ts["n_active"].max() == 2
    # UP always closes above its own rolling MA200 once mature; DOWN never does
    assert ts["pct_above_ma200"].iloc[-1] == pytest.approx(0.5)


def test_compute_breadth_timeseries_empty_lake(lake):
    assert cycle_forecast.compute_breadth_timeseries("stocks").empty


def test_benchmark_forward_returns_crypto_uses_btc(lake):
    days = 40
    closes = [100.0 + i for i in range(days)]  # +1/day
    db.replace_ohlcv(_daily("2025-01-01", days, closes), "BTC-USD", "crypto")
    db.replace_ohlcv(_daily("2025-01-01", days, [999.0] * days), "ETH-USD", "crypto")

    bench = cycle_forecast._benchmark_forward_returns("crypto")
    assert bench["ret_7d"].iloc[0] == pytest.approx((107 - 100) / 100)


def test_benchmark_forward_returns_stocks_equal_weighted(lake):
    days = 40
    # AAA +1/day, BBB flat: equal-weight 7d avg return is the mean of the two
    db.replace_ohlcv(_daily("2025-01-01", days, [100.0 + i for i in range(days)]), "AAA", "stocks")
    db.replace_ohlcv(_daily("2025-01-01", days, [50.0] * days), "BBB", "stocks")

    bench = cycle_forecast._benchmark_forward_returns("stocks")
    row = bench[bench["Date"] == pd.Timestamp("2025-01-01")].iloc[0]
    expected_aaa = (100.0 + cycle_forecast._TRADING_DAY_EQUIV[7] - 100.0) / 100.0
    assert row["ret_7d"] == pytest.approx((expected_aaa + 0.0) / 2)


def test_fit_breadth_model_empty_lake(lake):
    assert cycle_forecast.fit_breadth_model("crypto").empty


def test_fit_and_predict_roundtrip(lake):
    # Steady uptrend for long enough to mature past MA200 with margin to
    # spare for forward-return horizons: breadth should land in the top
    # band and the benchmark's forward returns should all be positive.
    days = 400
    closes = [100.0 * (1.002 ** i) for i in range(days)]
    db.replace_ohlcv(_daily_ending_now(days, closes), "BTC-USD", "crypto")

    model = cycle_forecast.fit_breadth_model("crypto")
    assert not model.empty
    assert set(model["horizon_days"]) <= {7, 30, 90}
    assert (model["avg_return"] > 0).all()

    stored = cycle_forecast.load_breadth_model("crypto")
    assert not stored.empty

    pred = cycle_forecast.predict_market_direction("crypto", horizon_days=30)
    assert pred["direction"] == "Up"
    assert pred["predicted_return"] > 0
    assert pred["n_samples"] > 0


def test_predict_market_direction_no_model_yet(lake):
    days = 260
    db.replace_ohlcv(_daily_ending_now(days, [100.0] * days), "BTC-USD", "crypto")
    pred = cycle_forecast.predict_market_direction("crypto")
    assert "note" in pred
    assert "no backtested model" in pred["note"]


def test_predict_market_direction_no_breadth_data(lake):
    assert cycle_forecast.predict_market_direction("crypto") is None


def test_forecast_line_empty_without_data(lake):
    assert cycle_forecast.forecast_line("crypto") == ""


def test_forecast_line_with_data(lake):
    days = 400
    closes = [100.0 * (1.002 ** i) for i in range(days)]
    db.replace_ohlcv(_daily_ending_now(days, closes), "BTC-USD", "crypto")
    cycle_forecast.fit_breadth_model("crypto")

    line = cycle_forecast.forecast_line("crypto")
    assert "Crypto" in line
    assert "7d" in line and "30d" in line and "90d" in line


def test_forecast_report_handles_no_data(lake):
    text = cycle_forecast.forecast_report(refit=False)
    assert "not enough breadth history" in text
    assert "Backtested forward-return forecast" in text
