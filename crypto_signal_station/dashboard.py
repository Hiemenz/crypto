"""Static HTML dashboard generated from the Parquet lake.

Writes a fully self-contained page (inline CSS/SVG/JS, no external requests)
to data/dashboard/index.html after each refresh. Serve it on the LAN with e.g.

    python -m http.server -d data/dashboard 8080

Content: regime stat tiles, a 90-day breadth trend chart (with crosshair
tooltip), today's signals per category/timeframe, recent golden/death
crosses, backtest scoreboard, and the crypto watchlist with sparklines.
Everything is read from stored tables — no network calls at render time.
"""

import html
import json
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import backtest as backtest_mod
import breadth as breadth_mod
import sectors as sectors_mod
import momentum as momentum_mod

# Resolved from this file, not the working directory, so scheduled runs from
# any cwd still find the config.
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptos.yml")

_MARKET_CONTEXT_PATH = None  # resolved lazily below


def _market_ctx_path():
    return db.table_path("market", "context.json")


def _load_market_context() -> dict:
    path = _market_ctx_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

CHART_DAYS = 90
SPARK_DAYS = 90
MAX_SYMBOLS_SHOWN = 12  # per signal cell before folding into <details>

TIMEFRAMES = ["1d", "2d", "3d", "1wk", "2wk"]

CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --s-stocks: #2a78d6; --s-crypto: #1baf7a;
  --buy: #008300; --sell: #e34948;
  --good: #0ca30c; --bad: #d03b3b; --up: #006300; --down: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --s-stocks: #3987e5; --s-crypto: #199e70;
    --buy: #008300; --sell: #e66767;
    --good: #0ca30c; --bad: #d03b3b; --up: #0ca30c; --down: #d03b3b;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19;
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --s-stocks: #3987e5; --s-crypto: #199e70;
  --buy: #008300; --sell: #e66767;
  --good: #0ca30c; --bad: #d03b3b; --up: #0ca30c; --down: #d03b3b;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 1080px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 2px; }
