import pandas as pd
import ta
import os

def label_signal(row):
    rsi, mfi, stoch_rsi = row['rsi'], row['mfi'], row['stoch_rsi']
    is_bull = row['is_bull']

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

def calculate_indicators_and_label(file_path):
    df = pd.read_parquet(file_path)
    df = df.sort_values("Date")

    # Calculate indicators
    df["rsi"] = ta.momentum.RSIIndicator(df["Close"]).rsi()
    df["mfi"] = ta.volume.MFIIndicator(df["High"], df["Low"], df["Close"], df["Volume"]).money_flow_index()
    df["stoch_rsi"] = ta.momentum.StochRSIIndicator(df["Close"]).stochrsi()

    # Moving averages and market trend
    df["ma_50"] = df["Close"].rolling(window=50).mean()
    df["ma_200"] = df["Close"].rolling(window=200).mean()
    df["is_bull"] = df["ma_50"] > df["ma_200"]

    # Label signals
    df["signal"] = df.apply(label_signal, axis=1)

    # Save new file
    base, ext = os.path.splitext(file_path)
    output_path = base + "_with_signals.parquet"
    df.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")

if __name__ == "__main__":
    input_file = "crypto_history_csv/crypto/1d/BTC-USD.parquet"  # change as needed
    calculate_indicators_and_label(input_file)
