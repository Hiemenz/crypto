"""Prophet-based crypto market forecast, plus a walk-forward backtest of it.

`prophet_forecast.py` already fits Prophet on any symbol's price history —
including BTC-USD, which stands in as "the crypto market" the same way
altcoin-season and market_cycle already benchmark against it. This module
adds two things on top:

  1. live_forecast_summary() — read the stored BTC-USD forecast as a
     directional call (Up/Down/Flat) at 7/30/90 days, not just raw yhat.
  2. run_backtest() — walk-forward validation: refit Prophet using only
     data available at each of several past cutoffs, forecast forward, and
     compare to what BTC-USD actually did. Unlike cycle_forecast.py's
     breadth-bucket backtest (one cheap pass over history), each fold here
     refits Prophet from scratch — a few real seconds each — so this is an
     on-demand CLI job, not part of the nightly refresh.

Crypto only for now: BTC-USD already has years of continuous daily history
in the lake. Stocks would need a synthetic index built first (no single
stored index series) — left for later if this proves useful.

Storage:
    data/backtest/prophet_<category>_events.parquet  one row per fold/horizon
    data/backtest/prophet_<category>_stats.parquet    aggregated per horizon
Usage:
    poetry run python crypto_signal_station/crypto_signal_pipeline.py prophet
"""

import os
import sys
import warnings

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

HORIZONS = (7, 30, 90)
DEFAULT_SYMBOL = "BTC-USD"
DEFAULT_CATEGORY = "crypto"
DIRECTION_FLAT_BAND = 0.005  # +/-0.5%: forecast return inside this band reads as "Flat"

MIN_TRAIN_HISTORY = 400        # rows needed before a fold can fit
N_FOLDS = 10
FOLD_SPACING_DAYS = 60          # walk the cutoff backward this many days per fold


def _fit_and_forecast(train: pd.DataFrame, periods: int):
    """Fit Prophet on train (columns ds/y) and return `periods` days of
    yhat/yhat_lower/yhat_upper beyond the last training date, or None on
    failure. Split out so tests can stub it instead of paying for a real
    Stan fit."""
    from prophet import Prophet  # imported lazily: install is optional on dev machines

    try:
        m = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=True,
            changepoint_prior_scale=0.05,
            interval_width=0.80,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m.fit(train)
        future = m.make_future_dataframe(periods=periods, freq="D")
        forecast = m.predict(future)
        return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods).reset_index(drop=True)
    except Exception as e:
        print(f"[prophet-backtest] fit failed: {e}")
        return None


def _fold_cutoffs(dates: pd.Series, n_folds=N_FOLDS, min_train=MIN_TRAIN_HISTORY,
                   spacing_days=FOLD_SPACING_DAYS):
    """Evenly-spaced cutoff dates, walking backward from the latest point
    that still leaves room for every horizon's realized outcome."""
    last = dates.max()
    latest_cutoff = last - pd.Timedelta(days=max(HORIZONS))
    earliest_cutoff = dates.min() + pd.Timedelta(days=min_train)
    if latest_cutoff <= earliest_cutoff:
        return []
    cutoffs = []
    cur = latest_cutoff
    while cur >= earliest_cutoff and len(cutoffs) < n_folds:
        cutoffs.append(cur)
        cur -= pd.Timedelta(days=spacing_days)
    return sorted(cutoffs)


def run_backtest(symbol=DEFAULT_SYMBOL, category=DEFAULT_CATEGORY, n_folds=N_FOLDS,
                  progress=print, _fit_fn=_fit_and_forecast) -> pd.DataFrame:
    """Walk-forward backtest: fit at each cutoff using only prior data,
    forecast forward, compare to the realized close. Returns aggregated
    stats per horizon (empty if there isn't enough history for a fold)."""
    df = db.load_ohlcv(symbol, category)
    if df.empty:
        progress(f"[prophet-backtest] no OHLCV history for {symbol}/{category}")
        return pd.DataFrame()
    df = df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

    cutoffs = _fold_cutoffs(df["Date"], n_folds=n_folds)
    if not cutoffs:
        progress(f"[prophet-backtest] not enough history for a fold ({len(df)} rows)")
        return pd.DataFrame()

    rows = []
    for i, cutoff in enumerate(cutoffs, 1):
        train = df[df["Date"] <= cutoff][["Date", "Close"]].rename(columns={"Date": "ds", "Close": "y"})
        if len(train) < MIN_TRAIN_HISTORY:
            continue
        progress(f"[prophet-backtest] fold {i}/{len(cutoffs)}: cutoff {cutoff.date()}, "
                 f"{len(train)} training rows")
        anchor_close = float(train["y"].iloc[-1])
        forecast = _fit_fn(train, max(HORIZONS))
        if forecast is None:
            continue

        future_actual = df[df["Date"] > cutoff][["Date", "Close"]].rename(
            columns={"Date": "fwd_date", "Close": "fwd_close"}
        )
        for h in HORIZONS:
            target = cutoff + pd.Timedelta(days=h)
            realized_match = future_actual[future_actual["fwd_date"] <= target]
            forecast_match = forecast[forecast["ds"] <= target]
            if realized_match.empty or forecast_match.empty:
                continue
            realized = float(realized_match.iloc[-1]["fwd_close"])
            predicted = float(forecast_match.iloc[-1]["yhat"])

            actual_ret = realized / anchor_close - 1
            predicted_ret = predicted / anchor_close - 1
            rows.append({
                "symbol": symbol, "category": category,
                "cutoff": cutoff, "horizon_days": h,
                "anchor_close": anchor_close,
                "predicted_close": predicted, "realized_close": realized,
                "predicted_return": predicted_ret, "actual_return": actual_ret,
                "abs_pct_error": abs(predicted - realized) / realized,
                "direction_correct": (predicted_ret > 0) == (actual_ret > 0),
            })

    events = pd.DataFrame(rows)
    if events.empty:
        progress("[prophet-backtest] no folds produced a usable forecast")
        return pd.DataFrame()

    stats_rows = []
    for h, g in events.groupby("horizon_days"):
        stats_rows.append({
            "symbol": symbol, "category": category, "horizon_days": int(h),
            "n_folds": int(len(g)),
            "mape": float(g["abs_pct_error"].mean()),
            "directional_accuracy": float(g["direction_correct"].mean()),
            "avg_predicted_return": float(g["predicted_return"].mean()),
            "avg_actual_return": float(g["actual_return"].mean()),
        })
    stats = pd.DataFrame(stats_rows)

    db.save_table(events, db.table_path("backtest", f"prophet_{category}_events.parquet"))
    db.save_table(stats, db.table_path("backtest", f"prophet_{category}_stats.parquet"))
    return stats


