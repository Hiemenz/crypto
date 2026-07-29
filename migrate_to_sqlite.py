#!/usr/bin/env python3
"""
One-time migration: import existing parquet files into the SQLite database.

Run this once after pulling the new code:
  python migrate_to_sqlite.py
"""

import os
import glob
import pandas as pd
import db

DATA_DIR = "crypto_history_csv"

TIMEFRAME_DIRS = ["1d", "2d", "3d", "1wk", "2wk"]


def migrate():
    db.init_db()
    print(f"Migrating parquet data from '{DATA_DIR}' into '{db.DB_PATH}'...")

    total_ohlcv = 0
    total_signals = 0

    for category in ["crypto", "stocks"]:
        # --- OHLCV (raw daily) ---
        ohlcv_dir = os.path.join(DATA_DIR, category, "1d")
        if os.path.exists(ohlcv_dir):
            for fpath in glob.glob(os.path.join(ohlcv_dir, "*.parquet")):
                fname = os.path.basename(fpath)
                if "_with_signals" in fname:
                    continue  # handled below
                symbol = fname.replace(".parquet", "")
                try:
                    df = pd.read_parquet(fpath)
                    if df.empty:
                        continue
                    if "Date" not in df.columns:
                        df = df.reset_index()
                    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
                    expected = ["Date", "Open", "High", "Low", "Close", "Volume"]
                    available = [c for c in expected if c in df.columns]
                    df = df[available].drop_duplicates(subset="Date")
                    db.upsert_ohlcv(df, symbol, category)
                    total_ohlcv += len(df)
                    print(f"  OHLCV {category}/{symbol}: {len(df)} rows")
                except Exception as e:
                    print(f"  ERROR OHLCV {category}/{symbol}: {e}")

        # --- Signals (all timeframes) ---
        for tf in TIMEFRAME_DIRS:
            tf_dir = os.path.join(DATA_DIR, category, tf)
            if not os.path.exists(tf_dir):
                continue
            for fpath in glob.glob(os.path.join(tf_dir, "*_with_signals.parquet")):
                symbol = os.path.basename(fpath).replace("_with_signals.parquet", "")
                try:
                    df = pd.read_parquet(fpath)
                    if df.empty:
                        continue
                    if "Date" not in df.columns:
                        df = df.reset_index()
                    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
                    db.upsert_signals(df, symbol, category, tf)
                    total_signals += len(df)
                    print(f"  Signals {category}/{tf}/{symbol}: {len(df)} rows")
                except Exception as e:
                    print(f"  ERROR Signals {category}/{tf}/{symbol}: {e}")

    print(f"\nMigration complete.")
    print(f"  OHLCV rows inserted:  {total_ohlcv}")
    print(f"  Signal rows inserted: {total_signals}")


if __name__ == "__main__":
    migrate()
