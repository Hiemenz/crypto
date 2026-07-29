from crypto_signal_pipeline import _process_asset_list
import pandas as pd
import os
import time

# 1. Setup: Create dummy raw data (yesterday)
symbol = "TEST-USD"
base_dir = "crypto_history_csv/crypto/1d"
os.makedirs(base_dir, exist_ok=True)
raw_path = f"{base_dir}/{symbol}.parquet"

# Create data if not exists
if not os.path.exists(raw_path):
    df = pd.DataFrame({
        "Date": [pd.Timestamp.now().normalize() - pd.Timedelta(days=1)],
        "Close": [100.0],
        "High": [105.0],
        "Low": [95.0],
        "Open": [98.0],
        "Volume": [1000]
    })
    df.to_parquet(raw_path)
    print("Created dummy raw data.")

print("\n--- Run 1 (Should process) ---")
_process_asset_list([symbol], "crypto")

print("\n--- Run 2 (Should skip processing) ---")
_process_asset_list([symbol], "crypto")
