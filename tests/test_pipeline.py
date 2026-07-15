import numpy as np
import pandas as pd
import pytest

import db
from crypto_signal_station import crypto_signal_pipeline as csp

TFS_1D = {"1d": None}
TFS_ALL = {"1d": None, "2d": "48h", "3d": "72h", "1wk": "W-SUN", "2wk": "336h"}

MARKET_BASE = pd.Timestamp("2025-01-01")


def _yf_frame(dates, close, tz="UTC", multi=False):
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    if tz is not None:
        idx = idx.tz_localize(tz)
    close = np.asarray(close, dtype=float)
    df = pd.DataFrame(
        {"Open": close, "High": close * 1.1, "Low": close * 0.9, "Close": close, "Volume": 1000.0},
        index=idx,
    )
    df.index.name = "Date"
    if multi:
        # Ticker level must match the symbol under test: _fetch_daily discards
        # payloads whose ticker level names a different symbol
        df.columns = pd.MultiIndex.from_product([df.columns, ["T"]])
    return df


class FakeMarket:
    """Deterministic daily market: Close(date) = (100 + days since base) * factor.

    Bump `factor` to simulate a retroactive re-adjustment of the whole history
    (what auto_adjust does after a split/dividend)."""

    def __init__(self, start="2025-01-01", end="2026-07-20", factor=1.0):
        self.dates = pd.date_range(start, end, freq="D")
        self.factor = factor
        self.calls = 0

    def download(self, symbol, start=None, end=None, **kwargs):
        self.calls += 1
        sel = self.dates[(self.dates >= pd.Timestamp(start)) & (self.dates < pd.Timestamp(end))]
        close = (100.0 + (sel - MARKET_BASE).days.to_numpy()) * self.factor
        return _yf_frame(sel, close)


@pytest.fixture
def env(lake, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # chart output (eink_output/) lands in tmp
    monkeypatch.setattr(csp, "HISTORY_START", "2025-01-01")
    monkeypatch.setattr(
        csp, "_last_complete_daily_date", lambda cat, now=None: pd.Timestamp("2026-07-13").date()
    )
    return lake


def _set_clock(monkeypatch, day):
    monkeypatch.setattr(
        csp, "_last_complete_daily_date", lambda cat, now=None: pd.Timestamp(day).date()
    )


# ── bar completeness ───────────────────────────────────────────────────────────

def test_last_complete_crypto_is_previous_utc_day():
    now = pd.Timestamp("2026-07-14 02:30", tz="UTC")  # 21:30 CDT July 13
    assert csp._last_complete_daily_date("crypto", now) == pd.Timestamp("2026-07-13").date()


def test_last_complete_stocks_flips_at_1600_eastern():
    before = pd.Timestamp("2026-07-13 15:59", tz="America/New_York")
    after = pd.Timestamp("2026-07-13 16:01", tz="America/New_York")
    assert csp._last_complete_daily_date("stocks", before) == pd.Timestamp("2026-07-12").date()
    assert csp._last_complete_daily_date("stocks", after) == pd.Timestamp("2026-07-13").date()


# ── _fetch_daily ───────────────────────────────────────────────────────────────

def test_fetch_daily_includes_last_complete_bar_and_drops_partials(monkeypatch):
    captured = {}

    def fake_download(symbol, start=None, end=None, **kwargs):
        captured["end"] = end
        # tz-aware MultiIndex frame with a partial bar past last_complete
        return _yf_frame(["2026-07-12", "2026-07-13", "2026-07-14"], [1.0, 2.0, 3.0], multi=True)

    monkeypatch.setattr(csp.yf, "download", fake_download)
    out = csp._fetch_daily("T", "2026-07-12", pd.Timestamp("2026-07-13").date())

    # yfinance `end` is exclusive, so it must be last_complete + 1
    assert captured["end"] == "2026-07-14"
    assert list(out["Date"].dt.strftime("%Y-%m-%d")) == ["2026-07-12", "2026-07-13"]
    assert out["Date"].dt.tz is None
    assert set(out.columns) == {"Date", "Close", "High", "Low", "Open", "Volume"}


def test_fetch_daily_handles_tz_naive_frames(monkeypatch):
    monkeypatch.setattr(
        csp.yf, "download", lambda *a, **k: _yf_frame(["2026-07-13"], [2.0], tz=None)
    )
    out = csp._fetch_daily("T", "2026-07-13", pd.Timestamp("2026-07-13").date())
    assert len(out) == 1


def test_fetch_daily_download_error_returns_empty(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(csp.yf, "download", boom)
    assert csp._fetch_daily("T", "2026-01-01", pd.Timestamp("2026-07-13").date()).empty


# ── _process_single_symbol ─────────────────────────────────────────────────────

def test_first_fetch_stores_through_last_complete_bar(env, monkeypatch):
    mkt = FakeMarket()
    monkeypatch.setattr(csp.yf, "download", mkt.download)
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)
    assert db.get_latest_ohlcv_date("TST-USD", "crypto") == pd.Timestamp("2026-07-13")
    sig = db.load_signals("TST-USD", "crypto", "1d")
    assert sig["Date"].max() == pd.Timestamp("2026-07-13")
    # Warm-up rows (no MA-200 yet) must never signal
    assert (sig["signal"].iloc[:199] == "Hold").all()


def test_incremental_update_appends_without_splice(env, monkeypatch):
    mkt = FakeMarket()
    monkeypatch.setattr(csp.yf, "download", mkt.download)
    _set_clock(monkeypatch, "2026-07-10")
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)
    _set_clock(monkeypatch, "2026-07-13")
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)

    out = db.load_ohlcv("TST-USD", "crypto")
    assert out["Date"].max() == pd.Timestamp("2026-07-13")
    expected = 100.0 + (out["Date"] - MARKET_BASE).dt.days
    assert np.allclose(out["Close"], expected)  # continuous series, no seam


