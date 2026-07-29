import os
import pandas as pd
import argparse
import sys
from datetime import timedelta

def generate_report_for_date(target_date, base_folder="crypto_history_csv", reports_base_dir="reports"):
    subfolders = ["crypto", "stocks"]
    timeframes = ["1d", "2d", "3d", "1wk", "2wk"]

    # We will generate two separate reports
    reports = {
        "crypto": [],
        "stocks": []
    }
    
    has_content = {
        "crypto": False,
        "stocks": False
    }

    # Helper to log to specific report list
    def log(category, msg=""):
        reports[category].append(msg)

    def get_days_until_next(folder_path, target_date):
        try:
            files = [f for f in os.listdir(folder_path) if f.endswith("_with_signals.parquet")]
            if not files:
                return None
            
            # Use the first file as a representative schedule
            # Ideally check a few or use a known major asset like BTC-USD or AAPL if available,
            # but any file with data should share the same timeframe schedule.
            ref_file = files[0]
            if "BTC-USD_with_signals.parquet" in files:
                ref_file = "BTC-USD_with_signals.parquet"
            
            df = pd.read_parquet(os.path.join(folder_path, ref_file))
            if "Date" not in df.columns or df.empty:
                return None
            
            if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
                df["Date"] = pd.to_datetime(df["Date"])
            
            dates = df["Date"].dt.normalize().sort_values().unique()
            
            # Find next date > target_date
            future_dates = dates[dates > target_date]
            
            if len(future_dates) > 0:
                next_date = future_dates[0]
                return (next_date - target_date).days
            else:
                # Extrapolate if target_date is beyond the last known date
                if len(dates) >= 2:
                    last_date = dates[-1]
                    # Calculate interval from last 2 dates
                    interval = dates[-1] - dates[-2]
                    
                    next_theoretical = last_date + interval
                    while next_theoretical <= target_date:
                        next_theoretical += interval
                    
                    return (next_theoretical - target_date).days
                return None
        except Exception:
            return None

    def validate_data_coverage(target_date, base_folder="crypto_history_csv"):
        """
        Ensures that at least some data exists for the target_date.
        If minimal data is missing (e.g. BTC for crypto, AAPL for stocks), returns False.
        """
        # Critical assets to check as proxy for category health
        # If these are missing, it's likely the whole category failed or market was closed.
        critical_checks = {
            "crypto": ["BTC-USD", "ETH-USD"],
            "stocks": ["AAPL", "MSFT", "SPY"]
        }
        
        found_any = False
        
        # Check Crypto
        crypto_path = os.path.join(base_folder, "crypto", "1d")
        if os.path.exists(crypto_path):
            files = os.listdir(crypto_path)
            for asset in critical_checks["crypto"]:
                fname = f"{asset}_with_signals.parquet"
                if fname in files:
                    try:
                        df = pd.read_parquet(os.path.join(crypto_path, fname))
                        if "Date" in df.columns:
                            # Check if target date exists in this file
                            if target_date in df["Date"].dt.normalize().values:
                                found_any = True
                                break
                    except Exception:
                        continue
        
        if found_any:
            return True
            
        # Check Stocks (if crypto check failed or just double checking)
        # Note: If user only cares about stocks, we should check stocks. 
        # But if found_any is True (crypto found), we assume pipeline ran.
        # However, stocks might be closed (weekend) while crypto is open.
        # So we should be careful.
        # Ideally, we want to ensure *relevant* data exists.
        # If crypto data exists, we can generate crypto report.
        # If stock data exists, we can generate stock report.
        # But this function returns a single boolean to block the WHOLE generation?
        # The user requested: "valid 'close' data exists before generating reports"
        # If we return False here, main() will exit.
        
        # Let's check stocks too if crypto wasn't found (or maybe unrelated)
        stocks_path = os.path.join(base_folder, "stocks", "1d")
        if os.path.exists(stocks_path):
            files = os.listdir(stocks_path)
            for asset in critical_checks["stocks"]:
                fname = f"{asset}_with_signals.parquet"
                if fname in files:
                    try:
                        df = pd.read_parquet(os.path.join(stocks_path, fname))
                        if "Date" in df.columns:
                            if target_date in df["Date"].dt.normalize().values:
                                found_any = True
                                break
                    except Exception:
                        continue
                        
        return found_any

    # Validate data existence before proceeding
    if not validate_data_coverage(target_date, base_folder):
        print(f"❌ Critical Validation Failed: No 'Close' data found for {target_date.date()} in key assets (BTC-USD, AAPL, etc).")
        print("   This likely means the data pipeline failed or no data was fetched.")
        print("   Aborting report generation to prevent empty reports.")
        sys.exit(1)

    for sub in subfolders:
        category = sub # "crypto" or "stocks"
        log(category, f"Report for {target_date.date()} ({category.capitalize()})\n")
        
        found_any_in_category = False
        
        for tf in timeframes:
            header_suffix = ""
            folder_path = os.path.join(base_folder, sub, tf)
            
            if tf in ["3d", "1wk", "2wk"] and os.path.exists(folder_path):
                days_next = get_days_until_next(folder_path, target_date)
                if days_next is not None:
                    header_suffix = f" (Next print in {days_next} days)"
            
            log(category, f"--- {tf} Timeframe{header_suffix} ---")
            tf_has_signals = False
            
            if not os.path.exists(folder_path):
                log(category, "No data folder found.")
                log(category, "")
                continue
            
            try:
                files = [f for f in os.listdir(folder_path) if f.endswith("_with_signals.parquet")]
            except FileNotFoundError:
                log(category, "No data files found.")
                log(category, "")
                continue

            files.sort()

            for file in files:
                file_path = os.path.join(folder_path, file)
                try:
                    df = pd.read_parquet(file_path)
                except Exception:
                    continue
                
                if "Date" not in df.columns:
                    continue
                
                if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
                    df["Date"] = pd.to_datetime(df["Date"])
                
                mask = df["Date"].dt.normalize() == target_date
                day_rows = df[mask]
                
                if day_rows.empty:
                    continue
                
                for _, row in day_rows.iterrows():
                    signal = row.get("signal")
                    if pd.isna(signal) or signal == "Hold" or signal is None:
                        continue
                        
                    symbol = file.replace("_with_signals.parquet", "")
                    close = row.get("Close", 0.0)
                    if pd.isna(close): close = 0.0
                    
                    rsi = row.get("rsi", 0.0)
                    if pd.isna(rsi): rsi = 0.0
                    
                    mfi = row.get("mfi", 0.0)
                    if pd.isna(mfi): mfi = 0.0
                    
                    stoch_k = row.get("stoch_rsi_k", 0.0)
                    if pd.isna(stoch_k): stoch_k = 0.0
                    stoch_d = row.get("stoch_rsi_d", 0.0)
                    if pd.isna(stoch_d): stoch_d = 0.0
                    
                    bb_pb = row.get("bb_pband", 0.0)
                    if pd.isna(bb_pb): bb_pb = 0.0
                    
                    macd_h = row.get("macd_hist", 0.0)
                    if pd.isna(macd_h): macd_h = 0.0
                    
                    # Format: Symbol Signal (Price: $X, RSI: X, MFI: X, StochRSI: K/D, BB: %B, MACD: H)
                    line = (f"{symbol:<10} {signal:<15} "
                            f"(Price: ${close:,.2f}, RSI: {rsi:.1f}, "
                            f"MFI: {mfi:.1f}, StochRSI: {stoch_k:.2f}/{stoch_d:.2f}, "
                            f"BB: {bb_pb:.2f}, MACD: {macd_h:.2f})")
                    
                    log(category, line)
                    tf_has_signals = True
                    found_any_in_category = True
            
            if not tf_has_signals:
                log(category, "No recommendations.")
            log(category, "")
        
        if not found_any_in_category:
            log(category, f"No recommendations found for {target_date.date()} across any timeframe.")
            # If strictly "do not show anything", we might want to clear it? 
            # But usually a "No recommendations" report is still useful to know it ran.
            # User said: "if there were no recomendations then do not show anything for that particular token or asset"
            # This implies if a token has no signal, don't show it. We are doing that.
            # If the whole day is empty, we show "No recommendations found".
        
        has_content[category] = found_any_in_category

    # Save reports
    for category in subfolders:
        # Create category folder: reports/crypto/YYYY-MM/ or reports/stocks/YYYY-MM/
        month_str = target_date.strftime("%Y-%m")
        cat_dir = os.path.join(reports_base_dir, category, month_str)
        os.makedirs(cat_dir, exist_ok=True)
        
        filename = f"{target_date.date()}.txt"
        filepath = os.path.join(cat_dir, filename)
        
        content = "\n".join(reports[category])
        
        with open(filepath, "w") as f:
            f.write(content)
        
        # Return content for printing if needed
    
    return reports

