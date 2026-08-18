"""Market-cycle classification, derived entirely from stored breadth /
momentum / sector / market-context tables (no network calls here — those
tables are populated by breadth.py, momentum.py, sectors.py and
fetch_and_store_market_context() during the nightly refresh).

Crypto gets a Wyckoff-style phase (Capitulation/Accumulation -> Markup ->
Late-Stage Bull/Euphoria -> Distribution -> Markdown) scored from breadth
level, breadth trend, 52w new highs/lows, Fear & Greed, and the altcoin
season index.

Stocks get a per-GICS-sector RRG-style quadrant (Leading/Improving/
Weakening/Lagging), derived from each sector's breadth level vs its 30d
momentum relative to peer sectors, then rolled up into a Fidelity-style
business-cycle stage (Early/Mid/Late/Recession) from whichever sector
cluster is leading.

Both feed algorithmic_summary(), a digest-style text report.
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import breadth as breadth_mod
import momentum as momentum_mod
import sectors as sectors_mod

BREADTH_TREND_LOOKBACK_DAYS = 28

# Fidelity-style business-cycle sector groupings. Consumer Staples shows up
# in both Late Cycle and Recession/Defensive — it behaves as both a
# late-cycle inflation play and a flight-to-safety sector in practice.
SECTOR_CLUSTERS = {
    "Early Cycle": {"Consumer Discretionary", "Financials", "Real Estate", "Industrials"},
    "Mid Cycle": {"Information Technology", "Communication Services"},
    "Late Cycle": {"Energy", "Materials", "Consumer Staples"},
    "Recession / Defensive": {"Utilities", "Health Care", "Consumer Staples"},
}

_QUADRANT_SCORE = {"Leading": 2, "Improving": 1, "Neutral": 0, "Weakening": -1, "Lagging": -2, "Unknown": 0}

_STAGE_NOTES = {
    "Early Cycle": "Cyclicals (Discretionary/Financials/Industrials/Real Estate) are leading — "
                   "consistent with an early-cycle recovery.",
    "Mid Cycle": "Tech/Communication Services are leading — consistent with a mid-cycle expansion.",
    "Late Cycle": "Energy/Materials/Staples are leading — consistent with a late-cycle, "
                  "inflation-sensitive tape.",
    "Recession / Defensive": "Utilities/Health Care/Staples are leading — defensive rotation "
                              "typical of a slowdown.",
    "Unknown": "Not enough sector data to place a stage.",
}


def _load_market_context() -> dict:
    path = db.table_path("market", "context.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _breadth_trend(category, lookback_days=BREADTH_TREND_LOOKBACK_DAYS):
    """Percentage-point change in pct_above_ma200 over ~lookback_days;
    None if there isn't enough stored history yet."""
    hist = breadth_mod.load_history(category)
    if len(hist) < 2:
        return None
    latest = hist.iloc[-1]
    if pd.isna(latest["pct_above_ma200"]):
        return None
    cutoff = latest["Date"] - pd.Timedelta(days=lookback_days)
    prior = hist[hist["Date"] <= cutoff]
    if prior.empty:
        return None
    prev_val = prior.iloc[-1]["pct_above_ma200"]
    if pd.isna(prev_val):
        return None
    return float(latest["pct_above_ma200"] - prev_val)


