import os
import json
import glob
import pandas as pd
import numpy as np
from datetime import datetime

# Configuration
REPORTS_DIR = "reports"
DATA_DIR = "crypto_history_csv"
OUTPUT_DIR = "frontend/public/data"

def parse_report_line(line):
    # Determine the type of line (Header or Asset)
    if line.startswith("#"):
        return {"type": "header", "content": line.strip("#").strip()}
    
    # Simple asset parsing logic (custom to your report format)
    # Assuming standard format: BTC-USD: Buy (Signal details...)
    if ": " in line:
        parts = line.split(": ", 1)
        symbol = parts[0].strip()
        details = parts[1].strip()
        return {"type": "asset", "symbol": symbol, "details": details}
    
    if line.strip() == "":
        return {"type": "empty"}

    return {"type": "text", "content": line.strip()}

def generate_reports_json():
    print(f"Generating reports JSON to {OUTPUT_DIR}/reports/...")
    report_files = glob.glob(os.path.join(REPORTS_DIR, "**", "*.txt"), recursive=True)
    
    index_data = set() # Use a set to avoid duplicates

    for report_path in report_files:
        filename = os.path.basename(report_path)
        date_str = filename.replace(".txt", "")
        
        # Read the report content
        with open(report_path, "r") as f:
            lines = f.readlines()
        
        parsed_content = [parse_report_line(line) for line in lines]
        
        # Save individual report JSON
        output_path = os.path.join(OUTPUT_DIR, "reports", f"{date_str}.json")
        with open(output_path, "w") as f:
            json.dump({"date": date_str, "content": parsed_content}, f, indent=2)
            
        index_data.add(date_str)
    
    # Save index JSON
    sorted_dates = sorted(list(index_data), reverse=True)
    with open(os.path.join(OUTPUT_DIR, "index.json"), "w") as f:
        json.dump({"dates": sorted_dates}, f, indent=2)
    print("Reports JSON generation complete.")

def generate_history_json():
    print(f"Generating history JSON to {OUTPUT_DIR}/history/...")
    # Scan for parquet files in crypto_history_csv/{category}/1d/*.parquet
    parquet_files = glob.glob(os.path.join(DATA_DIR, "*", "1d", "*_with_signals.parquet"))
    
    for file_path in parquet_files:
        try:
            filename = os.path.basename(file_path)
            symbol = filename.replace("_with_signals.parquet", "")
            
            df = pd.read_parquet(file_path)
            
            # Ensure Date is string for JSON
            if "Date" in df.columns:
                df["Date"] = df["Date"].astype(str)
            
            # Replace NaN with None (which becomes null in JSON)
            df = df.replace({np.nan: None})
            
            # Convert to list of dicts
            data = df.to_dict(orient="records")
            
            output_path = os.path.join(OUTPUT_DIR, "history", f"{symbol}.json")
            with open(output_path, "w") as f:
                json.dump({"symbol": symbol, "data": data}, f, indent=2)
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print("History JSON generation complete.")

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "history"), exist_ok=True)
    
    generate_reports_json()
    generate_history_json()
    generate_latest_signals_json()
    generate_crosses_json()

def calculate_score(row):
    """
    Calculates a 0-100 score representing the strength/confidence of the signal.
    """
    signal = str(row.get("signal", "")).lower()
    
    # Base score from signal tier
    if "excellent" in signal:
        score = 95
    elif "great" in signal:
        score = 85
    elif "good" in signal:
        score = 75
    else:
        # For 'Hold' or no signal, calculate a 'neutrality' or 'volatility' score? 
        # Or just a basic trend score.
        # Let's based it on RSI for Hold.
        rsi = row.get("rsi")
        if pd.isna(rsi):
            return 50
        
        # This is ambiguous.
        # Let's default to a "Stability" score for now, or just 50.
        score = 50
        
    # Add small variance based on indicators to differentiate same-tier signals
    # For Buys: lower RSI is better
    rsi = row.get("rsi", 50)
    if pd.isna(rsi): rsi = 50
    
    if "buy" in signal:
        # Bonus for lower RSI
        # RSI 20 vs 30: 20 is better.
        # Add (30 - RSI) * 0.5
        score += (30 - rsi) * 0.2
    elif "sell" in signal:
        # Bonus for higher RSI
        # RSI 80 vs 70: 80 is better.
        score += (rsi - 70) * 0.2
        
    return int(min(max(score, 0), 100))

