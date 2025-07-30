#!/usr/bin/env python3
import os
import sys
import hashlib
import yaml
from PIL import Image, ImageDraw, ImageFont
import platform


# Load configuration from YAML file
def load_config(config_path):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)




def generate_image_from_text(text_rows, config):
    """Generate an image with multi-line text without cutting off the last line."""
    # Read image settings from config
    width = config.get("width", 800)
    height = config.get("height", 480)
    bg_color = config.get("background_color", "white")
    text_color = config.get("text_color", "black")
    max_font_size = config.get("max_font_size", 100)
    min_font_size = config.get("min_font_size", 20)
    if platform.system().lower() == "linux" and ("arm" in platform.machine() or "aarch64" in platform.machine()):
        print('Using Raspberry Pi font')
        font_path = "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf"
    else:
        font_path = config.get("font_path", "/Library/Fonts/Arial Unicode.ttf")
    show_boxes = config.get("show_boxes", True)
    
    # Margins and line spacing
    margin = 20
    line_spacing = 2

    # Create a blank image
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    def wrap_text(lines, font, max_width):
        return lines  # already in (buy, sell, msg) format

    # Split text_rows into separate columns
    buy_lines = [row[0] for row in text_rows]
    sell_lines = [row[1] for row in text_rows]
    msg_lines = [row[2] for row in text_rows]

    col_width = width // 3
    box_height = height - 2 * margin

    def fits_in_box(font, lines, box_width, box_height):
        ascent, descent = font.getmetrics()
        line_height = ascent + descent
        total_text_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
        if total_text_height > box_height:
            return False
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            if line_width > (box_width - 2 * margin):
                return False
        return True

    def find_font_for_column(lines, box_width, box_height):
        size = max_font_size
        while size >= min_font_size:
            try:
                font = ImageFont.truetype(font_path, size)
            except OSError:
                print(f"WARNING: Could not open font at {font_path}. Falling back to default font.")
                return ImageFont.load_default()
            wrapped_lines = wrap_text(lines, font, box_width - 2 * margin)
            if fits_in_box(font, wrapped_lines, box_width, box_height):
                return font
            size -= 1
        try:
            return ImageFont.truetype(font_path, min_font_size)
        except OSError:
            print(f"WARNING: Could not open fallback font at {font_path}. Using default font.")
            return ImageFont.load_default()

    font_buy = find_font_for_column(buy_lines, col_width, box_height)
    font_sell = find_font_for_column(sell_lines, col_width, box_height)
    font_msg = find_font_for_column(msg_lines, col_width, box_height)

    # Use font metrics to determine line height (use max of three fonts)
    ascent_buy, descent_buy = font_buy.getmetrics()
    ascent_sell, descent_sell = font_sell.getmetrics()
    ascent_msg, descent_msg = font_msg.getmetrics()
    line_height = max(ascent_buy + descent_buy, ascent_sell + descent_sell, ascent_msg + descent_msg)

    # Coordinates for boxes (3 columns)
    box_y_start = margin
    box_y_end = box_y_start + box_height

    # Draw only the two middle vertical lines if show_boxes is True
    if show_boxes:
        for i in [1, 2]:
            x = i * col_width
            draw.line([(x, box_y_start), (x, box_y_end)], fill="black", width=2)

    # Determine maximum rows to display
    row_start_y = box_y_start + margin
    row_height = line_height + line_spacing
    max_rows = (box_y_end - row_start_y) // row_height

    # Display each row
    for idx in range(min(len(text_rows), max_rows)):
        buy_text, sell_text, msg_text = text_rows[idx]
        draw.text((10, row_start_y + idx * row_height), buy_text, fill=text_color, font=font_buy)
        draw.text((col_width + 10, row_start_y + idx * row_height), sell_text, fill=text_color, font=font_sell)
        draw.text((2 * col_width + 10, row_start_y + idx * row_height), msg_text, fill=text_color, font=font_msg)

    return img

def images_are_equal(img1, img2):
    """Compare two images by hashing their byte content."""
    hash1 = hashlib.md5(img1.tobytes()).hexdigest()
    hash2 = hashlib.md5(img2.tobytes()).hexdigest()
    return hash1 == hash2

def update_eink_display(new_img, output_path="eink_display.bmp"):
    """
    Compare the new image to the current file.
    Only update (overwrite) if they are different.
    """
    if os.path.exists(output_path):
        try:
            current_img = Image.open(output_path)
            if images_are_equal(current_img, new_img):
                print("No update needed; images are identical.")
                return False
        except Exception as e:
            print("Error comparing images:", e)
    new_img.save(output_path)
    print("E‑ink display updated with new image.")
    return True

def generate_crypto_signal_image(buy_signals, sell_signals, price_data, config):
    """
    buy_signals: string of crypto pairs to buy
    sell_signals: string of crypto pairs to sell
    price_data: string lines of price info
    config: loaded YAML config
    """
    from datetime import datetime

    # Prepare content for each column, preserving whitespace and not stripping text
    buy_lines = [line for line in buy_signals.splitlines() if line.strip()]
    sell_lines = [line for line in sell_signals.splitlines() if line.strip()]

    # Combine messages as single string line(s)
    msg_lines = [line for line in price_data.splitlines() if line.strip()]
    # Append timestamp line
    msg_lines.append(datetime.utcnow().strftime("%H:%M:%S • %m-%d-%Y UTC"))

    # Build signal_text as aligned tuples for rendering
    max_len = max(len(buy_lines), len(sell_lines), len(msg_lines))
    buy_lines += [""] * (max_len - len(buy_lines))
    sell_lines += [""] * (max_len - len(sell_lines))
    msg_lines += [""] * (max_len - len(msg_lines))
    signal_rows = list(zip(buy_lines, sell_lines, msg_lines))

    # Generate image from composed text
    new_img = generate_image_from_text(signal_rows, config)
    update_eink_display(new_img, config.get("output_path") or "eink_display.bmp")
    return config.get("output_path")


def main():
    config = load_config("cryptos.yml")
    
    # Example placeholder signal and price data
    buy_signals = """Sell
Good:
  LTC-USD

Great:
  ETH-USD
  ADA-USD

Excellent:
  XRP-USD
"""
    sell_signals = """Sell
Good:
  LTC-USD

Great:
  ETH-USD
  ADA-USD

Excellent:
  XRP-USD
"""
    price_data = """BTC $64820.45
XRP $0.6231
XLM $0.1285
HBAR $0.0679
BTC $64820.45
XRP $0.6231
XLM $0.1285
HBAR $0.0679
BTC $64820.45
XRP $0.6231
XLM $0.1285
HBAR $0.0679
BTC $64820.45
"""

    generate_crypto_signal_image(buy_signals, sell_signals, price_data, config)

if __name__ == "__main__":
    main()