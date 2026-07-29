#!/usr/bin/env python3
"""
E-Ink Bull/Bear Grid Display (B&W)
Renders an 800x480 grid showing bull/bear status for each symbol across timeframes.
Supports both crypto and stocks. Outputs black-and-white for B&W e-ink panels.
"""

import os
import sys
import platform
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eink_generator import update_eink_display, load_config


TIMEFRAMES = ["1d", "2d", "3d", "1wk", "2wk"]
BASE_DATA = "crypto_history_csv"

IMAGE_WIDTH = 800
IMAGE_HEIGHT = 480

# B&W palette
COLOR_WHITE  = (255, 255, 255)
COLOR_BLACK  = (0,   0,   0)
COLOR_LGRAY  = (220, 220, 220)   # BULL cell background
COLOR_DGRAY  = (80,  80,  80)    # BEAR cell background
COLOR_MGRAY  = (160, 160, 160)   # ? / header background
COLOR_GRID   = (120, 120, 120)


def classify_bull_bear(ma_50, ma_200, threshold_pct=0.02):
    """Classify market condition based on MA crossover."""
    if pd.isna(ma_50) or pd.isna(ma_200) or ma_200 == 0:
        return "?"
    ratio = (ma_50 - ma_200) / ma_200
    if ratio > threshold_pct:
        return "BULL"
    elif ratio < -threshold_pct:
        return "BEAR"
    return "?"


def get_bull_bear_data(symbols, asset_class, timeframes=TIMEFRAMES):
    """
    Returns a dict: { symbol: { timeframe: "BULL"/"BEAR"/"?" } }
    Missing parquet files gracefully return "?".
    """
    base_folder = os.path.join(BASE_DATA, asset_class)
    results = {}
    for symbol in symbols:
        results[symbol] = {}
        for tf in timeframes:
            path = os.path.join(base_folder, tf, f"{symbol}_with_signals.parquet")
            if not os.path.exists(path):
                results[symbol][tf] = "?"
                continue
            try:
                df = pd.read_parquet(path)
                if df.empty:
                    results[symbol][tf] = "?"
                    continue
                latest = df.iloc[-1]
                ma_50  = latest.get("ma_50",  float("nan"))
                ma_200 = latest.get("ma_200", float("nan"))
                results[symbol][tf] = classify_bull_bear(ma_50, ma_200)
            except Exception:
                results[symbol][tf] = "?"
    return results


def _get_font(size):
    """Load platform-appropriate font."""
    if platform.system() == "Darwin":
        candidates = [
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    for fp in candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_bull_bear_grid_image(symbols, asset_class="crypto", timeframes=TIMEFRAMES):
    """
    Generate the 800x480 B&W bull/bear grid image and return PIL Image.

    Cell styling:
      BULL → light gray background, black text
      BEAR → dark gray background, white text
      ?    → medium gray background, black text
    """
    data = get_bull_bear_data(symbols, asset_class, timeframes)

    img  = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), COLOR_WHITE)
    draw = ImageDraw.Draw(img)

    # Layout
    left_margin = 52
    top_margin  = 38
    n_cols = len(symbols)
    n_rows = len(timeframes)
    cell_w = (IMAGE_WIDTH  - left_margin) // n_cols
    cell_h = (IMAGE_HEIGHT - top_margin)  // n_rows

    font_hdr  = _get_font(12)
    font_cell = _get_font(11)
    font_tf   = _get_font(11)

    # ── Header row (symbol names) ──────────────────────────────────────────
    draw.rectangle([(0, 0), (IMAGE_WIDTH, top_margin - 1)], fill=COLOR_BLACK)
    # Corner (above TF labels)
    draw.rectangle([(0, 0), (left_margin - 1, top_margin - 1)], fill=COLOR_BLACK)

    for col_idx, symbol in enumerate(symbols):
        x = left_margin + col_idx * cell_w + cell_w // 2
        label = symbol.replace("-USD", "")
        draw.text((x, top_margin // 2), label, font=font_hdr,
                  fill=COLOR_WHITE, anchor="mm")

    # ── Rows ───────────────────────────────────────────────────────────────
    for row_idx, tf in enumerate(timeframes):
        y_top = top_margin + row_idx * cell_h
        y_mid = y_top + cell_h // 2

        # TF label column
        draw.rectangle([(0, y_top), (left_margin - 1, y_top + cell_h - 1)],
                       fill=COLOR_MGRAY)
        draw.text((left_margin // 2, y_mid), tf, font=font_tf,
                  fill=COLOR_BLACK, anchor="mm")

        for col_idx, symbol in enumerate(symbols):
            x_left = left_margin + col_idx * cell_w
            x_right = x_left + cell_w
            x_mid   = x_left + cell_w // 2

            status = data.get(symbol, {}).get(tf, "?")

            if status == "BULL":
                cell_bg  = COLOR_LGRAY
                txt_color = COLOR_BLACK
            elif status == "BEAR":
                cell_bg  = COLOR_DGRAY
                txt_color = COLOR_WHITE
            else:
                cell_bg  = COLOR_MGRAY
                txt_color = COLOR_BLACK

            draw.rectangle(
                [(x_left + 1, y_top + 1), (x_right - 1, y_top + cell_h - 1)],
                fill=cell_bg,
            )
            draw.text((x_mid, y_mid), status, font=font_cell,
                      fill=txt_color, anchor="mm")

    # ── Grid lines ─────────────────────────────────────────────────────────
    for row_idx in range(n_rows + 1):
        y = top_margin + row_idx * cell_h
        draw.line([(0, y), (IMAGE_WIDTH, y)], fill=COLOR_GRID, width=1)

    for col_idx in range(n_cols + 1):
        x = left_margin + col_idx * cell_w
        draw.line([(x, 0), (x, IMAGE_HEIGHT)], fill=COLOR_GRID, width=1)

    # Outer border
    draw.rectangle([(0, 0), (IMAGE_WIDTH - 1, IMAGE_HEIGHT - 1)],
                   outline=COLOR_BLACK, width=2)

    return img


def main():
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "cryptos.yml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Support crypto and/or stocks via CLI arg: --crypto | --stocks (default: crypto)
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks", action="store_true", help="Render stocks grid instead of crypto")
    args = parser.parse_args()

    if args.stocks:
        symbols = config.get("stocks", [])
        asset_class = "stocks"
        default_out = "bull_bear_grid_stocks.bmp"
    else:
        symbols = config.get("cryptos", [])
        asset_class = "crypto"
        default_out = "bull_bear_grid.bmp"

    if not symbols:
        print(f"No {asset_class} symbols found in cryptos.yml")
        return

    output_path = config.get(
        "bull_bear_grid_output",
        os.path.join(os.path.dirname(__file__), default_out),
    )

    img = generate_bull_bear_grid_image(symbols, asset_class)
    update_eink_display(img, output_path)
    print(f"Bull/bear grid ({asset_class}) saved to {output_path}")


if __name__ == "__main__":
    main()