def generate_latest_signals_json():
    print(f"Generating latest signals JSON to {OUTPUT_DIR}/latest_signals.json...")
    
    all_signals = []
    
    # Scan crypto and stocks
    for category in ["crypto", "stocks"]:
        parquet_files = glob.glob(os.path.join(DATA_DIR, category, "1d", "*_with_signals.parquet"))
        
        for file_path in parquet_files:
            try:
                filename = os.path.basename(file_path)
                symbol = filename.replace("_with_signals.parquet", "")
                
                df = pd.read_parquet(file_path)
                if df.empty:
                    continue
                    
                # Get last row
                last_row = df.iloc[-1]
                
                # Convert to dict
                item = last_row.to_dict()
                
                # Clean up values for JSON
                for k, v in item.items():
                    if pd.isna(v):
                        item[k] = None
                    elif isinstance(v, (pd.Timestamp, datetime)):
                        item[k] = str(v)
                
                # Add calculated fields
                item["symbol"] = symbol
                item["category"] = category
                item["score"] = calculate_score(last_row)
                
                # Determine "Side" (Buy/Sell/Hold) for easier frontend filtering
                sig_str = str(item.get("signal", "")).lower()
                if "buy" in sig_str:
                    item["side"] = "buy"
                elif "sell" in sig_str:
                    item["side"] = "sell"
                else:
                    item["side"] = "hold"
                
                all_signals.append(item)
                
            except Exception as e:
                print(f"Error processing {file_path} for latest signals: {e}")
                
    # Save
    output_path = os.path.join(OUTPUT_DIR, "latest_signals.json")
    with open(output_path, "w") as f:
        json.dump({"updated": str(datetime.now()), "signals": all_signals}, f, indent=2)
        
    print(f"Latest signals JSON generation complete. ({len(all_signals)} items)")

def generate_crosses_json():
    """
    Scans 1wk data for StochRSI crosses and exports to JSON.
    """
    print(f"Generating Stoch Crosses JSON to {OUTPUT_DIR}/crosses.json...")
    
    crosses = []
    categories = ["crypto", "stocks"]
    
    for category in categories:
        base_folder = os.path.join(DATA_DIR, category, "1wk") # Use DATA_DIR constant
        
        if not os.path.exists(base_folder):
            continue
        
        for file in os.listdir(base_folder):
            if not file.endswith("_with_signals.parquet"):
                continue
            
            symbol = file.replace("_with_signals.parquet", "")
            file_path = os.path.join(base_folder, file)
            
            try:
                df = pd.read_parquet(file_path)
                if len(df) < 2:
                    continue
                
                # Ensure sorted by date
                df = df.sort_values("Date")
                
                prev_k = df["stoch_rsi_k"].shift(1)
                prev_d = df["stoch_rsi_d"].shift(1)
                curr_k = df["stoch_rsi_k"]
                curr_d = df["stoch_rsi_d"]
                
                golden_mask = (prev_k < prev_d) & (curr_k > curr_d)
                death_mask = (prev_k > prev_d) & (curr_k < curr_d)
                
                events = []
                
                golden_events = df[golden_mask].copy()
                if not golden_events.empty:
                    golden_events["type"] = "Golden Cross"
                    events.append(golden_events)
                    
                death_events = df[death_mask].copy()
                if not death_events.empty:
                    death_events["type"] = "Death Cross"
                    events.append(death_events)
                
                if events:
                    all_events = pd.concat(events)
                    
                    for _, row in all_events.iterrows():
                        k = row.get("stoch_rsi_k", 0)
                        d = row.get("stoch_rsi_d", 0)
                        cross_type = row["type"]
                        
                        # Add confirmed mapping
                        if cross_type == "Golden Cross" and k > 0.2 and d > 0.2:
                            cross_type = "Confirmed Golden Cross"
                        elif cross_type == "Death Cross" and k < 0.8 and d < 0.8:
                            cross_type = "Confirmed Death Cross"
                            
                        crosses.append({
                            "category": category,
                            "symbol": symbol,
                            "type": cross_type,
                            "price": row.get("Close", 0),
                            "k": round(k, 2),
                            "d": round(d, 2),
                            "date": str(row["Date"]) # Ensure string format
                        })
                        
            except Exception as e:
                # print(f"Error processing {symbol}: {e}")
                continue
                
    # Filter for last 6 months to keep file size manageable but useful
    # Sorting in frontend
    
    # Save
    output_path = os.path.join(OUTPUT_DIR, "crosses.json")
    with open(output_path, "w") as f:
        json.dump({"updated": str(datetime.now()), "crosses": crosses}, f, indent=2)
        
    print(f"Stoch Crosses JSON generation complete. ({len(crosses)} items)")

if __name__ == "__main__":
    main()