def compute_crypto_cycle():
    """Return a dict describing the crypto market-cycle phase, or None if
    breadth history hasn't been recorded yet."""
    hist = breadth_mod.load_history("crypto")
    if hist.empty:
        return None
    row = hist.iloc[-1].to_dict()
    pct_above = row.get("pct_above_ma200")
    if pd.isna(pct_above):
        return None

    score = 0
    reasons = []

    if pct_above >= 0.75:
        score += 2
        reasons.append(f"{pct_above:.0%} of coins above their 200dMA (broad strength)")
    elif pct_above >= 0.60:
        score += 1
        reasons.append(f"{pct_above:.0%} above 200dMA (bullish breadth)")
    elif pct_above <= 0.25:
        score -= 2
        reasons.append(f"only {pct_above:.0%} above 200dMA (broad weakness)")
    elif pct_above <= 0.40:
        score -= 1
        reasons.append(f"{pct_above:.0%} above 200dMA (weak breadth)")
    else:
        reasons.append(f"{pct_above:.0%} above 200dMA (mixed)")

    trend = _breadth_trend("crypto")
    if trend is not None:
        if trend >= 0.10:
            score += 1
            reasons.append(f"breadth rising {trend:+.0%} over ~4wk")
        elif trend <= -0.10:
            score -= 1
            reasons.append(f"breadth falling {trend:+.0%} over ~4wk")

    highs, lows = row.get("new_highs_52w") or 0, row.get("new_lows_52w") or 0
    if highs > lows * 2 and highs > 0:
        score += 1
        reasons.append(f"{highs} new 52w highs vs {lows} lows")
    elif lows > highs * 2 and lows > 0:
        score -= 1
        reasons.append(f"{lows} new 52w lows vs {highs} highs")

    ctx = _load_market_context()
    fng = ctx.get("fear_greed_value")
    extreme_fear = extreme_greed = False
    if fng is not None:
        if fng >= 80:
            score += 1
            extreme_greed = True
            reasons.append(f"Fear & Greed {fng} ({ctx.get('fear_greed_label', 'Extreme Greed')})")
        elif fng <= 20:
            score -= 1
            extreme_fear = True
            reasons.append(f"Fear & Greed {fng} ({ctx.get('fear_greed_label', 'Extreme Fear')})")

    altseason = momentum_mod.load_altcoin_season()
    alt_label = altseason.get("label")
    if alt_label == "Altcoin Season":
        reasons.append(
            f"Altcoin Season ({altseason.get('pct_beating_btc', 0):.0%} of coins beating BTC) "
            "— late-cycle rotation into risk"
        )
    elif alt_label == "BTC Season":
        reasons.append("BTC Season — capital concentrated in majors, not yet chasing alts")

    vol_regime = row.get("vol_regime")
    if vol_regime and vol_regime != "Unknown":
        reasons.append(vol_regime)

    if pct_above <= 0.30 and extreme_fear:
        phase = "Capitulation / Accumulation"
        note = "Extreme fear at depressed breadth is the classic contrarian bottoming signature."
    elif score <= -3:
        phase = "Markdown (Bear)"
        note = "Broad, deteriorating breadth with no offsetting strength signals."
    elif score <= -1:
        phase = "Distribution / Early Bear"
        note = "Breadth is rolling over without confirming a durable new leg down yet."
    elif score == 0:
        phase = "Transition / Range-Bound"
        note = "No dominant signal either way — wait for breadth to break the range."
    elif score <= 2:
        phase = "Markup (Bull)"
        note = "Breadth and trend both point up without euphoric extremes yet."
    elif extreme_greed or alt_label == "Altcoin Season":
        phase = "Late-Stage Bull / Euphoria"
        note = "Strong breadth plus greed/altseason extremes — classic late-cycle distribution risk."
    else:
        phase = "Markup (Bull)"
        note = "Broad strength across coins with no euphoric excess yet."

    return {
        "category": "crypto",
        "phase": phase,
        "score": score,
        "note": note,
        "reasons": reasons,
        "as_of": row.get("Date"),
    }


def _sector_quadrant(pct_above_ma200, ret_30d, median_ret_30d):
    """RRG-style quadrant from breadth level (strength) vs 30d momentum
    relative to the peer-sector median (direction)."""
    if pd.isna(pct_above_ma200) or pd.isna(ret_30d) or pd.isna(median_ret_30d):
        return "Unknown"
    strong = pct_above_ma200 >= 0.55
    weak = pct_above_ma200 <= 0.45
    improving = ret_30d >= median_ret_30d
    if strong and improving:
        return "Leading"
    if strong and not improving:
        return "Weakening"
    if weak and not improving:
        return "Lagging"
    if weak and improving:
        return "Improving"
    return "Neutral"


