from pycoingecko import CoinGeckoAPI
import pandas as pd, duckdb, yaml, os

cg = CoinGeckoAPI()
db_path = "crypto.duckdb"
yaml_path = "crypto_pairs.yaml"

# Map your Yahoo-style symbols to CoinGecko ids & vs_currency
PAIR_MAP = {
    "BTC-USD": ("bitcoin",  "usd"),
    "ETH-USD": ("ethereum", "usd"),
    "XRP-USD": ("ripple",   "usd"),
    # add more…
}

def get_ohlcv(coin_id: str, vs_currency: str, days=365) -> pd.DataFrame:
    """Return daily OHLCV for the last `days` (≤ 365)."""
    # OHLC (open-high-low-close) – no volume yet
    ohlc = cg.get_coin_ohlc_by_id(coin_id, vs_currency, days)
    ohlc_df = (
        pd.DataFrame(ohlc, columns=["ts", "open", "high", "low", "close"])
          .assign(ts=lambda d: pd.to_datetime(d.ts, unit="ms"))
          .set_index("ts")
    )

    # Volume comes from market_chart
    mc = cg.get_coin_market_chart_by_id(coin_id, vs_currency, days)
    vol_df = (
        pd.DataFrame(mc["total_volumes"], columns=["ts", "volume"])
          .assign(ts=lambda d: pd.to_datetime(d.ts, unit="ms"))
          .set_index("ts")
    )

    return ohlc_df.join(vol_df, how="inner")

# --- main ingest ------------------------------------------------------------
with open(yaml_path) as f:
    cfg = yaml.safe_load(f)

con = duckdb.connect(db_path)

for pair in cfg["pairs"]:
    coin_id, vs_cur = PAIR_MAP.get(pair, (None, None))
    if coin_id is None:
        print(f"No mapping for {pair}; skipping.")
        continue

    df = get_ohlcv(coin_id, vs_cur, days=365)
    # Make sure the timestamp index becomes an explicit column for DuckDB
    df = df.reset_index().rename(columns={'ts': 'date'})
    if df.empty:
        print(f"{pair}: no data returned.")
        continue

    table = pair.lower().replace("-", "_")
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM df")
    print(f"{pair}: loaded {len(df)} daily rows into {table}")