#!/usr/bin/env python3
"""
Watch Feed Generator
Identifies assets that are "near" a buy or sell signal based on the strategy.
"""

import os
import pandas as pd
from datetime import datetime
import db


def generate_watch_feed():
    """
    Scan all assets and identify those that are close to triggering a signal.

    Near Buy Criteria (in Bear Market):
    - RSI between 30-45 OR
    - MFI between 20-35 OR
    - StochRSI between 0.2-0.4

    Near Sell Criteria (in Bull Market):
    - RSI between 55-70 OR
    - MFI between 65-80 OR
    - StochRSI between 0.6-0.8
    """

    timeframes = ["1d", "2d", "3d", "1wk", "2wk"]
    watch_items = []

    for category in ["crypto", "stocks"]:
        for tf in timeframes:
            symbol_pairs = db.list_symbols(category=category, timeframe=tf)
            for symbol, _ in symbol_pairs:
                try:
                    latest = db.load_signals_latest_row(symbol, category, tf)
                    if latest is None:
                        continue

                    rsi = latest.get("rsi", 0) or 0
                    mfi = latest.get("mfi", 0) or 0
                    stoch_rsi = latest.get("stoch_rsi", 0) or 0
                    is_bull = bool(latest.get("is_bull", False))
                    close = latest.get("Close", 0) or latest.get("close", 0) or 0
                    signal = latest.get("signal", "Hold") or "Hold"

                    if signal != "Hold":
                        continue

                    near_type = None
                    reason = []

                    if not is_bull:
                        if 30 <= rsi <= 45:
                            reason.append(f"RSI: {rsi:.1f}")
                        if 20 <= mfi <= 35:
                            reason.append(f"MFI: {mfi:.1f}")
                        if 0.2 <= stoch_rsi <= 0.4:
                            reason.append(f"StochRSI: {stoch_rsi:.2f}")
                        if reason:
                            near_type = "Near Buy"

                    if is_bull:
                        if 55 <= rsi <= 70:
                            reason.append(f"RSI: {rsi:.1f}")
                        if 65 <= mfi <= 80:
                            reason.append(f"MFI: {mfi:.1f}")
                        if 0.6 <= stoch_rsi <= 0.8:
                            reason.append(f"StochRSI: {stoch_rsi:.2f}")
                        if reason:
                            near_type = "Near Sell"

                    if near_type:
                        watch_items.append({
                            "category": category,
                            "symbol": symbol,
                            "timeframe": tf,
                            "type": near_type,
                            "price": close,
                            "reason": ", ".join(reason),
                            "market": "Bull" if is_bull else "Bear",
                        })

                except Exception as e:
                    print(f"Error processing {symbol} ({tf}): {e}")
                    continue

    os.makedirs("reports", exist_ok=True)
    report_path = "reports/watch_feed.txt"

    with open(report_path, "w") as f:
        f.write(f"Watch List - Assets Near Signals\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        if not watch_items:
            f.write("No assets currently near signals.\n")
        else:
            for category in ["crypto", "stocks"]:
                cat_items = [item for item in watch_items if item["category"] == category]
                if not cat_items:
                    continue

                f.write(f"\n--- {category.upper()} ---\n\n")

                for tf in timeframes:
                    tf_items = [item for item in cat_items if item["timeframe"] == tf]
                    if not tf_items:
                        continue

                    f.write(f"[{tf}]\n")
                    for item in tf_items:
                        f.write(f"{item['symbol']:<10} {item['type']:<15} "
                               f"(Price: ${item['price']:,.2f}, {item['reason']}, Market: {item['market']})\n")
                    f.write("\n")

    print(f"Watch feed generated: {report_path}")
    print(f"Found {len(watch_items)} assets near signals")


if __name__ == "__main__":
    generate_watch_feed()