def test_current_symbol_does_not_download_or_recompute(env, monkeypatch):
    mkt = FakeMarket()
    monkeypatch.setattr(csp.yf, "download", mkt.download)
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)

    def bomb(*args, **kwargs):
        raise RuntimeError("should not download")

    monkeypatch.setattr(csp.yf, "download", bomb)
    # A second run while current must succeed without touching the network
    # (a download attempt would make _process_single_symbol return False).
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)


def test_readjusted_history_triggers_full_refresh(env, monkeypatch):
    mkt = FakeMarket()
    monkeypatch.setattr(csp.yf, "download", mkt.download)
    _set_clock(monkeypatch, "2026-07-10")
    assert csp._process_single_symbol("TST", "stocks", TFS_1D)
    old = db.load_ohlcv("TST", "stocks")

    # Dividend: yfinance re-adjusts the whole history down 2%
    mkt.factor = 0.98
    _set_clock(monkeypatch, "2026-07-13")
    assert csp._process_single_symbol("TST", "stocks", TFS_1D)

    new = db.load_ohlcv("TST", "stocks")
    assert len(new) == len(old) + 3
    expected = (100.0 + (new["Date"] - MARKET_BASE).dt.days) * 0.98
    # Entire stored history is on the new adjustment basis — no spliced seam
    assert np.allclose(new["Close"], expected)


def test_stale_signals_recomputed_without_new_data(env, monkeypatch):
    mkt = FakeMarket()
    monkeypatch.setattr(csp.yf, "download", mkt.download)
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)

    # Simulate a crash after the OHLCV write but before the signal write
    sig = db.load_signals("TST-USD", "crypto", "1d")
    db.replace_signals(sig.iloc[:-1], "TST-USD", "crypto", "1d")

    monkeypatch.setattr(csp.yf, "download", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)
    assert db.load_signals("TST-USD", "crypto", "1d")["Date"].max() == pd.Timestamp("2026-07-13")


def test_history_gaps_are_healed_by_full_redownload(env, monkeypatch):
    mkt = FakeMarket()
    monkeypatch.setattr(csp.yf, "download", mkt.download)
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)
    full = db.load_ohlcv("TST-USD", "crypto")

    # Punch a hole in the middle of the stored history
    db.replace_ohlcv(pd.concat([full.iloc[:100], full.iloc[110:]]), "TST-USD", "crypto")
    assert csp._process_single_symbol("TST-USD", "crypto", TFS_1D)

    healed = db.load_ohlcv("TST-USD", "crypto")
    assert len(healed) == len(full)
    assert not csp._has_history_gaps(healed["Date"], "crypto")


