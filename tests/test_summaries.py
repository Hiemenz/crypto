import pandas as pd

import db
from conftest import make_ohlcv
from crypto_signal_station import crypto_signal_pipeline as csp


def _seed(sym, cat, last_bar, signal, tf="1d"):
    db.replace_ohlcv(make_ohlcv([last_bar]), sym, cat)  # drives the active check
    sig = pd.DataFrame({"Date": pd.to_datetime([last_bar]), "signal": [signal]})
    db.replace_signals(sig, sym, cat, tf)


def _dates(days_ago):
    today = pd.Timestamp.now().normalize()
    return (today - pd.Timedelta(days=days_ago)).strftime("%Y-%m-%d")


def test_active_symbols_filters_dead_tickers(lake):
    _seed("GOOD-USD", "crypto", _dates(1), "Hold")
    _seed("DEAD-USD", "crypto", _dates(30), "Hold")
    assert csp._active_symbols(["GOOD-USD", "DEAD-USD", "MISSING-USD"], "crypto") == ["GOOD-USD"]


def test_summaries_exclude_dead_tickers_and_keep_per_category_dates(lake, monkeypatch):
    fresh_crypto = _dates(1)
    fresh_stock = _dates(3)  # e.g. stocks lag crypto over a weekend
    stale = _dates(30)

    _seed("GOOD-USD", "crypto", fresh_crypto, "Good Buy")
    _seed("DEAD-USD", "crypto", stale, "Excellent Buy")  # delisted: must not appear
    _seed("AAPL", "stocks", fresh_stock, "Great Sell")

    monkeypatch.setattr(csp, "symbols", ["GOOD-USD", "DEAD-USD"])
    monkeypatch.setattr(csp, "stock_symbols", ["AAPL"])

    out = csp.generate_signals_summary_separate()
    _, crypto_buy, crypto_sell = out["crypto"]
    _, stock_buy, stock_sell = out["stocks"]
    _, combined_buy, combined_sell = out["combined"]

    assert "GOOD-USD" in crypto_buy and fresh_crypto in crypto_buy
    assert "DEAD-USD" not in crypto_buy  # neither listed nor dragging the date
    assert stale not in crypto_buy
    assert "AAPL" in stock_sell and fresh_stock in stock_sell
    # Combined keeps both categories even though their latest dates differ
    assert "GOOD-USD" in combined_buy
    assert "AAPL" in combined_sell


def test_summary_1d_uses_per_category_dates(lake, monkeypatch):
    _seed("GOOD-USD", "crypto", _dates(1), "Good Buy")
    _seed("DEAD-USD", "crypto", _dates(30), "Excellent Buy")
    _seed("AAPL", "stocks", _dates(3), "Great Sell")

    monkeypatch.setattr(csp, "symbols", ["GOOD-USD", "DEAD-USD"])
    monkeypatch.setattr(csp, "stock_symbols", ["AAPL"])

    _, buy, sell = csp.generate_signals_summary()
    assert "GOOD-USD" in buy
    assert "DEAD-USD" not in buy
    assert "AAPL" in sell


def test_summary_target_date_pins_all_categories(lake, monkeypatch):
    day = _dates(2)
    _seed("GOOD-USD", "crypto", day, "Good Buy")
    monkeypatch.setattr(csp, "symbols", ["GOOD-USD"])
    monkeypatch.setattr(csp, "stock_symbols", [])

    out = csp.generate_signals_summary_separate(target_date=day)
    _, crypto_buy, _ = out["crypto"]
    assert "GOOD-USD" in crypto_buy and day in crypto_buy

    out = csp.generate_signals_summary_separate(target_date=_dates(1))
    _, crypto_buy, _ = out["crypto"]
    assert "GOOD-USD" not in crypto_buy  # no signal row on that date


def test_count_signals_counts_distinct_tickers():
    buy = (
        "Buy on the 1d (2026-07-13):\nGood:\n  BTC-USD\n\n"
        "Buy on the 1wk (2026-07-12):\nGood:\n  BTC-USD\n  ETH-USD\n\n"
    )
    sell = "Sell on the 1d (2026-07-13):\nGreat:\n  AAPL\n\n"
    assert csp._count_signals(buy, sell) == (2, 1)