def compute_sector_quadrants() -> pd.DataFrame:
    """Stored per-sector breadth/momentum with a 'quadrant' column added."""
    df = sectors_mod.load()
    if df.empty:
        return df
    df = df.copy()
    median_ret = df["ret_30d"].median()
    df["quadrant"] = df.apply(
        lambda r: _sector_quadrant(r["pct_above_ma200"], r["ret_30d"], median_ret), axis=1
    )
    return df


def compute_stock_cycle():
    """Return a dict describing the stock-sector business-cycle stage, or
    None if sector breadth hasn't been computed yet."""
    quad = compute_sector_quadrants()
    if quad.empty:
        return None

    cluster_scores = {}
    for cluster, names in SECTOR_CLUSTERS.items():
        rows = quad[quad["sector"].isin(names)]
        if rows.empty:
            continue
        cluster_scores[cluster] = float(rows["quadrant"].map(_QUADRANT_SCORE).mean())

    stage = max(cluster_scores, key=cluster_scores.get) if cluster_scores else "Unknown"

    hist = breadth_mod.load_history("stocks")
    breadth_row = hist.iloc[-1].to_dict() if not hist.empty else {}
    regime = breadth_row.get("regime", "Unknown")
    vol_regime = breadth_row.get("vol_regime")

    leading = quad[quad["quadrant"] == "Leading"].sort_values("pct_above_ma200", ascending=False)
    lagging = quad[quad["quadrant"] == "Lagging"].sort_values("pct_above_ma200")

    reasons = []
    pct_above = breadth_row.get("pct_above_ma200")
    if pct_above is not None and pd.notna(pct_above):
        reasons.append(f"Breadth {regime} ({pct_above:.0%} >200dMA)")
    else:
        reasons.append(f"Breadth {regime}")
    if vol_regime and vol_regime != "Unknown":
        reasons.append(vol_regime)
    if len(leading):
        reasons.append("Leading: " + ", ".join(leading["sector"].head(3)))
    if len(lagging):
        reasons.append("Lagging: " + ", ".join(lagging["sector"].head(3)))

    return {
        "category": "stocks",
        "stage": stage,
        "cluster_scores": cluster_scores,
        "regime": regime,
        "note": _STAGE_NOTES.get(stage, ""),
        "reasons": reasons,
        "quadrants": quad,
        "as_of": breadth_row.get("Date"),
    }


def _crypto_summary_lines(cyc):
    if cyc is None:
        return ["Crypto: not enough breadth history yet — run the pipeline a few times first."]
    lines = [f"Crypto cycle: {cyc['phase']}  (score {cyc['score']:+d})", f"  {cyc['note']}"]
    lines += [f"  - {r}" for r in cyc["reasons"]]
    return lines


def _stock_summary_lines(cyc):
    if cyc is None:
        return ["Stock sectors: not enough sector data yet — run the pipeline a few times first."]
    lines = [f"Stock sectors: {cyc['stage']}  (breadth {cyc['regime']})", f"  {cyc['note']}"]
    lines += [f"  - {r}" for r in cyc["reasons"]]
    quad = cyc["quadrants"]
    if not quad.empty:
        lines.append("  Sector quadrants:")
        for _, r in quad.sort_values("pct_above_ma200", ascending=False).iterrows():
            ret = f"{r['ret_30d']:+.1%}" if pd.notna(r["ret_30d"]) else "n/a"
            lines.append(f"    {r['sector']:<24} {r['quadrant']:<10} {r['pct_above_ma200']:.0%} >200dMA, {ret} 30d")
    return lines


def algorithmic_summary() -> str:
    """Full text report: crypto cycle + stock sector cycle, ready to print,
    tweet-trim, or drop into the email digest."""
    lines = [f"Market Cycle Summary — {pd.Timestamp.now().date()}", ""]
    lines += _crypto_summary_lines(compute_crypto_cycle())
    lines.append("")
    lines += _stock_summary_lines(compute_stock_cycle())
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(algorithmic_summary())
