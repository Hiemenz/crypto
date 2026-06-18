"""
Open table-format storage for OHLCV + computed signals.

Data is stored as partitioned Parquet (an open columnar format) and queried
with DuckDB. Nothing here is committed to git — see the repo .gitignore.

Layout (Hive-style partitions, one small Parquet file per partition):

    data/ohlcv/category=<cat>/symbol=<sym>/data.parquet
    data/signals/category=<cat>/timeframe=<tf>/symbol=<sym>/data.parquet

All frames use capitalized columns. OHLCV frames have:
    Date, Open, High, Low, Close, Volume
Signal frames add indicator columns (rsi, mfi, macd, ...) plus a 'signal' label.

You can query the whole lake directly, e.g.:
    duckdb.sql("SELECT * FROM read_parquet('data/ohlcv/**/*.parquet', "
               "hive_partitioning=true) WHERE symbol='BTC-USD'")
"""

import os
import duckdb
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OHLCV_DIR = os.path.join(DATA_DIR, "ohlcv")
SIGNALS_DIR = os.path.join(DATA_DIR, "signals")

OHLCV_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]


def init_db():
    """Ensure the data directories exist. Safe to call repeatedly."""
    os.makedirs(OHLCV_DIR, exist_ok=True)
    os.makedirs(SIGNALS_DIR, exist_ok=True)


# ── path helpers ───────────────────────────────────────────────────────────────

def _ohlcv_file(symbol: str, category: str) -> str:
    return os.path.join(
        OHLCV_DIR, f"category={category}", f"symbol={symbol}", "data.parquet"
    )


def _signals_file(symbol: str, category: str, timeframe: str) -> str:
    return os.path.join(
        SIGNALS_DIR,
        f"category={category}",
        f"timeframe={timeframe}",
        f"symbol={symbol}",
        "data.parquet",
    )


# ── parquet I/O (DuckDB, no pyarrow needed) ─────────────────────────────────────

def _read_parquet(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    # hive_partitioning=false: each file is a single partition; we don't want
    # DuckDB synthesizing category/symbol columns from the directory names.
    return duckdb.sql(
        f"SELECT * FROM read_parquet('{path}', hive_partitioning=false)"
    ).df()


def _duckdb_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce pandas 3.0 string-backed columns to object dtype, which DuckDB's
    pandas scan understands (it does not recognize the new 'str'/StringDtype)."""
    out = df.copy()
    for col in out.columns:
        dtype = out[col].dtype
        if isinstance(dtype, pd.StringDtype) or str(dtype) == "str":
            out[col] = out[col].astype(object)
    return out


def _write_parquet_atomic(df: pd.DataFrame, path: str):
    """Write df to `path` atomically so a crash mid-write can't corrupt data."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    con = duckdb.connect()
    try:
        con.register("_to_write", _duckdb_safe(df))
        con.execute(f"COPY _to_write TO '{tmp}' (FORMAT PARQUET)")
    finally:
        con.close()
    os.replace(tmp, path)


def _merge_on_date(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Upsert semantics: combine rows, newest wins on duplicate Date."""
    incoming = incoming.copy()
    incoming["Date"] = pd.to_datetime(incoming["Date"])
    if existing.empty:
        combined = incoming
    else:
        existing = existing.copy()
        existing["Date"] = pd.to_datetime(existing["Date"])
        combined = pd.concat([existing, incoming], ignore_index=True)
    combined = combined.drop_duplicates(subset="Date", keep="last")
    return combined.sort_values("Date").reset_index(drop=True)


# ── OHLCV ───────────────────────────────────────────────────────────────────────

def get_latest_ohlcv_date(symbol: str, category: str):
    """Return the most recent Date (pd.Timestamp) for a symbol, or None."""
    path = _ohlcv_file(symbol, category)
    if not os.path.exists(path):
        return None
    row = duckdb.sql(f"SELECT max(Date) FROM read_parquet('{path}')").fetchone()
    if not row or row[0] is None:
        return None
    return pd.Timestamp(row[0])


def load_ohlcv(symbol: str, category: str) -> pd.DataFrame:
    """Load all OHLCV rows for a symbol/category, sorted by Date ascending."""
    df = _read_parquet(_ohlcv_file(symbol, category))
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def upsert_ohlcv(df: pd.DataFrame, symbol: str, category: str):
    """Insert or update OHLCV rows. df must have Date, Open, High, Low, Close, Volume."""
    incoming = df[[c for c in OHLCV_COLUMNS if c in df.columns]].copy()
    merged = _merge_on_date(_read_parquet(_ohlcv_file(symbol, category)), incoming)
    _write_parquet_atomic(merged, _ohlcv_file(symbol, category))


# ── SIGNALS ───────────────────────────────────────────────────────────────────

def get_signals_date_range(symbol: str, category: str, timeframe: str):
    """Return (min_date, max_date) as pd.Timestamps, or (None, None) if empty."""
    path = _signals_file(symbol, category, timeframe)
    if not os.path.exists(path):
        return None, None
    row = duckdb.sql(
        f"SELECT min(Date), max(Date) FROM read_parquet('{path}')"
    ).fetchone()
    if not row or row[0] is None:
        return None, None
    return pd.Timestamp(row[0]), pd.Timestamp(row[1])


def upsert_signals(df: pd.DataFrame, symbol: str, category: str, timeframe: str):
    """Insert or update signal rows. df must have a 'Date' column plus signal columns."""
    path = _signals_file(symbol, category, timeframe)
    merged = _merge_on_date(_read_parquet(path), df)
    _write_parquet_atomic(merged, path)


def load_signals(symbol: str, category: str, timeframe: str) -> pd.DataFrame:
    """Load all signal rows for a symbol/category/timeframe, sorted by Date ascending."""
    df = _read_parquet(_signals_file(symbol, category, timeframe))
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)
