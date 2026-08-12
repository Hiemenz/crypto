"""Weekly digest: the last 7 days of signals with market context.

`build_digest()` returns a full plain-text report (printed by the CLI);
`build_post()` returns a compact version sized for Mastodon/X. Posting goes
through the existing send_toot/send_tweet, guarded by --dry-run.

Suggested cron (Sunday evening, after the nightly refresh):
    0 22 * * 0  cd /home/pi/git/crypto && poetry run python \
        crypto_signal_station/crypto_signal_pipeline.py digest post
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import backtest as backtest_mod
import breadth as breadth_mod

WINDOW_DAYS = 7
TIMEFRAMES = ["1d", "2d", "3d", "1wk", "2wk"]
TOP_SYMBOLS = 5


def _week_events(category):
    """Non-Hold signal rows across all timeframes in the window, one frame."""
    frames = []
    # Anchor the window to today, not each timeframe's own latest bar: a slow
    # timeframe (2wk) must not smuggle a two-week-old signal into "this week"
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=WINDOW_DAYS - 1)
    for tf in TIMEFRAMES:
        sigs = db.scan_signals_lake(category, tf, columns=["Date", "signal"])
        if sigs.empty:
            continue
        recent = sigs[(sigs["Date"] >= cutoff) & (sigs["signal"] != "Hold")].copy()
        if recent.empty:
            continue
        recent["timeframe"] = tf
        frames.append(recent)
    if not frames:
        return pd.DataFrame(columns=["symbol", "Date", "signal", "timeframe"])
    return pd.concat(frames, ignore_index=True)


def _week_crosses(category):
    """Golden/death crosses (daily bars) in the window; None if the lake
    predates those columns."""
    try:
        df = db.scan_signals_lake(category, "1d", columns=["Date", "golden_cross", "death_cross"])
    except Exception:
        return None
    if df.empty or "golden_cross" not in df.columns:
        return None
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=WINDOW_DAYS - 1)
    recent = df[df["Date"] >= cutoff]
    golden = sorted(recent.loc[recent["golden_cross"].fillna(False), "symbol"].unique())
    death = sorted(recent.loc[recent["death_cross"].fillna(False), "symbol"].unique())
    return golden, death


def _breadth_context(category):
    """(latest_row, week_change_in_points) from stored breadth history."""
    hist = breadth_mod.load_history(category)
    if hist.empty:
        return None, None
    latest = hist.iloc[-1]
    week_ago = hist[hist["Date"] <= latest["Date"] - pd.Timedelta(days=WINDOW_DAYS - 1)]
    change = None
    if not week_ago.empty and pd.notna(latest["pct_above_ma200"]):
        prev = week_ago.iloc[-1]["pct_above_ma200"]
        if pd.notna(prev):
            change = (latest["pct_above_ma200"] - prev) * 100
    return latest.to_dict(), change


def _backtest_context(tiers_seen):
    """One line per observed tier: historical 30d win rate and avg return."""
    stats = backtest_mod.load_stats()
    if stats.empty:
        return []
    lines = []
    s30 = stats[stats["horizon_days"] == 30]
    for tier in [t for t in backtest_mod.TIER_ORDER if t in tiers_seen]:
        rows = s30[s30["signal"] == tier]
        if rows.empty:
            continue
        n = int(rows["n"].sum())
        avg = float((rows["avg_return"] * rows["n"]).sum() / n)
        win = float((rows["win_rate"] * rows["n"]).sum() / n)
        lines.append(f"  {tier}: historically {win:.0%} win, {avg:+.1%} avg over 30d (n={n})")
    return lines


def _category_block(category, name):
    ev = _week_events(category)
    if ev.empty:
        return f"{name}: no signals this week\n", set(), 0, 0
    buys = ev[ev["signal"].str.endswith("Buy")]
    sells = ev[ev["signal"].str.endswith("Sell")]
    n_buy = buys["symbol"].nunique()
    n_sell = sells["symbol"].nunique()
    out = f"{name}: {n_buy} symbols with buys, {n_sell} with sells ({len(ev)} signal-bars)\n"
    for label, side in (("buys", buys), ("sells", sells)):
        if side.empty:
            continue
        top = side.groupby("symbol").size().sort_values(ascending=False).head(TOP_SYMBOLS)
        listed = ", ".join(f"{s}×{c}" for s, c in top.items())
        out += f"  top {label}: {listed}\n"
    return out, set(ev["signal"].unique()), n_buy, n_sell


def build_digest():
    """Full weekly digest text."""
    end = pd.Timestamp.now().normalize()
    lines = [f"Weekly Signal Digest — week ending {end.date()}", ""]

    tiers_seen = set()
    for cat, name in (("crypto", "Crypto"), ("stocks", "Stocks")):
        block, tiers, _, _ = _category_block(cat, name)
        lines.append(block.rstrip())
        tiers_seen |= tiers

        crosses = _week_crosses(cat)
        if crosses:
            golden, death = crosses
            if golden:
                lines.append(f"  golden crosses: {', '.join(golden)}")
            if death:
                lines.append(f"  death crosses: {', '.join(death)}")
        lines.append("")

    for cat in ("stocks", "crypto"):
        row, change = _breadth_context(cat)
        if row:
            chg = f" ({change:+.0f}pp w/w)" if change is not None else ""
            lines.append(breadth_mod.breadth_line(row).rstrip() + chg)

    # Fear & Greed comes from the pipeline module (imported lazily: it loads
    # config at import time and imports this module's siblings)
    try:
        from crypto_signal_pipeline import get_fear_greed
        fng = get_fear_greed().rstrip()
        if fng:
            lines.append(fng)
    except Exception:
        pass

    ctx = _backtest_context(tiers_seen)
    if ctx:
        lines.append("")
        lines.append("Backtest context for this week's tiers:")
        lines.extend(ctx)

    lines.append("")
    lines.append(pd.Timestamp.now("UTC").strftime("%H:%M:%S • %m-%d-%Y UTC"))
    return "\n".join(lines) + "\n"


def build_post():
    """Compact digest sized for a toot/tweet."""
    end = pd.Timestamp.now().normalize()
    parts = [f"Weekly signals (thru {end.date()}):"]
    for cat, name in (("crypto", "Crypto"), ("stocks", "Stocks")):
        _, _, n_buy, n_sell = _category_block(cat, name)
        parts.append(f"{name}: {n_buy} buys / {n_sell} sells")
    row, change = _breadth_context("stocks")
    if row and pd.notna(row.get("pct_above_ma200")):
        chg = f" ({change:+.0f}pp)" if change is not None else ""
        parts.append(f"Breadth: {row['pct_above_ma200']:.0%} >200dMA, {row['regime']}{chg}")
    return "\n".join(parts) + "\n"


def post_digest(dry_run=False):
    text = build_post()
    if dry_run:
        print("--dry-run: would post:\n")
        print(text)
        return
    from toot import send_toot
    from send_to_x import send_tweet
    send_toot(text)
    send_tweet(text)


def build_html_digest() -> str:
    """Wrap the plain-text digest in a minimal HTML email shell."""
    text = build_digest()
    lines = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body_html = "<br>".join(lines.splitlines())
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Weekly Signal Digest</title></head>
<body style="font-family:monospace;font-size:14px;line-height:1.6;
             background:#0b0f14;color:#c9d1d9;padding:24px">
<div style="max-width:680px;margin:0 auto">
<h2 style="color:#58a6ff;margin-bottom:16px">📊 Weekly Signal Digest</h2>
<div style="background:#161b22;border:1px solid #30363d;
            border-radius:6px;padding:16px">
{body_html}
</div>
<p style="color:#6e7681;font-size:12px;margin-top:16px">
  Generated by <a href="https://github.com/Hiemenz/crypto" style="color:#58a6ff">
  Crypto Signal Station</a>
</p>
</div>
</body>
</html>"""


