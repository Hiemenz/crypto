"""Signal history log: append today's signals and measure forward returns.

Written once per nightly run by `append_today()`.  After 30+ days the log is
rich enough for `forward_returns()` to answer "did the signals work?" without
running a full backtest.

Storage: data/signal_log/{category}/{timeframe}/data.parquet
Columns : date (date), symbol (str), signal (str), close (float64)
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db


def _log_path(category: str, timeframe: str) -> str:
    return db.table_path(f"signal_log/{category}/{timeframe}", "data.parquet")


def append_today(category: str, timeframe: str) -> int:
    """Append today's signal rows to the log; return number of rows added.

    Idempotent: rows whose (date, symbol) pair already exists are dropped so
    re-running the pipeline doesn't double-count.
    """
    import duckdb

    # scan_signals_lake always includes 'symbol' as the first projected column
    lake = db.scan_signals_lake(category, timeframe, columns=["Date", "signal", "Close"])
    if lake.empty:
        return 0

    latest_date = lake["Date"].max()
    today = lake[lake["Date"] == latest_date].copy()

    # Build the log rows (symbol is already in the lake scan result)
    new_rows = today[["symbol", "Date", "signal", "Close"]].rename(
        columns={"Date": "date", "Close": "close"}
    ).copy()
    new_rows["date"] = pd.to_datetime(new_rows["date"]).dt.date
    new_rows["category"] = category
    new_rows["timeframe"] = timeframe

    path = _log_path(category, timeframe)
    if os.path.exists(path):
        con = duckdb.connect()
        try:
            old = con.execute(
                f"SELECT * FROM read_parquet('{path}', hive_partitioning=false)"
            ).df()
        finally:
            con.close()
        if not old.empty:
            old["date"] = pd.to_datetime(old["date"]).dt.date
            date_str = str(latest_date.date()) if hasattr(latest_date, "date") else str(latest_date)[:10]
            already = set(old.loc[old["date"].astype(str) == date_str, "symbol"].astype(str))
            new_rows = new_rows[~new_rows["symbol"].isin(already)]
        if new_rows.empty:
            print(f"Signal log [{category}/{timeframe}]: already up-to-date.")
            return 0
        combined = pd.concat([old, new_rows], ignore_index=True)
    else:
        combined = new_rows

    combined = combined.drop_duplicates(subset=["date", "symbol"])
    combined = combined.sort_values(["date", "symbol"]).reset_index(drop=True)
    db.save_table(combined, path)
    n = len(new_rows)
    print(f"Signal log [{category}/{timeframe}]: appended {n} rows.")
    return n


def load_log(category: str, timeframe: str) -> pd.DataFrame:
    """Load the full signal log (empty DataFrame if not yet built)."""
    path = _log_path(category, timeframe)
    return db.load_table(path)


def forward_returns(
    category: str,
    timeframe: str,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """Measure actual price change at each horizon after every logged signal.

    Returns a DataFrame with columns:
        signal, horizon_days, n, win_rate, avg_return, median_return
    Only rows with a non-Hold signal are included.
    """
    if horizons is None:
        horizons = [1, 7, 30]

    log = load_log(category, timeframe)
    if log.empty:
        return pd.DataFrame()

    log["date"] = pd.to_datetime(log["date"])
    signals = log[log["signal"] != "Hold"].copy()
    if signals.empty:
        return pd.DataFrame()

    ohlcv = db.scan_ohlcv_lake(category, columns=["Date", "Close"])
    if ohlcv.empty:
        return pd.DataFrame()

    ohlcv["Date"] = pd.to_datetime(ohlcv["Date"])
    price_by = ohlcv.groupby(["symbol", "Date"])["Close"].last()

    rows = []
    for _, sig_row in signals.iterrows():
        sym = sig_row["symbol"]
        entry_date = sig_row["date"]
        entry_close = sig_row["close"]
        if entry_close is None or entry_close == 0:
            continue
        for h in horizons:
            target_date = entry_date + pd.Timedelta(days=h)
            # Find the nearest available trading day at or after target
            sym_prices = price_by.get(sym)
            if sym_prices is None:
                continue
            future = sym_prices[sym_prices.index >= target_date]
            if future.empty:
                continue
            exit_close = float(future.iloc[0])
            pct = (exit_close - float(entry_close)) / float(entry_close) * 100
            rows.append({
                "signal": sig_row["signal"],
                "horizon_days": h,
                "symbol": sym,
                "entry_date": entry_date,
                "pct_return": round(pct, 4),
            })

    if not rows:
        return pd.DataFrame()

    detail = pd.DataFrame(rows)
    stats = (
        detail.groupby(["signal", "horizon_days"])["pct_return"]
        .agg(
            n="count",
            avg_return="mean",
            median_return="median",
            win_rate=lambda x: (x > 0).mean() * 100,
        )
        .reset_index()
        .round({"avg_return": 4, "median_return": 4, "win_rate": 2})
    )
    return stats


def scorecard_json(category: str, timeframe: str = "1d") -> list[dict]:
    """Return forward-return stats as a list of dicts for JSON export."""
    stats = forward_returns(category, timeframe)
    if stats.empty:
        return []
    return stats.to_dict(orient="records")


def main():
    """CLI: append today's signals to the log for all categories/timeframes."""
    for cat in ("crypto", "stocks"):
        for tf in ("1d", "1wk"):
            try:
                append_today(cat, tf)
            except Exception as e:
                print(f"signal_log [{cat}/{tf}] failed: {e}")


if __name__ == "__main__":
    main()
