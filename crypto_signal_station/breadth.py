"""Market breadth / regime statistics computed from the OHLCV lake.

Breadth answers "how healthy is the whole market?" independent of any single
ticker: the share of symbols above their 200-day MA, the share in a bull
alignment (50MA > 200MA), fresh 52-week highs/lows, and the share of symbols
carrying an active buy/sell signal today.

One row per day per category is appended to
    data/breadth/history_<category>.parquet
so trends can be charted; the latest row feeds the eink/tweet regime line.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

# Mirrors the pipeline's active-symbol cutoff (not imported: the pipeline
# imports this module, and importing back would be circular).
ACTIVE_MAX_AGE_DAYS = 7
TRADING_DAYS_52W = 252

# Share of symbols above their 200-day MA that separates market regimes.
RISK_ON_THRESHOLD = 0.60
RISK_OFF_THRESHOLD = 0.40


def regime_label(pct_above_ma200):
    if pd.isna(pct_above_ma200):
        return "Unknown"
    if pct_above_ma200 >= RISK_ON_THRESHOLD:
        return "Risk-On"
    if pct_above_ma200 <= RISK_OFF_THRESHOLD:
        return "Risk-Off"
    return "Neutral"


def compute_breadth(category="stocks"):
    """Cross-sectional breadth for one category. Returns a dict, or None if
    the lake has no usable data for it."""
    df = db.scan_ohlcv_lake(category, columns=["Date", "Close"])
    if df.empty:
        return None
    df = df.dropna(subset=["Close"]).sort_values(["symbol", "Date"])

    g52 = df.groupby("symbol").tail(TRADING_DAYS_52W).groupby("symbol")
    per_sym = g52.agg(
        last_date=("Date", "max"),
        high_52w=("Close", "max"),
        low_52w=("Close", "min"),
        n_bars=("Close", "size"),
    )
    per_sym["last_close"] = g52["Close"].last()
    per_sym["ma_200"] = df.groupby("symbol").tail(200).groupby("symbol")["Close"].mean()
    per_sym["ma_50"] = df.groupby("symbol").tail(50).groupby("symbol")["Close"].mean()

    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=ACTIVE_MAX_AGE_DAYS)
    per_sym = per_sym[per_sym["last_date"] >= cutoff]
    if per_sym.empty:
        return None
    as_of = per_sym["last_date"].max().normalize()

    # MA-based ratios only over symbols with enough history to have a real MA
    mature = per_sym[per_sym["n_bars"] >= 200]
    pct_above = float((mature["last_close"] > mature["ma_200"]).mean()) if len(mature) else float("nan")
    pct_bull = float((mature["ma_50"] > mature["ma_200"]).mean()) if len(mature) else float("nan")

    # The latest close is inside the 52w window, so a new high is equality
    # (tiny epsilon guards float noise)
    highs = int((per_sym["last_close"] >= per_sym["high_52w"] * (1 - 1e-9)).sum())
    lows = int((per_sym["last_close"] <= per_sym["low_52w"] * (1 + 1e-9)).sum())

    pct_buy = pct_sell = float("nan")
    sigs = db.scan_signals_lake(category, "1d", columns=["Date", "signal"])
    if not sigs.empty:
        latest = sigs[sigs["Date"] == sigs["Date"].max()]
        if len(latest):
            pct_buy = float(latest["signal"].str.endswith("Buy").mean())
            pct_sell = float(latest["signal"].str.endswith("Sell").mean())

    return {
        "Date": as_of,
        "category": category,
        "n_active": int(len(per_sym)),
        "pct_above_ma200": pct_above,
        "pct_bull": pct_bull,
        "new_highs_52w": highs,
        "new_lows_52w": lows,
        "pct_buy_signal": pct_buy,
        "pct_sell_signal": pct_sell,
        "regime": regime_label(pct_above),
    }


def _history_path(category):
    return db.table_path("breadth", f"history_{category}.parquet")


def load_history(category="stocks") -> pd.DataFrame:
    return db.load_table(_history_path(category))


def record_daily(categories=("stocks", "crypto")):
    """Compute breadth for each category and append it to the daily history.

    Returns {category: row_dict} for whatever could be computed."""
    out = {}
    for cat in categories:
        row = compute_breadth(cat)
        if row is None:
            print(f"Breadth: no data for {cat}")
            continue
        db.upsert_table_on_date(pd.DataFrame([row]), _history_path(cat))
        out[cat] = row
        print(breadth_line(row))
    return out


def breadth_line(row) -> str:
    """One-line summary for the eink display / tweet, e.g.
    'Stocks: 62% >200dMA • Risk-On • 52w H/L 12/3'."""
    if not row:
        return ""
    name = "Stocks" if row["category"] == "stocks" else row["category"].capitalize()
    pct = row["pct_above_ma200"]
    pct_str = f"{pct:.0%}" if pd.notna(pct) else "n/a"
    return (
        f"{name}: {pct_str} >200dMA • {row['regime']} • "
        f"52w H/L {row['new_highs_52w']}/{row['new_lows_52w']}\n"
    )


def latest_breadth_line(category="stocks") -> str:
    """Regime line from stored history (no recompute); '' when unavailable."""
    hist = load_history(category)
    if hist.empty:
        return ""
    return breadth_line(hist.iloc[-1].to_dict())


if __name__ == "__main__":
    record_daily()
