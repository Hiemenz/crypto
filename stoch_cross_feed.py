#!/usr/bin/env python3
"""
Stochastic RSI Cross Feed Generator
Identifies 1-week StochRSI K/D crosses (golden/death crosses).
"""

import os
import pandas as pd
from datetime import datetime
import db


def generate_stoch_cross_feed():
    """
    Scan 1wk signals for StochRSI K/D crosses.

    Golden Cross: K crosses above D (bullish)
    Death Cross: K crosses below D (bearish)
    """

    crosses = []

    for category in ["crypto", "stocks"]:
        symbol_pairs = db.list_symbols(category=category, timeframe="1wk")
        for symbol, _ in symbol_pairs:
            try:
                df = db.load_signals(symbol, category, "1wk")
                if len(df) < 2:
                    continue

                df = df.sort_values("Date")

                prev_k = df["stoch_rsi_k"].shift(1)
                prev_d = df["stoch_rsi_d"].shift(1)
                curr_k = df["stoch_rsi_k"]
                curr_d = df["stoch_rsi_d"]

                golden_mask = (prev_k < prev_d) & (curr_k > curr_d)
                death_mask = (prev_k > prev_d) & (curr_k < curr_d)

                for _, row in df[golden_mask].iterrows():
                    k = row.get("stoch_rsi_k", 0) or 0
                    d = row.get("stoch_rsi_d", 0) or 0
                    cross_type = "Confirmed Golden Cross" if k > 0.2 and d > 0.2 else "Golden Cross"
                    crosses.append({
                        "category": category,
                        "symbol": symbol,
                        "type": cross_type,
                        "price": row.get("Close", 0) or 0,
                        "k": k,
                        "d": d,
                        "date": row["Date"],
                    })

                for _, row in df[death_mask].iterrows():
                    k = row.get("stoch_rsi_k", 0) or 0
                    d = row.get("stoch_rsi_d", 0) or 0
                    cross_type = "Confirmed Death Cross" if k < 0.8 and d < 0.8 else "Death Cross"
                    crosses.append({
                        "category": category,
                        "symbol": symbol,
                        "type": cross_type,
                        "price": row.get("Close", 0) or 0,
                        "k": k,
                        "d": d,
                        "date": row["Date"],
                    })

            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                continue

    # Filter for last 3 months
    cutoff_date = datetime.now() - pd.Timedelta(days=90)
    crosses = [c for c in crosses if c["date"] >= cutoff_date]

    crosses.sort(key=lambda x: x["date"], reverse=True)

    os.makedirs("reports", exist_ok=True)
    report_path = "reports/stoch_cross_feed.txt"

    with open(report_path, "w") as f:
        f.write(f"1-Week StochRSI Crosses\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("There is roughly one stochastic RSI cross per year.\n")
        f.write("=" * 80 + "\n\n")

        if not crosses:
            f.write("No StochRSI crosses detected in the last 3 months.\n")
        else:
            for category in ["crypto", "stocks"]:
                cat_crosses = [c for c in crosses if c["category"] == category]
                if not cat_crosses:
                    continue

                f.write(f"\n--- {category.upper()} ---\n\n")

                for cross_type in ["Confirmed Golden Cross", "Golden Cross", "Confirmed Death Cross", "Death Cross"]:
                    type_crosses = [c for c in cat_crosses if c["type"] == cross_type]
                    if not type_crosses:
                        continue

                    f.write(f"[{cross_type}]\n")
                    for cross in type_crosses:
                        d_str = pd.to_datetime(cross['date']).strftime('%Y-%m-%d')
                        mark = "✅ " if "Confirmed" in cross_type else ""
                        f.write(f"{mark}{cross['symbol']:<10} {d_str} "
                               f"(Price: ${cross['price']:,.2f}, K: {cross['k']:.2f}, D: {cross['d']:.2f})\n")
                    f.write("\n")

    print(f"Stoch cross feed generated: {report_path}")
    print(f"Found {len(crosses)} crosses in the last 3 months")


if __name__ == "__main__":
    generate_stoch_cross_feed()
