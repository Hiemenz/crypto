import os
import pandas as pd
from datetime import datetime, timedelta
import db


def generate_cross_feed(output_file="reports/cross_feed.txt"):
    """
    Scans all 1d signals for Golden/Death crosses in the last 365 days.
    Saves a sorted list of events to output_file.
    """
    print("Generating Golden/Death Cross Feed...")

    events = []
    cutoff_date = pd.Timestamp.now().normalize() - timedelta(days=365)

    for category in ["crypto", "stocks"]:
        symbol_pairs = db.list_symbols(category=category, timeframe="1d")
        for symbol, _ in symbol_pairs:
            try:
                df = db.load_signals(symbol, category, "1d")
            except Exception:
                continue

            if df.empty or "ma_50" not in df.columns or "ma_200" not in df.columns:
                continue

            df = df.sort_values("Date")
            df = df[df["Date"] >= (cutoff_date - timedelta(days=1))]

            if len(df) < 2:
                continue

            prev_ma50 = df["ma_50"].shift(1)
            prev_ma200 = df["ma_200"].shift(1)
            curr_ma50 = df["ma_50"]
            curr_ma200 = df["ma_200"]

            golden_mask = (prev_ma50 <= prev_ma200) & (curr_ma50 > curr_ma200)
            death_mask = (prev_ma50 >= prev_ma200) & (curr_ma50 < curr_ma200)

            for _, row in df[golden_mask].iterrows():
                events.append({
                    "date": row["Date"],
                    "symbol": symbol,
                    "type": "Golden Cross",
                    "category": category,
                    "price": row["Close"],
                })

            for _, row in df[death_mask].iterrows():
                events.append({
                    "date": row["Date"],
                    "symbol": symbol,
                    "type": "Death Cross",
                    "category": category,
                    "price": row["Close"],
                })

    events.sort(key=lambda x: x["date"], reverse=True)

    lines = []
    lines.append(f"Cross Feed Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total Events (Last 365 Days): {len(events)}")
    lines.append("")

    for event in events:
        date_str = event["date"].strftime("%Y-%m-%d")
        line = f"{date_str} | {event['symbol']:<8} | {event['type']:<12} | Price: ${event['price']:,.2f}"
        lines.append(line)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"Feed saved to {output_file} ({len(events)} events)")


if __name__ == "__main__":
    generate_cross_feed()
