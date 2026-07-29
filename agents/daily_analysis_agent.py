#!/usr/bin/env python3
"""
Daily Analysis Agent
Reads today's report + watch/cross feeds → sends to Claude → saves AI analysis.

Usage:
    ANTHROPIC_API_KEY=... poetry run python agents/daily_analysis_agent.py
    ANTHROPIC_API_KEY=... poetry run python agents/daily_analysis_agent.py --date 2025-12-01
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import anthropic

REPORTS_DIR = "reports"
AI_REPORTS_DIR = os.path.join(REPORTS_DIR, "ai_analysis")
MODEL = "claude-sonnet-4-6"


def _read_file_safe(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


def gather_context(target_date: datetime) -> str:
    """Gather all relevant report context for the target date."""
    month_str = target_date.strftime("%Y-%m")
    date_str = target_date.strftime("%Y-%m-%d")

    parts = []

    # Daily crypto report
    crypto_report = _read_file_safe(os.path.join(REPORTS_DIR, "crypto", month_str, f"{date_str}.txt"))
    if crypto_report:
        parts.append(f"=== CRYPTO SIGNALS ({date_str}) ===\n{crypto_report}")

    # Daily stocks report
    stocks_report = _read_file_safe(os.path.join(REPORTS_DIR, "stocks", month_str, f"{date_str}.txt"))
    if stocks_report:
        parts.append(f"=== STOCK SIGNALS ({date_str}) ===\n{stocks_report}")

    # Analysis report
    analysis_report = _read_file_safe(os.path.join(REPORTS_DIR, "analysis", f"{date_str}.txt"))
    if analysis_report:
        parts.append(f"=== AGGREGATED ANALYSIS ({date_str}) ===\n{analysis_report}")

    # Watch feed
    watch_feed = _read_file_safe(os.path.join(REPORTS_DIR, "watch_feed.txt"))
    if watch_feed:
        parts.append(f"=== WATCH LIST (latest) ===\n{watch_feed}")

    # Cross feed
    cross_feed = _read_file_safe(os.path.join(REPORTS_DIR, "cross_feed.txt"))
    if cross_feed:
        parts.append(f"=== CROSS FEED (latest) ===\n{cross_feed}")

    if not parts:
        return f"No report data found for {date_str}."

    return "\n\n".join(parts)


def run_analysis(target_date: datetime) -> str:
    """Send context to Claude and return AI analysis."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    context = gather_context(target_date)
    date_str = target_date.strftime("%Y-%m-%d")

    prompt = f"""You are a crypto and stock market analyst. Below is the signal data for {date_str}.

{context}

Please provide a concise market analysis covering:
1. Notable buy/sell signals and their significance
2. Assets approaching signals (watch list)
3. Overall market sentiment (bull/bear indicators)
4. Key takeaways and any action items for traders

Keep the analysis factual, data-driven, and under 800 words."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def save_analysis(target_date: datetime, analysis: str) -> str:
    """Save AI analysis to file and return path."""
    os.makedirs(AI_REPORTS_DIR, exist_ok=True)
    date_str = target_date.strftime("%Y-%m-%d")
    path = os.path.join(AI_REPORTS_DIR, f"{date_str}.txt")
    with open(path, "w") as f:
        f.write(f"AI Market Analysis — {date_str}\n")
        f.write("=" * 50 + "\n\n")
        f.write(analysis)
    return path


def main():
    parser = argparse.ArgumentParser(description="Daily AI market analysis agent")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD), defaults to yesterday")
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)

    print(f"Running daily analysis for {target_date.strftime('%Y-%m-%d')}...")
    analysis = run_analysis(target_date)
    path = save_analysis(target_date, analysis)
    print(f"Analysis saved to {path}")
    print("\n" + analysis)


if __name__ == "__main__":
    main()
