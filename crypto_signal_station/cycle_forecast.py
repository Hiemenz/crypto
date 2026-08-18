"""Empirical, backtested market-direction forecast.

Where market_cycle.py names the *current* phase from today's snapshot,
this module answers "so what tends to happen next?" — by reconstructing
the full historical breadth time series straight from the OHLCV lake
(years of daily bars, unlike the sparse day-by-day breadth.parquet
snapshot table), bucketing it into the same breadth bands market_cycle
uses to score the crypto phase, and measuring the empirical forward
return of a benchmark after every historical occurrence of each band.

The "model" is a lookup table, not a fitted black box: for band X at
horizon h, {avg_return, win_rate, n} is the realized outcome every time
breadth was in band X historically. Predicting today's return is just
looking up which band today's breadth falls in — deterministic,
inspectable, and only as confident as its sample size (n) says it is.

Benchmark: BTC-USD's own forward return for crypto; the equal-weight
average forward return across all S&P 500 constituents in the lake for
stocks (no single index is stored in the OHLCV lake).

Storage: data/forecast/breadth_model_<category>.parquet
Usage:
    poetry run python crypto_signal_station/crypto_signal_pipeline.py forecast
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import breadth as breadth_mod

HORIZONS = (7, 30, 90)
# Stock bars only exist on trading days; ~5/21/63 trading days approximate
# 7/30/90 calendar days. Crypto trades every day, so a row-shift of h IS
# h calendar days there — no conversion needed.
_TRADING_DAY_EQUIV = {7: 5, 30: 21, 90: 63}
CRYPTO_BENCHMARK = "BTC-USD"

# Same edges market_cycle.compute_crypto_cycle() scores breadth against,
# so "phase" and "forecast" talk about the same regime boundaries.
BREADTH_BANDS = [
    (0.00, 0.25, "≤25%"),
    (0.25, 0.40, "25-40%"),
    (0.40, 0.60, "40-60%"),
    (0.60, 0.75, "60-75%"),
    (0.75, 1.01, "≥75%"),
]

MIN_SAMPLES_MEDIUM = 20
MIN_SAMPLES_HIGH = 60
DIRECTION_FLAT_BAND = 0.005  # +/-0.5%: avg return inside this band reads as "Flat"


def _band_label(pct):
    if pct is None or pd.isna(pct):
        return None
    for lo, hi, label in BREADTH_BANDS:
        if lo <= pct < hi:
            return label
    return BREADTH_BANDS[-1][2]


def _model_path(category):
    return db.table_path("forecast", f"breadth_model_{category}.parquet")


def compute_breadth_timeseries(category) -> pd.DataFrame:
    """Daily pct_above_ma200 / pct_bull reconstructed from the full OHLCV
    history (every symbol's own 200/50-day rolling MA), not the sparse
    breadth.parquet snapshot table. Columns: Date, pct_above_ma200,
    pct_bull, n_active."""
    df = db.scan_ohlcv_lake(category, columns=["Date", "Close"])
    if df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["Close"]).sort_values(["symbol", "Date"])
    df["ma200"] = df.groupby("symbol")["Close"].transform(
        lambda s: s.rolling(200, min_periods=200).mean()
    )
    df["ma50"] = df.groupby("symbol")["Close"].transform(
        lambda s: s.rolling(50, min_periods=50).mean()
    )
    mature = df.dropna(subset=["ma200"]).copy()
    if mature.empty:
        return pd.DataFrame()
    mature["above"] = mature["Close"] > mature["ma200"]
    mature["bull"] = mature["ma50"] > mature["ma200"]
    daily = mature.groupby("Date").agg(
        pct_above_ma200=("above", "mean"),
        pct_bull=("bull", "mean"),
        n_active=("symbol", "nunique"),
    ).reset_index()
    return daily


def _benchmark_forward_returns(category) -> pd.DataFrame:
    """Per-date forward return of the category's benchmark at each horizon.
    Columns: Date, ret_7d, ret_30d, ret_90d."""
    ohlcv = db.scan_ohlcv_lake(category, columns=["Date", "Close"])
    if ohlcv.empty:
        return pd.DataFrame()
    ohlcv = ohlcv.dropna(subset=["Close"]).sort_values(["symbol", "Date"])

    if category == "crypto":
        bench = ohlcv[ohlcv["symbol"] == CRYPTO_BENCHMARK].sort_values("Date").copy()
        if bench.empty:
            return pd.DataFrame()
        for h in HORIZONS:
            bench[f"ret_{h}d"] = bench["Close"].shift(-h) / bench["Close"] - 1
        return bench[["Date"] + [f"ret_{h}d" for h in HORIZONS]].reset_index(drop=True)

    for h in HORIZONS:
        n_rows = _TRADING_DAY_EQUIV[h]
        ohlcv[f"ret_{h}d"] = ohlcv.groupby("symbol")["Close"].transform(
            lambda s, n=n_rows: s.shift(-n) / s - 1
        )
    bench = ohlcv.groupby("Date")[[f"ret_{h}d" for h in HORIZONS]].mean().reset_index()
    return bench


def fit_breadth_model(category) -> pd.DataFrame:
    """Backtest: bucket every historical day by breadth band, measure the
    benchmark's realized forward return at each horizon from that day.
    Persists and returns the resulting lookup table (empty if there isn't
    enough history yet)."""
    breadth_ts = compute_breadth_timeseries(category)
    bench = _benchmark_forward_returns(category)
    if breadth_ts.empty or bench.empty:
        return pd.DataFrame()

    merged = breadth_ts.merge(bench, on="Date", how="inner")
    merged["band"] = merged["pct_above_ma200"].apply(_band_label)
    merged = merged.dropna(subset=["band"])
    if merged.empty:
        return pd.DataFrame()

    rows = []
    for band, g in merged.groupby("band"):
        for h in HORIZONS:
            rets = g[f"ret_{h}d"].dropna()
            if rets.empty:
                continue
            rows.append({
                "category": category,
                "band": band,
                "horizon_days": h,
                "n": int(len(rets)),
                "avg_return": float(rets.mean()),
                "median_return": float(rets.median()),
                "win_rate": float((rets > 0).mean()),
            })
    model = pd.DataFrame(rows)
    db.save_table(model, _model_path(category))
    return model


def load_breadth_model(category) -> pd.DataFrame:
    return db.load_table(_model_path(category))


def predict_market_direction(category, horizon_days=30):
    """Look up today's live breadth band in the backtested model. Returns
    None if breadth can't be computed right now; otherwise a dict — with
    a 'note' key (no prediction fields) if the model or that band/horizon
    has no historical sample yet."""
    live = breadth_mod.compute_breadth(category)
    if live is None or pd.isna(live.get("pct_above_ma200")):
        return None
    pct_above = live["pct_above_ma200"]
    band = _band_label(pct_above)

    base = {
        "category": category, "band": band,
        "pct_above_ma200": pct_above, "horizon_days": horizon_days,
    }
    model = load_breadth_model(category)
    if model.empty:
        return {**base, "note": "no backtested model yet — run fit_breadth_model() first"}

    row = model[(model["band"] == band) & (model["horizon_days"] == horizon_days)]
    if row.empty:
        return {**base, "note": f"no historical samples for the {band} breadth band at {horizon_days}d"}

    r = row.iloc[0]
    avg_ret, win_rate, n = float(r["avg_return"]), float(r["win_rate"]), int(r["n"])
    if avg_ret >= DIRECTION_FLAT_BAND:
        direction = "Up"
    elif avg_ret <= -DIRECTION_FLAT_BAND:
        direction = "Down"
    else:
        direction = "Flat"
    if n >= MIN_SAMPLES_HIGH and (win_rate >= 0.60 or win_rate <= 0.40):
        confidence = "High"
    elif n >= MIN_SAMPLES_MEDIUM:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        **base,
        "predicted_return": avg_ret,
        "median_return": float(r["median_return"]),
        "win_rate": win_rate,
        "n_samples": n,
        "direction": direction,
        "confidence": confidence,
    }


def forecast_line(category) -> str:
    """One line per category across all horizons, e.g.
    'Crypto (breadth 62%, band 60-75%): 7d Up +1.2%/58% (n=210) | 30d ...'"""
    preds = [predict_market_direction(category, h) for h in HORIZONS]
    preds = [p for p in preds if p is not None]
    if not preds:
        return ""
    name = "Crypto" if category == "crypto" else category.capitalize()
    head = preds[0]
    parts = [f"{name} (breadth {head['pct_above_ma200']:.0%}, band {head['band']}):"]
    for p in preds:
        if "predicted_return" not in p:
            parts.append(f"{p['horizon_days']}d n/a")
            continue
        parts.append(
            f"{p['horizon_days']}d {p['direction']} {p['predicted_return']:+.1%}/"
            f"{p['win_rate']:.0%} (n={p['n_samples']}, {p['confidence']})"
        )
    return " ".join(parts) + "\n"


def fit_all(categories=("crypto", "stocks")):
    """Refit the backtested model for each category; returns {category: model_df}."""
    out = {}
    for cat in categories:
        model = fit_breadth_model(cat)
        out[cat] = model
        if model.empty:
            print(f"Forecast model [{cat}]: not enough history to fit yet")
        else:
            print(f"Forecast model [{cat}]: {len(model)} band/horizon rows fitted")
    return out


def forecast_report(refit=True) -> str:
    """Market-cycle phase (market_cycle.py) plus the backtested forward-
    return forecast for each category, ready to print."""
    import market_cycle as market_cycle_mod

    if refit:
        fit_all()

    lines = [market_cycle_mod.algorithmic_summary().rstrip(), "", "Backtested forward-return forecast:"]
    for cat in ("crypto", "stocks"):
        line = forecast_line(cat)
        lines.append("  " + line.rstrip() if line else f"  {cat.capitalize()}: no forecast available")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(forecast_report())
