"""Pre-compute momentum rankings from the OHLCV lake.

Computes 1-month, 3-month, and 6-month trailing returns for every active symbol
and stores the result in data/momentum/latest.parquet. Called during refresh;
the dashboard reads the stored frame without re-scanning the lake.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

HORIZONS_DAYS = [30, 90, 180]
ACTIVE_MAX_AGE_DAYS = 7


def compute(categories=("stocks", "crypto")) -> pd.DataFrame:
    """Compute trailing returns for all active symbols; return combined DataFrame."""
    now = pd.Timestamp.now().normalize()
    cutoff_active = now - pd.Timedelta(days=ACTIVE_MAX_AGE_DAYS)
    cutoff_h = {h: now - pd.Timedelta(days=h) for h in HORIZONS_DAYS}

    frames = []
    for cat in categories:
        lake = db.scan_ohlcv_lake(cat, columns=["Date", "Close"])
        if lake.empty:
            continue
        lake = lake.sort_values(["symbol", "Date"])

        rows = []
        for sym, g in lake.groupby("symbol"):
            g = g.sort_values("Date")
            if g["Date"].iloc[-1] < cutoff_active:
                continue
            last = float(g["Close"].iloc[-1])
            row = {"symbol": sym, "category": cat, "last_close": last}
            for h in HORIZONS_DAYS:
                past = g[g["Date"] <= cutoff_h[h]]
                if not past.empty:
                    prev = float(past["Close"].iloc[-1])
                    row[f"ret_{h}d"] = (last / prev - 1) if prev > 0 else None
                else:
                    row[f"ret_{h}d"] = None
            rows.append(row)

        if rows:
            frames.append(pd.DataFrame(rows))
        print(f"Momentum [{cat}]: {len(rows)} symbols computed")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    db.save_table(combined, db.table_path("momentum", "latest.parquet"))
    return combined


def load() -> pd.DataFrame:
    """Load stored momentum data (empty frame if not yet computed)."""
    path = db.table_path("momentum", "latest.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    import duckdb
    con = duckdb.connect()
    try:
        df = con.execute(
            f"SELECT * FROM read_parquet('{path}', hive_partitioning=false)"
        ).df()
    finally:
        con.close()
    return df