def generate_analysis_report(target_date, base_folder="crypto_history_csv", reports_base_dir="reports"):
    """
    Generates an aggregated analysis report grouping signals by type.
    Saved to reports/analysis/YYYY-MM-DD.txt
    """
    subfolders = ["crypto", "stocks"]
    timeframes = ["1d", "2d", "3d", "1wk", "2wk"]

    # Priority order for sorting
    signal_priority = [
        "Excellent Buy", "Great Buy", "Good Buy",
        "Excellent Sell", "Great Sell", "Good Sell"
    ]
    
    # Structure: { "Excellent Buy": [ (symbol, details, category, timeframe), ... ], ... }
    aggregated_signals = {sig: [] for sig in signal_priority}
    
    has_any_signals = False

    for sub in subfolders:
        category = sub # "crypto" or "stocks"
        
        for tf in timeframes:
            folder_path = os.path.join(base_folder, sub, tf)
            if not os.path.exists(folder_path):
                continue
            
            try:
                files = [f for f in os.listdir(folder_path) if f.endswith("_with_signals.parquet")]
            except FileNotFoundError:
                continue

            for file in files:
                file_path = os.path.join(folder_path, file)
                try:
                    df = pd.read_parquet(file_path)
                except Exception:
                    continue
                
                if "Date" not in df.columns:
                    continue
                
                if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
                    df["Date"] = pd.to_datetime(df["Date"])
                
                mask = df["Date"].dt.normalize() == target_date
                day_rows = df[mask]
                
                if day_rows.empty:
                    continue
                
                for _, row in day_rows.iterrows():
                    signal = row.get("signal")
                    if pd.isna(signal) or signal == "Hold" or signal is None:
                        continue
                    
                    # Clean up signal string just in case
                    signal = str(signal).strip()
                    
                    if signal in aggregated_signals:
                        symbol = file.replace("_with_signals.parquet", "")
                        close = row.get("Close", 0.0)
                        if pd.isna(close): close = 0.0
                        
                        rsi = row.get("rsi", 0.0)
                        if pd.isna(rsi): rsi = 0.0
                        
                        mfi = row.get("mfi", 0.0)
                        if pd.isna(mfi): mfi = 0.0
                        
                        stoch_k = row.get("stoch_rsi_k", 0.0)
                        if pd.isna(stoch_k): stoch_k = 0.0
                        stoch_d = row.get("stoch_rsi_d", 0.0)
                        if pd.isna(stoch_d): stoch_d = 0.0

                        bb_pb = row.get("bb_pband", 0.0)
                        if pd.isna(bb_pb): bb_pb = 0.0

                        macd_h = row.get("macd_hist", 0.0)
                        if pd.isna(macd_h): macd_h = 0.0
                        
                        details = (f"(Price: ${close:,.2f}, RSI: {rsi:.1f}, "
                                   f"MFI: {mfi:.1f}, StochRSI: {stoch_k:.2f}/{stoch_d:.2f}, "
                                   f"BB: {bb_pb:.2f}, MACD: {macd_h:.2f})")
                        
                        aggregated_signals[signal].append({
                            "symbol": symbol,
                            "details": details,
                            "category": category,
                            "timeframe": tf
                        })
                        has_any_signals = True

    # Generate Report Content
    report_lines = []
    report_lines.append(f"Analysis Report for {target_date.date()}\n")
    
    if not has_any_signals:
        report_lines.append("No signals found for this date.")
    else:
        for sig_type in signal_priority:
            items = aggregated_signals[sig_type]
            if items:
                report_lines.append(f"### {sig_type}")
                # Sort by symbol within the group
                items.sort(key=lambda x: x["symbol"])
                
                for item in items:
                    # Format: SYMBOL [Category/TF] Details
                    line = (f"{item['symbol']:<10} [{item['category'].capitalize()}/{item['timeframe']}] "
                            f"{item['details']}")
                    report_lines.append(line)
                report_lines.append("") # Empty line after group

    # Save Report
    analysis_dir = os.path.join(reports_base_dir, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    
    filename = f"{target_date.date()}.txt"
    filepath = os.path.join(analysis_dir, filename)
    
    with open(filepath, "w") as f:
        f.write("\n".join(report_lines))
        
    return report_lines

def main():
    parser = argparse.ArgumentParser(description="Generate daily crypto/stock signal report.")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD). Defaults to today.", default=None)
    parser.add_argument("--backfill", action="store_true", help="Generate reports for the last N days.")
    parser.add_argument("--days", type=int, default=60, help="Number of days to backfill (default: 60).")
    
    args = parser.parse_args()
    
    base_folder = "crypto_history_csv"
    reports_base_dir = "reports"

    if args.backfill:
        print(f"Starting backfill for the last {args.days} days...")
        end_date = pd.Timestamp.now().normalize()
        start_date = end_date - timedelta(days=args.days)
        
        current = start_date
        current = start_date
        while current <= end_date:
            # Skip if day hasn't closed (current date >= today)
            if current.date() >= pd.Timestamp.now().date():
                print(f"Skipping {current.date()} (Day not closed)")
                current += timedelta(days=1)
                continue

            generate_report_for_date(current, base_folder, reports_base_dir)
            generate_analysis_report(current, base_folder, reports_base_dir)
            current += timedelta(days=1)
        print("Backfill complete.")
        
    else:
        if args.date:
            try:
                target_date = pd.to_datetime(args.date).normalize()
            except ValueError:
                print(f"Error: Invalid date format '{args.date}'. Please use YYYY-MM-DD.")
                sys.exit(1)
        else:
            # Default to yesterday to ensure we report on the last CLOSED candle
            target_date = (pd.Timestamp.now() - timedelta(days=1)).normalize()
            
        # Check if target_date has closed
        if target_date.date() >= pd.Timestamp.now().date():
            print(f"Skipping report for {target_date.date()} because the day has not closed yet.")
            sys.exit(0)

        reports = generate_report_for_date(target_date, base_folder, reports_base_dir)
        analysis_lines = generate_analysis_report(target_date, base_folder, reports_base_dir)
        
        # Print to console for single-day run
        print(f"--- Crypto Report ({target_date.date()}) ---")
        print("\n".join(reports["crypto"]))
        print("\n" + "="*40 + "\n")
        print(f"--- Stocks Report ({target_date.date()}) ---")
        print("\n".join(reports["stocks"]))
        print("\n" + "="*40 + "\n")
        print(f"--- Analysis Report ({target_date.date()}) ---")
        print("\n".join(analysis_lines))
        
        print(f"\nReports saved to {reports_base_dir}/crypto/, {reports_base_dir}/stocks/, and {reports_base_dir}/analysis/")

if __name__ == "__main__":
    main()