h2 { font-size: 16px; margin: 28px 0 10px; }
.asof { color: var(--ink-2); margin: 0 0 20px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.tile {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px;
}
.tile .label { color: var(--ink-2); font-size: 13px; }
.tile .value { font-size: 28px; font-weight: 600; margin-top: 2px; }
.tile .sub { color: var(--muted); font-size: 12.5px; margin-top: 2px; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); }
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: none; }
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; overflow-x: auto;
}
.legend { display: flex; gap: 18px; margin: 0 0 6px; font-size: 13px; color: var(--ink-2); }
.legend .key { display: inline-block; width: 18px; height: 0; border-top: 2px solid; vertical-align: middle; margin-right: 6px; border-radius: 1px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th { text-align: left; color: var(--ink-2); font-weight: 600; padding: 6px 10px; border-bottom: 1px solid var(--axis); }
td { padding: 6px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.syms { color: var(--ink); }
.tier { white-space: nowrap; }
details { display: inline; }
details summary { cursor: pointer; color: var(--ink-2); display: inline; }
.empty { color: var(--muted); }
.up { color: var(--up); } .down { color: var(--down); }
svg text { font: 12px system-ui, -apple-system, "Segoe UI", sans-serif; fill: var(--muted); }
svg .endlabel { fill: var(--ink-2); }
#tooltip {
  position: fixed; pointer-events: none; display: none; z-index: 10;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 10px; font-size: 13px; box-shadow: 0 2px 10px rgba(0,0,0,.15);
}
#tooltip .tdate { color: var(--ink-2); margin-bottom: 4px; }
#tooltip .trow { display: flex; align-items: center; gap: 7px; }
#tooltip .tkey { width: 14px; border-top: 2px solid; border-radius: 1px; }
#tooltip .tval { font-weight: 600; font-variant-numeric: tabular-nums; }
#tooltip .tname { color: var(--ink-2); }
footer { color: var(--muted); font-size: 12.5px; margin-top: 32px; }
h3 { font-size: 14px; margin: 16px 0 6px; color: var(--ink-2); }
.heatmap td { text-align: center; font-size: 12px; font-variant-numeric: tabular-nums; padding: 5px 6px; }
.heatmap th { text-align: center; font-size: 12px; padding: 5px 6px; }
.bar-cell { font-size: 11px; letter-spacing: -1px; }
.vol-low { color: var(--muted); }
.vol-normal { color: var(--ink-2); }
.vol-high { color: #c07000; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .vol-high { color: #e09020; } }
:root[data-theme="dark"] .vol-high { color: #e09020; }
.tile .vol-sub { font-size: 11.5px; margin-top: 3px; }
.altcoin-season { color: var(--s-crypto); font-weight: 600; }
.btc-season { color: var(--s-stocks); font-weight: 600; }
.neutral-season { color: var(--ink-2); }
.section-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.mini-tile {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px; min-width: 130px; flex: 1;
}
.mini-tile .label { color: var(--ink-2); font-size: 12px; }
.mini-tile .value { font-size: 20px; font-weight: 600; margin-top: 2px; }
.mini-tile .sub { color: var(--muted); font-size: 11.5px; margin-top: 2px; }
"""

CROSSHAIR_JS = """
(function () {
  var data = JSON.parse(document.getElementById('breadth-data').textContent);
  var svg = document.getElementById('breadth-chart');
  if (!svg || !data.dates.length) return;
  var hair = document.getElementById('crosshair');
  var tip = document.getElementById('tooltip');
  var pad = data.pad, W = data.w, H = data.h;
  var n = data.dates.length;
  function xFor(i) { return n < 2 ? pad.l : pad.l + (W - pad.l - pad.r) * i / (n - 1); }

  svg.addEventListener('pointermove', function (ev) {
    var r = svg.getBoundingClientRect();
    var px = (ev.clientX - r.left) * (W / r.width);
    var best = 0, bd = Infinity;
    for (var i = 0; i < n; i++) {
      var d = Math.abs(xFor(i) - px);
      if (d < bd) { bd = d; best = i; }
    }
    hair.setAttribute('x1', xFor(best)); hair.setAttribute('x2', xFor(best));
    hair.style.display = '';
    while (tip.firstChild) tip.removeChild(tip.firstChild);
    var dt = document.createElement('div');
    dt.className = 'tdate'; dt.textContent = data.dates[best];
    tip.appendChild(dt);
    data.series.forEach(function (s) {
      var v = s.values[best];
      if (v === null) return;
      var row = document.createElement('div'); row.className = 'trow';
      var key = document.createElement('span');
      key.className = 'tkey'; key.style.borderTopColor = s.color;
      var val = document.createElement('span');
      val.className = 'tval'; val.textContent = v.toFixed(0) + '%';
      var name = document.createElement('span');
      name.className = 'tname'; name.textContent = s.name;
      row.appendChild(key); row.appendChild(val); row.appendChild(name);
      tip.appendChild(row);
    });
    tip.style.display = 'block';
    var tw = tip.offsetWidth;
    var left = ev.clientX + 14;
    if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
    tip.style.left = left + 'px';
    tip.style.top = (ev.clientY + 14) + 'px';
  });
  svg.addEventListener('pointerleave', function () {
    hair.style.display = 'none'; tip.style.display = 'none';
  });
})();
"""


def _esc(s):
    return html.escape(str(s))


# ── SVG builders ────────────────────────────────────────────────────────────────

def _breadth_chart_svg(histories):
    """90-day '% above 200dMA' line chart for stocks + crypto.

    histories: {name: (color_var, df)} with Date + pct_above_ma200 columns.
    Returns (svg_html, embedded_json) — the JSON drives the crosshair tooltip.
    """
    W, H = 840, 260
    pad = {"l": 44, "r": 96, "t": 12, "b": 26}

    all_dates = sorted(
        {d for _, df in histories.values() for d in df["Date"].dt.normalize()}
    )[-CHART_DAYS:]
    if not all_dates:
        return "<p class='empty'>No breadth history yet — it accrues one point per refresh.</p>", None
    idx = {d: i for i, d in enumerate(all_dates)}
    n = len(all_dates)

    def x(i):
        return pad["l"] if n < 2 else pad["l"] + (W - pad["l"] - pad["r"]) * i / (n - 1)

    def y(pct):  # 0..100
        return pad["t"] + (H - pad["t"] - pad["b"]) * (1 - pct / 100)

    parts = [
        f'<svg id="breadth-chart" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Share of symbols above their 200-day moving average, last {CHART_DAYS} days" '
        'style="width:100%;height:auto;display:block">'
    ]
    for gv in (0, 25, 50, 75, 100):
        gy = y(gv)
        parts.append(
            f'<line x1="{pad["l"]}" y1="{gy:.1f}" x2="{W - pad["r"]}" y2="{gy:.1f}" '
            'stroke="var(--grid)" stroke-width="1"/>'
        )
        parts.append(f'<text x="{pad["l"] - 8}" y="{gy + 4:.1f}" text-anchor="end">{gv}%</text>')

    tick_is = sorted({0, n // 2, n - 1})
    for i in tick_is:
        parts.append(
            f'<text x="{x(i):.1f}" y="{H - 6}" text-anchor="middle">'
            f"{all_dates[i].strftime('%b %d')}</text>"
        )

    series_json = []
    for name, (color, df) in histories.items():
        pts = {}
        for d, v in zip(df["Date"].dt.normalize(), df["pct_above_ma200"]):
            if d in idx and pd.notna(v):
                pts[idx[d]] = float(v) * 100
        values = [pts.get(i) for i in range(n)]
        coords = [(x(i), y(v)) for i, v in enumerate(values) if v is not None]
        if not coords:
            continue
        path = "M" + " L".join(f"{cx:.1f} {cy:.1f}" for cx, cy in coords)
        parts.append(
            f'<path d="{path}" fill="none" stroke="var({color})" '
            'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        ex, ey = coords[-1]
        # end dot with a 2px surface ring, then a direct end label
        parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="6" fill="var(--surface)"/>')
        parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="var({color})"/>')
        last_val = next(v for v in reversed(values) if v is not None)
        parts.append(
            f'<text class="endlabel" x="{ex + 10:.1f}" y="{ey + 4:.1f}">'
            f"{_esc(name)} {last_val:.0f}%</text>"
        )
        series_json.append(
            {"name": name, "color": _css_color(color), "values": values}
        )

    parts.append(
        f'<line id="crosshair" x1="0" y1="{pad["t"]}" x2="0" y2="{H - pad["b"]}" '
        'stroke="var(--axis)" stroke-width="1" style="display:none"/>'
    )
    parts.append(
        f'<rect x="{pad["l"]}" y="{pad["t"]}" width="{W - pad["l"] - pad["r"]}" '
        f'height="{H - pad["t"] - pad["b"]}" fill="transparent"/>'
    )
    parts.append("</svg>")

    payload = {
        "dates": [d.strftime("%Y-%m-%d") for d in all_dates],
        "series": series_json,
        "w": W, "h": H, "pad": pad,
    }
    return "".join(parts), payload


def _css_color(var_name):
    # The tooltip is DOM (not SVG), built in JS; give it the var() reference
    return f"var({var_name})"


def _sparkline_svg(closes):
    """Tiny single-series sparkline: muted line, accent end dot."""
    W, H, P = 120, 30, 3
    vals = [float(v) for v in closes if pd.notna(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)

    def pt(i, v):
        return (P + (W - 2 * P) * i / (n - 1), P + (H - 2 * P) * (1 - (v - lo) / rng))

    coords = [pt(i, v) for i, v in enumerate(vals)]
    path = "M" + " L".join(f"{cx:.1f} {cy:.1f}" for cx, cy in coords)
    ex, ey = coords[-1]
    return (
        f'<svg viewBox="0 0 {W} {H}" style="width:120px;height:30px" aria-hidden="true">'
        f'<path d="{path}" fill="none" stroke="var(--muted)" stroke-width="2" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="var(--surface)"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="var(--s-crypto)"/>'
        "</svg>"
    )


# ── HTML sections ───────────────────────────────────────────────────────────────

def _regime_dot(regime):
    color = {"Risk-On": "var(--good)", "Risk-Off": "var(--bad)"}.get(regime, "var(--muted)")
    return f'<span class="dot" style="background:{color}"></span>'


def _vol_regime_cls(regime):
    return {"Low Vol": "vol-low", "High Vol": "vol-high"}.get(regime, "vol-normal")


def _tiles_html(rows, signal_counts):
    tiles = []
    for cat, label in (("stocks", "Stocks breadth"), ("crypto", "Crypto breadth")):
        row = rows.get(cat)
        if not row:
            continue
        pct = row["pct_above_ma200"]
        pct_str = f"{pct:.0%}" if pd.notna(pct) else "n/a"
        vol = row.get("avg_vol_20d")
        vol_regime = row.get("vol_regime", "")
        vol_str = ""
        if vol is not None and not pd.isna(vol):
            vcls = _vol_regime_cls(vol_regime)
            vol_str = (
                f'<div class="vol-sub {vcls}">Vol {vol:.0%} annlzd &nbsp;·&nbsp; '
                f'{_esc(vol_regime)}</div>'
            )
        tiles.append(
            '<div class="tile">'
            f'<div class="label">{label} &gt;200dMA</div>'
            f'<div class="value">{pct_str}</div>'
            f'<div class="chip">{_regime_dot(row["regime"])}{_esc(row["regime"])}'
            f' &nbsp;·&nbsp; 52w H/L {row["new_highs_52w"]}/{row["new_lows_52w"]}</div>'
            + vol_str +
            "</div>"
        )
    buys, sells = signal_counts
    tiles.append(
        '<div class="tile">'
        '<div class="label">Signals today (all timeframes)</div>'
        f'<div class="value">{buys + sells}</div>'
        f'<div class="sub"><span class="dot" style="background:var(--buy)"></span> {buys} buy'
        f' &nbsp; <span class="dot" style="background:var(--sell)"></span> {sells} sell</div>'
        "</div>"
    )
    return '<div class="tiles">' + "".join(tiles) + "</div>"


def _symbol_cell(pairs):
    """pairs: [(symbol, tier)] → 'SYM (tier)' list, folded when long."""
    if not pairs:
        return '<span class="empty">—</span>'
    frags = [f'{_esc(s)}&nbsp;<span class="tier">({_esc(t.split()[0])})</span>' for s, t in pairs]
    if len(frags) <= MAX_SYMBOLS_SHOWN:
        return '<span class="syms">' + ", ".join(frags) + "</span>"
    head = ", ".join(frags[:MAX_SYMBOLS_SHOWN])
    rest = ", ".join(frags[MAX_SYMBOLS_SHOWN:])
    return (
        f'<span class="syms">{head}, </span>'
        f"<details><summary>+{len(frags) - MAX_SYMBOLS_SHOWN} more</summary>"
        f'<span class="syms">{rest}</span></details>'
    )


def _signals_section(latest_signals):
    out = []
    for cat in ("crypto", "stocks"):
        rows = []
        for tf in TIMEFRAMES:
            info = latest_signals.get((cat, tf))
            if not info:
                continue
            date, buys, sells = info
            rows.append(
                f"<tr><td>{tf}</td><td>{date:%Y-%m-%d}</td>"
                f"<td>{_symbol_cell(buys)}</td><td>{_symbol_cell(sells)}</td></tr>"
            )
        if not rows:
            continue
        out.append(f"<h2>{'Crypto' if cat == 'crypto' else 'Stocks'} — latest signals</h2>")
        out.append(
            '<div class="card"><table>'
            "<tr><th>Timeframe</th><th>As of</th>"
            '<th><span class="dot" style="background:var(--buy)"></span> Buys</th>'
            '<th><span class="dot" style="background:var(--sell)"></span> Sells</th></tr>'
            + "".join(rows)
            + "</table></div>"
        )
    return "".join(out)


def _crosses_section(crosses):
    if crosses is None:
        return ""
    out = ["<h2>Golden / death crosses (last 30 days, daily bars)</h2>", '<div class="card">']
    if crosses.empty:
        out.append('<p class="empty">None.</p>')
    else:
        rows = "".join(
            f"<tr><td>{r.Date:%Y-%m-%d}</td><td>{_esc(r.symbol)}</td>"
            f"<td>{_esc(r.category)}</td><td>{r.kind}</td></tr>"
            for r in crosses.itertuples()
        )
        out.append(
            "<table><tr><th>Date</th><th>Symbol</th><th>Category</th><th>Event</th></tr>"
            + rows + "</table>"
        )
    out.append("</div>")
    return "".join(out)


def _backtest_section(stats):
    if stats.empty:
        return (
            "<h2>Signal backtest</h2><div class='card'><p class='empty'>"
            "No backtest yet — run: poetry run python crypto_signal_station/crypto_signal_pipeline.py backtest"
            "</p></div>"
        )
    rows = []
    for (cat, tf), g in stats.groupby(["category", "timeframe"], sort=True):
        tiers = sorted(
            g["signal"].unique(),
            key=lambda t: backtest_mod.TIER_ORDER.index(t)
            if t in backtest_mod.TIER_ORDER else 99,
        )
        base30 = g.loc[g["horizon_days"] == 30, "baseline_return"]
        base_str = f"{base30.iloc[0]:+.1%}" if len(base30) else "n/a"
        for tier in tiers:
            r30 = g[(g["signal"] == tier) & (g["horizon_days"] == 30)]
            r90 = g[(g["signal"] == tier) & (g["horizon_days"] == 90)]
            if r30.empty:
                continue
            row = r30.iloc[0]
            side_color = "var(--buy)" if row["side"] == "buy" else "var(--sell)"
            beats = pd.notna(row["baseline_return"]) and (
                row["avg_return"] > row["baseline_return"]
                if row["side"] == "buy"
                else row["avg_return"] < row["baseline_return"]
            )
            beat_cls = "up" if beats else "down"
            r90_str = f"{r90.iloc[0]['avg_return']:+.1%}" if len(r90) else "n/a"
            rows.append(
                f"<tr><td>{_esc(cat)}</td><td>{_esc(tf)}</td>"
                f'<td><span class="dot" style="background:{side_color}"></span> {_esc(tier)}</td>'
                f'<td class="num">{int(row["n"])}</td>'
                f'<td class="num {beat_cls}">{row["avg_return"]:+.1%}</td>'
                f'<td class="num">{row["win_rate"]:.0%}</td>'
                f'<td class="num">{base_str}</td>'
                f'<td class="num">{r90_str}</td></tr>'
            )
    return (
        "<h2>Signal backtest — average forward returns</h2>"
        '<div class="card"><table>'
        "<tr><th>Category</th><th>Timeframe</th><th>Tier</th>"
        '<th class="num">n</th><th class="num">30d avg</th><th class="num">30d win</th>'
        '<th class="num">30d baseline</th><th class="num">90d avg</th></tr>'
        + "".join(rows)
        + "</table>"
        "<p class='empty'>Green 30d avg = beats the unconditional baseline for its side; "
        "win = share of signals whose price moved the called direction.</p></div>"
    )


def _watchlist_section(watchlist_frames):
    if not watchlist_frames:
        return ""
    rows = []
    for sym, df in watchlist_frames.items():
        closes = df["Close"].tail(SPARK_DAYS)
        if closes.empty:
            continue
        last = float(closes.iloc[-1])
        month_ago = df[df["Date"] <= df["Date"].max() - pd.Timedelta(days=30)]
        delta_html = '<span class="empty">n/a</span>'
        if not month_ago.empty and float(month_ago["Close"].iloc[-1]) > 0:
            delta = last / float(month_ago["Close"].iloc[-1]) - 1
            cls = "up" if delta >= 0 else "down"
            delta_html = f'<span class="{cls}">{delta:+.1%}</span>'
        price = f"${last:,.4f}" if last < 1 else f"${last:,.2f}"
        rows.append(
            f"<tr><td>{_esc(sym)}</td><td class='num'>{price}</td>"
            f"<td class='num'>{delta_html}</td><td>{_sparkline_svg(closes)}</td></tr>"
        )
    if not rows:
        return ""
    return (
        "<h2>Crypto watchlist</h2>"
        '<div class="card"><table>'
        '<tr><th>Symbol</th><th class="num">Last close</th><th class="num">30d</th>'
        f"<th>{SPARK_DAYS}d trend</th></tr>"
        + "".join(rows)
        + "</table></div>"
    )


# ── new feature sections ────────────────────────────────────────────────────────

def _fmt_cap(v):
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    return f"${v:,.0f}"


def _fmt_ret(v, signed=True):
    if v is None or pd.isna(v):
        return "n/a"
    cls = "up" if v >= 0 else "down"
    s = f"{v:+.2%}" if signed else f"{v:.2%}"
    return f'<span class="{cls}">{s}</span>'


def _market_overview_section(ctx: dict) -> str:
    if not ctx:
        return ""

    parts = ["<h2>Market Overview</h2>", '<div class="section-row">']

    # Crypto tiles
    btc_dom = ctx.get("btc_dominance")
    eth_dom = ctx.get("eth_dominance")
    if btc_dom is not None:
        sub = f"ETH {eth_dom:.1f}%" if eth_dom is not None else ""
        parts.append(
            '<div class="mini-tile">'
            '<div class="label">BTC Dominance</div>'
            f'<div class="value">{btc_dom:.1f}%</div>'
            f'<div class="sub">{sub}</div>'
            "</div>"
        )

    tmc = ctx.get("total_market_cap_usd")
    tmc_chg = ctx.get("market_cap_change_24h_pct")
    if tmc is not None:
        chg_html = _fmt_ret(tmc_chg / 100 if tmc_chg is not None else None)
        parts.append(
            '<div class="mini-tile">'
            '<div class="label">Crypto Market Cap</div>'
            f'<div class="value">{_fmt_cap(tmc)}</div>'
            f'<div class="sub">{chg_html} 24h</div>'
            "</div>"
        )

    fng_v = ctx.get("fear_greed_value")
    fng_l = ctx.get("fear_greed_label", "")
    if fng_v is not None:
        fng_cls = "down" if fng_v < 40 else ("up" if fng_v > 60 else "")
        parts.append(
            '<div class="mini-tile">'
            '<div class="label">Fear &amp; Greed</div>'
            f'<div class="value"><span class="{fng_cls}">{fng_v}</span></div>'
            f'<div class="sub">{_esc(fng_l)}</div>'
            "</div>"
        )

    # Stock index ETF tiles
    for key, label in [("spy", "SPY"), ("qqq", "QQQ"), ("dia", "DIA")]:
        last = ctx.get(f"{key}_last")
        ret_1d = ctx.get(f"{key}_ret_1d")
        ret_1m = ctx.get(f"{key}_ret_1m")
        if last is None:
            continue
        price_str = f"${last:,.2f}"
        parts.append(
            '<div class="mini-tile">'
            f'<div class="label">{label}</div>'
            f'<div class="value">{_fmt_ret(ret_1d)} today</div>'
            f'<div class="sub">{price_str} &nbsp;·&nbsp; 1m {_fmt_ret(ret_1m)}</div>'
            "</div>"
        )

    parts.append("</div>")
    return "".join(parts)


def _altcoin_season_section() -> str:
    data = momentum_mod.load_altcoin_season()
    if not data:
        return ""
    label = data.get("label", "")
    pct = data.get("pct_beating_btc")
    n_total = data.get("n_total", 0)
    btc_ret = data.get("btc_ret_90d")
    pct_str = f"{pct:.0%}" if pct is not None else "n/a"
    btc_str = f"{btc_ret:+.1%}" if btc_ret is not None else "n/a"
    lbl_cls = {
        "Altcoin Season": "altcoin-season",
        "BTC Season": "btc-season",
        "Neutral": "neutral-season",
    }.get(label, "")
    return (
        "<h2>Altcoin Season Index</h2>"
        '<div class="card" style="padding:12px 16px">'
        f'<span class="{lbl_cls}" style="font-size:20px">{_esc(label)}</span>'
        f'<span style="color:var(--ink-2);font-size:13px;margin-left:16px">'
        f"{pct_str} of {n_total} cryptos beating BTC over 90d &nbsp;·&nbsp; "
        f"BTC 90d return: {btc_str}"
        "</span></div>"
    )


def _rsi_divergences_data() -> dict:
    """Return {category: {bullish: [syms], bearish: [syms]}} for today's 1d bars."""
    result = {}
    for cat in ("crypto", "stocks"):
        try:
            df = db.scan_signals_lake(
                cat, "1d", columns=["Date", "rsi_bullish_div", "rsi_bearish_div"]
            )
        except Exception:
            continue
        if df.empty:
            continue
        has_bull = "rsi_bullish_div" in df.columns
        has_bear = "rsi_bearish_div" in df.columns
        if not has_bull and not has_bear:
            continue
        today = df[df["Date"] == df["Date"].max()]
        bull = (
            sorted(today.loc[today["rsi_bullish_div"].fillna(False).astype(bool), "symbol"].unique())
            if has_bull else []
        )
        bear = (
            sorted(today.loc[today["rsi_bearish_div"].fillna(False).astype(bool), "symbol"].unique())
            if has_bear else []
        )
        if bull or bear:
            result[cat] = {"bullish": bull, "bearish": bear}
    return result


def _rsi_divergences_section(div_data: dict) -> str:
    if not div_data:
        return ""
    rows = []
    for cat in ("crypto", "stocks"):
        entry = div_data.get(cat)
        if not entry:
            continue
        cat_label = "Crypto" if cat == "crypto" else "Stocks"
        for sym in entry.get("bullish", []):
            rows.append(
                f"<tr><td>{_esc(sym)}</td><td>{cat_label}</td>"
                f'<td><span class="up">Bullish</span> — price near low, RSI recovering</td></tr>'
            )
        for sym in entry.get("bearish", []):
            rows.append(
                f"<tr><td>{_esc(sym)}</td><td>{cat_label}</td>"
                f'<td><span class="down">Bearish</span> — price near high, RSI fading</td></tr>'
            )
    if not rows:
        return ""
    return (
        "<h2>RSI Divergences (today, daily bars)</h2>"
        '<div class="card"><table>'
        "<tr><th>Symbol</th><th>Category</th><th>Signal</th></tr>"
        + "".join(rows)
        + "</table></div>"
    )


def _conviction_section(latest_signals):
    """Symbols where 2+ timeframes agree on buy or sell direction."""
    sym_buy: dict = {}
    sym_sell: dict = {}
    for (cat, tf), (date, buys, sells) in latest_signals.items():
        for sym, _ in buys:
            sym_buy[sym] = sym_buy.get(sym, 0) + 1
        for sym, _ in sells:
            sym_sell[sym] = sym_sell.get(sym, 0) + 1

    high_buy = sorted([(s, c) for s, c in sym_buy.items() if c >= 2], key=lambda x: -x[1])
    high_sell = sorted([(s, c) for s, c in sym_sell.items() if c >= 2], key=lambda x: -x[1])
    if not high_buy and not high_sell:
        return ""

    rows = []
    for sym, count in high_buy:
        bar = "█" * count + "░" * (5 - count)
        rows.append(
            f"<tr><td>{_esc(sym)}</td><td class='num'>{count}/5</td>"
            f"<td><span style='color:var(--buy)'>{bar} Buy</span></td></tr>"
        )
    for sym, count in high_sell:
        bar = "█" * count + "░" * (5 - count)
        rows.append(
            f"<tr><td>{_esc(sym)}</td><td class='num'>{count}/5</td>"
            f"<td><span style='color:var(--sell)'>{bar} Sell</span></td></tr>"
        )
    return (
        "<h2>High-conviction signals (2+ timeframes agree)</h2>"
        '<div class="card"><table>'
        "<tr><th>Symbol</th><th class='num'>Timeframes</th><th>Direction</th></tr>"
        + "".join(rows)
        + "</table></div>"
    )


def _volume_spikes_data():
    """Symbols with vol_spike on their latest daily bar, per category."""
    result = {}
    for cat in ("crypto", "stocks"):
        try:
            df = db.scan_signals_lake(cat, "1d", columns=["Date", "vol_spike"])
        except Exception:
            continue
        if df.empty or "vol_spike" not in df.columns:
            continue
        latest = df["Date"].max()
        spikes = df[(df["Date"] == latest) & df["vol_spike"].fillna(False)]
        if not spikes.empty:
            result[cat] = sorted(spikes["symbol"].unique())
    return result


def _volume_spikes_section(spikes_data):
    if not spikes_data:
        return ""
    parts = ["<h2>Volume spikes today (2× 20-day average)</h2>", '<div class="card">']
    for cat, syms in spikes_data.items():
        label = "Crypto" if cat == "crypto" else "Stocks"
        parts.append(f"<p><strong>{label}:</strong> {', '.join(_esc(s) for s in syms)}</p>")
    parts.append("</div>")
    return "".join(parts)


def _sector_breadth_section():
    df = sectors_mod.load()
    if df.empty:
        return ""
    has_ret = "ret_30d" in df.columns
    has_sigs = "buy_signals" in df.columns and "sell_signals" in df.columns
    rows = []
    for r in df.itertuples():
        pct = r.pct_above_ma200
        breadth_cls = "up" if pct >= 0.6 else ("down" if pct <= 0.4 else "")
        filled = round(pct * 10)
        bar = "█" * filled + "░" * (10 - filled)
        ret_td = ""
        if has_ret:
            ret = getattr(r, "ret_30d", None)
            if ret is not None and not pd.isna(ret):
                rcls = "up" if ret >= 0 else "down"
                ret_td = f"<td class='num {rcls}'>{ret:+.1%}</td>"
            else:
                ret_td = "<td class='num'>—</td>"
        sig_td = ""
        if has_sigs:
            buys = getattr(r, "buy_signals", 0) or 0
            sells = getattr(r, "sell_signals", 0) or 0
            sig_td = (
                f"<td class='num'>"
                f'<span style="color:var(--buy)">{buys}↑</span>'
                f' <span style="color:var(--sell)">{sells}↓</span>'
                "</td>"
            )
        rows.append(
            f"<tr><td>{_esc(r.sector)}</td>"
            f"<td class='num {breadth_cls}'>{pct:.0%}</td>"
            f"<td class='num'>{r.n}</td>"
            f"<td class='bar-cell' style='color:var(--muted)'>{bar}</td>"
            + ret_td + sig_td
            + "</tr>"
        )
    ret_th = "<th class='num'>30d return</th>" if has_ret else ""
    sig_th = "<th class='num'>Signals↑↓</th>" if has_sigs else ""
    return (
        "<h2>S&amp;P 500 — breadth by GICS sector</h2>"
        '<div class="card"><table>'
        "<tr><th>Sector</th><th class='num'>Above 200dMA</th>"
        f"<th class='num'>n</th><th>Bar</th>{ret_th}{sig_th}</tr>"
        + "".join(rows)
        + "</table></div>"
    )


def _momentum_section():
    df = momentum_mod.load()
    if df.empty or "ret_30d" not in df.columns:
        return ""

    N = 10
    parts = ["<h2>Momentum — top &amp; bottom movers by 1-month return</h2>"]

    def _row(r):
        def fmt(v):
            if v is None or (hasattr(v, '__class__') and v.__class__.__name__ == 'float' and pd.isna(v)):
                return "<td class='num'>—</td>"
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return "<td class='num'>—</td>"
            if pd.isna(fv):
                return "<td class='num'>—</td>"
            cls = "up" if fv >= 0 else "down"
            return f"<td class='num {cls}'>{fv:+.1%}</td>"
        return (
            f"<tr><td>{_esc(r.symbol)}</td>"
            + fmt(r.ret_30d) + fmt(r.ret_90d) + fmt(r.ret_180d)
            + "</tr>"
        )

    for cat in ("stocks", "crypto"):
        sub = df[df["category"] == cat].dropna(subset=["ret_30d"])
        if sub.empty:
            continue
        label = "Stocks" if cat == "stocks" else "Crypto"
        parts.append(f"<h3>{label}</h3>")
        parts.append(
            '<div class="card"><table>'
            "<tr><th>Symbol</th><th class='num'>1m</th>"
            "<th class='num'>3m</th><th class='num'>6m</th></tr>"
        )
        top = sub.nlargest(N, "ret_30d")
        bottom = sub.nsmallest(N, "ret_30d")
        parts.append(
            "<tr><td colspan='4' style='color:var(--ink-2);font-size:12px;"
            "padding:3px 10px'>▲ Top gainers</td></tr>"
        )
        for r in top.itertuples():
            parts.append(_row(r))
        parts.append(
            "<tr><td colspan='4' style='color:var(--ink-2);font-size:12px;"
            "padding:3px 10px'>▼ Top losers</td></tr>"
        )
        for r in bottom.itertuples():
            parts.append(_row(r))
        parts.append("</table></div>")

    return "".join(parts)


def _correlation_heatmap_html(watchlist_frames):
    """30-day daily return correlation matrix for the crypto watchlist."""
    if len(watchlist_frames) < 2:
        return ""

    closes = pd.DataFrame({
        sym: df.set_index("Date")["Close"].tail(30)
        for sym, df in watchlist_frames.items()
    })
    rets = closes.pct_change().dropna()
    if len(rets) < 5:
        return ""

    corr = rets.corr()
    syms = list(corr.columns)
    labels = [s.replace("-USD", "") for s in syms]

    def _cell_style(val):
        if pd.isna(val):
            return ""
        alpha = min(0.70, abs(float(val)) * 0.70)
        if val > 0:
            return f"background:rgba(0,131,0,{alpha:.2f})"
        return f"background:rgba(227,73,72,{alpha:.2f})"

    header = (
        "<tr><th></th>"
        + "".join(f"<th>{_esc(lb)}</th>" for lb in labels)
        + "</tr>"
    )
    rows = []
    for i, s1 in enumerate(syms):
        cells = f"<th>{_esc(labels[i])}</th>"
        for s2 in syms:
            val = corr.loc[s1, s2]
            style = _cell_style(val)
            text = f"{val:.2f}" if not pd.isna(val) else "—"
            cells += f'<td style="{style}">{text}</td>'
        rows.append(f"<tr>{cells}</tr>")

    return (
        "<h2>Crypto watchlist — 30-day return correlations</h2>"
        '<div class="card" style="overflow-x:auto">'
        '<table class="heatmap">'
        + header + "".join(rows)
        + "</table></div>"
    )


# ── data assembly ───────────────────────────────────────────────────────────────

def _latest_signals():
    """{(category, timeframe): (date, [(sym, tier) buys], [(sym, tier) sells])}
    plus overall (buys, sells) distinct-symbol counts."""
    out = {}
    buy_syms, sell_syms = set(), set()
    for cat in ("crypto", "stocks"):
        for tf in TIMEFRAMES:
            sigs = db.scan_signals_lake(cat, tf, columns=["Date", "signal"])
            if sigs.empty:
                continue
            latest = sigs["Date"].max()
            day = sigs[(sigs["Date"] == latest) & (sigs["signal"] != "Hold")]
            buys = sorted(
                (r.symbol, r.signal) for r in day.itertuples() if r.signal.endswith("Buy")
            )
            sells = sorted(
                (r.symbol, r.signal) for r in day.itertuples() if r.signal.endswith("Sell")
            )
            out[(cat, tf)] = (latest, buys, sells)
            buy_syms |= {s for s, _ in buys}
            sell_syms |= {s for s, _ in sells}
    return out, (len(buy_syms), len(sell_syms))


def _recent_crosses():
    """Golden/death crosses on daily bars in the last 30 days, or None when no
    category has those columns yet (they appear on the first refresh after the
    indicator update). A category without the columns must not hide the other."""
    frames = []
    any_valid = False
    for cat in ("crypto", "stocks"):
        try:
            df = db.scan_signals_lake(cat, "1d", columns=["Date", "golden_cross", "death_cross"])
        except Exception:
            continue
        if df.empty or "golden_cross" not in df.columns:
            continue
        any_valid = True
        cutoff = df["Date"].max() - pd.Timedelta(days=30)
        recent = df[df["Date"] >= cutoff]
        for col, kind in (("golden_cross", "Golden cross"), ("death_cross", "Death cross")):
            hits = recent[recent[col].fillna(False)]
            for r in hits.itertuples():
                frames.append({"Date": r.Date, "symbol": r.symbol, "category": cat, "kind": kind})
    if not any_valid:
        return None
    if not frames:
        return pd.DataFrame(columns=["Date", "symbol", "category", "kind"])
    return pd.DataFrame(frames).sort_values("Date", ascending=False).reset_index(drop=True)


def _watchlist_data():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    watch = list(cfg.get("cryptos", []))
    if not watch:
        return {}
    lake = db.scan_ohlcv_lake("crypto", columns=["Date", "Close"])
    if lake.empty:
        return {}
    lake = lake[lake["symbol"].isin(watch)].sort_values(["symbol", "Date"])
    return {sym: g.reset_index(drop=True) for sym, g in lake.groupby("symbol") if sym in watch}


def generate(output_path=None) -> str:
    """Build the dashboard; returns the path written."""
    output_path = output_path or db.table_path("dashboard", "index.html")

    histories = {}
    latest_rows = {}
    for cat, color, name in (("stocks", "--s-stocks", "Stocks"), ("crypto", "--s-crypto", "Crypto")):
        hist = breadth_mod.load_history(cat)
        if not hist.empty:
            histories[name] = (color, hist)
            latest_rows[cat] = hist.iloc[-1].to_dict()

    latest_signals, signal_counts = _latest_signals()
    chart_svg, chart_payload = _breadth_chart_svg(histories) if histories else (
        "<p class='empty'>No breadth history yet — it accrues one point per refresh.</p>", None)
    watchlist_frames = _watchlist_data()
    spikes_data = _volume_spikes_data()
    market_ctx = _load_market_context()
    div_data = _rsi_divergences_data()

    body = [
        "<main>",
        "<h1>Crypto Signal Station</h1>",
        f'<p class="asof">Generated {pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")} local · reads nightly Parquet lake</p>',
        _market_overview_section(market_ctx),
        _tiles_html(latest_rows, signal_counts),
        f"<h2>Market breadth — % of symbols above 200-day MA ({CHART_DAYS}d)</h2>",
        '<div class="card">',
        '<div class="legend">'
        '<span><span class="key" style="border-top-color:var(--s-stocks)"></span>Stocks</span>'
        '<span><span class="key" style="border-top-color:var(--s-crypto)"></span>Crypto</span>'
        "</div>",
        chart_svg,
        "</div>",
        _altcoin_season_section(),
        _conviction_section(latest_signals),
        _rsi_divergences_section(div_data),
        _signals_section(latest_signals),
        _volume_spikes_section(spikes_data),
        _crosses_section(_recent_crosses()),
        _backtest_section(backtest_mod.load_stats()),
        _sector_breadth_section(),
        _momentum_section(),
        _watchlist_section(watchlist_frames),
        _correlation_heatmap_html(watchlist_frames),
        "<footer>Static page regenerated after each pipeline refresh. "
        "Serve with: python -m http.server -d data/dashboard 8080</footer>",
        "</main>",
        '<div id="tooltip"></div>',
    ]
    if chart_payload:
        body.append(
            '<script type="application/json" id="breadth-data">'
            + json.dumps(chart_payload)
            + "</script>"
        )
        body.append("<script>" + CROSSHAIR_JS + "</script>")

    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Crypto Signal Station</title>"
        f"<style>{CSS}</style></head><body>"
        + "".join(body)
        + "</body></html>"
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(page)
    print(f"Dashboard written to {output_path}")
    return output_path


if __name__ == "__main__":
    generate()
