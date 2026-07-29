import os
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import db

# Configuration
DOCS_DIR = "docs"
HISTORY_DIR = os.path.join(DOCS_DIR, "history")

# HTML Template for History Page
HISTORY_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{symbol} History - Crypto Signal Station</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 10px; background-color: #f4f4f9; color: #333; }}
        .container {{ max-width: 100%; margin: 0 auto; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        @media (min-width: 768px) {{
            .container {{ max-width: 1200px; padding: 30px; }}
            body {{ padding: 20px; }}
        }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; font-size: 1.5em; }}
        .chart-container {{ width: 100%; height: 600px; border: 1px solid #ddd; border-radius: 4px; }}
        @media (min-width: 768px) {{
            .chart-container {{ height: 800px; }}
        }}

        /* Nav Bar */
        .nav-bar {{ margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #eee; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }}
        .nav-link {{ text-decoration: none; color: #2c3e50; font-weight: bold; font-size: 1.1em; padding: 5px 0; }}
        .nav-link:hover {{ color: #007bff; }}
        .nav-link.active {{ color: #007bff; border-bottom: 2px solid #007bff; }}
        .nav-toggle {{ display: none; font-size: 1.5em; cursor: pointer; padding: 5px; }}

        @media (max-width: 768px) {{
            .nav-bar {{ flex-direction: column; align-items: flex-start; gap: 5px; }}
            .nav-link {{ display: none; width: 100%; padding: 10px 0; border-bottom: 1px solid #eee; }}
            .nav-toggle {{ display: block; }}
            .nav-bar.responsive .nav-link {{ display: block; }}
        }}
    </style>
    <script>
    function toggleNav() {{
        var x = document.getElementById("myTopnav");
        if (x.className.includes("responsive")) {{
            x.className = "nav-bar";
        }} else {{
            x.className += " responsive";
        }}
    }}
    </script>
</head>
<body>
<div class="container">
    <div class="nav-bar" id="myTopnav">
        <span class="nav-toggle" onclick="toggleNav()">☰ Menu</span>
        <a href="../../index.html" class="nav-link">Home</a>
        <a href="../../history.html" class="nav-link">History</a>
        <a href="../../analysis.html" class="nav-link">Analysis</a>
        <a href="../../crosses.html" class="nav-link">Crosses</a>
        <a href="../../watch.html" class="nav-link">Watch</a>
        <a href="../../stoch_crosses.html" class="nav-link">1w Stoch</a>
    </div>
    <h1>{symbol} Full History</h1>
    <div class="chart-container">
        {chart_html}
    </div>
</div>
</body>
</html>
"""

def get_signal_color(signal):
    signal = str(signal).lower()
    if "excellent buy" in signal: return "darkgreen"
    if "great buy" in signal: return "green"
    if "good buy" in signal: return "lightgreen"
    if "excellent sell" in signal: return "darkred"
    if "great sell" in signal: return "red"
    if "good sell" in signal: return "lightcoral"
    return "gray"

def generate_asset_history_page(category, timeframe, symbol):
    # Only generate for 1d timeframe
    if timeframe != "1d":
        return None

    try:
        df = db.load_signals(symbol, category, timeframe)
        if df.empty or "Date" not in df.columns:
            return None

        if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
            df["Date"] = pd.to_datetime(df["Date"])

        # Calculate Moving Averages (already stored, but recalculate for safety)
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()

        fig = go.Figure()

        # Price Line
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], mode='lines', name='Close Price', line=dict(color='black', width=1)))

        # SMAs
        fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA_50'], mode='lines', name='50-MA', line=dict(color='dodgerblue', width=1, dash='dash')))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA_200'], mode='lines', name='200-MA', line=dict(color='orange', width=1, dash='dash')))

        # Signals
        signals_df = df[df['signal'].notna() & (df['signal'] != 'Hold')].copy()

        if not signals_df.empty:
            for signal_type in signals_df['signal'].unique():
                subset = signals_df[signals_df['signal'] == signal_type]
                color = get_signal_color(signal_type)
                fig.add_trace(go.Scatter(
                    x=subset['Date'],
                    y=subset['Close'],
                    mode='markers',
                    name=signal_type,
                    marker=dict(color=color, size=10, line=dict(width=1, color='black'))
                ))

        fig.update_layout(
            title=dict(text=f"{symbol} ({timeframe}) Buy/Sell Signals", font=dict(size=24)),
            xaxis=dict(title="Date", title_font=dict(size=18), tickfont=dict(size=14)),
            yaxis=dict(title="Price (USD)", title_font=dict(size=18), tickfont=dict(size=14)),
            height=800,
            template="plotly_white",
            hovermode="x unified",
            autosize=True,
            margin=dict(l=10, r=10, t=50, b=50),
            legend=dict(font=dict(size=16), orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        chart_html = fig.to_html(full_html=False, include_plotlyjs=False, config={'responsive': True, 'displayModeBar': False})

        out_dir = os.path.join(HISTORY_DIR, category)
        os.makedirs(out_dir, exist_ok=True)

        out_filename = f"{symbol}.html"
        out_path = os.path.join(out_dir, out_filename)

        with open(out_path, "w") as f:
            f.write(HISTORY_HTML_TEMPLATE.format(symbol=symbol, chart_html=chart_html))

        return f"history/{category}/{out_filename}"

    except Exception as e:
        print(f"Error generating history for {symbol}: {e}")
        return None
