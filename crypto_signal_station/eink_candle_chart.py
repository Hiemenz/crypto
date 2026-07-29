#!/usr/bin/env python3
"""
E-Ink Candlestick Chart Display
Renders a full 800x480 candlestick chart with MA overlays for a rotating set of symbols.
"""

import os
import sys
import json
import platform
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from io import BytesIO
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eink_generator import update_eink_display, load_config

IMAGE_WIDTH = 800
IMAGE_HEIGHT = 480
BASE_DATA_FOLDER = "crypto_history_csv/crypto/1d"
STATE_FILE = os.path.join(os.path.dirname(__file__), "candle_chart_state.json")
DAYS_OF_HISTORY = 365


def _load_state(symbols):
    """Load or initialize symbol rotation state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            idx = state.get("index", 0)
            return idx % len(symbols)
        except Exception:
            pass
    return 0


def _save_state(index):
    """Persist the current symbol index."""
    with open(STATE_FILE, "w") as f:
        json.dump({"index": index}, f)


def generate_candle_chart_image(symbol, base_folder=BASE_DATA_FOLDER):
    """Generate an 800x480 PIL Image with a candlestick chart for the given symbol."""
    path = os.path.join(base_folder, f"{symbol}_with_signals.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No data file found: {path}")

    df = pd.read_parquet(path)
    if df.empty:
        raise ValueError(f"Empty dataframe for {symbol}")

    if "Date" not in df.columns:
        raise ValueError("No Date column in parquet")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    # Limit to last DAYS_OF_HISTORY days
    cutoff = df["Date"].max() - pd.Timedelta(days=DAYS_OF_HISTORY)
    df = df[df["Date"] >= cutoff].copy()

    if df.empty:
        raise ValueError(f"No data in last {DAYS_OF_HISTORY} days for {symbol}")

    fig, ax = plt.subplots(figsize=(IMAGE_WIDTH / 100, IMAGE_HEIGHT / 100), dpi=100)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Draw candlestick bars
    for _, row in df.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        date = row["Date"]
        color = "green" if c >= o else "red"

        # Wick
        ax.plot([date, date], [l, h], color=color, linewidth=0.6, zorder=1)

        # Body
        body_bottom = min(o, c)
        body_height = abs(c - o) if abs(c - o) > 0 else (h - l) * 0.01
        rect = mpatches.FancyBboxPatch(
            (matplotlib.dates.date2num(date.to_pydatetime()) - 0.4, body_bottom),
            0.8,
            body_height,
            boxstyle="square,pad=0",
            facecolor=color,
            edgecolor=color,
            linewidth=0.3,
            zorder=2,
        )
        ax.add_patch(rect)

    # MA overlays
    if "ma_50" in df.columns:
        ax.plot(df["Date"], df["ma_50"], color="blue", linewidth=1.2, label="50 MA", zorder=3)
    if "ma_200" in df.columns:
        ax.plot(df["Date"], df["ma_200"], color="orange", linewidth=1.2, label="200 MA", zorder=3)

    ax.set_title(f"{symbol} — 1D ({df['Date'].min().strftime('%Y-%m-%d')} to {df['Date'].max().strftime('%Y-%m-%d')})",
                 fontsize=9)
    ax.set_xlabel("")
    ax.set_ylabel("Price (USD)", fontsize=8)
    ax.tick_params(axis="both", labelsize=7)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.6)

    plt.tight_layout(pad=0.5)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)

    pil_img = Image.open(buf).convert("RGB")
    pil_img = pil_img.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.LANCZOS)
    return pil_img


def main():
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "cryptos.yml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    symbols = config.get("cryptos", [])
    if not symbols:
        print("No crypto symbols found in cryptos.yml")
        return

    output_path = config.get("candle_chart_output", os.path.join(os.path.dirname(__file__), "candle_chart.bmp"))

    idx = _load_state(symbols)
    symbol = symbols[idx]
    print(f"Rendering candle chart for {symbol} ({idx + 1}/{len(symbols)})")

    img = generate_candle_chart_image(symbol)
    update_eink_display(img, output_path)
    print(f"Candle chart saved to {output_path}")

    _save_state((idx + 1) % len(symbols))


if __name__ == "__main__":
    main()
