import pandas as pd
import matplotlib.pyplot as plt
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

global symbols
global config
    # Load symbols from YAML
with open("crypto_signal_station/cryptos.yml", "r") as f:
    config = yaml.safe_load(f)
    symbols = config["cryptos"]

def process_crypto_data():
    # List of crypto tickers on Yahoo Finance
    # symbols = ["BTC-USD","LTC-USD","ADA-USD", "XLM-USD","ETH-USD", "XRP-USD","HBAR-USD", "DOGE-USD", "SOL-USD"]

    # Folder to save CSV files
    output_folder = "crypto_history_csv"
    os.makedirs(output_folder, exist_ok=True)

    # Download and save
    for symbol in symbols:
        output_path = os.path.join(output_folder, f"{symbol}.csv")
        if os.path.exists(output_path):
            print(f"Data for {symbol} already exists. Checking for updates...")
            df_existing = pd.read_csv(output_path, parse_dates=["Date"])
            df_existing = df_existing.dropna(subset=["Date"])  # Remove corrupted rows if any

            last_date = df_existing["Date"].max().date()
            fetch_start = last_date + pd.Timedelta(days=1)

            df_new = yf.download(
                symbol,
                start=fetch_start.strftime("%Y-%m-%d"),
                end=pd.Timestamp.today().strftime("%Y-%m-%d"),
                interval="1d",
                progress=False,
                auto_adjust=True
            )
            if not df_new.empty:
                df_new = df_new.reset_index()
                # Ensure column headers are renamed to preferred format
                df_new.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
                expected_cols = ["Date", "Close", "High", "Low", "Open", "Volume"]
                df_new = df_new[expected_cols]
                df_new = df_new.astype(df_existing.dtypes.to_dict())
                df_combined = pd.concat([df_existing, df_new], ignore_index=True).drop_duplicates(subset="Date")
                df_combined.to_csv(output_path, index=False)
                df = df_combined
                print(f"Updated CSV saved to {output_path}")
            else:
                print(f"No new data for {symbol}.")
                df = df_existing
        else:
            print(f"Fetching data for {symbol}...")
            df = yf.download(symbol, start="2014-01-01", interval="1d", progress=False, auto_adjust=True)
            # Drop the last row (often partially updated or mislabeled)


            df = df.iloc[:-1]
            
            if df.empty:
                print(f"No data for {symbol}")
                continue

            df.to_csv(output_path)
            print(f"Saved to {output_path}")

            with open(output_path, 'r') as f:
                lines = f.readlines()
                # Normalize CSV only if first line starts with 'Price' and second with 'Ticker'
                if lines[0].startswith("Price") and lines[1].startswith("Ticker"):
                    print('Modifying the csv file cleaning it up')
                    with open(output_path, 'w') as f:
                        f.write("Date,Close,High,Low,Open,Volume\n")
                        f.writelines(lines[3:])
                    df = pd.read_csv(output_path, parse_dates=["Date"])

        # Ensure numeric columns are properly parsed and clean data before indicator calculations
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df["Close"] = df["Close"].astype(float).values.flatten()
        df["High"] = pd.to_numeric(df["High"], errors="coerce")
        df["Low"] = pd.to_numeric(df["Low"], errors="coerce")
        df["Open"] = pd.to_numeric(df["Open"], errors="coerce")
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
        df.dropna(subset=["Close", "High", "Low", "Open", "Volume"], inplace=True)

        

        # Calculate indicators
        df["rsi"] = ta.momentum.RSIIndicator(df["Close"]).rsi()
        df["mfi"] = ta.volume.MFIIndicator(df["High"], df["Low"], df["Close"], df["Volume"]).money_flow_index()
        df["stoch_rsi"] = ta.momentum.StochRSIIndicator(
            close=df["Close"],
            window=14,
            smooth1=3,
            smooth2=4
        ).stochrsi()

        # Moving averages and market trend
        df["ma_50"] = df["Close"].rolling(window=50).mean()
        df["ma_200"] = df["Close"].rolling(window=200).mean()
        df["is_bull"] = df["ma_50"] > df["ma_200"]

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

        df["signal"] = df.apply(label_signal, axis=1)

        # Save enhanced file
        enhanced_output = os.path.join(output_folder, f"{symbol}_with_signals.csv")
        df.to_csv(enhanced_output, index=False)
        print(f"Signal-enhanced file saved to {enhanced_output}")

        time.sleep(1.5)  # Prevent rate limit



def generate_signals_summary(folder="crypto_history_csv", target_date=None):


    buy_tiers = {"Excellent": [], "Great": [], "Good": []}
    sell_tiers = {"Excellent": [], "Great": [], "Good": []}
    summary_output = ""
    buy_summary = ""
    sell_summary = ""

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
        for symbol in symbols:
            filepath = os.path.join(folder, f"{symbol}_with_signals.csv")
            if not os.path.exists(filepath):
                continue
            df = pd.read_csv(filepath, parse_dates=["Date"])
            date = df["Date"].max().normalize()
            if latest_available_date is None or date < latest_available_date:
                latest_available_date = date

    if latest_available_date is None:
        summary_output += "No signal files found.\n"
        print(summary_output)
        return summary_output, buy_summary, sell_summary

    for symbol in symbols:
        filepath = os.path.join(folder, f"{symbol}_with_signals.csv")
        if not os.path.exists(filepath):
            continue
        df = pd.read_csv(filepath, parse_dates=["Date"])
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

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        process_crypto_data()
    

    else:
        combined, buy_summary_str, sell_summary_str = generate_signals_summary(target_date=None)
        current_prices_str = get_total_marketcap()
        current_prices_str += get_current_prices_string()
        
        image_path = generate_crypto_signal_image(buy_summary_str, sell_summary_str, current_prices_str, config)
        if is_raspberry_pi():
            display_single_image(image_path)

        if len(sys.argv) > 1 and sys.argv[1] == "tweet":
            send_toot(combined)
            send_tweet(combined)