def load_stats(category=DEFAULT_CATEGORY) -> pd.DataFrame:
    return db.load_table(db.table_path("backtest", f"prophet_{category}_stats.parquet"))


def format_backtest_report(stats: pd.DataFrame) -> str:
    if stats.empty:
        return "No Prophet backtest statistics available.\n"
    lines = [f"  {'horizon':<10}{'folds':>7}{'MAPE':>9}{'dir.acc':>10}{'pred ret':>11}{'actual ret':>12}"]
    for _, r in stats.sort_values("horizon_days").iterrows():
        lines.append(
            f"  {int(r['horizon_days']):>3}d{'':<7}{int(r['n_folds']):>7}"
            f"{r['mape']:>9.1%}{r['directional_accuracy']:>10.0%}"
            f"{r['avg_predicted_return']:>+11.1%}{r['avg_actual_return']:>+12.1%}"
        )
    return "\n".join(lines) + "\n"


def live_forecast_summary(symbol=DEFAULT_SYMBOL, category=DEFAULT_CATEGORY) -> str:
    """Directional read (Up/Down/Flat + 80% CI) of the stored Prophet
    forecast at 7/30/90 days. Does not fit — run refit_live_forecast()
    (or prophet_forecast.py) first."""
    import prophet_forecast as prophet_forecast_mod

    fc = prophet_forecast_mod.load_forecast(symbol, category)
    if fc.empty:
        return f"{symbol}: no stored Prophet forecast yet\n"
    ohlcv = db.load_ohlcv(symbol, category)
    if ohlcv.empty:
        return ""
    ohlcv = ohlcv.dropna(subset=["Close"]).sort_values("Date")
    last_close = float(ohlcv["Close"].iloc[-1])
    last_date = ohlcv["Date"].iloc[-1]

    lines = [f"{symbol} Prophet forecast (fit on full history, last close ${last_close:,.2f}):"]
    for h in HORIZONS:
        target = last_date + pd.Timedelta(days=h)
        match = fc[fc["ds"] <= target]
        if match.empty:
            continue
        row = match.iloc[-1]
        pred_ret = float(row["yhat"]) / last_close - 1
        lo_ret = float(row["yhat_lower"]) / last_close - 1
        hi_ret = float(row["yhat_upper"]) / last_close - 1
        if pred_ret >= DIRECTION_FLAT_BAND:
            direction = "Up"
        elif pred_ret <= -DIRECTION_FLAT_BAND:
            direction = "Down"
        else:
            direction = "Flat"
        lines.append(f"  {h}d: {direction} {pred_ret:+.1%} (80% CI {lo_ret:+.1%} to {hi_ret:+.1%})")
    return "\n".join(lines) + "\n"


def refit_live_forecast(symbol=DEFAULT_SYMBOL, category=DEFAULT_CATEGORY):
    """Fit Prophet on the full history and persist it (reuses
    prophet_forecast.py's storage) so live_forecast_summary() has
    something to read."""
    import prophet_forecast as prophet_forecast_mod

    fc = prophet_forecast_mod.forecast_symbol(symbol, category, periods=max(HORIZONS))
    if fc is not None:
        prophet_forecast_mod.save_forecast(fc, symbol, category, "1d")
    return fc


def full_report(symbol=DEFAULT_SYMBOL, category=DEFAULT_CATEGORY,
                 refit_live=True, refit_backtest=True) -> str:
    """Live directional forecast + walk-forward backtest, ready to print."""
    if refit_live:
        refit_live_forecast(symbol, category)
    lines = [live_forecast_summary(symbol, category).rstrip(), ""]

    lines.append(f"Walk-forward backtest ({symbol}, refit at each past cutoff):")
    stats = run_backtest(symbol, category) if refit_backtest else load_stats(category)
    lines.append(format_backtest_report(stats).rstrip())
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(full_report())
