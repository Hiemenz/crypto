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
MAX_WORKERS = 4

def _process_single_symbol(symbol, base_output_folder, timeframes, fetch_start_override=None):
    """
    Process a single symbol: Download 1d data, then generate signals for all timeframes.
    Return True if successful/updated, False otherwise.
    """
    try:
        # 1. Manage 1D Data (Download/Update)
        output_path_1d = os.path.join(base_output_folder, "1d", f"{symbol}.parquet")
        
        df_1d = None
        is_new_data = False
        
        if os.path.exists(output_path_1d):
            # print(f"Checking {symbol}...")
            df_existing = pd.read_parquet(output_path_1d)
            if not pd.api.types.is_datetime64_any_dtype(df_existing["Date"]):
                df_existing["Date"] = pd.to_datetime(df_existing["Date"])
            
                # Ensure Dates are timezone-naive for consistency
                if pd.api.types.is_datetime64_any_dtype(df_existing["Date"]):
                    df_existing["Date"] = df_existing["Date"].dt.tz_localize(None)

            # --- DEDUPLICATION START ---
            # Remove any duplicate columns if they exist
            df_existing = df_existing.loc[:, ~df_existing.columns.duplicated()]
            
            # Ensure unique index (Date) if set, although we are using 'Date' column here
            df_existing = df_existing.drop_duplicates(subset=["Date"])
            # --- DEDUPLICATION END ---

            df_existing = df_existing.dropna(subset=["Date"])

            last_date = df_existing["Date"].max().date()
            fetch_start = last_date + pd.Timedelta(days=1)
            today_date = pd.Timestamp.now().date()

            if fetch_start >= today_date:
                # print(f"{symbol} is up to date.")
                df_1d = df_existing
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
                        threads=False # We handle threading externally
                    )
                except Exception as e:
                    print(f"Error downloading {symbol}: {e}")
                    df_new = pd.DataFrame()

                if not df_new.empty:
                    if isinstance(df_new.columns, pd.MultiIndex):
                        df_new.columns = df_new.columns.get_level_values(0)

                    # Deduplicate columns immediately after flattening
                    df_new = df_new.loc[:, ~df_new.columns.duplicated()]

                    df_new = df_new.reset_index()
                    
                    # Normalize New Data Dates to TZ-naive
                    if "Date" in df_new.columns:
                        df_new["Date"] = pd.to_datetime(df_new["Date"]).dt.tz_localize(None)

                    expected_cols = ["Date", "Close", "High", "Low", "Open", "Volume"]
                    available_cols = [c for c in expected_cols if c in df_new.columns]
                    df_new = df_new[available_cols]
                    
                    try:
                         # Attempt merge
                        df_combined = pd.concat([df_existing, df_new], ignore_index=True).drop_duplicates(subset="Date")
                    except Exception as merge_err:
                        print(f"Error merging data for {symbol}: {merge_err}. Corrupt file likely. Deleting and restarting.")
                        if os.path.exists(output_path_1d):
                            os.remove(output_path_1d)
                        # Recursive retry (or just return False to pick it up next time)
                        # returning False lets the logic fall through to 'Fetching new data' block below if we restructured, 
                        # but here we are inside the 'if exists' block. 
                        # Simplest fix: Force df_1d to None so we don't save bad state, and let next run fix it.
                        # Better: Process as if it's new data.
                        print(f"Redownloading full history for {symbol}...")
                        df_1d = None # Force re-fetch logic essentially (but we need to trigger the else block)
                         # Actually, we can just let it fail this run, and delete the file.
                        return False

                    # Check partial candle
                    if not df_combined.empty:
                        last_date = df_combined["Date"].iloc[-1].date()
                        if last_date >= today_date:
                            df_combined = df_combined.iloc[:-1]

                    df_combined.to_parquet(output_path_1d, index=False)
                    df_1d = df_combined
                    is_new_data = True
                    # print(f"Updated {symbol}")
                else:
                    df_1d = df_existing
        else:
            print(f"Fetching new data for {symbol}...")
            try:
                df = yf.download(symbol, start="2014-01-01", interval="1d", progress=False, auto_adjust=True, threads=False)
                df = df.iloc[:-1] # Drop partial
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                # Deduplicate columns immediately after flattening
                df = df.loc[:, ~df.columns.duplicated()]

                if not df.empty:
                    df = df.reset_index()
                    if "Date" not in df.columns and df.index.name == "Date":
                         df = df.reset_index()
                    
                    df.to_parquet(output_path_1d, index=False)
                    df_1d = df
                    is_new_data = True
            except Exception as e:
                print(f"Failed to fetch {symbol}: {e}")
                return False

        if df_1d is None or df_1d.empty:
            return False

        # 2. Process All Timeframes
        cols_to_numeric = ["Close", "High", "Low", "Open", "Volume"]
        for col in cols_to_numeric:
            if col in df_1d.columns:
                df_1d[col] = pd.to_numeric(df_1d[col], errors="coerce")
        
        df_1d.dropna(subset=["Close", "High", "Low", "Open", "Volume"], inplace=True)
        
        # Ensure Date is datetime and normalized to remove time components
        df_1d["Date"] = pd.to_datetime(df_1d["Date"]).dt.normalize()
        
        # FINAL duplicate check before setting index
        df_1d = df_1d.drop_duplicates(subset=["Date"], keep="last")
        
        df_1d = df_1d.set_index("Date").sort_index()
        
        # Double check index uniqueness just in case
        if not df_1d.index.is_unique:
             # print(f"Warning: {symbol} has duplicate index after cleanup. deduping...")
             df_1d = df_1d[~df_1d.index.duplicated(keep='last')]

        for tf_name, tf_alias in timeframes.items():
            output_folder_tf = os.path.join(base_output_folder, tf_name)
            enhanced_output = os.path.join(output_folder_tf, f"{symbol}_with_signals.parquet")

            needs_processing = is_new_data
            if not needs_processing and os.path.exists(enhanced_output):
                try:
                    existing_cols = pd.read_parquet(enhanced_output).columns
                    required_cols = ["bb_upper", "macd", "stoch_rsi_k"]
                    if any(col not in existing_cols for col in required_cols):
                        needs_processing = True
                except Exception:
                    needs_processing = True

            if not needs_processing and os.path.exists(enhanced_output):
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
            df_tf.to_parquet(enhanced_output, index=False)
            
            # Chart generation
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(df_tf["Date"], df_tf["Close"], color='black', label='Close Price')

            # Scatter signals
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
            plt.savefig(os.path.join(output_folder_tf, f"{symbol}_signals_chart.png"), dpi=150, bbox_inches="tight") # Lower DPI for speed
            plt.close()

        return True

    except Exception as e:
        print(f"Critical error processing {symbol}: {e}")
        traceback.print_exc()
        return False