def send_email_digest(dry_run: bool = False) -> bool:
    """Send the HTML digest via SMTP.

    Reads config from the `email:` section of cryptos.yml:
        email:
          smtp_host: smtp.gmail.com
          smtp_port: 587
          username: you@gmail.com
          password: app-password   # Gmail: 16-char app password
          to: recipient@example.com
    Returns True on success, False if config is missing or send fails.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptos.yml")
    with open(CONFIG_PATH) as f:
        import yaml
        cfg = yaml.safe_load(f).get("email") or {}

    host = (cfg.get("smtp_host") or "").strip()
    port = int(cfg.get("smtp_port") or 587)
    username = (cfg.get("username") or "").strip()
    password = (cfg.get("password") or "").strip()
    to_addr = (cfg.get("to") or "").strip()

    if not (host and username and password and to_addr):
        print("Email digest: SMTP config incomplete — skipping.")
        return False

    subject = f"Weekly Signal Digest — {pd.Timestamp.now().date()}"
    plain = build_digest()
    html = build_html_digest()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = to_addr
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    if dry_run:
        print(f"--dry-run: would send email to {to_addr} via {host}:{port}")
        print(plain)
        return True

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, to_addr, msg.as_string())
        print(f"Email digest sent to {to_addr}")
        return True
    except Exception as e:
        print(f"Email digest failed: {e}")
        return False


if __name__ == "__main__":
    print(build_digest())
