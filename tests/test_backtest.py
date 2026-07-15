import pandas as pd
import pytest

import db
from conftest import make_ohlcv
from crypto_signal_station import backtest


def _daily(start, days, closes):
    dates = pd.date_range(start, periods=days, freq="D")
    return make_ohlcv(dates.strftime("%Y-%m-%d"), closes)


def test_forward_returns_at_horizons(lake):
    # 100 days of linearly rising closes: 100, 101, ..., 199
    daily = _daily("2025-01-01", 100, [100.0 + i for i in range(100)])
    events = pd.DataFrame({"Date": pd.to_datetime(["2025-01-01"]), "Close": [100.0]})
    out = backtest._forward_returns(events, daily)
    assert out["ret_7d"].iloc[0] == pytest.approx((107 - 100) / 100)
    assert out["ret_30d"].iloc[0] == pytest.approx((130 - 100) / 100)
    assert out["ret_90d"].iloc[0] == pytest.approx((190 - 100) / 100)


def test_forward_returns_nan_when_horizon_not_elapsed(lake):
    daily = _daily("2025-01-01", 10, [100.0 + i for i in range(10)])
    events = pd.DataFrame({"Date": pd.to_datetime(["2025-01-02"]), "Close": [101.0]})
    out = backtest._forward_returns(events, daily)
    # 7d target (01-09, close 108) is inside the data
    assert out["ret_7d"].iloc[0] == pytest.approx((108 - 101) / 101)
    # 30/90 day targets are beyond the data: must be NaN, never a stale match
    assert pd.isna(out["ret_30d"].iloc[0])
    assert pd.isna(out["ret_90d"].iloc[0])


def test_forward_returns_bridges_weekend_gaps(lake):
    # Stock-style series with weekend holes: Fri 2025-01-03 + following Mon-Fri
    dates = ["2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08",
             "2025-01-09", "2025-01-10", "2025-01-13"]
    daily = make_ohlcv(dates, [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    events = pd.DataFrame({"Date": pd.to_datetime(["2025-01-03"]), "Close": [100.0]})
    out = backtest._forward_returns(events, daily)
    # Target 01-10 exists; matched exactly
    assert out["ret_7d"].iloc[0] == pytest.approx((105 - 100) / 100)


def test_run_backtest_scores_buys_and_sells(lake):
    # BUY-USD rises 1%/day: buys should win; SELL-USD too: sells should lose
    days = 130
    closes = [100.0 * (1.01 ** i) for i in range(days)]
    for sym in ("BUY-USD", "SELL-USD"):
        db.replace_ohlcv(_daily("2025-01-01", days, closes), sym, "crypto")
    sig_buy = pd.DataFrame(
        {"Date": pd.to_datetime(["2025-01-10"]), "Close": [closes[9]], "signal": ["Good Buy"]}
    )
    sig_sell = pd.DataFrame(
        {"Date": pd.to_datetime(["2025-01-10"]), "Close": [closes[9]], "signal": ["Good Sell"]}
    )
    db.replace_signals(sig_buy, "BUY-USD", "crypto", "1d")
    db.replace_signals(sig_sell, "SELL-USD", "crypto", "1d")

    events, stats = backtest.run_backtest(progress=lambda *a: None)
    assert len(events) == 2

    buy30 = stats[(stats["signal"] == "Good Buy") & (stats["horizon_days"] == 30)].iloc[0]
    sell30 = stats[(stats["signal"] == "Good Sell") & (stats["horizon_days"] == 30)].iloc[0]
    assert buy30["win_rate"] == 1.0      # price rose after the buy call
    assert sell30["win_rate"] == 0.0     # price rose after the sell call too
    assert buy30["avg_return"] > 0
    assert buy30["baseline_return"] > 0  # unconditional drift is positive here

    # Stats are persisted for the dashboard/digest
    stored = backtest.load_stats()
    assert not stored.empty
    assert set(stored["horizon_days"]) <= {7, 30, 90}


def test_run_backtest_empty_lake(lake):
    events, stats = backtest.run_backtest(progress=lambda *a: None)
    assert events.empty and stats.empty


def test_format_report_handles_empty():
    assert "No backtest" in backtest.format_report(pd.DataFrame())
