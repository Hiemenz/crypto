import pandas as pd
import matplotlib
matplotlib.use('Agg') # Thread-safe backend for saving images
import matplotlib.pyplot as plt
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
from pycoingecko import CoinGeckoAPI
import sys
import traceback

# Add parent directory to path so we can import db
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

global symbols
global stock_symbols
global config
# Load symbols from YAML
with open("crypto_signal_station/cryptos.yml", "r") as f:
    config = yaml.safe_load(f)
    # Crypto tickers (Yahoo Finance symbols, e.g., BTC-USD)
    symbols = config.get("cryptos", [])
    # Stock tickers (Yahoo Finance symbols, e.g., AAPL, MSFT)
    stock_symbols = config.get("stocks", [])


# Pi-Optimization: Limit concurrent downloads to save RAM
MAX_WORKERS = 1

def _process_single_symbol(symbol, category, timeframes):
    """
    Process a single symbol: Download/update 1d OHLCV, then compute signals for all timeframes.
    Return True if successful, False otherwise.
    """
    try:
        db.init_db()

        # 1. Manage 1D OHLCV (Download/Update from DB)
        latest_date = db.get_latest_ohlcv_date(symbol, category)
        df_1d = None
        is_new_data = False

        if latest_date is not None:
            today_date = pd.Timestamp.now().date()
            fetch_start = (latest_date + pd.Timedelta(days=1)).date()

            if fetch_start >= today_date:
                # Already up to date – load from DB
                df_1d = db.load_ohlcv(symbol, category)
            else:
                print(f"Updating {symbol}...")
                try:
                    df_new = yf.download(
                        symbol,
                        start=fetch_start.strftime("%Y-%m-%d"),
                        end=pd.Timestamp.today().strftime("%Y-%m-%d"),
                        interval="1d",
                        progress=False,
                        auto_adjust=True,
                        threads=False,
                    )
                except Exception as e:
                    print(f"Error downloading {symbol}: {e}")
                    df_new = pd.DataFrame()

                if not df_new.empty:
                    if isinstance(df_new.columns, pd.MultiIndex):
                        df_new.columns = df_new.columns.get_level_values(0)
                    df_new = df_new.loc[:, ~df_new.columns.duplicated()]
                    df_new = df_new.reset_index()
                    if "Date" in df_new.columns:
                        df_new["Date"] = pd.to_datetime(df_new["Date"]).dt.tz_localize(None)

                    expected_cols = ["Date", "Close", "High", "Low", "Open", "Volume"]
                    available_cols = [c for c in expected_cols if c in df_new.columns]
                    df_new = df_new[available_cols].drop_duplicates(subset="Date")

                    # Drop partial (today's) candle
                    if not df_new.empty:
                        if df_new["Date"].iloc[-1].date() >= today_date:
                            df_new = df_new.iloc[:-1]

                    if not df_new.empty:
                        db.upsert_ohlcv(df_new, symbol, category)
                        is_new_data = True

                df_1d = db.load_ohlcv(symbol, category)
        else:
            print(f"Fetching new data for {symbol}...")
            try:
                df = yf.download(symbol, start="2014-01-01", interval="1d", progress=False, auto_adjust=True, threads=False)
                df = df.iloc[:-1]  # Drop partial candle
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.loc[:, ~df.columns.duplicated()]
                if not df.empty:
                    df = df.reset_index()
                    if "Date" in df.columns:
                        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
                    db.upsert_ohlcv(df, symbol, category)
                    df_1d = db.load_ohlcv(symbol, category)
                    is_new_data = True
            except Exception as e:
                print(f"Failed to fetch {symbol}: {e}")
                return False

        if df_1d is None or df_1d.empty:
            return False

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
        for tf_name, tf_alias in timeframes.items():
            # Check if signals already exist and are current
            if not is_new_data:
                _, max_date = db.get_signals_date_range(symbol, category, tf_name)
                if max_date is not None:
                    # Signals exist and data hasn't changed – skip
                    continue

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
                df_tf = df_1d.resample(tf_alias).agg(agg_dict).dropna()

                if not df_tf.empty:
                    last_idx = df_tf.index[-1]
                    today = pd.Timestamp.now().normalize()

                    should_drop = False
                    if tf_name in ["1wk", "2wk"]:
                        if last_idx >= today:
                            should_drop = True
                    elif tf_name == "3d":
                        if last_idx + pd.Timedelta(days=3) > today:
                            should_drop = True
                    elif tf_name == "2d":
                        if last_idx + pd.Timedelta(days=2) > today:
                            should_drop = True

                    if should_drop:
                        df_tf = df_tf.iloc[:-1]

                    if df_tf.empty:
                        continue

            if df_tf.empty:
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

            # Label signals
            def label_signal(row):
                rsi, mfi, stoch_rsi = row['rsi'], row['mfi'], row['stoch_rsi']
                is_bull = row["is_bull"]

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

            df_tf["signal"] = df_tf.apply(label_signal, axis=1)

            df_tf = df_tf.reset_index()

            # Save signals to DB
            db.upsert_signals(df_tf, symbol, category, tf_name)

            # Chart generation
            fig, ax = plt.subplots(figsize=(10, 6))
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

            dollar_fmt = mticker.StrMethodFormatter('${x:,.0f}')
            ax.yaxis.set_major_formatter(dollar_fmt)
            ax2 = ax.secondary_yaxis('right', functions=(lambda y: y, lambda y: y))
            ax2.yaxis.set_major_formatter(dollar_fmt)
            ax2.set_ylabel("Price (USD)")

            ax.set_title(f"{symbol} ({tf_name}) Buy/Sell Signals")
            ax.set_xlabel("Date")
            ax.set_ylabel("Price (USD)")
            ax.legend()
            plt.tight_layout()

            # Save chart to eink_output or similar directory
            chart_dir = os.path.join("eink_output", category, tf_name)
            os.makedirs(chart_dir, exist_ok=True)
            plt.savefig(os.path.join(chart_dir, f"{symbol}_signals_chart.png"), dpi=150, bbox_inches="tight")
            plt.close()

        return True

    except Exception as e:
        print(f"Critical error processing {symbol}: {e}")
        traceback.print_exc()
        return False


