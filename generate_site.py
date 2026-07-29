import os
import shutil
import re
from datetime import datetime, timedelta
import glob
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import generate_history  # Import the new module
import db

# Configuration
REPORTS_DIR = "reports"
DOCS_DIR = "docs"
IMAGES_DIR = os.path.join(DOCS_DIR, "images")

# HTML Templates
HTML_HEADER = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Signal Station</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 10px; background-color: #f4f4f9; color: #333; }
        .container { max-width: 100%; margin: 0 auto; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        @media (min-width: 768px) {
            .container { max-width: 1000px; padding: 30px; }
            body { padding: 20px; }
        }
        h1 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; font-size: 1.5em; }
        h2 { color: #34495e; margin-top: 30px; font-size: 1.3em; }
        h3 { color: #7f8c8d; margin-top: 20px; border-bottom: 1px solid #eee; padding-bottom: 5px; }
        .report-link { display: block; padding: 15px; margin: 10px 0; background: #f8f9fa; text-decoration: none; color: #2c3e50; border-radius: 4px; transition: background 0.2s; border: 1px solid #eee; }
        .report-link:hover { background: #e9ecef; border-color: #ddd; }
        .signal-row { padding: 15px 0; border-bottom: 1px solid #f1f1f1; display: flex; flex-direction: column; }
        .signal-row:last-child { border-bottom: none; }
        .signal-info { margin-bottom: 10px; }
        .signal-chart-container { width: 100%; overflow-x: hidden; }
        .tag { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-right: 5px; margin-bottom: 5px; }
        .tag-buy { background-color: #d4edda; color: #155724; }
        .tag-sell { background-color: #f8d7da; color: #721c24; }
        .back-link { display: inline-block; margin-bottom: 20px; color: #666; text-decoration: none; }
        .back-link:hover { text-decoration: underline; }
        .meta { color: #999; font-size: 0.9em; display: block; margin-top: 5px; }
        .history-link { font-size: 0.9em; margin-left: 10px; color: #007bff; text-decoration: none; white-space: nowrap; }
        .history-link:hover { text-decoration: underline; }
        
        /* Nav Bar */
        .nav-bar { margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #eee; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
        .nav-link { text-decoration: none; color: #2c3e50; font-weight: bold; font-size: 1.1em; padding: 5px 0; }
        .nav-link:hover { color: #007bff; }
        .nav-link.active { color: #007bff; border-bottom: 2px solid #007bff; }
        .nav-toggle { display: none; font-size: 1.5em; cursor: pointer; padding: 5px; }
        
        @media (max-width: 768px) {
            .nav-bar { flex-direction: column; align-items: flex-start; gap: 5px; }
            .nav-link { display: none; width: 100%; padding: 10px 0; border-bottom: 1px solid #eee; }
            .nav-toggle { display: block; }
            .nav-bar.responsive .nav-link { display: block; }
        }

        /* Grid for History Index */
        .asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 10px; margin-top: 10px; }
        .asset-link { display: block; padding: 10px; background: #fff; border: 1px solid #ddd; border-radius: 4px; text-align: center; text-decoration: none; color: #2c3e50; font-weight: bold; transition: all 0.2s; }
        .asset-link:hover { background: #007bff; color: white; border-color: #007bff; transform: translateY(-2px); box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        
        /* Swapped Colors: Bull=Red, Bear=Green */
        .asset-bull { background-color: #f8d7da; color: #721c24; border-color: #f5c6cb; } /* Red */
        .asset-bull:hover { background-color: #f5c6cb; color: #721c24; }
        .asset-bear { background-color: #d4edda; color: #155724; border-color: #c3e6cb; } /* Green */
        .asset-bear:hover { background-color: #c3e6cb; color: #155724; }
    </style>
    <script>
    function toggleNav() {
        var x = document.getElementById("myTopnav");
        if (x.className.includes("responsive")) {
            x.className = "nav-bar";
        } else {
            x.className += " responsive";
        }
    }
    </script>
</head>
<body>
<div class="container">
    <div class="nav-bar" id="myTopnav">
        <span class="nav-toggle" onclick="toggleNav()">☰ Menu</span>
        <a href="index.html" class="nav-link">Home</a>
        <a href="history.html" class="nav-link">History</a>
        <a href="analysis.html" class="nav-link">Analysis</a>
        <a href="crosses.html" class="nav-link">Crosses</a>
        <a href="watch.html" class="nav-link">Watch</a>

    </div>
"""

HTML_FOOTER = """
    <div style="margin-top: 40px; text-align: center; color: #999; font-size: 0.8em;">
        Generated by Crypto Signal Station
    </div>
</div>
</body>
</html>
"""

def setup_dirs():
    # Do NOT remove existing docs dir to allow incremental updates
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
    os.makedirs(os.path.join(DOCS_DIR, "history"), exist_ok=True)

def parse_report_line(line):
    # Example: AMGN       Great Sell      (Price: $343.99, RSI: 75.3, MFI: 88.0, StochRSI: 0.95/0.92, BB: 1.05, MACD: 2.50)
    # The regex needs to be flexible enough to catch the symbol, signal, and the parenthesized details
    # Old format: (Price: $X, RSI: Y, MFI: Z, StochRSI: K)
    # New format: (Price: $X, RSI: Y, MFI: Z, StochRSI: K/D, BB: B, MACD: H)
    match = re.match(r"^(\S+)\s+(.+?)\s+(\(Price:.+\))$", line)
    if match:
        return match.groups()
    return None

def create_plotly_chart(category, timeframe, symbol):
    try:
        df = db.load_signals(symbol, category, timeframe)
        if df.empty or "Date" not in df.columns:
            return None

        if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
            df["Date"] = pd.to_datetime(df["Date"])

        # Slice last 100 periods for better visibility
        df = df.tail(100).copy()
        
        # Create subplots: Price (with BB), RSI, MFI, StochRSI, MACD
        fig = make_subplots(rows=5, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.03, 
                            row_heights=[0.4, 0.15, 0.15, 0.15, 0.15],
                            subplot_titles=(f"{symbol} Price & BB", "RSI", "MFI", "StochRSI", "MACD"))

        # 1. Price & Bollinger Bands
        # BB Upper
        if "bb_upper" in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['bb_upper'], name="BB Upper", 
                                     line=dict(color='gray', width=1, dash='dash'), showlegend=False), row=1, col=1)
        # BB Lower
        if "bb_lower" in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['bb_lower'], name="BB Lower", 
                                     line=dict(color='gray', width=1, dash='dash'), fill='tonexty', fillcolor='rgba(200,200,200,0.1)', showlegend=False), row=1, col=1)
        
        # Candlestick
        fig.add_trace(go.Candlestick(x=df['Date'],
                        open=df['Open'], high=df['High'],
                        low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)

        # 2. RSI
        if "rsi" in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['rsi'], name="RSI", line=dict(color='purple')), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

        # 3. MFI
        if "mfi" in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['mfi'], name="MFI", line=dict(color='orange')), row=3, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="green", row=3, col=1)

        # 4. StochRSI (K & D)
        if "stoch_rsi_k" in df.columns and "stoch_rsi_d" in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['stoch_rsi_k'], name="Stoch K", line=dict(color='blue')), row=4, col=1)
            fig.add_trace(go.Scatter(x=df['Date'], y=df['stoch_rsi_d'], name="Stoch D", line=dict(color='orange', dash='dot')), row=4, col=1)
            fig.add_hline(y=0.8, line_dash="dash", line_color="red", row=4, col=1)
            fig.add_hline(y=0.2, line_dash="dash", line_color="green", row=4, col=1)
        elif "stoch_rsi" in df.columns: # Fallback
             fig.add_trace(go.Scatter(x=df['Date'], y=df['stoch_rsi'], name="StochRSI", line=dict(color='blue')), row=4, col=1)

        # 5. MACD
        if "macd" in df.columns and "macd_signal" in df.columns and "macd_hist" in df.columns:
            # Histogram
            colors = ['green' if v >= 0 else 'red' for v in df['macd_hist']]
            fig.add_trace(go.Bar(x=df['Date'], y=df['macd_hist'], name="MACD Hist", marker_color=colors), row=5, col=1)
            # Lines
            fig.add_trace(go.Scatter(x=df['Date'], y=df['macd'], name="MACD", line=dict(color='blue')), row=5, col=1)
            fig.add_trace(go.Scatter(x=df['Date'], y=df['macd_signal'], name="Signal", line=dict(color='orange')), row=5, col=1)

        fig.update_layout(height=1000, showlegend=False, margin=dict(l=20, r=20, t=40, b=20))
        fig.update_xaxes(rangeslider_visible=False)
        
        # Return HTML div only (full_html=False)
        return fig.to_html(full_html=False, include_plotlyjs=False)
        
    except Exception as e:
        print(f"Error creating chart for {symbol}: {e}")
        return None

def generate_report_page(report_path, category, date_str, prev_date=None, next_date=None):
    out_filename = f"{category}_{date_str}.html"
    out_path = os.path.join(DOCS_DIR, out_filename)
    
    # Incremental Build: Skip if file already exists
    # if os.path.exists(out_path):
    #     return out_filename

    with open(report_path, "r") as f:
        lines = f.readlines()

    html_content = [HTML_HEADER]
    # html_content.append(f'<a href="index.html" class="back-link">← Back to Index</a>') # Replaced by Nav Bar
    html_content.append(f"<h1>{category.capitalize()} Report: {date_str}</h1>")
    
    # Educational Blurb
    html_content.append("""
    <div style="background-color: #e8f4fc; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
        <p style="margin: 0;"><strong>Daily Report Guide:</strong> This report highlights trading signals generated for today. 
        Look for <strong>Buy</strong> (Green) or <strong>Sell</strong> (Red) tags. 
        Charts show Price/Bollinger Bands, RSI (Momentum), MFI (Volume Flow), StochRSI, and MACD.
        </p>
    </div>
    """)

    # Navigation Links
    nav_links = []
    if prev_date:
        nav_links.append(f'<a href="{category}_{prev_date}.html" class="back-link">← Previous Day ({prev_date})</a>')
    if next_date:
        nav_links.append(f'<a href="{category}_{next_date}.html" class="back-link" style="float:right;">Next Day ({next_date}) →</a>')
    
    if nav_links:
        html_content.append('<div style="margin-bottom: 20px; overflow: hidden;">' + "".join(nav_links) + '</div>')

    current_timeframe = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for Timeframe Header
        tf_match = re.match(r"^---\s+(\w+)\s+Timeframe.*---$", line)
        if tf_match:
            current_timeframe = tf_match.group(1)
            html_content.append(f"<h2>{line.replace('---', '').strip()}</h2>")
            continue
            
        if "Report for" in line or "No recommendations" in line:
            html_content.append(f"<p>{line}</p>")
            continue
            
        # Parse Signal Line
        parsed = parse_report_line(line)
        if parsed:
            symbol, signal, details = parsed
            tag_class = "tag-buy" if "Buy" in signal else "tag-sell" if "Sell" in signal else ""
            
            # Generate History Page (only for 1d usually, but we can check)
            history_link_html = ""
            # Generate the history page for this symbol
            hist_rel_path = generate_history.generate_asset_history_page(category, "1d", symbol)
            if hist_rel_path:
                history_link_html = f'<a href="{hist_rel_path}" class="history-link" target="_blank">View Full History ↗</a>'
            
            html_content.append('<div class="signal-row">')
            html_content.append('<div class="signal-info">')
            html_content.append(f"<strong>{symbol}</strong> <span class='tag {tag_class}'>{signal}</span>{history_link_html}<br>")
            html_content.append(f"<span class='meta'>{details}</span>")
            html_content.append('</div>')
            
            # Generate Interactive Chart (Short term)
            if current_timeframe:
                chart_html = create_plotly_chart(category, current_timeframe, symbol)
                if chart_html:
                    html_content.append(f'<div class="signal-chart-container">{chart_html}</div>')
            
            html_content.append('</div>')
        else:
            html_content.append(f"<p>{line}</p>")

    html_content.append(HTML_FOOTER.format(gen_date="")) # Removed dynamic date
    
    with open(out_path, "w") as f:
        f.write("\n".join(html_content))
        
    print(f"Generated {out_filename}")
    return out_filename

def generate_history_index():
    html_content = [HTML_HEADER]
    html_content.append("<h1>Asset History Index</h1>")
    
    # Educational Blurb
    html_content.append("""
    <div style="background-color: #e8f4fc; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
        <p style="margin: 0;"><strong>History Index:</strong> Browse the complete historical performance and signals for all tracking assets.
        Assets are color-coded by their long-term trend (Bull/Bear) based on the 50/200 day Moving Averages.
        </p>
    </div>
    """)
    
    # Add Legend
    html_content.append("""
    <div style="margin-bottom: 20px; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 4px;">
        <strong>Key:</strong>
        <span class="tag asset-bear" style="margin-left: 10px;">Buy / Bear Market (Green)</span>
        <span class="tag asset-bull" style="margin-left: 10px;">Sell / Bull Market (Red)</span>
    </div>
    """)
    
    for category in ["crypto", "stocks"]:
        html_content.append(f"<h2>{category.capitalize()}</h2>")
        symbol_pairs = db.list_symbols(category=category, timeframe="1d")
        if symbol_pairs:
            html_content.append('<div class="asset-grid">')
            for symbol, _ in sorted(symbol_pairs):
                extra_class = ""
                try:
                    latest = db.load_signals_latest_row(symbol, category, "1d")
                    if latest is not None:
                        ma50 = latest.get("ma_50")
                        ma200 = latest.get("ma_200")
                        if pd.notna(ma50) and pd.notna(ma200):
                            extra_class = " asset-bull" if ma50 > ma200 else " asset-bear"
                except Exception:
                    pass
                html_content.append(f'<a href="history/{category}/{symbol}.html" class="asset-link{extra_class}">{symbol}</a>')
            html_content.append("</div>")
        else:
            html_content.append("<p>No data found.</p>")
            
    html_content.append(HTML_FOOTER.format(gen_date=""))
    
    with open(os.path.join(DOCS_DIR, "history.html"), "w") as f:
        f.write("\n".join(html_content))
    print("Generated history.html")

def generate_analysis_page(report_path, date_str, prev_date=None, next_date=None):
    out_filename = f"analysis_{date_str}.html"
    out_path = os.path.join(DOCS_DIR, out_filename)
    
    # Incremental Build: Skip if file already exists
    # if os.path.exists(out_path):
    #     return out_filename

    with open(report_path, "r") as f:
        lines = f.readlines()

    html_content = [HTML_HEADER]
    html_content.append(f"<h1>Analysis Report: {date_str}</h1>")
    
    # Educational Blurb
    html_content.append("""
    <div style="background-color: #e8f4fc; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
        <p style="margin: 0;"><strong>Daily Analysis:</strong> This AI-generated summary interprets today's technical indicators across the market.
        It groups assets by signal strength (e.g., "Excellent Buy") and provides context on <i>why</i> a signal was generated.
        </p>
    </div>
    """)
    
    # Navigation Links
    nav_links = []
    if prev_date:
        nav_links.append(f'<a href="analysis_{prev_date}.html" class="back-link">← Previous Day ({prev_date})</a>')
    if next_date:
        nav_links.append(f'<a href="analysis_{next_date}.html" class="back-link" style="float:right;">Next Day ({next_date}) →</a>')
    
    if nav_links:
        html_content.append('<div style="margin-bottom: 20px; overflow: hidden;">' + "".join(nav_links) + '</div>')

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for Signal Group Header (### Excellent Buy)
        header_match = re.match(r"^###\s+(.+)$", line)
        if header_match:
            group_name = header_match.group(1)
            # Style header based on type
            color = "#2c3e50"
            if "Buy" in group_name: color = "#155724" # Green
            if "Sell" in group_name: color = "#721c24" # Red
            
            html_content.append(f'<h2 style="color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px;">{group_name}</h2>')
            continue
            
        if "Analysis Report for" in line or "No signals found" in line:
            html_content.append(f"<p>{line}</p>")
            continue
            
        # Parse Analysis Line
        # Format: SYMBOL     [Category/TF] (Price: $X, ...)
        # Regex: ^(\S+)\s+\[(.+?)\]\s+(\(Price:.+\))$
        match = re.match(r"^(\S+)\s+\[(.+?)\]\s+(\(Price:.+\))$", line)
        if match:
            symbol, context, details = match.groups()
            
            # Generate History Page Link
            history_link_html = ""
            # Determine category from context (Crypto/1d) -> crypto
            cat_raw = context.split("/")[0].lower()
            category = "crypto" if "crypto" in cat_raw else "stocks"
            
            hist_rel_path = generate_history.generate_asset_history_page(category, "1d", symbol)
            if hist_rel_path:
                history_link_html = f'<a href="{hist_rel_path}" class="history-link" target="_blank">View History ↗</a>'
            
            html_content.append('<div class="signal-row">')
            html_content.append('<div class="signal-info">')
            html_content.append(f"<strong>{symbol}</strong> <span class='tag' style='background:#eee;'>{context}</span>{history_link_html}<br>")
            html_content.append(f"<span class='meta'>{details}</span>")
            html_content.append('</div>')
            
            # Optional: Add chart here too? Maybe too cluttered for aggregated view.
            # Let's keep it clean for now.
            
            html_content.append('</div>')
        else:
            html_content.append(f"<p>{line}</p>")

    html_content.append(HTML_FOOTER.format(gen_date=""))
    
    with open(out_path, "w") as f:
        f.write("\n".join(html_content))
        
    print(f"Generated {out_filename}")
    return out_filename

def generate_analysis_index(reports_list):
    html_content = [HTML_HEADER]
    html_content.append("<h1>Analysis Reports Index</h1>")
    
    # Sort reports descending by date
    # reports_list contains filenames like "analysis_2025-11-22.html"
    
    # Extract dates to sort
    dated_reports = []
    for r in reports_list:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", r)
        if match:
            dated_reports.append((match.group(1), r))
    
    dated_reports.sort(key=lambda x: x[0], reverse=True)
    
    if not dated_reports:
        html_content.append("<p>No analysis reports found.</p>")
    else:
        for date_str, filename in dated_reports:
             html_content.append(f'<a href="{filename}" class="report-link">')
             html_content.append(f"<strong>{date_str}</strong>")
             html_content.append('</a>')

    html_content.append(HTML_FOOTER.format(gen_date=""))
    
    with open(os.path.join(DOCS_DIR, "analysis.html"), "w") as f:
        f.write("\n".join(html_content))
    print("Generated analysis.html")

def generate_crosses_page():
    input_path = "reports/cross_feed.txt"
    if not os.path.exists(input_path):
        print("No cross feed found.")
        return

    with open(input_path, "r") as f:
        lines = f.readlines()

    html_content = [HTML_HEADER]
    html_content = [HTML_HEADER]
    html_content.append("<h1>Golden & Death Cross Feed</h1>")
    
    # Educational Blurb
    html_content.append("""
    <div style="background-color: #e8f4fc; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
        <p style="margin: 0;"><strong>Crosses Guide:</strong>
        <span style="color: #155724; font-weight: bold;">Golden Cross:</span> 50-day MA crosses <i>above</i> 200-day MA (Bullish - Start of potential uptrend).<br>
        <span style="color: #721c24; font-weight: bold;">Death Cross:</span> 50-day MA crosses <i>below</i> 200-day MA (Bearish - Start of potential downtrend).
        </p>
    </div>
    """)
    
    html_content.append("<p><i>Events from the last 365 days (Newest First)</i></p>")

    # Skip header lines
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip() == "":
            start_idx = i + 1
            break
    
    data_lines = lines[start_idx:]
    
    for line in data_lines:
        line = line.strip()
        if not line: continue
        
        # Format: 2025-11-21 | BKNG     | Death Cross  | Price: $4,768.00
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4:
            date_str, symbol, cross_type, price_info = parts[0], parts[1], parts[2], parts[3]
            
            # Style
            row_style = "border-left: 5px solid #ccc;"
            tag_class = "tag"
            tag_style = "background: #eee;"
            
            if "Golden" in cross_type:
                row_style = "border-left: 5px solid #28a745;" # Green
                tag_style = "background: #d4edda; color: #155724;"
            elif "Death" in cross_type:
                row_style = "border-left: 5px solid #dc3545;" # Red
                tag_style = "background: #f8d7da; color: #721c24;"
                
            # History Link
            # Try crypto first, then stocks (simple heuristic or check file existence)
            # Since we don't know category easily here without looking up, let's try to find it
            # Or just link to history/crypto/SYMBOL.html and history/stocks/SYMBOL.html and see which exists?
            # Better: cross_feed.py knows the category, maybe we should have saved it in the text file?
            # The current text file format is: DATE | SYMBOL | TYPE | Price...
            # Let's just try to link to both or guess. 
            # Actually, let's use generate_history.generate_asset_history_page to find it.
            # But that function needs category.
            # Let's just check existence.
            
            # Determine category by checking DB
            cat = "crypto"
            stock_syms = [s for s, _ in db.list_symbols(category="stocks", timeframe="1d")]
            if symbol in stock_syms:
                cat = "stocks"
            
            hist_rel_path = generate_history.generate_asset_history_page(cat, "1d", symbol)
            history_link = ""
            if hist_rel_path:
                history_link = f'<a href="{hist_rel_path}" class="history-link" target="_blank">View History ↗</a>'

            html_content.append(f'<div class="signal-row" style="{row_style} padding-left: 15px;">')
            html_content.append(f'<div class="signal-info">')
            html_content.append(f'<strong>{date_str}</strong> - <strong>{symbol}</strong> <span class="{tag_class}" style="{tag_style}">{cross_type}</span> {history_link}<br>')
            html_content.append(f'<span class="meta">{price_info}</span>')
            html_content.append('</div></div>')

    html_content.append(HTML_FOOTER.format(gen_date=""))
    
    with open(os.path.join(DOCS_DIR, "crosses.html"), "w") as f:
        f.write("\n".join(html_content))
    print("Generated crosses.html")

def generate_index(reports_list):
    html_content = [HTML_HEADER]
    html_content.append("<h1>Daily Reports Index</h1>")
    
    # Educational Blurb
    html_content.append("""
    <div style="background-color: #e8f4fc; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
        <p style="margin: 0;"><strong>Dashboard Home:</strong> Access daily technical reports for Crypto and Stocks. 
        Select a date below to view detailed charts and trading signals generated for that day.
        </p>
    </div>
    """)
    
    # Group by Month
    reports_by_month = {}
    for report in reports_list:
        # report: "crypto_2025-11-20.html"
        match = re.match(r"(\w+)_(\d{4}-\d{2})-\d{2}\.html", report)
        if match:
            category, month = match.groups()
            key = f"{month} ({category.capitalize()})"
            if key not in reports_by_month:
                reports_by_month[key] = []
            reports_by_month[key].append(report)
            
    # Sort months descending
    sorted_months = sorted(reports_by_month.keys(), reverse=True)
    
    for month_key in sorted_months:
        html_content.append(f"<h3>{month_key}</h3>")
        # Sort reports descending by date
        for report in sorted(reports_by_month[month_key], reverse=True):
             # Extract date for display
             date_match = re.search(r"\d{4}-\d{2}-\d{2}", report)
             date_display = date_match.group(0) if date_match else report
             
             # Use Button Style Link
             html_content.append(f'<a href="{report}" class="report-link">')
             html_content.append(f"<strong>{date_display}</strong>")
             html_content.append('</a>')

    html_content.append(HTML_FOOTER.format(gen_date=""))
    
    with open(os.path.join(DOCS_DIR, "index.html"), "w") as f:
        f.write("\n".join(html_content))
    print("Generated index.html")

def generate_all_histories():
    print("Generating all history pages...")
    for category in ["crypto", "stocks"]:
        symbol_pairs = db.list_symbols(category=category, timeframe="1d")
        for symbol, _ in symbol_pairs:
            generate_history.generate_asset_history_page(category, "1d", symbol)
    print("History pages generated.")

def main():
    print("Generating static site...")
    setup_dirs()
    
    # Find all text reports
    # reports/{category}/{YYYY-MM}/{YYYY-MM-DD}.txt
    report_files = glob.glob(os.path.join(REPORTS_DIR, "*", "*", "*.txt"))
    
    generated_reports = []
    
    # Sort report files by date to determine prev/next
    # We need to group by category first
    reports_by_category = {}
    for report_path in report_files:
        parts = report_path.split(os.sep)
        if len(parts) >= 4:
            category = parts[-3]
            filename = parts[-1]
            date_str = filename.replace(".txt", "")
            
            # Skip today's incomplete report
            if date_str == datetime.now().strftime("%Y-%m-%d"):
                continue

            if category not in reports_by_category:
                reports_by_category[category] = []
            reports_by_category[category].append((date_str, report_path))

    generated_reports = []

    for category, files in reports_by_category.items():
        # Sort ascending by date
        files.sort(key=lambda x: x[0])
        
        for i, (date_str, report_path) in enumerate(files):
            prev_date = files[i-1][0] if i > 0 else None
            next_date = files[i+1][0] if i < len(files) - 1 else None
            
            out_filename = f"{category}_{date_str}.html"
            out_path = os.path.join(DOCS_DIR, out_filename)
            
            # Incremental Build: Skip if file exists AND it's not the latest file
            # We always regenerate the latest file just in case data updated
            is_latest = (i == len(files) - 1)
            if os.path.exists(out_path) and not is_latest:
                generated_reports.append(out_filename)
                continue

            out_file = generate_report_page(report_path, category, date_str, prev_date, next_date)
            generated_reports.append(out_file)
            
    generate_index(generated_reports)
    
    # Generate Analysis Pages
    print("Generating analysis pages...")
    analysis_files = glob.glob(os.path.join(REPORTS_DIR, "analysis", "*.txt"))
    
    # Sort analysis files by date to determine prev/next
    analysis_files_sorted = []
    for report_path in analysis_files:
        filename = os.path.basename(report_path)
        date_str = filename.replace(".txt", "")
        analysis_files_sorted.append((date_str, report_path))
    
    analysis_files_sorted.sort(key=lambda x: x[0]) # Sort ascending
    
    generated_analysis = []
    
    for i, (date_str, report_path) in enumerate(analysis_files_sorted):
        prev_date = analysis_files_sorted[i-1][0] if i > 0 else None
        next_date = analysis_files_sorted[i+1][0] if i < len(analysis_files_sorted) - 1 else None
        
        out_filename = f"analysis_{date_str}.html"
        out_path = os.path.join(DOCS_DIR, out_filename)
        
        # Incremental Build: Skip if file exists AND it's not the latest file
        is_latest = (i == len(analysis_files_sorted) - 1)
        if os.path.exists(out_path) and not is_latest:
            generated_analysis.append(out_filename)
            continue

        out_file = generate_analysis_page(report_path, date_str, prev_date, next_date)
        generated_analysis.append(out_file)
        
    generate_analysis_index(generated_analysis)
    
    # Generate Crosses Page
    generate_crosses_page()
    
    # Generate Watch Page
    generate_watch_page()
    
    # Finalize Site
    generate_all_histories()
    generate_history_index()
    print(f"Site generated in '{DOCS_DIR}/'. Open 'docs/index.html' to view.")

def generate_watch_page():
    """Generate the Watch page from watch_feed.txt"""
    input_path = "reports/watch_feed.txt"
    if not os.path.exists(input_path):
        print("No watch feed found.")
        return

    with open(input_path, "r") as f:
        lines = f.readlines()

    html_content = [HTML_HEADER]
    html_content = [HTML_HEADER]
    html_content.append("<h1>Watch List - Assets Near Signals</h1>")
    
    # Educational Blurb
    html_content.append("""
    <div style="background-color: #e8f4fc; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
        <p style="margin: 0;"><strong>Watch List Guide:</strong> These assets haven't triggered a full signal yet but are getting close.
        <br>• <strong>Near Buy:</strong> RSI < 35 (Oversold) or Approaching Golden Cross.
        <br>• <strong>Near Sell:</strong> RSI > 65 (Overbought) or Approaching Death Cross.
        </p>
    </div>
    """)
    
    html_content.append("<p><i>Assets approaching buy/sell signal thresholds</i></p>")

    # Skip header lines (first 3 lines)
    start_idx = 0
    for i, line in enumerate(lines):
        if "=" in line:
            start_idx = i + 1
            break
    
    data_lines = lines[start_idx:]
    
    current_section = None
    
    for line in data_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        # Section headers like "--- CRYPTO ---"
        if line_stripped.startswith("---") and line_stripped.endswith("---"):
            section_name = line_stripped.replace("-", "").strip()
            html_content.append(f"<h2>{section_name}</h2>")
            current_section = section_name
            continue
        
        # Timeframe headers like "[1d]"
        if line_stripped.startswith("[") and line_stripped.endswith("]"):
            tf = line_stripped[1:-1]
            html_content.append(f"<h3>{tf} Timeframe</h3>")
            continue
        
        # Parse data lines
        # Format: SYMBOL     Near Buy/Sell   (Price: $X, RSI: Y, MFI: Z, Market: Bull/Bear)
        match = re.match(r"^(\S+)\s+(Near (?:Buy|Sell))\s+\((.+)\)$", line_stripped)
        if match:
            symbol, near_type, details = match.groups()
            
            # Styling
            row_style = "border-left: 5px solid #ccc;"
            tag_style = "background: #eee;"
            
            if "Buy" in near_type:
                row_style = "border-left: 5px solid #28a745;"
                tag_style = "background: #d4edda; color: #155724;"
            elif "Sell" in near_type:
                row_style = "border-left: 5px solid #dc3545;"
                tag_style = "background: #f8d7da; color: #721c24;"
            
            # Determine category
            cat = "crypto" if current_section and "CRYPTO" in current_section else "stocks"
            
            # Generate history link
            hist_rel_path = generate_history.generate_asset_history_page(cat, "1d", symbol)
            history_link = ""
            if hist_rel_path:
                history_link = f'<a href="{hist_rel_path}" class="history-link" target="_blank">View History ↗</a>'
            
            html_content.append(f'<div class="signal-row" style="{row_style} padding-left: 15px;">')
            html_content.append(f'<div class="signal-info">')
            html_content.append(f'<strong>{symbol}</strong> <span class="tag" style="{tag_style}">{near_type}</span> {history_link}<br>')
            html_content.append(f'<span class="meta">{details}</span>')
            html_content.append('</div></div>')

    html_content.append(HTML_FOOTER.format(gen_date=""))
    
    with open(os.path.join(DOCS_DIR, "watch.html"), "w") as f:
        f.write("\n".join(html_content))
    print("Generated watch.html")




if __name__ == "__main__":
    main()

