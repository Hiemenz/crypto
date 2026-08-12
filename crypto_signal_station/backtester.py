#!/usr/bin/env python3
"""
Backtesting module for Crypto Signal Station.

Usage:
    poetry run python crypto_signal_station/backtester.py BTC-USD 1d
    poetry run python crypto_signal_station/backtester.py ETH-USD 1wk
"""

import os
import sys
import json
import math
import csv
from datetime import datetime
import duckdb
import pandas as pd

BASE_DATA = "crypto_history_csv"
REPORTS_DIR = "reports/backtests"

BUY_SIGNALS = {"Good Buy", "Great Buy", "Excellent Buy"}
SELL_SIGNALS = {"Good Sell", "Great Sell", "Excellent Sell"}


def run_backtest(symbol: str, timeframe: str, trailing_stop_pct: float | None = None):
    """Run backtest for symbol/timeframe. Returns metrics dict and trades list.

    Args:
        trailing_stop_pct: If set, exit a position when price falls this many
            percent below its peak since entry (e.g. 8.0 → exit at -8%).
            A signal-based sell still closes the position first.
    """
    for asset_class in ("crypto", "stocks"):
        path = os.path.join(BASE_DATA, asset_class, timeframe, f"{symbol}_with_signals.parquet")
        if os.path.exists(path):
            break
    else:
        raise FileNotFoundError(f"No parquet found for {symbol} / {timeframe}")

    con = duckdb.connect()
    try:
        df = con.execute(f"SELECT * FROM read_parquet('{path}')").df()
    finally:
        con.close()
    if df.empty:
        raise ValueError(f"Empty dataframe for {symbol} {timeframe}")

    df = df.sort_values("Date").reset_index(drop=True)

    trades = []
    open_position = None

    def _close_trade(entry, exit_price, exit_date, exit_signal):
        ep = entry["entry_price"]
        pct = (exit_price - ep) / ep * 100 if ep else 0.0
        return {
            "entry_date": entry["entry_date"],
            "exit_date": exit_date,
            "entry_price": ep,
            "exit_price": exit_price,
            "entry_signal": entry["entry_signal"],
            "exit_signal": exit_signal,
            "pct_return": round(pct, 4),
            "status": "closed",
        }

    for _, row in df.iterrows():
        signal = row.get("signal", "Hold")
        close = float(row.get("Close", 0.0))
        date = row.get("Date")
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)

        if open_position is None:
            if signal in BUY_SIGNALS:
                open_position = {
                    "entry_date": date_str,
                    "entry_price": close,
                    "entry_signal": signal,
                    "peak_price": close,
                }
        else:
            # Update trailing peak
            if close > open_position["peak_price"]:
                open_position["peak_price"] = close

            # Check trailing stop before signal exit
            if trailing_stop_pct is not None:
                stop_price = open_position["peak_price"] * (1 - trailing_stop_pct / 100)
                if close <= stop_price:
                    trades.append(_close_trade(open_position, close, date_str, "Trailing Stop"))
                    open_position = None
                    continue

            if signal in SELL_SIGNALS:
                trades.append(_close_trade(open_position, close, date_str, signal))
                open_position = None

    open_trades = []
    if open_position is not None:
        open_trades.append({**open_position, "status": "open"})

    return _compute_metrics(symbol, timeframe, trades, open_trades)


