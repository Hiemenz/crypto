"""Pre-compute momentum rankings from the OHLCV lake.

Computes 1-month, 3-month, and 6-month trailing returns for every active symbol
and stores the result in data/momentum/latest.parquet. Also computes the altcoin
season index (% of cryptos outperforming BTC over 90 days) and stores it to
data/momentum/altcoin_season.json. Called during refresh; the dashboard reads
the stored frames without re-scanning the lake.
"""

import json
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

    _compute_and_store_altcoin_season(combined)
    return combined


def _compute_and_store_altcoin_season(df: pd.DataFrame):
    """Altcoin season index: % of crypto symbols outperforming BTC over 90d."""
    crypto = df[df["category"] == "crypto"].dropna(subset=["ret_90d"])
    if crypto.empty:
        return

    btc_rows = crypto[crypto["symbol"] == "BTC-USD"]
    if btc_rows.empty:
        print("Altcoin season: BTC-USD not in momentum data, skipping")
        return

    btc_ret = float(btc_rows["ret_90d"].iloc[0])
    n_total = len(crypto)
    n_beating = int((crypto["ret_90d"] > btc_ret).sum())
    pct_beating = n_beating / n_total if n_total > 0 else 0.0

    if pct_beating >= 0.75:
        label = "Altcoin Season"
    elif pct_beating >= 0.50:
        label = "Neutral"
    else:
        label = "BTC Season"

    result = {
        "btc_ret_90d": btc_ret,
        "pct_beating_btc": pct_beating,
        "n_total": n_total,
        "n_beating": n_beating,
        "label": label,
        "as_of": pd.Timestamp.now().isoformat(),
    }
    path = db.table_path("momentum", "altcoin_season.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f)
    print(f"Altcoin season: {label} ({pct_beating:.0%} of {n_total} beating BTC {btc_ret:+.1%})")


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


def load_altcoin_season() -> dict:
    """Load stored altcoin season data ({} if not yet computed)."""
    path = db.table_path("momentum", "altcoin_season.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}
