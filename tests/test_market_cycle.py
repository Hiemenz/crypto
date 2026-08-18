import json
import os

import pandas as pd
import pytest

import db
from crypto_signal_station import breadth, market_cycle, sectors


def _breadth_row(date, pct_above_ma200, new_highs=0, new_lows=0, vol_regime="Normal Vol"):
    return {
        "Date": pd.Timestamp(date),
        "category": "crypto",
        "n_active": 10,
        "pct_above_ma200": pct_above_ma200,
        "pct_bull": pct_above_ma200,
        "new_highs_52w": new_highs,
        "new_lows_52w": new_lows,
        "pct_buy_signal": float("nan"),
        "pct_sell_signal": float("nan"),
        "regime": breadth.regime_label(pct_above_ma200),
        "avg_vol_20d": 0.6,
        "pct_high_vol": 0.5,
        "vol_regime": vol_regime,
    }


def _write_breadth_history(category, rows):
    df = pd.DataFrame(rows)
    df["category"] = category
    db.save_table(df, breadth._history_path(category))


def _write_market_context(**ctx):
    path = db.table_path("market", "context.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(ctx, f)


def _write_altcoin_season(label, pct_beating_btc=0.8):
    path = db.table_path("momentum", "altcoin_season.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"label": label, "pct_beating_btc": pct_beating_btc}, f)


def test_compute_crypto_cycle_none_without_breadth_history(lake):
    assert market_cycle.compute_crypto_cycle() is None


def test_compute_crypto_cycle_bull_phase(lake):
    _write_breadth_history(
        "crypto", [_breadth_row("2026-08-17", 0.65, new_highs=6, new_lows=1)]
    )
    cyc = market_cycle.compute_crypto_cycle()
    assert cyc["phase"] == "Markup (Bull)"
    assert cyc["score"] >= 1


def test_compute_crypto_cycle_capitulation_on_extreme_fear(lake):
    _write_breadth_history("crypto", [_breadth_row("2026-08-17", 0.15)])
    _write_market_context(fear_greed_value=10, fear_greed_label="Extreme Fear")
    cyc = market_cycle.compute_crypto_cycle()
    assert cyc["phase"] == "Capitulation / Accumulation"
    assert any("Extreme Fear" in r for r in cyc["reasons"])


def test_compute_crypto_cycle_euphoria_on_extreme_greed(lake):
    _write_breadth_history("crypto", [_breadth_row("2026-08-17", 0.80, new_highs=10)])
    _write_market_context(fear_greed_value=85, fear_greed_label="Extreme Greed")
    cyc = market_cycle.compute_crypto_cycle()
    assert cyc["phase"] == "Late-Stage Bull / Euphoria"


def test_compute_crypto_cycle_euphoria_on_altcoin_season(lake):
    _write_breadth_history("crypto", [_breadth_row("2026-08-17", 0.80, new_highs=10)])
    _write_altcoin_season("Altcoin Season", pct_beating_btc=0.9)
    cyc = market_cycle.compute_crypto_cycle()
    assert cyc["phase"] == "Late-Stage Bull / Euphoria"
    assert any("Altcoin Season" in r for r in cyc["reasons"])


def test_compute_crypto_cycle_bear_phase(lake):
    _write_breadth_history("crypto", [_breadth_row("2026-08-17", 0.15, new_lows=8)])
    cyc = market_cycle.compute_crypto_cycle()
    assert cyc["phase"] == "Markdown (Bear)"
    assert cyc["score"] <= -3


def test_breadth_trend_adds_to_score(lake):
    old = _breadth_row("2026-07-15", 0.40)  # 33 days before "now" below
    new = _breadth_row("2026-08-17", 0.65, new_highs=1)
    _write_breadth_history("crypto", [old, new])
    trend = market_cycle._breadth_trend("crypto")
    assert trend == pytest.approx(0.25)


def test_sector_quadrant_labels():
    assert market_cycle._sector_quadrant(0.60, 0.10, 0.02) == "Leading"
    assert market_cycle._sector_quadrant(0.60, -0.05, 0.02) == "Weakening"
    assert market_cycle._sector_quadrant(0.30, -0.05, 0.02) == "Lagging"
    assert market_cycle._sector_quadrant(0.30, 0.10, 0.02) == "Improving"
    assert market_cycle._sector_quadrant(0.50, 0.02, 0.02) == "Neutral"
    assert market_cycle._sector_quadrant(float("nan"), 0.02, 0.02) == "Unknown"


def test_compute_stock_cycle_none_without_sector_data(lake):
    assert market_cycle.compute_stock_cycle() is None


def test_compute_stock_cycle_picks_leading_cluster(lake):
    # Early-cycle sectors leading (strong + above-median momentum);
    # everything else lagging (weak + below-median momentum).
    rows = []
    for sector in ("Consumer Discretionary", "Financials", "Real Estate", "Industrials"):
        rows.append({"sector": sector, "n": 5, "pct_above_ma200": 0.70, "ret_30d": 0.08,
                      "buy_signals": 0, "sell_signals": 0})
    for sector in ("Utilities", "Health Care", "Information Technology", "Energy"):
        rows.append({"sector": sector, "n": 5, "pct_above_ma200": 0.20, "ret_30d": -0.05,
                      "buy_signals": 0, "sell_signals": 0})
    db.save_table(pd.DataFrame(rows), db.table_path("sectors", "breadth.parquet"))

    cyc = market_cycle.compute_stock_cycle()
    assert cyc["stage"] == "Early Cycle"
    assert "Leading" in "".join(cyc["reasons"]) or any(
        "Consumer Discretionary" in r for r in cyc["reasons"]
    )


def test_algorithmic_summary_handles_no_data(lake):
    text = market_cycle.algorithmic_summary()
    assert "not enough breadth history" in text
    assert "not enough sector data" in text


def test_algorithmic_summary_with_data(lake):
    _write_breadth_history("crypto", [_breadth_row("2026-08-17", 0.65, new_highs=6, new_lows=1)])
    rows = [{"sector": "Information Technology", "n": 5, "pct_above_ma200": 0.60,
             "ret_30d": 0.05, "buy_signals": 0, "sell_signals": 0}]
    db.save_table(pd.DataFrame(rows), db.table_path("sectors", "breadth.parquet"))

    text = market_cycle.algorithmic_summary()
    assert "Crypto cycle: Markup (Bull)" in text
    assert "Stock sectors:" in text
    assert "Information Technology" in text
