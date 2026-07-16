import io
import json

import pandas as pd
import matplotlib
matplotlib.use('Agg') # Thread-safe backend for saving images
# The OO API (Figure, not pyplot) is used for charts: pyplot keeps global
# state and is not safe under the thread pool.
from matplotlib.figure import Figure
import matplotlib.ticker as mticker
import yfinance as yf
import time
import os
import ta
import yaml
import requests
from eink_generator import generate_crypto_signal_image
from toot import send_toot
from send_to_x import send_tweet

from datetime import datetime
from zoneinfo import ZoneInfo
from pycoingecko import CoinGeckoAPI
import sys
import threading
import traceback

# Add parent directory to path so we can import db
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import breadth as breadth_mod
import dashboard as dashboard_mod
import notify
import sectors as sectors_mod
import momentum as momentum_mod

# Load config from YAML (symbol lists are resolved by _load_universe below,
# which layers the auto-updated universe caches on top of the YAML lists)
with open("crypto_signal_station/cryptos.yml", "r") as f:
    config = yaml.safe_load(f)


def _universe_file(name):
    return os.path.join(db.DATA_DIR, "universe", name)


def _load_universe():
    """Resolve the effective symbol lists.

    Stocks: the YAML `stocks:` list, or the cached S&P 500 constituents when
    `auto_update_stocks: sp500` is set (replacement, so removed constituents
    drop out). Cryptos: the YAML `cryptos:` list, plus the cached CoinGecko
    top-N when `auto_update_cryptos: <N>` is set (union, curated picks stay).
    """
    global symbols, stock_symbols
    symbols = list(config.get("cryptos", []))
    stock_symbols = list(config.get("stocks", []))

    if config.get("auto_update_stocks") == "sp500":
        path = _universe_file("sp500.json")
        if os.path.exists(path):
            with open(path) as f:
                stock_symbols = json.load(f)

    if config.get("auto_update_cryptos"):
        path = _universe_file("top_cryptos.json")
        if os.path.exists(path):
            with open(path) as f:
                extra = json.load(f)
            symbols += [s for s in extra if s not in symbols]


_load_universe()


# One worker per Pi core: downloads are network-bound and pandas/numpy release
# the GIL for most of the indicator math. Charts use the thread-safe Figure API.
MAX_WORKERS = 4

HISTORY_START = "2014-01-01"
# Relative change in the re-downloaded last stored Close that signals a
# retroactive re-adjustment (split/dividend) of the whole history.
ADJUSTMENT_TOLERANCE = 1e-4
# A symbol whose latest bar is older than this is considered inactive
# (delisted/halted) and excluded from summaries.
ACTIVE_MAX_AGE_DAYS = 7
# A fixed Monday, so 2wk bins cover the same Mon–Sun fortnights for every symbol
TWO_WEEK_ORIGIN = pd.Timestamp("2014-01-06")


def _last_complete_daily_date(category, now=None):
    """Date of the most recent fully-closed daily bar for this market.

    Crypto daily candles are UTC-dated and close at 00:00 UTC of the next day.
    Stock bars are dated by the US/Eastern trading day and close at 16:00 ET;
    weekends/holidays need no special-casing because yfinance simply returns
    no bar for them.

    `now` (a tz-aware Timestamp) defaults to the current time.
    """
    if now is None:
        now = pd.Timestamp.now(tz="UTC")
    if category == "crypto":
        return (now.tz_convert("UTC") - pd.Timedelta(days=1)).date()
    now_et = now.tz_convert(ZoneInfo("America/New_York"))
    if now_et.hour >= 16:
        return now_et.date()
    return (now_et - pd.Timedelta(days=1)).date()


# yf.download is NOT safe under concurrent callers (threads=False only turns
# off yfinance's internal pool): parallel calls can receive each other's
# payloads. This corrupted ETH-USD with ADA-USD's history (and HBAR with
# DOGE's) on 2026-07-14 — every download must hold this lock.
_YF_LOCK = threading.Lock()


