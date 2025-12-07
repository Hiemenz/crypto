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

if __name__ == "__main__":
    main()