def test_threaded_processing_updates_every_symbol(env, monkeypatch):
    # Exercises the real thread pool: concurrent downloads, DuckDB reads/writes
    # and Figure-based chart rendering must not interfere.
    mkt = FakeMarket()
    monkeypatch.setattr(csp.yf, "download", mkt.download)
    symbols = [f"T{i}-USD" for i in range(4)]
    csp._process_asset_list(symbols, "crypto")
    for sym in symbols:
        assert db.get_latest_ohlcv_date(sym, "crypto") == pd.Timestamp("2026-07-13")
        _, sig_max = db.get_signals_date_range(sym, "crypto", "1d")
        assert sig_max == pd.Timestamp("2026-07-13")


def test_resample_bins_align_across_symbols(env, monkeypatch):
    # Different history starts must still produce identical bin dates,
    # otherwise the cross-symbol summaries can't match on a common date.
    for sym, start in [("A-USD", "2025-01-01"), ("B-USD", "2025-03-04")]:
        mkt = FakeMarket(start=start)
        monkeypatch.setattr(csp.yf, "download", mkt.download)
        monkeypatch.setattr(csp, "HISTORY_START", start)
        assert csp._process_single_symbol(sym, "crypto", TFS_ALL)

    for tf in ["2d", "3d", "1wk", "2wk"]:
        _, a_max = db.get_signals_date_range("A-USD", "crypto", tf)
        _, b_max = db.get_signals_date_range("B-USD", "crypto", tf)
        assert a_max == b_max, f"{tf} latest bins differ between symbols"
        a_dates = set(db.load_signals("A-USD", "crypto", tf)["Date"])
        b_dates = set(db.load_signals("B-USD", "crypto", tf)["Date"])
        assert b_dates <= a_dates, f"{tf} bins are phase-shifted between symbols"

    # 1wk/2wk labels are ending Sundays
    for tf in ["1wk", "2wk"]:
        dates = db.load_signals("A-USD", "crypto", tf)["Date"]
        assert (dates.dt.day_name() == "Sunday").all(), tf


# ── _label_signal ──────────────────────────────────────────────────────────────

def _row(**overrides):
    row = dict(rsi=50.0, mfi=50.0, stoch_rsi=0.5, is_bull=True, ma_200=1.0)
    row.update(overrides)
    return row


def test_label_warmup_rows_hold_even_on_extreme_readings():
    row = _row(ma_200=float("nan"), is_bull=False, rsi=10.0, mfi=5.0, stoch_rsi=0.01)
    assert csp._label_signal(row) == "Hold"


def test_label_buy_tiers_only_in_bear_regime():
    assert csp._label_signal(_row(is_bull=False, rsi=19, mfi=9, stoch_rsi=0.05)) == "Excellent Buy"
    assert csp._label_signal(_row(is_bull=False, rsi=25, mfi=15, stoch_rsi=0.15)) == "Great Buy"
    assert csp._label_signal(_row(is_bull=False, rsi=35, mfi=25, stoch_rsi=0.25)) == "Good Buy"
    assert csp._label_signal(_row(is_bull=True, rsi=19, mfi=9, stoch_rsi=0.05)) == "Hold"


def test_label_sell_tiers_only_in_bull_regime():
    assert csp._label_signal(_row(is_bull=True, rsi=81, mfi=91, stoch_rsi=0.95)) == "Excellent Sell"
    assert csp._label_signal(_row(is_bull=True, rsi=75, mfi=85, stoch_rsi=0.85)) == "Great Sell"
    assert csp._label_signal(_row(is_bull=True, rsi=65, mfi=75, stoch_rsi=0.75)) == "Good Sell"
    assert csp._label_signal(_row(is_bull=False, rsi=81, mfi=91, stoch_rsi=0.95)) == "Hold"
