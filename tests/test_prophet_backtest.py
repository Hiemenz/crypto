import pandas as pd
import pytest

import db
from conftest import make_ohlcv
from crypto_signal_station import prophet_backtest as pb


def _daily_ending_now(days, closes):
    end = pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=days, freq="D")
    return make_ohlcv(dates.strftime("%Y-%m-%d"), closes)


def _perfect_stub(full_df):
    """A _fit_fn stub that 'predicts' the real future exactly, so the
    backtest's own horizon-matching/aggregation logic can be verified
    without paying for a real Prophet fit."""
    def _fit_fn(train, periods):
        cutoff = train["ds"].max()
        future = full_df[full_df["Date"] > cutoff].sort_values("Date").head(periods)
        return pd.DataFrame({
            "ds": future["Date"].to_numpy(),
            "yhat": future["Close"].to_numpy(),
            "yhat_lower": future["Close"].to_numpy(),
            "yhat_upper": future["Close"].to_numpy(),
        })
    return _fit_fn


def test_fold_cutoffs_spacing_and_bounds():
    dates = pd.Series(pd.date_range("2020-01-01", periods=1000, freq="D"))
    cutoffs = pb._fold_cutoffs(dates, n_folds=5, min_train=400, spacing_days=60)
    assert len(cutoffs) == 5
    assert cutoffs == sorted(cutoffs)
    assert cutoffs[-1] <= dates.max() - pd.Timedelta(days=max(pb.HORIZONS))
    assert cutoffs[0] >= dates.min() + pd.Timedelta(days=400)
    diffs = [(cutoffs[i + 1] - cutoffs[i]).days for i in range(len(cutoffs) - 1)]
    assert all(d == 60 for d in diffs)


def test_fold_cutoffs_empty_when_too_short():
    dates = pd.Series(pd.date_range("2020-01-01", periods=100, freq="D"))
    assert pb._fold_cutoffs(dates) == []


def test_run_backtest_no_data(lake):
    stats = pb.run_backtest(progress=lambda *a: None)
    assert stats.empty


def test_run_backtest_perfect_stub_scores_zero_error(lake):
    days = 900
    closes = [100.0 * (1.001 ** i) for i in range(days)]
    ohlcv = _daily_ending_now(days, closes)
    db.replace_ohlcv(ohlcv, "BTC-USD", "crypto")

    stats = pb.run_backtest(n_folds=3, progress=lambda *a: None, _fit_fn=_perfect_stub(ohlcv))

    assert not stats.empty
    assert set(stats["horizon_days"]) <= set(pb.HORIZONS)
    assert (stats["mape"] < 1e-9).all()
    assert (stats["directional_accuracy"] == 1.0).all()

    stored = pb.load_stats("crypto")
    assert not stored.empty


def test_format_backtest_report_empty_and_nonempty():
    assert "No Prophet backtest" in pb.format_backtest_report(pd.DataFrame())
    stats = pd.DataFrame([{
        "symbol": "BTC-USD", "category": "crypto", "horizon_days": 30, "n_folds": 4,
        "mape": 0.05, "directional_accuracy": 0.75,
        "avg_predicted_return": 0.02, "avg_actual_return": 0.03,
    }])
    text = pb.format_backtest_report(stats)
    assert "30d" in text and "75%" in text


def test_live_forecast_summary_no_stored_forecast(lake):
    assert "no stored Prophet forecast" in pb.live_forecast_summary()


def test_live_forecast_summary_reads_direction(lake):
    import prophet_forecast as prophet_forecast_mod

    days = 30
    ohlcv = _daily_ending_now(days, [100.0] * days)
    db.replace_ohlcv(ohlcv, "BTC-USD", "crypto")
    last_date = ohlcv["Date"].max()

    fc = pd.DataFrame({
        "ds": pd.date_range(last_date + pd.Timedelta(days=1), periods=90, freq="D"),
        "yhat": [110.0] * 90,       # +10% vs last close of 100
        "yhat_lower": [105.0] * 90,
        "yhat_upper": [115.0] * 90,
    })
    prophet_forecast_mod.save_forecast(fc, "BTC-USD", "crypto", "1d")

    text = pb.live_forecast_summary()
    assert "BTC-USD" in text
    assert "Up" in text
    assert "7d" in text and "30d" in text and "90d" in text


def test_full_report_without_refit(lake):
    import prophet_forecast as prophet_forecast_mod

    days = 30
    ohlcv = _daily_ending_now(days, [100.0] * days)
    db.replace_ohlcv(ohlcv, "BTC-USD", "crypto")
    last_date = ohlcv["Date"].max()
    fc = pd.DataFrame({
        "ds": pd.date_range(last_date + pd.Timedelta(days=1), periods=90, freq="D"),
        "yhat": [90.0] * 90,        # -10%: Down
        "yhat_lower": [85.0] * 90,
        "yhat_upper": [95.0] * 90,
    })
    prophet_forecast_mod.save_forecast(fc, "BTC-USD", "crypto", "1d")

    stats = pd.DataFrame([{
        "symbol": "BTC-USD", "category": "crypto", "horizon_days": 30, "n_folds": 2,
        "mape": 0.1, "directional_accuracy": 0.5,
        "avg_predicted_return": -0.1, "avg_actual_return": -0.05,
    }])
    db.save_table(stats, db.table_path("backtest", "prophet_crypto_stats.parquet"))

    text = pb.full_report(refit_live=False, refit_backtest=False)
    assert "Down" in text
    assert "Walk-forward backtest" in text
    assert "30d" in text


def test_run_backtest_zero_realized_price_yields_nan_not_crash(lake):
    """A zero Close in the OHLCV at a realized date (the kind of OHLCV corruption
    the repo's verify command catches) must not raise ZeroDivisionError.
    abs_pct_error for that fold/horizon becomes NaN; other folds are unaffected."""
    days = 900
    closes = [100.0 * (1.001 ** i) for i in range(days)]
    closes[600] = 0.0  # corrupt one future close
    ohlcv = _daily_ending_now(days, closes)
    db.replace_ohlcv(ohlcv, "BTC-USD", "crypto")

    # Reaching here without ZeroDivisionError is the whole point of this test.
    pb.run_backtest(n_folds=3, progress=lambda *a: None, _fit_fn=_perfect_stub(ohlcv))
