#!/usr/bin/env python3
"""
Signal Monitor Agent
Scans for Excellent-tier signals across all assets and timeframes,
then generates Claude commentary on each one.

Usage:
    ANTHROPIC_API_KEY=... poetry run python agents/signal_monitor_agent.py
"""

import os
import sys
import pandas as pd
import anthropic

BASE_DATA = "crypto_history_csv"
TIMEFRAMES = ["1d", "2d", "3d", "1wk", "2wk"]
EXCELLENT_SIGNALS = {"Excellent Buy", "Excellent Sell"}
MODEL = "claude-sonnet-4-6"


def find_excellent_signals():
    """Scan all parquet files and return list of recent Excellent-tier signals."""
    found = []
    for asset_class in ("crypto", "stocks"):
        base = os.path.join(BASE_DATA, asset_class)
        for tf in TIMEFRAMES:
            tf_folder = os.path.join(base, tf)
            if not os.path.exists(tf_folder):
                continue
            for fname in os.listdir(tf_folder):
                if not fname.endswith("_with_signals.parquet"):
                    continue
                symbol = fname.replace("_with_signals.parquet", "")
                path = os.path.join(tf_folder, fname)
                try:
                    df = pd.read_parquet(path)
                    if df.empty:
                        continue
                    latest = df.iloc[-1]
                    signal = latest.get("signal", "Hold")
                    if signal in EXCELLENT_SIGNALS:
                        found.append({
                            "symbol": symbol,
                            "asset_class": asset_class,
                            "timeframe": tf,
                            "signal": signal,
                            "close": float(latest.get("Close", 0.0)),
                            "rsi": float(latest.get("rsi", 0.0)),
                            "mfi": float(latest.get("mfi", 0.0)),
                            "stoch_rsi": float(latest.get("stoch_rsi", 0.0)),
                            "ma_50": float(latest.get("ma_50", 0.0)) if not pd.isna(latest.get("ma_50", float("nan"))) else None,
                            "ma_200": float(latest.get("ma_200", 0.0)) if not pd.isna(latest.get("ma_200", float("nan"))) else None,
                            "date": str(latest.get("Date", "?")),
                        })
                except Exception:
                    continue
    return found


def get_commentary(signals: list) -> str:
    """Generate Claude commentary for Excellent signals."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set")

    if not signals:
        return "No Excellent-tier signals found at this time."

    client = anthropic.Anthropic(api_key=api_key)

    signal_text = "\n".join(
        f"- {s['symbol']} ({s['asset_class']}/{s['timeframe']}): {s['signal']} | "
        f"Price: ${s['close']:,.4f} | RSI: {s['rsi']:.1f} | MFI: {s['mfi']:.1f} | "
        f"StochRSI: {s['stoch_rsi']:.2f} | Date: {s['date']}"
        for s in signals
    )

    prompt = f"""You are a quantitative trading analyst. The following Excellent-tier signals were detected:

{signal_text}

For each signal, provide:
1. A brief explanation of why this signal is significant
2. Historical context (what Excellent signals typically indicate)
3. Risk factors to consider
4. A one-line action summary

Be concise and data-focused. Total response under 600 words."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main():
    print("Scanning for Excellent-tier signals...")
    signals = find_excellent_signals()
    print(f"Found {len(signals)} Excellent signal(s)")

    if signals:
        for s in signals:
            print(f"  {s['symbol']} ({s['timeframe']}): {s['signal']}")

    print("\nGenerating AI commentary...")
    commentary = get_commentary(signals)
    print("\n" + commentary)


if __name__ == "__main__":
    main()