def _compute_metrics(symbol, timeframe, trades, open_trades):
    """Compute performance metrics from closed trades."""
    closed = [t for t in trades if t["status"] == "closed"]
    n = len(closed)

    if n == 0:
        metrics = {
            "symbol": symbol,
            "timeframe": timeframe,
            "total_trades": 0,
            "open_positions": len(open_trades),
            "win_rate": None,
            "avg_return_pct": None,
            "max_drawdown_pct": None,
            "sharpe_ratio": None,
        }
        return metrics, trades + open_trades

    returns = [t["pct_return"] for t in closed]
    wins = [r for r in returns if r > 0]
    win_rate = len(wins) / n * 100

    avg_return = sum(returns) / n

    # Max drawdown (peak-to-trough on cumulative return series)
    cumulative = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        cumulative *= (1 + r / 100)
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualized, assuming risk-free = 0)
    if n > 1:
        mean_r = avg_return
        variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
        std_r = math.sqrt(variance)
        sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    metrics = {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_trades": n,
        "open_positions": len(open_trades),
        "win_rate": round(win_rate, 2),
        "avg_return_pct": round(avg_return, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
    }
    return metrics, trades + open_trades


def save_csv(symbol, timeframe, all_trades):
    """Save all trades to CSV."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"{symbol}_{timeframe}_trades.csv")
    if not all_trades:
        return path
    fieldnames = list(all_trades[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_trades)
    return path


def save_html(symbol, timeframe, metrics, all_trades):
    """Save HTML report."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"{symbol}_{timeframe}.html")

    rows = ""
    for t in all_trades:
        status_style = "color:green" if t.get("status") == "closed" else "color:orange"
        pct = t.get("pct_return", "")
        pct_str = f"{pct:.2f}%" if isinstance(pct, float) else "open"
        rows += (
            f"<tr>"
            f"<td>{t.get('entry_date','')}</td>"
            f"<td>{t.get('exit_date','')}</td>"
            f"<td>${t.get('entry_price', 0):,.4f}</td>"
            f"<td>${t.get('exit_price', 0):,.4f}</td>"
            f"<td>{t.get('entry_signal','')}</td>"
            f"<td>{t.get('exit_signal','')}</td>"
            f"<td>{pct_str}</td>"
            f"<td style='{status_style}'>{t.get('status','')}</td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html>
<html>
<head><title>Backtest: {symbol} {timeframe}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
th {{ background: #333; color: white; }}
tr:nth-child(even) {{ background: #f9f9f9; }}
.metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
.metric-label {{ font-size: 12px; color: #666; }}
.metric-value {{ font-size: 22px; font-weight: bold; }}
</style>
</head>
<body>
<h1>Backtest Report: {symbol} ({timeframe})</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<div>
  <div class="metric"><div class="metric-label">Total Trades</div><div class="metric-value">{metrics.get('total_trades','N/A')}</div></div>
  <div class="metric"><div class="metric-label">Open Positions</div><div class="metric-value">{metrics.get('open_positions','N/A')}</div></div>
  <div class="metric"><div class="metric-label">Win Rate</div><div class="metric-value">{metrics.get('win_rate','N/A')}%</div></div>
  <div class="metric"><div class="metric-label">Avg Return</div><div class="metric-value">{metrics.get('avg_return_pct','N/A')}%</div></div>
  <div class="metric"><div class="metric-label">Max Drawdown</div><div class="metric-value">{metrics.get('max_drawdown_pct','N/A')}%</div></div>
  <div class="metric"><div class="metric-label">Sharpe Ratio</div><div class="metric-value">{metrics.get('sharpe_ratio','N/A')}</div></div>
</div>
<h2>Trades</h2>
<table>
<tr><th>Entry Date</th><th>Exit Date</th><th>Entry Price</th><th>Exit Price</th><th>Entry Signal</th><th>Exit Signal</th><th>Return</th><th>Status</th></tr>
{rows}
</table>
</body>
</html>"""

    with open(path, "w") as f:
        f.write(html)
    return path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backtest a symbol against its stored signals")
    parser.add_argument("symbol", help="Symbol, e.g. BTC-USD")
    parser.add_argument("timeframe", help="Timeframe, e.g. 1d or 1wk")
    parser.add_argument(
        "--trailing-stop",
        type=float,
        default=None,
        metavar="PCT",
        help="Exit when price drops this %% below its peak (e.g. 8.0)",
    )
    args = parser.parse_args()
    symbol = args.symbol.upper()
    timeframe = args.timeframe

    metrics, all_trades = run_backtest(symbol, timeframe, trailing_stop_pct=args.trailing_stop)

    print(json.dumps(metrics, indent=2))

    csv_path = save_csv(symbol, timeframe, all_trades)
    html_path = save_html(symbol, timeframe, metrics, all_trades)
    print(f"\nCSV saved:  {csv_path}")
    print(f"HTML saved: {html_path}")


if __name__ == "__main__":
    main()
