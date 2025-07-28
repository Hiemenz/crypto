from prophet import Prophet
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
import time
import os
import ta

# List of crypto tickers on Yahoo Finance
symbols = ["BTC-USD", "XLM-USD","ETH-USD", "XRP-USD","HBAR-USD", "DOGE-USD", "SOL-USD"]

# Folder to save CSV files
output_folder = "crypto_history_csv"
os.makedirs(output_folder, exist_ok=True)

# Download and save
for symbol in symbols:
    output_path = os.path.join(output_folder, f"{symbol}.csv")
    if os.path.exists(output_path):
        print(f"Data for {symbol} already exists. Skipping download.")
        df = pd.read_csv(output_path, parse_dates=["Date"])
    else:
        print(f"Fetching data for {symbol}...")
        df = yf.download(symbol, start="2010-01-01", interval="1d", progress=False)
        
        if df.empty:
            print(f"No data for {symbol}")
            continue

        df.to_csv(output_path)
        print(f"Saved to {output_path}")
    
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
        return None

    df["signal"] = df.apply(label_signal, axis=1)

    # Save enhanced file
    enhanced_output = os.path.join(output_folder, f"{symbol}_with_signals.csv")
    df.to_csv(enhanced_output, index=False)
    print(f"Signal-enhanced file saved to {enhanced_output}")

    # Prophet forecast and plot
    # Prepare data for Prophet
    df_prophet = df[["Date", "Close"]].rename(columns={"Date": "ds", "Close": "y"})
    df_prophet.dropna(inplace=True)

    model = Prophet()
    model.fit(df_prophet)

    future = model.make_future_dataframe(periods=300)
    forecast = model.predict(future)

    fig = model.plot(forecast)
    plt.plot(df["Date"], df["ma_50"], label="50-day MA", linestyle='--')
    plt.plot(df["Date"], df["ma_200"], label="200-day MA", linestyle='--')
    plt.legend()
    plt.title(f"{symbol} Price Forecast")
    plt.xlabel("Date")
    plt.ylabel("Price (USD)")
    plt.tight_layout()
    # Save high-resolution and vector versions
    plt.savefig(os.path.join(output_folder, f"{symbol}_forecast.png"), dpi=600, bbox_inches="tight")

    plt.close()
    print(f"Forecast plot saved to {symbol}_forecast.png")

    # Chart with buy/sell signal dots
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df["Date"], df["Close"], color='black', label='Close Price')

    # Scatter buy signals in shades of green
    ax.scatter(df[df["signal"] == "Excellent Buy"]["Date"], df[df["signal"] == "Excellent Buy"]["Close"], color='darkgreen', label="Excellent Buy", marker='o')
    ax.scatter(df[df["signal"] == "Great Buy"]["Date"], df[df["signal"] == "Great Buy"]["Close"], color='green', label="Great Buy", marker='o')
    ax.scatter(df[df["signal"] == "Good Buy"]["Date"], df[df["signal"] == "Good Buy"]["Close"], color='lightgreen', label="Good Buy", marker='o')

    # Scatter sell signals in shades of blue
    ax.scatter(df[df["signal"] == "Excellent Sell"]["Date"], df[df["signal"] == "Excellent Sell"]["Close"], color='navy', label="Excellent Sell", marker='o')
    ax.scatter(df[df["signal"] == "Great Sell"]["Date"], df[df["signal"] == "Great Sell"]["Close"], color='blue', label="Great Sell", marker='o')
    ax.scatter(df[df["signal"] == "Good Sell"]["Date"], df[df["signal"] == "Good Sell"]["Close"], color='skyblue', label="Good Sell", marker='o')

    ax.set_title(f"{symbol} Buy/Sell Signals")
    ax.set_xlabel("Date")
    ax.set_ylabel("Price (USD)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_folder, f"{symbol}_signals_chart.png"), dpi=600, bbox_inches="tight")
    plt.close()
    print(f"Signal chart saved to {symbol}_signals_chart.png")

    time.sleep(1.5)  # Prevent rate limit