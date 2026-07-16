"""GICS sector breadth: per-sector share of S&P 500 symbols above their 200dMA.

The sector map (symbol → GICS sector) is populated by update_symbol_universe()
in the pipeline and cached at data/universe/sp500_sectors.json. Breadth is
computed from the OHLCV lake and stored in data/sectors/breadth.parquet.
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

ACTIVE_MAX_AGE_DAYS = 7
MIN_HISTORY = 200


def _map_path():
    return os.path.join(db.DATA_DIR, "universe", "sp500_sectors.json")


def load_sector_map() -> dict:
    """Return {yahoo_symbol: gics_sector}; {} if cache not built yet."""
    try:
        with open(_map_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_sector_map(mapping: dict):
    os.makedirs(os.path.dirname(_map_path()), exist_ok=True)
    with open(_map_path(), "w") as f:
        json.dump(mapping, f)


def compute_and_save() -> pd.DataFrame:
    """Compute per-sector breadth, momentum, and signal activity; persist results."""
    sector_map = load_sector_map()
    if not sector_map:
        print("Sector breadth: no sector map cached yet (run update_symbol_universe first).")
        return pd.DataFrame()

    lake = db.scan_ohlcv_lake("stocks", columns=["Date", "Close"])
    if lake.empty:
        return pd.DataFrame()

    lake = lake.sort_values(["symbol", "Date"])
    cutoff_active = pd.Timestamp.now().normalize() - pd.Timedelta(days=ACTIVE_MAX_AGE_DAYS)

    per_sym = []
    for sym, g in lake.groupby("symbol"):
        g = g.sort_values("Date")
        if len(g) < MIN_HISTORY or g["Date"].iloc[-1] < cutoff_active:
            continue
        per_sym.append({
            "symbol": sym,
            "last_close": float(g["Close"].iloc[-1]),
            "ma200": float(g["Close"].tail(MIN_HISTORY).mean()),
        })

    if not per_sym:
        return pd.DataFrame()

    df = pd.DataFrame(per_sym)
    df["sector"] = df["symbol"].map(sector_map)
    df = df.dropna(subset=["sector"])
    df["above"] = df["last_close"] > df["ma200"]

    # 30-day returns from stored momentum parquet (may be from prior run, ±1 day)
    mom_by_sym: dict = {}
    mom_path = db.table_path("momentum", "latest.parquet")
    if os.path.exists(mom_path):
        try:
            import duckdb
            con = duckdb.connect()
            try:
                mom = con.execute(
                    f"SELECT symbol, ret_30d FROM read_parquet('{mom_path}', hive_partitioning=false)"
                ).df()
            finally:
                con.close()
            mom_by_sym = dict(zip(mom["symbol"], mom["ret_30d"]))
        except Exception as e:
            print(f"Sector breadth: momentum load failed: {e}")

    df["ret_30d"] = df["symbol"].map(mom_by_sym)

    # Today's buy/sell signal counts per sector (1d timeframe)
    sig_buy_syms: set = set()
    sig_sell_syms: set = set()
    try:
        sigs = db.scan_signals_lake("stocks", "1d", columns=["Date", "signal"])
        if not sigs.empty:
            today_sigs = sigs[sigs["Date"] == sigs["Date"].max()]
            sig_buy_syms = set(today_sigs.loc[today_sigs["signal"].str.endswith("Buy"), "symbol"])
            sig_sell_syms = set(today_sigs.loc[today_sigs["signal"].str.endswith("Sell"), "symbol"])
    except Exception as e:
        print(f"Sector breadth: signal load failed: {e}")

    rows = []
    for s, g in df.groupby("sector"):
        sym_set = set(g["symbol"])
        rows.append({
            "sector": s,
            "n": len(g),
            "pct_above_ma200": float(g["above"].mean()),
            "ret_30d": float(g["ret_30d"].mean()) if g["ret_30d"].notna().any() else float("nan"),
            "buy_signals": len(sym_set & sig_buy_syms),
            "sell_signals": len(sym_set & sig_sell_syms),
        })

    result = (
        pd.DataFrame(rows)
        .sort_values("pct_above_ma200", ascending=False)
        .reset_index(drop=True)
    )
    db.save_table(result, db.table_path("sectors", "breadth.parquet"))
    print(f"Sector breadth updated: {len(result)} sectors")
    return result


def load() -> pd.DataFrame:
    """Load stored sector breadth (empty frame if not yet computed)."""
    return db.load_table(db.table_path("sectors", "breadth.parquet"))