def _fetch_daily(symbol, start_date, last_complete):
    """Download and normalize daily bars for [start_date, last_complete].

    Returns a frame with Date/Open/High/Low/Close/Volume containing only
    fully-closed candles, or an empty frame on failure/no data.
    """
    try:
        with _YF_LOCK:
            df = _yf_download_locked(symbol, start_date, last_complete)
    except Exception as e:
        print(f"Error downloading {symbol}: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        # Belt-and-braces: verify the payload is actually for this symbol
        tickers = {t for t in df.columns.get_level_values(-1) if t}
        if tickers and symbol not in tickers:
            print(f"Error downloading {symbol}: response was for {tickers}, discarding")
            return pd.DataFrame()
        df.columns = df.columns.get_level_values(0)
    df = df.loc[:, ~df.columns.duplicated()]
    df = df.reset_index()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        if df["Date"].dt.tz is not None:
            df["Date"] = df["Date"].dt.tz_localize(None)

    expected_cols = ["Date", "Close", "High", "Low", "Open", "Volume"]
    df = df[[c for c in expected_cols if c in df.columns]].drop_duplicates(subset="Date")
    # Yahoo pads some histories with all-NaN rows (pre-listing dates, or
    # ranges it has since backfilled); they carry no data and would mask
    # real coverage, so they must never reach storage
    df = df.dropna(subset=[c for c in df.columns if c != "Date"])
    # Keep only fully-closed candles
    return df[df["Date"].dt.date <= last_complete]


def _yf_download_locked(symbol, start_date, last_complete):
    return yf.download(
        symbol,
        start=pd.Timestamp(start_date).strftime("%Y-%m-%d"),
        # yfinance's `end` is exclusive: +1 day so the bar dated
        # `last_complete` itself is included.
        end=(pd.Timestamp(last_complete) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
        progress=False,
        auto_adjust=True,
        threads=False,
    )


# Longest run of days a stock can legitimately not trade (a holiday attached
# to a weekend); anything longer means the stored history has a hole.
MAX_STOCK_GAP_DAYS = 5

# CoinGecko ids that rank in the top of the market-cap list but aren't
# tradeable directional assets (stablecoins, wrapped/staked duplicates).
EXCLUDED_COINGECKO_IDS = {
    "tether", "usd-coin", "dai", "ethena-usde", "usds", "first-digital-usd",
    "paypal-usd", "true-usd", "frax", "usdd", "binance-usd",
    "wrapped-bitcoin", "coinbase-wrapped-btc", "wrapped-steth", "weth",
    "wrapped-eeth", "staked-ether", "wrapped-beacon-eth", "rocket-pool-eth",
    "kelp-dao-restaked-eth", "solv-btc", "lombard-staked-btc",
    "binance-staked-sol",
}


def _has_history_gaps(dates, category):
    """True if the stored daily history has missing days in the middle.

    Crypto trades every calendar day, so any 2+ day step is a hole. Stocks
    skip weekends/holidays, so only steps longer than a holiday weekend count.
    """
    d = pd.to_datetime(dates).dt.normalize().drop_duplicates().sort_values()
    if len(d) < 2:
        return False
    gap_limit = 1 if category == "crypto" else MAX_STOCK_GAP_DAYS
    return bool((d.diff().dt.days.iloc[1:] > gap_limit).any())


def _wiki_to_yahoo(sym):
    """Wikipedia constituent symbols use dots (BRK.B); Yahoo uses dashes."""
    return str(sym).strip().upper().replace(".", "-")


def _fetch_sp500_symbols():
    """Return (sorted symbol list, {yahoo_symbol: gics_sector}) from Wikipedia."""
    resp = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resp.raise_for_status()
    table = pd.read_html(io.StringIO(resp.text))[0]
    syms = sorted({_wiki_to_yahoo(s) for s in table["Symbol"].astype(str)})
    sector_map = {}
    if "GICS Sector" in table.columns:
        for _, row in table.iterrows():
            sym = _wiki_to_yahoo(str(row["Symbol"]))
            sector = str(row["GICS Sector"]).strip()
            if sector and sector.lower() != "nan":
                sector_map[sym] = sector
    return syms, sector_map


def _coingecko_to_yahoo(markets, top_n):
    """Map CoinGecko market rows to Yahoo tickers, skipping non-directional
    assets (stablecoins, wrapped/staked duplicates)."""
    out = []
    for coin in markets:
        cid = str(coin.get("id", ""))
        csym = str(coin.get("symbol", ""))
        if not cid or not csym:
            continue
        if cid in EXCLUDED_COINGECKO_IDS:
            continue
        if "usd" in csym.lower():
            continue
        if cid.startswith(("wrapped-", "staked-", "bridged-")):
            continue
        out.append(f"{csym.upper()}-USD")
        if len(out) >= top_n:
            break
    return out


def _fetch_top_cryptos(top_n):
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return _coingecko_to_yahoo(resp.json(), top_n)


def update_symbol_universe():
    """Refresh the auto-updated symbol caches, then re-resolve the lists.

    Any fetch failure keeps the previous cache, so a flaky source can never
    empty the universe mid-run. New symbols backfill their full history on
    the next processing pass; removed ones simply stop being fetched and the
    active-symbol filter drops them from the alerts.
    """
    os.makedirs(_universe_file(""), exist_ok=True)

    if config.get("auto_update_stocks") == "sp500":
        try:
            syms, sector_map = _fetch_sp500_symbols()
            # Sanity floor: never clobber the cache with a bad scrape
            if len(syms) > 400:
                with open(_universe_file("sp500.json"), "w") as f:
                    json.dump(syms, f)
                if sector_map:
                    sectors_mod.save_sector_map(sector_map)
                print(f"S&P 500 universe updated: {len(syms)} symbols, {len(sector_map)} sector mappings")
            else:
                print(f"S&P 500 scrape returned only {len(syms)} symbols; keeping previous list")
        except Exception as e:
            print(f"S&P 500 update failed (keeping previous list): {e}")

    top_n = config.get("auto_update_cryptos")
    if top_n:
        try:
            syms = _fetch_top_cryptos(int(top_n))
            if syms:
                with open(_universe_file("top_cryptos.json"), "w") as f:
                    json.dump(syms, f)
                print(f"Top-crypto universe updated: {len(syms)} symbols")
        except Exception as e:
            print(f"Crypto universe update failed (keeping previous list): {e}")

    _load_universe()


def verify_history():
    """Audit stored OHLCV coverage; print only problem symbols, then totals."""
    issues = 0
    # One lake scan per category: 512 per-symbol loads (~2 DuckDB connections
    # each) take minutes on a Pi, the two glob scans take seconds
    lake_by_cat = {
        cat: db.scan_ohlcv_lake(cat) for cat in ("crypto", "stocks")
    }
    frames_by_cat = {
        cat: (dict(tuple(lake.groupby("symbol"))) if not lake.empty else {})
        for cat, lake in lake_by_cat.items()
    }
    pairs = [(s, "crypto") for s in symbols] + [(s, "stocks") for s in stock_symbols]
    for sym, cat in pairs:
        df = frames_by_cat[cat].get(sym)
        if df is None or df.empty:
            print(f"MISSING {cat:6} {sym}: no data stored")
            issues += 1
            continue
        df = df.sort_values("Date")
        problems = []
        if _has_history_gaps(df["Date"], cat):
            problems.append("gaps in history")
        value_cols = [c for c in db.OHLCV_COLUMNS if c != "Date" and c in df.columns]
        nan_rows = int(df[value_cols].isna().any(axis=1).sum())
        if nan_rows:
            problems.append(f"{nan_rows} NaN rows")
        last_complete = pd.Timestamp(_last_complete_daily_date(cat))
        stale_allowance = 0 if cat == "crypto" else 3  # stocks: weekend + holiday
        if (last_complete - df["Date"].max()).days > stale_allowance:
            problems.append(f"stale (last bar {df['Date'].max().date()})")
        if problems:
            print(
                f"PROBLEM {cat:6} {sym}: {', '.join(problems)} "
                f"[{df['Date'].min().date()} → {df['Date'].max().date()}, {len(df)} bars]"
            )
            issues += 1

    # Cross-contamination: two distinct assets never share identical closes on
    # 5 consecutive days, so matching fingerprints mean one symbol's download
    # was stored under another's name (the yfinance race behind _YF_LOCK).
    for cat, lake in lake_by_cat.items():
        if lake.empty:
            continue
        tails = lake.sort_values("Date").groupby("symbol").tail(5)
        fingerprints = tails.groupby("symbol")["Close"].agg(tuple)
        dupes = fingerprints[fingerprints.duplicated(keep=False)]
        for _, grp in dupes.groupby(dupes):
            syms = sorted(grp.index)
            print(f"CONTAMINATED {cat:6}: identical recent closes across {syms}")
            issues += 1

    print(f"Checked {len(pairs)} symbols: {issues} with issues")
    return issues


def _add_rsi_divergence(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Add rsi_bullish_div and rsi_bearish_div boolean columns (vectorized).

    Bearish: close near 20-period high but RSI below its recent high (momentum fading).
    Bullish: close near 20-period low but RSI above its recent low (momentum recovering).
    Both compare the current bar to rolling stats over the prior `window` bars.
    """
    if "rsi" not in df.columns or len(df) < window + 1:
        df["rsi_bullish_div"] = False
        df["rsi_bearish_div"] = False
        return df

    prior_max_close = df["Close"].shift(1).rolling(window).max()
    prior_min_close = df["Close"].shift(1).rolling(window).min()
    prior_max_rsi = df["rsi"].shift(1).rolling(window).max()
    prior_min_rsi = df["rsi"].shift(1).rolling(window).min()

    valid_bear = prior_max_close.notna() & prior_max_rsi.notna()
    valid_bull = prior_min_close.notna() & prior_min_rsi.notna()

    df["rsi_bearish_div"] = (
        valid_bear
        & (df["Close"] >= prior_max_close * 0.97)
        & (df["rsi"] < prior_max_rsi - 5)
    ).fillna(False)

    df["rsi_bullish_div"] = (
        valid_bull
        & (df["Close"] <= prior_min_close * 1.03)
        & (df["rsi"] > prior_min_rsi + 5)
    ).fillna(False)

    return df


def _label_signal(row):
    """Map one indicator row to a signal tier. Buys only in a bear regime,
    sells only in a bull regime (mean-reversion tiers)."""
    rsi, mfi, stoch_rsi = row['rsi'], row['mfi'], row['stoch_rsi']
    is_bull = row["is_bull"]

    # Warm-up rows: regime/indicators undefined, never signal
    if pd.isna(row["ma_200"]) or pd.isna(rsi) or pd.isna(mfi) or pd.isna(stoch_rsi):
        return 'Hold'

    if not is_bull:
        if rsi < 20 and mfi < 10 and stoch_rsi < 0.1:
            return 'Excellent Buy'
        elif rsi < 30 and mfi < 20 and stoch_rsi < 0.2:
            return 'Great Buy'
        elif rsi < 40 and mfi < 30 and stoch_rsi < 0.3:
            return 'Good Buy'
    if is_bull:
        if rsi > 80 and mfi > 90 and stoch_rsi > 0.9:
            return 'Excellent Sell'
        elif rsi > 70 and mfi > 80 and stoch_rsi > 0.8:
            return 'Great Sell'
        elif rsi > 60 and mfi > 70 and stoch_rsi > 0.7:
            return 'Good Sell'
    return 'Hold'


def _process_single_symbol(symbol, category, timeframes):
    """
    Process a single symbol: Download/update 1d OHLCV, then compute signals for all timeframes.
    Return True if successful, False otherwise.
    """
    try:
        db.init_db()

        # 1. Manage 1D OHLCV (Download/Update from DB)
        last_complete = _last_complete_daily_date(category)
        latest_date = db.get_latest_ohlcv_date(symbol, category)
        is_new_data = False

        if latest_date is None:
            print(f"Fetching new data for {symbol}...")
            df_new = _fetch_daily(symbol, HISTORY_START, last_complete)
            if df_new.empty:
                print(f"Failed to fetch {symbol}: no data")
                return False
            db.replace_ohlcv(df_new, symbol, category)
            is_new_data = True
        elif latest_date.date() < last_complete:
            print(f"Updating {symbol}...")
            # Re-download from the last stored bar (1-bar overlap): if its
            # adjusted Close moved, a split/dividend re-adjusted the whole
            # history and an incremental append would splice two different
            # adjustment bases together.
            df_new = _fetch_daily(symbol, latest_date, last_complete)
            if not df_new.empty:
                stored = db.load_ohlcv(symbol, category)
                stored_close = float(stored["Close"].iloc[-1])
                overlap = df_new[df_new["Date"].dt.date == latest_date.date()]
                readjusted = (
                    not overlap.empty
                    and stored_close > 0
                    and abs(float(overlap["Close"].iloc[0]) / stored_close - 1) > ADJUSTMENT_TOLERANCE
                )
                if readjusted:
                    print(f"{symbol}: adjusted history changed, refreshing full history...")
                    df_full = _fetch_daily(symbol, HISTORY_START, last_complete)
                    if not df_full.empty:
                        db.replace_ohlcv(df_full, symbol, category)
                        is_new_data = True
                else:
                    is_new_data = bool((df_new["Date"].dt.date > latest_date.date()).any())
                    # Upsert includes the overlap row, refreshing any volume revision
                    db.upsert_ohlcv(df_new, symbol, category)
        # else: every completed bar is already stored

        df_1d = db.load_ohlcv(symbol, category)
        if df_1d is None or df_1d.empty:
            return False

        # Heal holes left by crashed runs or transient Yahoo outages: one full
        # re-download, kept only if it actually recovers more bars (a symbol
        # with a genuine trading halt would otherwise re-download every night).
        if _has_history_gaps(df_1d["Date"], category):
            df_full = _fetch_daily(symbol, HISTORY_START, last_complete)
            if len(df_full) > len(df_1d):
                print(f"{symbol}: healed history gaps ({len(df_1d)} → {len(df_full)} bars)")
                db.replace_ohlcv(df_full, symbol, category)
                is_new_data = True
                df_1d = db.load_ohlcv(symbol, category)

        # 2. Prepare 1D DataFrame
        cols_to_numeric = ["Close", "High", "Low", "Open", "Volume"]
        for col in cols_to_numeric:
            if col in df_1d.columns:
                df_1d[col] = pd.to_numeric(df_1d[col], errors="coerce")

        df_1d.dropna(subset=["Close", "High", "Low", "Open", "Volume"], inplace=True)
        df_1d["Date"] = pd.to_datetime(df_1d["Date"]).dt.normalize()
        df_1d = df_1d.drop_duplicates(subset=["Date"], keep="last")
        df_1d = df_1d.set_index("Date").sort_index()
        if not df_1d.index.is_unique:
            df_1d = df_1d[~df_1d.index.duplicated(keep='last')]

        # 3. Process All Timeframes
        complete_through = pd.Timestamp(last_complete)

        for tf_name, tf_alias in timeframes.items():
            if tf_name == "1d":
                df_tf = df_1d.copy()
            else:
                agg_dict = {
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }
                if tf_name == "2wk":
                    # Fixed-anchor fortnights (pairs of Mon–Sun weeks). A plain
                    # 2W-SUN resample phases its bins off each symbol's first
                    # data date, so different symbols land on alternating
                    # Sundays and can't be summarized on a common date.
                    df_tf = df_1d.resample(tf_alias, origin=TWO_WEEK_ORIGIN).agg(agg_dict).dropna()
                    df_tf.index = df_tf.index + pd.Timedelta(days=13)  # label by ending Sunday
                elif tf_name in ("2d", "3d"):
                    # Fixed origin so bins don't shift if the history start changes
                    df_tf = df_1d.resample(tf_alias, origin=pd.Timestamp(0)).agg(agg_dict).dropna()
                else:
                    df_tf = df_1d.resample(tf_alias).agg(agg_dict).dropna()

                # Drop the trailing bar unless its period has fully elapsed
                if not df_tf.empty:
                    last_idx = df_tf.index[-1]
                    if tf_name == "2d":
                        bin_end = last_idx + pd.Timedelta(days=1)
                    elif tf_name == "3d":
                        bin_end = last_idx + pd.Timedelta(days=2)
                    else:  # 1wk / 2wk are labeled by their ending Sunday
                        bin_end = last_idx
                    if bin_end > complete_through:
                        df_tf = df_tf.iloc[:-1]

            if df_tf.empty:
                continue

            # Skip only when stored signals already cover exactly the latest
            # completed bar (an existence check would serve stale signals after
            # a crash between the OHLCV and signal writes).
            if not is_new_data:
                _, sig_max = db.get_signals_date_range(symbol, category, tf_name)
                if sig_max is not None and pd.Timestamp(sig_max) == df_tf.index[-1]:
                    continue

            # Indicators
            df_tf["rsi"] = ta.momentum.RSIIndicator(df_tf["Close"]).rsi()
            df_tf["mfi"] = ta.volume.MFIIndicator(df_tf["High"], df_tf["Low"], df_tf["Close"], df_tf["Volume"]).money_flow_index()
            stoch_rsi_ind = ta.momentum.StochRSIIndicator(close=df_tf["Close"], window=14, smooth1=3, smooth2=3)
            df_tf["stoch_rsi"] = stoch_rsi_ind.stochrsi()
            df_tf["stoch_rsi_k"] = stoch_rsi_ind.stochrsi_k()
            df_tf["stoch_rsi_d"] = stoch_rsi_ind.stochrsi_d()

            bb_ind = ta.volatility.BollingerBands(close=df_tf["Close"], window=20, window_dev=2)
            df_tf["bb_upper"] = bb_ind.bollinger_hband()
            df_tf["bb_lower"] = bb_ind.bollinger_lband()
            df_tf["bb_pband"] = bb_ind.bollinger_pband()

            macd_ind = ta.trend.MACD(close=df_tf["Close"], window_slow=26, window_fast=12, window_sign=9)
            df_tf["macd"] = macd_ind.macd()
            df_tf["macd_signal"] = macd_ind.macd_signal()
            df_tf["macd_hist"] = macd_ind.macd_diff()

            df_tf["ma_50"] = df_tf["Close"].rolling(window=50).mean()
            df_tf["ma_200"] = df_tf["Close"].rolling(window=200).mean()
            df_tf["is_bull"] = df_tf["ma_50"] > df_tf["ma_200"]

            # Extra event/volatility columns. Stored for measurement (backtest,
            # dashboard, digest) but deliberately NOT folded into _label_signal
            # until a backtest shows they earn their place.
            atr_ind = ta.volatility.AverageTrueRange(
                df_tf["High"], df_tf["Low"], df_tf["Close"], window=14
            )
            df_tf["atr"] = atr_ind.average_true_range()
            df_tf["atr_pct"] = df_tf["atr"] / df_tf["Close"] * 100

            # Cross events need a valid MA on both sides of the flip, or the
            # first bar after MA warm-up would register a phantom cross
            ma_valid = df_tf["ma_200"].notna() & df_tf["ma_200"].shift(1).notna()
            df_tf["golden_cross"] = (
                df_tf["is_bull"] & ~df_tf["is_bull"].shift(1, fill_value=False) & ma_valid
            )
            df_tf["death_cross"] = (
                ~df_tf["is_bull"] & df_tf["is_bull"].shift(1, fill_value=True) & ma_valid
            )

            df_tf["vol_spike"] = df_tf["Volume"] > 2 * df_tf["Volume"].rolling(window=20).mean()

            df_tf = _add_rsi_divergence(df_tf)
            df_tf["signal"] = df_tf.apply(_label_signal, axis=1)

            df_tf = df_tf.reset_index()

            # Save signals to DB (replace: the full-history recompute is
            # authoritative, and merging would keep phantom rows if bin
            # boundaries or upstream data ever change)
            db.replace_signals(df_tf, symbol, category, tf_name)

            # Chart generation
            fig = Figure(figsize=(10, 6))
            ax = fig.add_subplot()
            ax.plot(df_tf["Date"], df_tf["Close"], color='black', label='Close Price')

            for tier, color in [("Excellent Buy", "darkgreen"), ("Great Buy", "green"), ("Good Buy", "lightgreen")]:
                subset = df_tf[df_tf["signal"] == tier]
                ax.scatter(subset["Date"], subset["Close"], color=color, label=tier, marker='o', s=80)

            for tier, color in [("Excellent Sell", "navy"), ("Great Sell", "blue"), ("Good Sell", "skyblue")]:
                subset = df_tf[df_tf["signal"] == tier]
                ax.scatter(subset["Date"], subset["Close"], color=color, label=tier, marker='o', s=80)

            ax.plot(df_tf["Date"], df_tf["ma_50"], linestyle='--', label='50-MA')
            ax.plot(df_tf["Date"], df_tf["ma_200"], linestyle='--', label='200-MA')

            ax.set_axisbelow(True)
            ax.grid(True, which='both', linestyle=':', linewidth=0.6, alpha=0.6)

            max_close = float(df_tf["Close"].max())
            if max_close < 1:
                dollar_fmt = mticker.StrMethodFormatter('${x:,.4f}')
            elif max_close < 100:
                dollar_fmt = mticker.StrMethodFormatter('${x:,.2f}')
            else:
                dollar_fmt = mticker.StrMethodFormatter('${x:,.0f}')
            ax.yaxis.set_major_formatter(dollar_fmt)
            ax2 = ax.secondary_yaxis('right', functions=(lambda y: y, lambda y: y))
            ax2.yaxis.set_major_formatter(dollar_fmt)
            ax2.set_ylabel("Price (USD)")

            ax.set_title(f"{symbol} ({tf_name}) Buy/Sell Signals")
            ax.set_xlabel("Date")
            ax.set_ylabel("Price (USD)")
            ax.legend()
            fig.tight_layout()

            # Save chart to eink_output or similar directory
            chart_dir = os.path.join("eink_output", category, tf_name)
            os.makedirs(chart_dir, exist_ok=True)
            fig.savefig(os.path.join(chart_dir, f"{symbol}_signals_chart.png"), dpi=150, bbox_inches="tight")

        return True

    except Exception as e:
        print(f"Critical error processing {symbol}: {e}")
        traceback.print_exc()
        return False


def _process_asset_list(asset_symbols, category):
    timeframes = {
        # Hour-based tick frequencies: pandas only honors a fixed `origin` for
        # tick-like freqs, and without one the 2d/3d/2wk bins would phase off
        # each symbol's first data date (the index is daily midnights, so
        # 48h/72h/336h are exactly 2/3/14 days).
        "1d": None,
        "2d": "48h",
        "3d": "72h",
        "1wk": "W-SUN",
        "2wk": "336h",  # fixed-anchor fortnights; see TWO_WEEK_ORIGIN
    }

    db.init_db()
    print(f"Processing {len(asset_symbols)} items for {category} with {MAX_WORKERS} threads...")

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_process_single_symbol, symbol, category, timeframes): symbol for symbol in asset_symbols}

        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"Exception for {symbol}: {e}")

    print(f"Completed {category} processing.")


def process_crypto_data():
    _process_asset_list(symbols, "crypto")


def process_stock_data():
    _process_asset_list(stock_symbols, "stocks")


def _active_symbols(subset_symbols, category):
    """Symbols whose latest stored bar is recent enough to still be trading.

    A delisted/halted ticker keeps its old data forever; without this filter a
    single dead symbol would drag every summary back to its last trade date."""
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=ACTIVE_MAX_AGE_DAYS)
    latest = db.latest_ohlcv_dates(category)
    return [s for s in subset_symbols if s in latest and latest[s] >= cutoff]


def _normalize_target_date(target_date):
    if isinstance(target_date, str):
        return pd.to_datetime(target_date).normalize()
    if isinstance(target_date, pd.Timestamp):
        return target_date.normalize()
    return pd.Timestamp(target_date).normalize()


def _scan_signals_normalized(category, timeframe):
    """One bulk scan of a category/timeframe's signals with normalized Dates.

    Per-symbol load_signals calls (2 DuckDB connections each) add up to ~10
    minutes across the S&P 500 on a Pi; one glob scan takes seconds."""
    df = db.scan_signals_lake(category, timeframe, columns=["Date", "signal"])
    if df.empty:
        return df
    df["Date"] = df["Date"].dt.normalize()
    return df


def _tier_lists(day_df, ordered_symbols):
    """Split one day's signal rows into buy/sell tier lists, preserving the
    universe's symbol order (matches the old per-symbol loop output)."""
    buy_tiers = {"Excellent": [], "Great": [], "Good": []}
    sell_tiers = {"Excellent": [], "Great": [], "Good": []}
    for tier in ["Excellent", "Great", "Good"]:
        buys = set(day_df.loc[day_df["signal"] == f"{tier} Buy", "symbol"])
        sells = set(day_df.loc[day_df["signal"] == f"{tier} Sell", "symbol"])
        buy_tiers[tier] = [s for s in ordered_symbols if s in buys]
        sell_tiers[tier] = [s for s in ordered_symbols if s in sells]
    return buy_tiers, sell_tiers


def generate_signals_summary(target_date=None):
    summary_output = ""
    buy_summary = ""
    sell_summary = ""

    active_by_cat = {
        "crypto": _active_symbols(symbols, "crypto"),
        "stocks": _active_symbols(stock_symbols, "stocks"),
    }
    sigs_by_cat = {cat: _scan_signals_normalized(cat, "1d") for cat in active_by_cat}

    # Latest signal date per category (max over active symbols, not min: one
    # lagging symbol must not pull every alert back to an old date). Kept per
    # category because crypto trades weekends when stocks don't.
    cat_lads = {}
    for cat, active in active_by_cat.items():
        if not active:
            continue
        if target_date is not None:
            cat_lads[cat] = _normalize_target_date(target_date)
            continue
        sigs = sigs_by_cat[cat]
        if sigs.empty:
            continue
        sub = sigs[sigs["symbol"].isin(active)]
        if not sub.empty:
            cat_lads[cat] = sub["Date"].max()

    if not cat_lads:
        summary_output += "No signal data found.\n"
        print(summary_output)
        return summary_output, buy_summary, sell_summary

    lad_str = str(max(cat_lads.values()).date())

    buy_tiers = {"Excellent": [], "Great": [], "Good": []}
    sell_tiers = {"Excellent": [], "Great": [], "Good": []}
    for cat, active in active_by_cat.items():
        if cat not in cat_lads:
            continue
        sigs = sigs_by_cat[cat]
        if sigs.empty:
            continue
        day = sigs[(sigs["Date"] == cat_lads[cat]) & sigs["symbol"].isin(active)]
        cat_buys, cat_sells = _tier_lists(day, active)
        for tier in ["Excellent", "Great", "Good"]:
            buy_tiers[tier] += cat_buys[tier]
            sell_tiers[tier] += cat_sells[tier]

    summary_output += "\n"
    if not any(buy_tiers.values()) and not any(sell_tiers.values()):
        sell_summary += f'No Sell signals\n{lad_str}\n'
        buy_summary += f'No Buy signals\n{lad_str}\n'
        summary_output += 'No Buy or Sell signals\n'
    else:
        if any(sell_tiers.values()):
            sell_summary += "Sell on the One Day:\n"
            for tier in ["Good", "Great", "Excellent"]:
                if sell_tiers[tier]:
                    sell_summary += f'{tier}:\n'
                    for sym in sell_tiers[tier]:
                        sell_summary += f'  {sym}\n'
                    sell_summary += "\n"
        if any(buy_tiers.values()):
            buy_summary += "Buy on the One Day:\n"
            for tier in ["Good", "Great", "Excellent"]:
                if buy_tiers[tier]:
                    buy_summary += f"{tier}:\n"
                    for sym in buy_tiers[tier]:
                        buy_summary += f"  {sym}\n"
                    buy_summary += "\n"
        summary_output += sell_summary + buy_summary

    now_utc = pd.Timestamp.now("UTC")
    summary_output += now_utc.strftime("%H:%M:%S • %m-%d-%Y UTC\n")
    print(summary_output)
    return summary_output, buy_summary, sell_summary


def generate_signals_summary_separate(target_date=None):
    """
    Returns separate summaries for crypto and stocks, plus a combined summary.
    Output format:
      {
        "crypto": (summary_output, buy_summary, sell_summary),
        "stocks": (summary_output, buy_summary, sell_summary),
        "combined": (summary_output, buy_summary, sell_summary)
      }
    """
    timeframes = ["1d", "2d", "3d", "1wk", "2wk"]

    # One scan per (category, timeframe), shared across the three summaries
    scan_cache = {}

    def _sigs(category, tf):
        if (category, tf) not in scan_cache:
            scan_cache[(category, tf)] = _scan_signals_normalized(category, tf)
        return scan_cache[(category, tf)]

    active_cache = {}

    def _active(subset_symbols, category):
        key = (tuple(subset_symbols), category)
        if key not in active_cache:
            active_cache[key] = _active_symbols(subset_symbols, category)
        return active_cache[key]

    def _resolve_lad(subset_symbols, category, tf):
        if target_date is not None:
            return _normalize_target_date(target_date)
        # Max over active symbols: one lagging symbol must not pull the
        # whole category's alert back to an old date
        sigs = _sigs(category, tf)
        if sigs.empty:
            return None
        sub = sigs[sigs["symbol"].isin(subset_symbols)]
        return None if sub.empty else sub["Date"].max()

    def _summarize_symbols(subset_symbols, category):
        summary_output = ""
        buy_summary = ""
        sell_summary = ""

        subset_symbols = _active(subset_symbols, category)

        for tf in timeframes:
            lad = _resolve_lad(subset_symbols, category, tf)
            sigs = _sigs(category, tf)
            if lad is None or sigs.empty:
                continue

            day = sigs[(sigs["Date"] == lad) & sigs["symbol"].isin(subset_symbols)]
            buy_tiers, sell_tiers = _tier_lists(day, subset_symbols)

            if not any(buy_tiers.values()) and not any(sell_tiers.values()):
                pass
            else:
                if any(sell_tiers.values()):
                    sell_summary += f"Sell on the {tf} ({lad.date()}):\n"
                    for tier in ["Good", "Great", "Excellent"]:
                        if sell_tiers[tier]:
                            sell_summary += f'{tier}:\n'
                            for sym in sell_tiers[tier]:
                                sell_summary += f'  {sym}\n'
                            sell_summary += "\n"
                if any(buy_tiers.values()):
                    buy_summary += f"Buy on the {tf} ({lad.date()}):\n"
                    for tier in ["Good", "Great", "Excellent"]:
                        if buy_tiers[tier]:
                            buy_summary += f"{tier}:\n"
                            for sym in buy_tiers[tier]:
                                buy_summary += f"  {sym}\n"
                            buy_summary += "\n"

        if not buy_summary and not sell_summary:
            summary_output += "No signals found across any timeframe.\n"
        else:
            summary_output += sell_summary + buy_summary

        now_utc = pd.Timestamp.now("UTC")
        summary_output += now_utc.strftime("%H:%M:%S • %m-%d-%Y UTC\n")
        return summary_output, buy_summary, sell_summary

    def _summarize_combined(crypto_syms, stock_syms):
        summary_output = ""
        buy_summary = ""
        sell_summary = ""

        groups = [
            (_active(crypto_syms, "crypto"), "crypto"),
            (_active(stock_syms, "stocks"), "stocks"),
        ]

        for tf in timeframes:
            buy_tiers = {"Excellent": [], "Great": [], "Good": []}
            sell_tiers = {"Excellent": [], "Great": [], "Good": []}

            # Resolve the date per category: crypto trades weekends when
            # stocks don't, so a single shared date would silently drop one
            # category's signals whenever their latest bars differ.
            cat_lads = {cat: _resolve_lad(syms, cat, tf) for syms, cat in groups}
            resolved = [d for d in cat_lads.values() if d is not None]
            if not resolved:
                continue
            header_lad = max(resolved)

            for syms, cat in groups:
                lad = cat_lads[cat]
                sigs = _sigs(cat, tf)
                if lad is None or sigs.empty:
                    continue
                day = sigs[(sigs["Date"] == lad) & sigs["symbol"].isin(syms)]
                cat_buys, cat_sells = _tier_lists(day, syms)
                for tier in ["Excellent", "Great", "Good"]:
                    buy_tiers[tier] += cat_buys[tier]
                    sell_tiers[tier] += cat_sells[tier]

            if not any(buy_tiers.values()) and not any(sell_tiers.values()):
                pass
            else:
                if any(sell_tiers.values()):
                    sell_summary += f"Sell on the {tf} ({header_lad.date()}):\n"
                    for tier in ["Good", "Great", "Excellent"]:
                        if sell_tiers[tier]:
                            sell_summary += f'{tier}:\n'
                            for sym in sell_tiers[tier]:
                                sell_summary += f'  {sym}\n'
                            sell_summary += "\n"
                if any(buy_tiers.values()):
                    buy_summary += f"Buy on the {tf} ({header_lad.date()}):\n"
                    for tier in ["Good", "Great", "Excellent"]:
                        if buy_tiers[tier]:
                            buy_summary += f"{tier}:\n"
                            for sym in buy_tiers[tier]:
                                buy_summary += f"  {sym}\n"
                            buy_summary += "\n"

        if not buy_summary and not sell_summary:
            summary_output += "No signals found across any timeframe.\n"
        else:
            summary_output += sell_summary + buy_summary

        now_utc = pd.Timestamp.now("UTC")
        summary_output += now_utc.strftime("%H:%M:%S • %m-%d-%Y UTC\n")
        return summary_output, buy_summary, sell_summary

    crypto_summary = _summarize_symbols(symbols, "crypto")
    stock_summary = _summarize_symbols(stock_symbols, "stocks")
    combined_summary = _summarize_combined(symbols, stock_symbols)

    return {
        "crypto": crypto_summary,
        "stocks": stock_summary,
        "combined": combined_summary,
    }


def fetch_and_store_market_context():
    """Pull CoinGecko global data + SPY/QQQ/DIA closes and store to
    data/market/context.json for the dashboard to read without network calls."""
    ctx: dict = {}

    # CoinGecko /global: dominance, total market cap, 24h change
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=30)
        resp.raise_for_status()
        gdata = resp.json()["data"]
        dom = gdata.get("market_cap_percentage", {})
        ctx["btc_dominance"] = float(dom.get("btc", 0))
        ctx["eth_dominance"] = float(dom.get("eth", 0))
        ctx["total_market_cap_usd"] = float(gdata["total_market_cap"]["usd"])
        ctx["market_cap_change_24h_pct"] = float(gdata["market_cap_change_percentage_24h_usd"])
        ctx["active_cryptos"] = int(gdata.get("active_cryptocurrencies", 0))
        print(f"Market context: BTC dom {ctx['btc_dominance']:.1f}%, "
              f"TMC ${ctx['total_market_cap_usd']/1e12:.2f}T")
    except Exception as e:
        print(f"Market context: CoinGecko global failed: {e}")

    # Fear & Greed
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=30)
        resp.raise_for_status()
        d = resp.json()["data"][0]
        ctx["fear_greed_value"] = int(d["value"])
        ctx["fear_greed_label"] = str(d["value_classification"])
    except Exception as e:
        print(f"Market context: Fear & Greed failed: {e}")

    # US equity index ETFs via yfinance (65 days covers 1m + buffer)
    for ticker, key in [("SPY", "spy"), ("QQQ", "qqq"), ("DIA", "dia")]:
        try:
            with _YF_LOCK:
                raw = yf.download(
                    ticker, period="65d", interval="1d",
                    progress=False, auto_adjust=True, threads=False,
                )
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw = raw.reset_index()
            date_col = "Date" if "Date" in raw.columns else raw.columns[0]
            raw = raw.rename(columns={date_col: "Date"})
            closes = raw["Close"].dropna()
            if len(closes) < 2:
                continue
            ctx[f"{key}_last"] = float(closes.iloc[-1])
            ctx[f"{key}_ret_1d"] = float(closes.iloc[-1] / closes.iloc[-2] - 1)
            if len(closes) >= 22:
                ctx[f"{key}_ret_1m"] = float(closes.iloc[-1] / closes.iloc[-22] - 1)
        except Exception as e:
            print(f"Market context: {ticker} failed: {e}")

    ctx["as_of"] = pd.Timestamp.now().isoformat()
    path = db.table_path("market", "context.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(ctx, f)
    return ctx


def get_current_prices_string(vs_currency="usd"):
    symbols_cg = [entry["id"] for entry in config["crypto_prices"]]
    id_to_symbol = {entry["id"]: entry["symbol"] for entry in config["crypto_prices"]}

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(symbols_cg)}&vs_currencies={vs_currency}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        prices = response.json()
    except Exception as e:
        print(f"Error fetching CoinGecko prices: {e}")
        prices = {}

    result = ""
    for symbol in symbols_cg:
        price = prices.get(symbol, {}).get(vs_currency)
        if price is None:
            result += f"{id_to_symbol[symbol]}: N/A\n"
        elif price >= 1:
            result += f"{id_to_symbol[symbol]}: ${price:,.2f}\n"
        else:
            result += f"{id_to_symbol[symbol]}: ${price:,.5f}\n"

    result += get_btc_dominance()
    result += get_fear_greed()
    result += breadth_mod.latest_breadth_line("crypto")

    now_utc = pd.Timestamp.now("UTC")
    result += now_utc.strftime("%H:%M:%S • %m-%d-%Y UTC\n")
    return result


def get_fear_greed():
    """Crypto Fear & Greed index (alternative.me), e.g. 'Fear & Greed: 34 (Fear)'."""
    try:
        response = requests.get("https://api.alternative.me/fng/", timeout=30)
        response.raise_for_status()
        d = response.json()["data"][0]
        return f"Fear & Greed: {d['value']} ({d['value_classification']})\n"
    except Exception as e:
        print(f"Error fetching Fear & Greed index: {e}")
        return ""


def get_btc_dominance():
    url = "https://api.coingecko.com/api/v3/global"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        btc_dominance = response.json()["data"]["market_cap_percentage"]["btc"]
    except Exception as e:
        print(f"Error fetching BTC dominance: {e}")
        return "BTC Dominance: N/A\n"
    return f"BTC Dominance: {btc_dominance:.2f}%\n"


def get_total_marketcap():
    try:
        cg = CoinGeckoAPI()
        global_data = cg.get_global()
        total_market_cap = global_data['total_market_cap']['usd']
    except Exception as e:
        print(f"Error fetching total market cap: {e}")
        return "TMC: N/A\n"
    print(f"Total Market Cap: ${total_market_cap:,.0f}\n")
    return f"TMC: ${total_market_cap:,.0f}\n"


import platform

def is_raspberry_pi():
    return platform.system().lower() == "linux" and ("arm" in platform.machine() or "aarch64" in platform.machine())


if is_raspberry_pi():
    from display import display_single_image

def _count_signals(buy_summary_text: str, sell_summary_text: str):
    def _count_items(block: str) -> int:
        # Distinct tickers: the same symbol can appear on several timeframes
        return len({line.strip() for line in block.splitlines() if line.startswith("  ")})
    return _count_items(buy_summary_text), _count_items(sell_summary_text)

def _price_alert_state_path():
    return db.table_path("notify", "price_alert_state.json")


def check_price_alerts():
    """Notify when a symbol's latest close crosses a configured price threshold.

    Alerts in cryptos.yml:
        price_alerts:
          BTC-USD: 100000
          ETH-USD: 3000

    Fires once on each direction change (below→above and above→below).
    State is in data/notify/price_alert_state.json; delete to reset.
    """
    alerts = config.get("price_alerts") or {}
    if not alerts:
        return

    try:
        with open(_price_alert_state_path()) as f:
            import json as _json
            state = _json.load(f)
    except (OSError, ValueError):
        state = {}

    def _latest_close(symbol):
        for cat in ("crypto", "stocks"):
            df = db.load_ohlcv(symbol, cat)
            if not df.empty:
                return float(df["Close"].iloc[-1])
        return None

    dirty = False
    for symbol, threshold in alerts.items():
        threshold = float(threshold)
        current = _latest_close(symbol)
        if current is None:
            print(f"Price alert: no OHLCV data for {symbol}, skipping")
            continue

        current_side = "above" if current >= threshold else "below"
        sym_state = state.get(symbol, {})
        # Reset if the threshold was changed in config
        last_side = sym_state.get("side") if sym_state.get("threshold") == threshold else None

        if last_side != current_side:
            fmt = lambda v: f"${v:,.2f}" if v >= 1 else f"${v:,.5f}"
            direction = "above" if current_side == "above" else "below"
            msg = (
                f"{symbol} is now {direction} {fmt(threshold)}\n"
                f"Current price: {fmt(current)}"
            )
            notify.send_notification(f"Price Alert: {symbol}", msg, priority="high")
            state[symbol] = {"threshold": threshold, "side": current_side}
            dirty = True

    if dirty:
        import os as _os
        import json as _json
        _os.makedirs(_os.path.dirname(_price_alert_state_path()), exist_ok=True)
        with open(_price_alert_state_path(), "w") as f:
            _json.dump(state, f)


USAGE = """\
Commands:
  refresh          update universe + OHLCV + signals, then breadth, dashboard,
                   and push notifications (failure alerts on crash)
  verify           audit stored history (gaps, NaNs, staleness, contamination)
  backtest         recompute the signal scoreboard (forward returns/hit rates)
  breadth          record today's market breadth row
  dashboard        regenerate data/dashboard/index.html
  digest [post]    weekly signal digest (post = also toot/tweet it)
  tweet            render eink image and post the daily signal tweets
  (no command)     render eink image and show it on the display

Flags: --dry-run    print what would be posted instead of posting (tweet/digest)
"""

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv
    cmd = args[0] if args else None

    if cmd == "help" or cmd == "--help":
        print(USAGE)

    elif cmd == "refresh":
        try:
            update_symbol_universe()
            process_crypto_data()
            process_stock_data()
            breadth_mod.record_daily()
            momentum_mod.compute()          # before sectors so sectors get fresh 30d returns
            sectors_mod.compute_and_save()
            fetch_and_store_market_context()
            dashboard_mod.generate()
            _, buy_all, sell_all = generate_signals_summary_separate()["combined"]
            notify.notify_signals(buy_all, sell_all)
            check_price_alerts()
        except Exception:
            tb = traceback.format_exc()
            print(tb)
            notify.notify_failure("refresh", tb)
            sys.exit(1)

    elif cmd == "verify":
        sys.exit(1 if verify_history() else 0)

    elif cmd == "backtest":
        import backtest as backtest_mod
        _, _stats = backtest_mod.run_backtest()
        print(backtest_mod.format_report(_stats))

    elif cmd == "breadth":
        breadth_mod.record_daily()

    elif cmd == "dashboard":
        dashboard_mod.generate()

    elif cmd == "digest":
        import digest as digest_mod
        print(digest_mod.build_digest())
        if len(args) > 1 and args[1] == "post":
            digest_mod.post_digest(dry_run=dry_run)

    else:
        separated = generate_signals_summary_separate(target_date=None)
        crypto_combined, crypto_buy_summary, crypto_sell_summary = separated["crypto"]
        stock_combined, stock_buy_summary, stock_sell_summary = separated["stocks"]
        combined_all, buy_summary_str, sell_summary_str = separated["combined"]

        crypto_prices_str = get_total_marketcap()
        crypto_prices_str += get_current_prices_string()

        # Image: crypto-only (per your instruction)
        image_path = generate_crypto_signal_image(crypto_buy_summary, crypto_sell_summary, crypto_prices_str, config)

        if is_raspberry_pi() and "tweet" not in sys.argv:
            display_single_image(image_path)

        if cmd == "tweet":
            crypto_buy_count, crypto_sell_count = _count_signals(crypto_buy_summary, crypto_sell_summary)
            stock_buy_count, stock_sell_count = _count_signals(stock_buy_summary, stock_sell_summary)

            crypto_tweet = (
                f"Crypto: {crypto_buy_count} buys, {crypto_sell_count} sells\n"
                + "— Crypto —\n"
                + crypto_combined
                + "\n"
                + crypto_prices_str
            )
            stocks_tweet = (
                f"Stocks: {stock_buy_count} buys, {stock_sell_count} sells\n"
                + "— Stocks —\n"
                + stock_combined
                + breadth_mod.latest_breadth_line("stocks")
            )

            if dry_run:
                print("--dry-run: would tweet:\n")
                print(crypto_tweet)
                print("---")
                print(stocks_tweet)
            else:
                send_tweet(crypto_tweet)
                send_tweet(stocks_tweet)
