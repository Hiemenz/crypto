#!/usr/bin/env python3
"""
Discord Bot for Crypto Signal Station
Commands: !signals, !bull_bear, !price, !report, !cross, !watch
"""

import os
import sys
import glob
import discord
from discord.ext import commands
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eink_bull_bear_grid import classify_bull_bear, TIMEFRAMES

BASE_DATA = "crypto_history_csv"
REPORTS_DIR = "reports"
DISCORD_CHAR_LIMIT = 2000


def _chunk_send(text):
    """Split text into <=2000-char chunks for Discord."""
    chunks = []
    while len(text) > DISCORD_CHAR_LIMIT:
        split_at = text.rfind("\n", 0, DISCORD_CHAR_LIMIT)
        if split_at == -1:
            split_at = DISCORD_CHAR_LIMIT
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)
    return chunks


def _get_latest_parquet(symbol, asset_class="crypto", timeframe="1d"):
    path = os.path.join(BASE_DATA, asset_class, timeframe, f"{symbol}_with_signals.parquet")
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command(name="signals")
async def cmd_signals(ctx, symbol: str = "BTC-USD"):
    """Show the latest signal for each timeframe for a symbol."""
    symbol = symbol.upper()
    lines = [f"**Signals for {symbol}**"]

    for tf in TIMEFRAMES:
        for asset_class in ("crypto", "stocks"):
            df = _get_latest_parquet(symbol, asset_class, tf)
            if df is not None:
                break
        else:
            lines.append(f"`{tf}`: no data")
            continue

        latest = df.iloc[-1]
        signal = latest.get("signal", "N/A")
        close = latest.get("Close", 0.0)
        date = latest.get("Date", "?")
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")
        lines.append(f"`{tf}` ({date}): **{signal}** @ ${close:,.2f}")

    text = "\n".join(lines)
    for chunk in _chunk_send(text):
        await ctx.send(chunk)


@bot.command(name="bull_bear")
async def cmd_bull_bear(ctx):
    """Text summary of the bull/bear grid across crypto assets."""
    import yaml
    try:
        with open(os.path.join(os.path.dirname(__file__), "cryptos.yml"), "r") as f:
            config = yaml.safe_load(f)
        symbols = config.get("cryptos", [])
    except Exception:
        await ctx.send("Could not load cryptos.yml")
        return

    lines = ["**Bull/Bear Grid**", "```"]
    header = "       " + "  ".join(s.replace("-USD", "").ljust(4) for s in symbols)
    lines.append(header)

    for tf in TIMEFRAMES:
        row_parts = [tf.ljust(5)]
        for symbol in symbols:
            path = os.path.join(BASE_DATA, "crypto", tf, f"{symbol}_with_signals.parquet")
            status = "?   "
            if os.path.exists(path):
                try:
                    df = pd.read_parquet(path)
                    if not df.empty:
                        latest = df.iloc[-1]
                        ma50 = latest.get("ma_50", float("nan"))
                        ma200 = latest.get("ma_200", float("nan"))
                        s = classify_bull_bear(ma50, ma200)
                        status = s.ljust(4)
                except Exception:
                    pass
            row_parts.append(status + " ")
        lines.append("  ".join(row_parts))

    lines.append("```")
    text = "\n".join(lines)
    for chunk in _chunk_send(text):
        await ctx.send(chunk)


@bot.command(name="price")
async def cmd_price(ctx, symbol: str = "BTC-USD"):
    """Show the latest close price for a symbol."""
    symbol = symbol.upper()
    for asset_class in ("crypto", "stocks"):
        df = _get_latest_parquet(symbol, asset_class, "1d")
        if df is not None:
            latest = df.iloc[-1]
            close = latest.get("Close", None)
            date = latest.get("Date", "?")
            if hasattr(date, "strftime"):
                date = date.strftime("%Y-%m-%d")
            if close is not None:
                await ctx.send(f"**{symbol}** — ${float(close):,.4f} (as of {date})")
                return
    await ctx.send(f"No price data found for `{symbol}`")


@bot.command(name="report")
async def cmd_report(ctx, date_str: str = None):
    """Show today's (or a specific date's) crypto report."""
    if date_str:
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            await ctx.send("Date format should be YYYY-MM-DD")
            return
    else:
        target = datetime.now() - timedelta(days=1)

    month_str = target.strftime("%Y-%m")
    date_file = target.strftime("%Y-%m-%d") + ".txt"
    report_path = os.path.join(REPORTS_DIR, "crypto", month_str, date_file)

    if not os.path.exists(report_path):
        await ctx.send(f"No report found for {target.strftime('%Y-%m-%d')}")
        return

    with open(report_path, "r") as f:
        content = f.read()

    for chunk in _chunk_send(content):
        await ctx.send(f"```\n{chunk}\n```")


@bot.command(name="cross")
async def cmd_cross(ctx):
    """Show golden/death crosses from cross_feed report."""
    path = os.path.join(REPORTS_DIR, "cross_feed.txt")
    if not os.path.exists(path):
        await ctx.send("No cross_feed.txt found.")
        return
    with open(path, "r") as f:
        content = f.read()
    for chunk in _chunk_send(content):
        await ctx.send(f"```\n{chunk}\n```")


@bot.command(name="watch")
async def cmd_watch(ctx):
    """Show near-signal assets from watch_feed report."""
    path = os.path.join(REPORTS_DIR, "watch_feed.txt")
    if not os.path.exists(path):
        await ctx.send("No watch_feed.txt found.")
        return
    with open(path, "r") as f:
        content = f.read()
    for chunk in _chunk_send(content):
        await ctx.send(f"```\n{chunk}\n```")


@bot.event
async def on_ready():
    print(f"Discord bot logged in as {bot.user} (ID: {bot.user.id})")


def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN environment variable not set.")
        sys.exit(1)
    bot.run(token)


if __name__ == "__main__":
    main()