def _process_asset_list(asset_symbols, category):
    timeframes = {
        "1d": None,
        "2d": "2D",
        "3d": "3D",
        "1wk": "W-SUN",
        "2wk": "2W-SUN",
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


def generate_signals_summary(target_date=None):
    buy_tiers = {"Excellent": [], "Great": [], "Good": []}
    sell_tiers = {"Excellent": [], "Great": [], "Good": []}
    summary_output = ""
    buy_summary = ""
    sell_summary = ""

    all_symbols_with_cat = [(s, "crypto") for s in symbols] + [(s, "stocks") for s in stock_symbols]

    if target_date is not None:
        if isinstance(target_date, str):
            target_date = pd.to_datetime(target_date).normalize()
        elif isinstance(target_date, pd.Timestamp):
            target_date = target_date.normalize()
        else:
            target_date = pd.Timestamp(target_date).normalize()
        latest_available_date = target_date
    else:
        latest_available_date = None
        for sym, cat in all_symbols_with_cat:
            _, max_date = db.get_signals_date_range(sym, cat, "1d")
            if max_date:
                d = pd.Timestamp(max_date).normalize()
                if latest_available_date is None or d < latest_available_date:
                    latest_available_date = d

    if latest_available_date is None:
        summary_output += "No signal data found.\n"
        print(summary_output)
        return summary_output, buy_summary, sell_summary

    lad_str = str(latest_available_date.date())

    for sym, cat in all_symbols_with_cat:
        df = db.load_signals(sym, cat, "1d")
        if df.empty:
            continue
        today_df = df[df["Date"].dt.normalize() == latest_available_date]
        for tier in ["Excellent", "Great", "Good"]:
            if not today_df[today_df["signal"] == f"{tier} Buy"].empty:
                buy_tiers[tier].append(sym)
            if not today_df[today_df["signal"] == f"{tier} Sell"].empty:
                sell_tiers[tier].append(sym)

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

    now_utc = pd.Timestamp.utcnow()
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

    def _resolve_lad(subset_symbols, category, tf):
        if target_date is not None:
            if isinstance(target_date, str):
                return pd.to_datetime(target_date).normalize()
            elif isinstance(target_date, pd.Timestamp):
                return target_date.normalize()
            else:
                return pd.Timestamp(target_date).normalize()
        lad = None
        for sym in subset_symbols:
            _, max_date = db.get_signals_date_range(sym, category, tf)
            if max_date:
                d = pd.Timestamp(max_date).normalize()
                if lad is None or d < lad:
                    lad = d
        return lad

    def _summarize_symbols(subset_symbols, category):
        summary_output = ""
        buy_summary = ""
        sell_summary = ""

        for tf in timeframes:
            buy_tiers = {"Excellent": [], "Great": [], "Good": []}
            sell_tiers = {"Excellent": [], "Great": [], "Good": []}

            lad = _resolve_lad(subset_symbols, category, tf)
            if lad is None:
                continue

            for sym in subset_symbols:
                df = db.load_signals(sym, category, tf)
                if df.empty:
                    continue
                today_df = df[df["Date"].dt.normalize() == lad]
                for tier in ["Excellent", "Great", "Good"]:
                    if not today_df[today_df["signal"] == f"{tier} Buy"].empty:
                        buy_tiers[tier].append(sym)
                    if not today_df[today_df["signal"] == f"{tier} Sell"].empty:
                        sell_tiers[tier].append(sym)

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

        now_utc = pd.Timestamp.utcnow()
        summary_output += now_utc.strftime("%H:%M:%S • %m-%d-%Y UTC\n")
        return summary_output, buy_summary, sell_summary

    def _summarize_combined(crypto_syms, stock_syms):
        summary_output = ""
        buy_summary = ""
        sell_summary = ""

        for tf in timeframes:
            buy_tiers = {"Excellent": [], "Great": [], "Good": []}
            sell_tiers = {"Excellent": [], "Great": [], "Good": []}

            # Resolve lad across both categories
            if target_date is not None:
                if isinstance(target_date, str):
                    lad = pd.to_datetime(target_date).normalize()
                elif isinstance(target_date, pd.Timestamp):
                    lad = target_date.normalize()
                else:
                    lad = pd.Timestamp(target_date).normalize()
            else:
                lad = None
                for sym, cat in [(s, "crypto") for s in crypto_syms] + [(s, "stocks") for s in stock_syms]:
                    _, max_date = db.get_signals_date_range(sym, cat, tf)
                    if max_date:
                        d = pd.Timestamp(max_date).normalize()
                        if lad is None or d < lad:
                            lad = d

            if lad is None:
                continue

            for sym, cat in [(s, "crypto") for s in crypto_syms] + [(s, "stocks") for s in stock_syms]:
                df = db.load_signals(sym, cat, tf)
                if df.empty:
                    continue
                today_df = df[df["Date"].dt.normalize() == lad]
                for tier in ["Excellent", "Great", "Good"]:
                    if not today_df[today_df["signal"] == f"{tier} Buy"].empty:
                        buy_tiers[tier].append(sym)
                    if not today_df[today_df["signal"] == f"{tier} Sell"].empty:
                        sell_tiers[tier].append(sym)

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

        now_utc = pd.Timestamp.utcnow()
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


def get_current_prices_string(config_path="cryptos.yml", vs_currency="usd"):
    symbols_cg = [entry["id"] for entry in config["crypto_prices"]]
    id_to_symbol = {entry["id"]: entry["symbol"] for entry in config["crypto_prices"]}

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(symbols_cg)}&vs_currencies={vs_currency}"
    response = requests.get(url)
    prices = response.json()

    result = ""
    for symbol in symbols_cg:
        price = prices[symbol][vs_currency]
        if price >= 1:
            result += f"{id_to_symbol[symbol]}: ${price:,.2f}\n"
        else:
            result += f"{id_to_symbol[symbol]}: ${price:,.5f}\n"

    result += get_btc_dominance()

    now_utc = pd.Timestamp.utcnow()
    result += now_utc.strftime("%H:%M:%S • %m-%d-%Y UTC\n")
    return result