def _process_asset_list(asset_symbols, subfolder):
    # Base folder for this asset class (crypto or stocks)
    base_output_folder = os.path.join("crypto_history_csv", subfolder)
    
    # Define timeframes and their pandas offset aliases
    # 1d is the base, others are resampled from it
    timeframes = {
        "1d": None,
        "3d": "3D",
        "1wk": "W-SUN", # Weekly starting Sunday
        "2wk": "2W-SUN" # Bi-weekly starting Sunday
    }

    # Ensure subfolders exist
    for tf in timeframes:
        os.makedirs(os.path.join(base_output_folder, tf), exist_ok=True)

    print(f"Processing {len(asset_symbols)} items for {subfolder} with {MAX_WORKERS} threads...")
    
    import concurrent.futures
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        futures = {executor.submit(_process_single_symbol, symbol, base_output_folder, timeframes): symbol for symbol in asset_symbols}
        
        # Wait for completion (optional: use as_completed for progress bar)
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"Exception for {symbol}: {e}")
    
    print(f"Completed {subfolder} processing.")


def process_crypto_data():
    _process_asset_list(symbols, "crypto")


def process_stock_data():
    _process_asset_list(stock_symbols, "stocks")


def generate_signals_summary(folder="crypto_history_csv", target_date=None):

    buy_tiers = {"Excellent": [], "Great": [], "Good": []}
    sell_tiers = {"Excellent": [], "Great": [], "Good": []}
    summary_output = ""
    buy_summary = ""
    sell_summary = ""

    all_symbols = symbols + stock_symbols

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
        for symbol in all_symbols:
            filepath = os.path.join(folder, f"{symbol}_with_signals.parquet")
            if not os.path.exists(filepath):
                continue
            df = pd.read_parquet(filepath)
            date = df["Date"].max().normalize()
            if latest_available_date is None or date < latest_available_date:
                latest_available_date = date

    if latest_available_date is None:
        summary_output += "No signal files found.\n"
        print(summary_output)
        return summary_output, buy_summary, sell_summary

    for symbol in all_symbols:
        filepath = os.path.join(folder, f"{symbol}_with_signals.parquet")
        if not os.path.exists(filepath):
            continue
        df = pd.read_parquet(filepath)
        today_df = df[df["Date"].dt.normalize() == latest_available_date]
        for tier in ["Excellent", "Great", "Good"]:
            if not today_df[today_df["signal"] == f"{tier} Buy"].empty:
                buy_tiers[tier].append(symbol)
            if not today_df[today_df["signal"] == f"{tier} Sell"].empty:
                sell_tiers[tier].append(symbol)

    # Build summary output string
    summary_output += "\n"
    if not any(buy_tiers.values()) and not any(sell_tiers.values()):
        sell_summary += f'No Sell signals\n{latest_available_date.date()}\n'
        buy_summary += f'No Buy signals\n{latest_available_date.date()}\n'
        summary_output += f'No Buy or Sell signals\n'
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


