import pandas as pd

import db
from conftest import make_ohlcv
from crypto_signal_station import breadth, dashboard, digest


def _seed_symbol(sym, cat, signal="Good Buy"):
    end = pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=260, freq="D")
    closes = [100.0 + i for i in range(260)]
    db.replace_ohlcv(make_ohlcv(dates.strftime("%Y-%m-%d"), closes), sym, cat)
    sig = pd.DataFrame(
        {
            "Date": dates[-3:],
            "Close": closes[-3:],
            "signal": ["Hold", "Hold", signal],
            "golden_cross": [False, True, False],
            "death_cross": [False, False, False],
        }
    )
    db.replace_signals(sig, sym, cat, "1d")


def test_dashboard_generates_self_contained_html(lake, tmp_path):
    _seed_symbol("BTC-USD", "crypto")
    _seed_symbol("AAPL", "stocks", "Great Sell")
    breadth.record_daily()

    out = tmp_path / "dash" / "index.html"
    dashboard.generate(str(out))
    html_text = out.read_text()

    assert "<!doctype html>" in html_text
    assert "BTC-USD" in html_text        # signal table + watchlist
    assert "AAPL" in html_text
    assert "Golden cross" in html_text   # cross event rendered
    assert "prefers-color-scheme: dark" in html_text
    # Self-contained: no external fetches
    assert "http://" not in html_text.replace("http.server", "")
    assert "https://" not in html_text


def test_dashboard_empty_lake_still_renders(lake, tmp_path):
    out = tmp_path / "index.html"
    dashboard.generate(str(out))
    text = out.read_text()
    assert "No breadth history yet" in text


def test_digest_summarizes_week(lake):
    _seed_symbol("BTC-USD", "crypto", "Good Buy")
    _seed_symbol("AAPL", "stocks", "Great Sell")
    breadth.record_daily()

    text = digest.build_digest()
    assert "BTC-USD" in text
    assert "AAPL" in text
    assert "golden crosses: AAPL" in text or "golden crosses: BTC-USD" in text

    post = digest.build_post()
    assert "Crypto: 1 buys / 0 sells" in post
    assert "Stocks: 0 buys / 1 sells" in post
    assert len(post) < 500  # must fit a toot


def test_digest_empty_lake(lake):
    text = digest.build_digest()
    assert "no signals this week" in text