def get_current_stock_prices_string(vs_currency="usd"):
    if not stock_symbols:
        return ""
    result = "Stocks:\n"
    for sym in stock_symbols:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                if price >= 1:
                    result += f"{sym}: ${price:,.2f}\n"
                else:
                    result += f"{sym}: ${price:,.5f}\n"
            else:
                result += f"{sym}: N/A\n"
        except Exception:
            result += f"{sym}: N/A\n"
    return result


def get_btc_dominance():
    url = "https://api.coingecko.com/api/v3/global"
    response = requests.get(url)
    if response.status_code != 200:
        return "Error fetching BTC dominance"
    data = response.json()
    btc_dominance = data["data"]["market_cap_percentage"]["btc"]
    return f"BTC Dominance: {btc_dominance:.2f}%\n"


def get_total_marketcap():
    cg = CoinGeckoAPI()
    global_data = cg.get_global()
    total_market_cap = global_data['total_market_cap']['usd']
    print(f"Total Market Cap: ${total_market_cap:,.0f}\n")
    return f"TMC: ${total_market_cap:,.0f}\n"


import platform

def is_raspberry_pi():
    return platform.system().lower() == "linux" and ("arm" in platform.machine() or "aarch64" in platform.machine())


if is_raspberry_pi():
    from display import display_single_image

def _count_signals(buy_summary_text: str, sell_summary_text: str):
    def _count_items(block: str) -> int:
        return sum(1 for line in block.splitlines() if line.startswith("  "))
    return _count_items(buy_summary_text), _count_items(sell_summary_text)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        process_crypto_data()
        process_stock_data()


    else:
        separated = generate_signals_summary_separate(target_date=None)
        crypto_combined, crypto_buy_summary, crypto_sell_summary = separated["crypto"]
        stock_combined, stock_buy_summary, stock_sell_summary = separated["stocks"]
        combined_all, buy_summary_str, sell_summary_str = separated["combined"]

        crypto_prices_str = get_total_marketcap()
        crypto_prices_str += get_current_prices_string()
        stock_prices_str = get_current_stock_prices_string()

        # Image: crypto-only (per your instruction)
        image_path = generate_crypto_signal_image(crypto_buy_summary, crypto_sell_summary, crypto_prices_str, config)

        if is_raspberry_pi() and "tweet" not in sys.argv:
            display_single_image(image_path)

        if len(sys.argv) > 1 and sys.argv[1] == "tweet":
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
            )

            send_tweet(crypto_tweet)
            send_tweet(stocks_tweet)