def generate_signals_summary_separate(base_folder="crypto_history_csv", target_date=None):
    """
    Returns separate summaries for crypto and stocks, plus a combined summary for convenience.
    Output format:
      {
        "crypto": (summary_output, buy_summary, sell_summary),
        "stocks": (summary_output, buy_summary, sell_summary),
        "combined": (summary_output, buy_summary, sell_summary)
      }
    """
    crypto_folder = os.path.join(base_folder, "crypto")
    stocks_folder = os.path.join(base_folder, "stocks")

    def _summarize_symbols(subset_symbols, folder):
        summary_output = ""
        buy_summary = ""
        sell_summary = ""
        
        timeframes = ["1d", "3d", "1wk", "2wk"]
        
        for tf in timeframes:
            tf_folder = os.path.join(folder, tf)
            if not os.path.exists(tf_folder):
                continue

            buy_tiers = {"Excellent": [], "Great": [], "Good": []}
            sell_tiers = {"Excellent": [], "Great": [], "Good": []}

            # Resolve latest_available_date for this subset if not provided
            if target_date is not None:
                if isinstance(target_date, str):
                    lad = pd.to_datetime(target_date).normalize()
                elif isinstance(target_date, pd.Timestamp):
                    lad = target_date.normalize()
                else:
                    lad = pd.Timestamp(target_date).normalize()
            else:
                lad = None
                for symbol in subset_symbols:
                    filepath = os.path.join(tf_folder, f"{symbol}_with_signals.parquet")
                    if not os.path.exists(filepath):
                        continue
                    df = pd.read_parquet(filepath)
                    date = df["Date"].max().normalize()
                    if lad is None or date < lad:
                        lad = date

            if lad is None:
                summary_output += f"[{tf}] No signal files found.\n"
                continue

            # Build tiers for this subset
            for symbol in subset_symbols:
                filepath = os.path.join(tf_folder, f"{symbol}_with_signals.parquet")
                if not os.path.exists(filepath):
                    continue
                df = pd.read_parquet(filepath)
                today_df = df[df["Date"].dt.normalize() == lad]
                for tier in ["Excellent", "Great", "Good"]:
                    if not today_df[today_df["signal"] == f"{tier} Buy"].empty:
                        buy_tiers[tier].append(symbol)
                    if not today_df[today_df["signal"] == f"{tier} Sell"].empty:
                        sell_tiers[tier].append(symbol)

            # summary_output += "\n"
            if not any(buy_tiers.values()) and not any(sell_tiers.values()):
                # sell_summary += f'[{tf}] No Sell signals ({lad.date()})\n'
                # buy_summary += f'[{tf}] No Buy signals ({lad.date()})\n'
                # summary_output += f'[{tf}] No Buy or Sell signals\n'
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

    def _summarize_combined(subset_symbols):
        summary_output = ""
        buy_summary = ""
        sell_summary = ""
        
        timeframes = ["1d", "3d", "1wk", "2wk"]

        for tf in timeframes:
            buy_tiers = {"Excellent": [], "Great": [], "Good": []}
            sell_tiers = {"Excellent": [], "Great": [], "Good": []}

            # Resolve latest_available_date across both folders
            if target_date is not None:
                if isinstance(target_date, str):
                    lad = pd.to_datetime(target_date).normalize()
                elif isinstance(target_date, pd.Timestamp):
                    lad = target_date.normalize()
                else:
                    lad = pd.Timestamp(target_date).normalize()
            else:
                lad = None
                for symbol in subset_symbols:
                    for folder in (crypto_folder, stocks_folder):
                        filepath = os.path.join(folder, tf, f"{symbol}_with_signals.parquet")
                        if os.path.exists(filepath):
                            df = pd.read_parquet(filepath)
                            date = df["Date"].max().normalize()
                            if lad is None or date < lad:
                                lad = date

            if lad is None:
                # summary_output += f"[{tf}] No signal files found.\n"
                continue

            # Build tiers across both folders
            for symbol in subset_symbols:
                df = None
                for folder in (crypto_folder, stocks_folder):
                    filepath = os.path.join(folder, tf, f"{symbol}_with_signals.parquet")
                    if os.path.exists(filepath):
                        df = pd.read_parquet(filepath) 
                        break
                if df is None:
                    continue
                today_df = df[df["Date"].dt.normalize() == lad]
                for tier in ["Excellent", "Great", "Good"]:
                    if not today_df[today_df["signal"] == f"{tier} Buy"].empty:
                        buy_tiers[tier].append(symbol)
                    if not today_df[today_df["signal"] == f"{tier} Sell"].empty:
                        sell_tiers[tier].append(symbol)

            # summary_output += "\n"
            if not any(buy_tiers.values()) and not any(sell_tiers.values()):
                # sell_summary += f'[{tf}] No Sell signals ({lad.date()})\n'
                # buy_summary += f'[{tf}] No Buy signals ({lad.date()})\n'
                # summary_output += f'[{tf}] No Buy or Sell signals\n'
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

    # Separate sets
    crypto_syms = symbols
    stock_syms = stock_symbols

    crypto_summary = _summarize_symbols(crypto_syms, crypto_folder)
    stock_summary = _summarize_symbols(stock_syms, stocks_folder)

    # Also provide a combined view that searches both folders
    combined_syms = crypto_syms + stock_syms
    combined_summary = _summarize_combined(combined_syms)

    return {
        "crypto": crypto_summary,
        "stocks": stock_summary,
        "combined": combined_summary
    }


def get_current_prices_string(config_path="cryptos.yml", vs_currency="usd"):
    # with open(config_path, "r") as f:
    #     config = yaml.safe_load(f)

    symbols = [entry["id"] for entry in config["crypto_prices"]]
    id_to_symbol = {entry["id"]: entry["symbol"] for entry in config["crypto_prices"]}

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(symbols)}&vs_currencies={vs_currency}"
    response = requests.get(url)
    prices = response.json()

    result = ""
    for symbol in symbols:
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


# Function to fetch and display BTC dominance from CoinGecko
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
        # Count lines that are indented with two spaces (ticker lines)
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

        if is_raspberry_pi():
            display_single_image(image_path)

        if len(sys.argv) > 1 and sys.argv[1] == "tweet":
            # Counts
            crypto_buy_count, crypto_sell_count = _count_signals(crypto_buy_summary, crypto_sell_summary)
            stock_buy_count, stock_sell_count = _count_signals(stock_buy_summary, stock_sell_summary)

            # Two separate tweets
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

            # send_toot(crypto_tweet)
            send_tweet(crypto_tweet)
            # send_toot(stocks_tweet)
            send_tweet(stocks_tweet)
