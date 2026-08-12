"""Prophet price forecasting for Crypto Signal Station.

Fits a Facebook Prophet model on each symbol's OHLCV history and stores a
30-day forward forecast to the data lake. Designed to run after the nightly
pipeline refresh.

Storage: data/forecasts/{category}/{timeframe}/{symbol}.parquet
Columns : ds (date), yhat (float), yhat_lower (float), yhat_upper (float)

Usage:
    poetry run python crypto_signal_station/prophet_forecast.py
    poetry run python crypto_signal_station/prophet_forecast.py --symbol BTC-USD --category crypto
"""

import argparse
import logging
import os
import sys
import warnings

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

# Prophet emits noisy Stan / cmdstanpy output; suppress everything below WARNING
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", message=".*Importing plotly.*")

MIN_HISTORY = 60       # rows needed for a meaningful fit
DEFAULT_PERIODS = 30   # forecast horizon in trading days
CATEGORIES = ("crypto", "stocks")
TIMEFRAMES = ("1d",)


def _forecast_path(category: str, timeframe: str, symbol: str) -> str:
    return db.table_path("forecasts", category, timeframe, f"{symbol}.parquet")


def forecast_symbol(
    symbol: str,
    category: str,
    timeframe: str = "1d",
    periods: int = DEFAULT_PERIODS,
) -> pd.DataFrame | None:
    """Fit Prophet on a symbol's history and return a forecast DataFrame.

    Returns None if there is insufficient history or the fit fails.
    Columns: ds (datetime64), yhat, yhat_lower, yhat_upper (float64).
    """
    from prophet import Prophet  # imported lazily: install is optional on dev machines

    df = db.load_signals(symbol, category, timeframe)
    if df.empty or len(df) < MIN_HISTORY:
        return None

    train = (
        df[["Date", "Close"]]
        .rename(columns={"Date": "ds", "Close": "y"})
        .dropna()
        .copy()
    )
    train["ds"] = pd.to_datetime(train["ds"])

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

        future = m.make_future_dataframe(periods=periods, freq="B")  # business days
        forecast = m.predict(future)
        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods).copy()
        result = result.reset_index(drop=True)
        result["symbol"] = symbol
        result["category"] = category
        result["timeframe"] = timeframe
        return result
    except Exception as e:
        print(f"[prophet] {symbol}/{category}/{timeframe} fit failed: {e}")
        return None


def save_forecast(fc: pd.DataFrame, symbol: str, category: str, timeframe: str):
    """Persist a forecast DataFrame atomically."""
    path = _forecast_path(category, timeframe, symbol)
    db.save_table(fc[["ds", "yhat", "yhat_lower", "yhat_upper"]], path)


def load_forecast(symbol: str, category: str, timeframe: str = "1d") -> pd.DataFrame:
    """Load stored forecast (empty DataFrame if not yet computed)."""
    path = _forecast_path(category, timeframe, symbol)
    df = db.load_table(path)
    if not df.empty and "ds" in df.columns:
        df["ds"] = pd.to_datetime(df["ds"])
    return df


def run_all_forecasts(
    category: str | None = None,
    timeframe: str | None = None,
    periods: int = DEFAULT_PERIODS,
    max_symbols: int | None = None,
) -> dict[str, bool]:
    """Generate and persist forecasts for all tracked symbols.

    Returns {symbol: ok} mapping.
    """
    cats = [category] if category else list(CATEGORIES)
    tfs = [timeframe] if timeframe else list(TIMEFRAMES)
    results: dict[str, bool] = {}
    for cat in cats:
        for tf in tfs:
            keys = [(s, c, t) for s, c, t in db.list_signal_keys() if c == cat and t == tf]
            if max_symbols:
                keys = keys[:max_symbols]
            for sym, cat_, tf_ in keys:
                fc = forecast_symbol(sym, cat_, tf_, periods=periods)
                if fc is not None:
                    save_forecast(fc, sym, cat_, tf_)
                    print(f"[prophet] saved forecast: {sym}/{cat_}/{tf_}")
                    results[sym] = True
                else:
                    results[sym] = False
    return results


def forecast_to_json(symbol: str, category: str, timeframe: str = "1d") -> list[dict]:
    """Load a stored forecast and return it as a JSON-serialisable list."""
    df = load_forecast(symbol, category, timeframe)
    if df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        out.append({
            "date": str(row["ds"].date()) if hasattr(row["ds"], "date") else str(row["ds"])[:10],
            "yhat": round(float(row["yhat"]), 6),
            "yhat_lower": round(float(row["yhat_lower"]), 6),
            "yhat_upper": round(float(row["yhat_upper"]), 6),
        })
    return out


def main():
    parser = argparse.ArgumentParser(description="Run Prophet forecasts for tracked symbols")
    parser.add_argument("--symbol", help="Run for one symbol only")
    parser.add_argument("--category", choices=list(CATEGORIES), help="Restrict to one category")
    parser.add_argument("--timeframe", default="1d", help="Timeframe (default: 1d)")
    parser.add_argument("--periods", type=int, default=DEFAULT_PERIODS, help="Forecast horizon")
    parser.add_argument("--max-symbols", type=int, help="Cap number of symbols per category")
    args = parser.parse_args()

    if args.symbol:
        cat = args.category or "crypto"
        fc = forecast_symbol(args.symbol, cat, args.timeframe, args.periods)
        if fc is not None:
            save_forecast(fc, args.symbol, cat, args.timeframe)
            print(fc.to_string(index=False))
        else:
            print(f"Forecast failed or insufficient history for {args.symbol}")
        return

    results = run_all_forecasts(
        category=args.category,
        timeframe=args.timeframe,
        periods=args.periods,
        max_symbols=args.max_symbols,
    )
    ok = sum(v for v in results.values())
    print(f"\nForecasts complete: {ok}/{len(results)} succeeded.")


if __name__ == "__main__":
    main()
