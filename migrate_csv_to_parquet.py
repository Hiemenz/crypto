"""
One-time migration: import the existing crypto OHLCV history from
crypto_history_csv/*.csv into the open table-format Parquet lake (see db.py).

This preserves the full price history so the daily pipeline doesn't have to
re-download ~12 years of data. Signals are intentionally NOT migrated — the
pipeline recomputes them (with the current indicator set) on its next run.

Only plain "<SYMBOL>.csv" files are read; "<SYMBOL>_with_signals.csv" is skipped.
All CSVs present are crypto symbols.

Run once:  poetry run python migrate_csv_to_parquet.py
"""

import glob
import os

import pandas as pd

import db

CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_history_csv")


def main():
    db.init_db()
    csvs = sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
    if not csvs:
        print(f"No CSVs found in {CSV_DIR}; nothing to migrate.")
        return

    migrated = 0
    for path in csvs:
        name = os.path.basename(path)
        if name.endswith("_with_signals.csv"):
            continue
        symbol = name[:-len(".csv")]
        df = pd.read_csv(path)
        if "Date" not in df.columns or df.empty:
            print(f"  skip {symbol}: no usable rows")
            continue
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
        db.upsert_ohlcv(df, symbol, "crypto")
        latest = db.get_latest_ohlcv_date(symbol, "crypto")
        print(f"  migrated {symbol}: {len(df)} rows (through {latest.date()})")
        migrated += 1

    print(f"Done. Migrated {migrated} crypto symbols into {db.OHLCV_DIR}")


if __name__ == "__main__":
    main()
