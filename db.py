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


def list_signal_keys():
    """Enumerate stored signal partitions as (symbol, category, timeframe).

    Walks the lake directory rather than the config universe, so signals for
    symbols that later left the universe still show up (e.g. for backtests).
    """
    keys = []
    if not os.path.isdir(SIGNALS_DIR):
        return keys
    for cat_dir in sorted(os.listdir(SIGNALS_DIR)):
        if not cat_dir.startswith("category="):
            continue
        cat = cat_dir.split("=", 1)[1]
        cat_path = os.path.join(SIGNALS_DIR, cat_dir)
        for tf_dir in sorted(os.listdir(cat_path)):
            if not tf_dir.startswith("timeframe="):
                continue
            tf = tf_dir.split("=", 1)[1]
            tf_path = os.path.join(cat_path, tf_dir)
            for sym_dir in sorted(os.listdir(tf_path)):
                if not sym_dir.startswith("symbol="):
                    continue
                if os.path.exists(os.path.join(tf_path, sym_dir, "data.parquet")):
                    keys.append((sym_dir.split("=", 1)[1], cat, tf))
    return keys


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

def _fetch_one(sql: str):
    """Run a query on a private connection and return its first row (the
    module-level default DuckDB connection is not safe under the pipeline's
    thread pool)."""
    con = duckdb.connect()
    try:
        return con.execute(sql).fetchone()
    finally:
        con.close()


def _read_parquet(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    # hive_partitioning=false: each file is a single partition; we don't want
    # DuckDB synthesizing category/symbol columns from the directory names.
    con = duckdb.connect()
    try:
        return con.execute(
            f"SELECT * FROM read_parquet('{path}', hive_partitioning=false)"
        ).df()
    finally:
        con.close()


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
    row = _fetch_one(f"SELECT max(Date) FROM read_parquet('{path}')")
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


def replace_ohlcv(df: pd.DataFrame, symbol: str, category: str):
    """Overwrite ALL OHLCV rows for a symbol/category with df (no merge).

    Use when history has been re-adjusted (split/dividend) and stale rows
    must not survive."""
    out = df[[c for c in OHLCV_COLUMNS if c in df.columns]].copy()
    out["Date"] = pd.to_datetime(out["Date"])
    out = (
        out.drop_duplicates(subset="Date", keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    _write_parquet_atomic(out, _ohlcv_file(symbol, category))


# ── SIGNALS ───────────────────────────────────────────────────────────────────

def get_signals_date_range(symbol: str, category: str, timeframe: str):
    """Return (min_date, max_date) as pd.Timestamps, or (None, None) if empty."""
    path = _signals_file(symbol, category, timeframe)
    if not os.path.exists(path):
        return None, None
    row = _fetch_one(f"SELECT min(Date), max(Date) FROM read_parquet('{path}')")
    if not row or row[0] is None:
        return None, None
    return pd.Timestamp(row[0]), pd.Timestamp(row[1])


def upsert_signals(df: pd.DataFrame, symbol: str, category: str, timeframe: str):
    """Insert or update signal rows. df must have a 'Date' column plus signal columns."""
    path = _signals_file(symbol, category, timeframe)
    merged = _merge_on_date(_read_parquet(path), df)
    _write_parquet_atomic(merged, path)


def replace_signals(df: pd.DataFrame, symbol: str, category: str, timeframe: str):
    """Overwrite ALL signal rows for a symbol/category/timeframe with df (no merge).

    Signals are recomputed over full history each run, so the incoming frame is
    authoritative; merging would leave phantom rows when bin boundaries or
    upstream data change."""
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"])
    out = (
        out.drop_duplicates(subset="Date", keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    _write_parquet_atomic(out, _signals_file(symbol, category, timeframe))


def scan_ohlcv_lake(category: str, columns=None) -> pd.DataFrame:
    """Scan every symbol's OHLCV in one DuckDB query, adding a 'symbol' column.

    hive_partitioning=true here (unlike single-file reads): the glob spans
    partition directories, so DuckDB derives category/symbol from the paths.
    union_by_name tolerates schema drift between old and new partitions.
    """
    glob = os.path.join(OHLCV_DIR, f"category={category}", "symbol=*", "data.parquet")
    if not os.path.isdir(os.path.join(OHLCV_DIR, f"category={category}")):
        return pd.DataFrame()
    cols = "*" if not columns else ", ".join(f'"{c}"' for c in ["symbol", *columns])
    con = duckdb.connect()
    try:
        df = con.execute(
            f"SELECT {cols} FROM read_parquet('{glob}', "
            "hive_partitioning=true, union_by_name=true)"
        ).df()
    except duckdb.IOException:
        # Partition dir exists but holds no parquet files (crash mid-write,
        # manual cleanup): an empty lake, not an error
        return pd.DataFrame()
    finally:
        con.close()
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def latest_ohlcv_dates(category: str) -> dict:
    """{symbol: latest Date} for every stored symbol, in one aggregation query
    (per-symbol get_latest_ohlcv_date calls cost ~2 connections each and add
    up to minutes across the S&P 500 on a Pi)."""
    glob = os.path.join(OHLCV_DIR, f"category={category}", "symbol=*", "data.parquet")
    if not os.path.isdir(os.path.join(OHLCV_DIR, f"category={category}")):
        return {}
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT symbol, max(Date) FROM read_parquet('{glob}', "
            "hive_partitioning=true, union_by_name=true) GROUP BY symbol"
        ).fetchall()
    except duckdb.IOException:
        return {}
    finally:
        con.close()
    return {sym: pd.Timestamp(d) for sym, d in rows if d is not None}


def scan_signals_lake(category: str, timeframe: str, columns=None) -> pd.DataFrame:
    """Scan every symbol's signals for one category/timeframe in one query."""
    base = os.path.join(SIGNALS_DIR, f"category={category}", f"timeframe={timeframe}")
    if not os.path.isdir(base):
        return pd.DataFrame()
    glob = os.path.join(base, "symbol=*", "data.parquet")
    cols = "*" if not columns else ", ".join(f'"{c}"' for c in ["symbol", *columns])
    con = duckdb.connect()
    try:
        df = con.execute(
            f"SELECT {cols} FROM read_parquet('{glob}', "
            "hive_partitioning=true, union_by_name=true)"
        ).df()
    except duckdb.IOException:
        # Partition dir exists but holds no parquet files: empty, not an error
        return pd.DataFrame()
    finally:
        con.close()
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df


# ── generic tables (breadth history, backtest stats, ...) ───────────────────────

def table_path(*parts) -> str:
    """Path of a small auxiliary table inside the data lake, e.g.
    table_path('backtest', 'stats.parquet')."""
    return os.path.join(DATA_DIR, *parts)


def load_table(path: str) -> pd.DataFrame:
    """Load an auxiliary Parquet table (empty frame if absent)."""
    df = _read_parquet(path)
    if not df.empty and "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
    return df


def save_table(df: pd.DataFrame, path: str):
    """Overwrite an auxiliary Parquet table atomically."""
    _write_parquet_atomic(df, path)


def upsert_table_on_date(df: pd.DataFrame, path: str):
    """Merge rows into an auxiliary table keyed on Date (newest wins)."""
    _write_parquet_atomic(_merge_on_date(_read_parquet(path), df), path)


def load_signals(symbol: str, category: str, timeframe: str) -> pd.DataFrame:
    """Load all signal rows for a symbol/category/timeframe, sorted by Date ascending."""
    df = _read_parquet(_signals_file(symbol, category, timeframe))
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)
