import json
import os

import pandas as pd

import db
from crypto_signal_station import crypto_signal_pipeline as csp
from crypto_signal_station import sectors as sectors_mod


def test_wiki_to_yahoo_maps_share_classes():
    assert csp._wiki_to_yahoo("BRK.B") == "BRK-B"
    assert csp._wiki_to_yahoo(" bf.b ") == "BF-B"
    assert csp._wiki_to_yahoo("AAPL") == "AAPL"


def test_coingecko_to_yahoo_filters_and_limits():
    markets = [
        {"id": "bitcoin", "symbol": "btc"},
        {"id": "tether", "symbol": "usdt"},           # stablecoin: excluded id
        {"id": "ethereum", "symbol": "eth"},
        {"id": "wrapped-bitcoin", "symbol": "wbtc"},  # wrapped: excluded id
        {"id": "some-new-stable", "symbol": "xusd"},  # stable by symbol
        {"id": "staked-frax-ether", "symbol": "sfrxeth"},  # staked- prefix
        {"id": "solana", "symbol": "sol"},
        {"id": "cardano", "symbol": "ada"},
    ]
    assert csp._coingecko_to_yahoo(markets, 3) == ["BTC-USD", "ETH-USD", "SOL-USD"]


def _fixture_universe(lake, monkeypatch, cfg):
    # setattr with the current values registers them for restore at teardown
    monkeypatch.setattr(csp, "symbols", list(csp.symbols))
    monkeypatch.setattr(csp, "stock_symbols", list(csp.stock_symbols))
    monkeypatch.setattr(csp, "config", cfg)
    os.makedirs(csp._universe_file(""), exist_ok=True)


def test_load_universe_uses_caches_when_enabled(lake, monkeypatch):
    cfg = {
        "cryptos": ["BTC-USD", "ETH-USD"],
        "stocks": ["OLD1", "OLD2"],
        "auto_update_stocks": "sp500",
        "auto_update_cryptos": 5,
    }
    _fixture_universe(lake, monkeypatch, cfg)
    with open(csp._universe_file("sp500.json"), "w") as f:
        json.dump(["AAPL", "MSFT"], f)
    with open(csp._universe_file("top_cryptos.json"), "w") as f:
        json.dump(["BTC-USD", "SOL-USD"], f)

    csp._load_universe()
    # sp500 cache replaces the YAML stocks; crypto cache unions without dupes
    assert csp.stock_symbols == ["AAPL", "MSFT"]
    assert csp.symbols == ["BTC-USD", "ETH-USD", "SOL-USD"]


def test_load_universe_falls_back_to_yaml_without_caches(lake, monkeypatch):
    cfg = {
        "cryptos": ["BTC-USD"],
        "stocks": ["OLD1"],
        "auto_update_stocks": "sp500",
        "auto_update_cryptos": 5,
    }
    _fixture_universe(lake, monkeypatch, cfg)
    csp._load_universe()
    assert csp.stock_symbols == ["OLD1"]
    assert csp.symbols == ["BTC-USD"]


def test_update_universe_rejects_bad_scrape_and_survives_errors(lake, monkeypatch):
    cfg = {"cryptos": [], "stocks": ["OLD1"], "auto_update_stocks": "sp500"}
    _fixture_universe(lake, monkeypatch, cfg)
    with open(csp._universe_file("sp500.json"), "w") as f:
        json.dump(["GOOD1", "GOOD2"], f)

    # A truncated scrape (< 400 symbols) must not clobber the cache
    monkeypatch.setattr(csp, "_fetch_sp500_symbols", lambda: (["ONLY", "THREE", "ROWS"], {}))
    csp.update_symbol_universe()
    assert csp.stock_symbols == ["GOOD1", "GOOD2"]

    # A network failure must not clobber the cache either
    def boom():
        raise RuntimeError("wikipedia down")

    monkeypatch.setattr(csp, "_fetch_sp500_symbols", boom)
    csp.update_symbol_universe()
    assert csp.stock_symbols == ["GOOD1", "GOOD2"]


def test_update_universe_writes_good_scrape(lake, monkeypatch):
    cfg = {"cryptos": [], "stocks": ["OLD1"], "auto_update_stocks": "sp500"}
    _fixture_universe(lake, monkeypatch, cfg)
    fake_sp500 = sorted(f"SYM{i}" for i in range(500))
    fake_sector_map = {"SYM0": "Technology"}
    monkeypatch.setattr(csp, "_fetch_sp500_symbols", lambda: (fake_sp500, fake_sector_map))
    csp.update_symbol_universe()
    assert csp.stock_symbols == fake_sp500
    with open(csp._universe_file("sp500.json")) as f:
        assert json.load(f) == fake_sp500
    assert sectors_mod.load_sector_map() == fake_sector_map


def test_has_history_gaps():
    crypto_ok = pd.Series(pd.date_range("2026-01-01", "2026-01-10", freq="D"))
    assert not csp._has_history_gaps(crypto_ok, "crypto")
    crypto_hole = pd.concat([crypto_ok[:4], crypto_ok[6:]])
    assert csp._has_history_gaps(crypto_hole, "crypto")

    # Stocks: weekends and a Monday holiday are not gaps
    stock_ok = pd.Series(pd.to_datetime([
        "2026-01-02",                                # Fri
        "2026-01-05", "2026-01-06",                  # Mon, Tue
        "2026-01-09",                                # Fri
        "2026-01-13",                                # Tue (Mon holiday)
    ]))
    assert not csp._has_history_gaps(stock_ok, "stocks")
    stock_hole = pd.Series(pd.to_datetime(["2026-01-02", "2026-01-12"]))
    assert csp._has_history_gaps(stock_hole, "stocks")
