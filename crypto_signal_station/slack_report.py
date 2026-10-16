"""Format the daily signal run as a compact Slack message (Block Kit + plain-text fallback).

Input is the pipeline's own summary strings, e.g.

    Buy on the weekly (2026-10-12):
    Excellent:
      BTC-USD
    Great:
      ETH-USD

Output groups them as: header with counts, one line per timeframe/tier, prices in a code block.
"""
import re

TIERS = ("Excellent", "Great", "Good")  # strongest first
_HEADER = re.compile(r"^(Buy|Sell) on the (.+?) \((\d{4}-\d{2}-\d{2})\):$")
_FOOTER = re.compile(r"\d{2}:\d{2}:\d{2} • ")  # the "HH:MM:SS • MM-DD-YYYY UTC" stamp


def parse_summary(text):
    """-> [(timeframe, date, {tier: [symbols]})] in input order."""
    groups, cur, tier = [], None, None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m = _HEADER.match(line)
        if m:
            cur = (m.group(2), m.group(3), {})
            groups.append(cur)
            tier = None
        elif cur and line.endswith(":") and line[:-1] in TIERS:
            tier = line[:-1]
            cur[2][tier] = []
        elif cur and tier and line.startswith("  ") and line.strip():
            cur[2][tier].append(line.strip())
    return groups


def _signal_lines(emoji, label, text):
    out = []
    for tf, date, tiers in parse_summary(text):
        parts = [f"*{t}* {', '.join(tiers[t])}" for t in TIERS if tiers.get(t)]
        if parts:
            out.append(f"{emoji} *{label}* · {tf} ({date}) — " + "  ·  ".join(parts))
    return out


def _distinct(text):
    return len({s for _, _, tiers in parse_summary(text) for syms in tiers.values() for s in syms})


def _market_lines(prices_str):
    return [l.rstrip() for l in (prices_str or "").splitlines() if l.strip() and not _FOOTER.match(l)]


def build_report(date_label, crypto_buy, crypto_sell, stock_buy, stock_sell, prices_str, stock_extra=""):
    """-> (fallback_text, blocks). Counts are distinct tickers, matching the tweet."""
    cb, cs = _distinct(crypto_buy), _distinct(crypto_sell)
    sb, ss = _distinct(stock_buy), _distinct(stock_sell)
    fallback = f"Daily signals {date_label} — Crypto: {cb} buys, {cs} sells · Stocks: {sb} buys, {ss} sells"

    def section(title, buy, sell):
        lines = _signal_lines(":chart_with_downwards_trend:", "Sell", sell) + _signal_lines(":chart_with_upwards_trend:", "Buy", buy)
        return {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\n" + ("\n".join(lines) if lines else "_No signals today_")}}

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Daily signals · {date_label}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f":coin: Crypto *{cb}* buy · *{cs}* sell     :bar_chart: Stocks *{sb}* buy · *{ss}* sell"}]},
        section(":coin: Crypto", crypto_buy, crypto_sell),
    ]
    market = _market_lines(prices_str)
    if market:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "```" + "\n".join(market) + "```"}})
    blocks.append({"type": "divider"})
    stocks = section(":bar_chart: Stocks", stock_buy, stock_sell)
    if stock_extra.strip():
        stocks["text"]["text"] += "\n_" + stock_extra.strip() + "_"
    blocks.append(stocks)
    return fallback, blocks
