#!/usr/bin/env python3
"""
Discord Report Agent
Generates a Discord-ready (<1900 char) market summary using Claude.

Usage:
    ANTHROPIC_API_KEY=... poetry run python agents/discord_report_agent.py
    ANTHROPIC_API_KEY=... poetry run python agents/discord_report_agent.py --date 2025-12-01
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import anthropic

REPORTS_DIR = "reports"
MODEL = "claude-sonnet-4-6"
MAX_DISCORD_CHARS = 1900


def _read_file_safe(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


def gather_context(target_date: datetime) -> str:
    """Gather report context for the target date (concise version for Discord)."""
    month_str = target_date.strftime("%Y-%m")
    date_str = target_date.strftime("%Y-%m-%d")

    parts = []

    analysis = _read_file_safe(os.path.join(REPORTS_DIR, "analysis", f"{date_str}.txt"))
    if analysis:
        # Truncate to first 2000 chars to keep prompt manageable
        parts.append(f"=== SIGNALS ({date_str}) ===\n{analysis[:2000]}")

    watch = _read_file_safe(os.path.join(REPORTS_DIR, "watch_feed.txt"))
    if watch:
        parts.append(f"=== WATCH LIST ===\n{watch[:800]}")

    if not parts:
        # Fall back to crypto daily report
        crypto = _read_file_safe(os.path.join(REPORTS_DIR, "crypto", month_str, f"{date_str}.txt"))
        if crypto:
            parts.append(f"=== CRYPTO ({date_str}) ===\n{crypto[:2000]}")

    return "\n\n".join(parts) if parts else f"No data available for {date_str}."


def generate_discord_summary(target_date: datetime) -> str:
    """Generate a Discord-ready market summary."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    context = gather_context(target_date)
    date_str = target_date.strftime("%Y-%m-%d")

    prompt = f"""You are a crypto/stock signal bot posting to Discord. Generate a concise market summary for {date_str}.

Data:
{context}

Rules:
- Maximum 1800 characters total
- Use Discord markdown (** for bold, ` for code)
- Lead with most important signals
- Include watch list highlights if notable
- End with overall sentiment (Bullish/Bearish/Neutral)
- No bullet walls — keep it scannable"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    summary = message.content[0].text

    # Hard truncate to stay under Discord limit
    if len(summary) > MAX_DISCORD_CHARS:
        summary = summary[:MAX_DISCORD_CHARS - 3] + "..."

    return summary


def main():
    parser = argparse.ArgumentParser(description="Generate Discord-ready market summary")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD), defaults to yesterday")
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)

    print(f"Generating Discord summary for {target_date.strftime('%Y-%m-%d')}...")
    summary = generate_discord_summary(target_date)

    print(f"\nSummary ({len(summary)} chars):")
    print("-" * 40)
    print(summary)
    print("-" * 40)


if __name__ == "__main__":
    main()
