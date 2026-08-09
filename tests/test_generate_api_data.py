import json

import pandas as pd
import pytest

import db
import generate_api_data as gad


@pytest.fixture(autouse=True)
def _output_dir(lake, monkeypatch):
    """Redirect JSON output under the same temp dir the lake fixture uses."""
    out = lake / "frontend_data"
    monkeypatch.setattr(gad, "OUTPUT_DIR", str(out))
    return out


def _seed_signals(sym, cat, tf, rows):
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    db.replace_signals(df, sym, cat, tf)


def test_history_json_replaces_nan_and_inf_with_null(_output_dir):
    """json.dump would otherwise emit bare NaN/Infinity tokens, which are not
    valid JSON — JSON.parse rejects the document and the page goes blank."""
    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-01", "Close": 100.0, "Volume": float("nan"), "signal": "Hold"},
        {"Date": "2026-01-02", "Close": float("inf"), "Volume": 5.0, "signal": "Hold"},
    ])

    gad.generate_history_json()

    raw = (_output_dir / "history" / "BTC-USD.json").read_text()
    assert "NaN" not in raw and "Infinity" not in raw
    rows = json.loads(raw)["data"]
    assert rows[0]["Volume"] is None
    assert rows[1]["Close"] is None


def test_latest_signals_json_replaces_nan_and_inf_with_null(_output_dir):
    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-02", "Close": 105.0, "rsi": float("nan"),
         "bb_pband": float("inf"), "signal": "Hold"},
    ])

    gad.generate_latest_signals_json()

    raw = (_output_dir / "latest_signals.json").read_text()
    assert "NaN" not in raw and "Infinity" not in raw
    row = json.loads(raw)["signals"][0]
    assert row["rsi"] is None
    assert row["bb_pband"] is None
    assert row["score"] == 50  # neutral when RSI is unusable


def test_history_json_exports_only_frontend_columns(_output_dir):
    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-01", "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5,
         "Volume": 10.0, "signal": "Hold", "rsi": 40.0, "macd": 0.1, "atr": 0.2},
    ])

    gad.generate_history_json()

    row = json.loads((_output_dir / "history" / "BTC-USD.json").read_text())["data"][0]
    assert set(row) == {"Date", "Open", "High", "Low", "Close", "Volume", "signal"}


def test_generate_history_json_writes_per_symbol_file(_output_dir):
    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-01", "Close": 100.0, "rsi": 40.0, "signal": "Hold"},
        {"Date": "2026-01-02", "Close": 105.0, "rsi": 45.0, "signal": "Good Buy"},
    ])

    gad.generate_history_json()

    path = _output_dir / "history" / "BTC-USD.json"
    payload = json.loads(path.read_text())
    assert payload["symbol"] == "BTC-USD"
    assert len(payload["data"]) == 2
    assert payload["data"][0]["Date"] == "2026-01-01"
    assert payload["data"][1]["signal"] == "Good Buy"
    # Lake-only partition columns must not leak into the per-row records
    assert "symbol" not in payload["data"][0]
    assert "category" not in payload["data"][0]


def test_generate_history_json_empty_lake_writes_nothing(_output_dir):
    gad.generate_history_json()
    assert not (_output_dir / "history").exists()


def test_generate_latest_signals_json_uses_last_row_and_scores(_output_dir):
    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-01", "Close": 100.0, "rsi": 40.0, "signal": "Hold"},
        {"Date": "2026-01-02", "Close": 105.0, "rsi": 15.0, "signal": "Excellent Buy"},
    ])

    gad.generate_latest_signals_json()

    payload = json.loads((_output_dir / "latest_signals.json").read_text())
    assert len(payload["signals"]) == 1
    row = payload["signals"][0]
    assert row["symbol"] == "BTC-USD"
    assert row["category"] == "crypto"
    assert row["signal"] == "Excellent Buy"
    assert row["side"] == "buy"
    assert row["score"] == 98  # base 95 for "Excellent" tier + (30-15)*0.2 RSI bonus


def _weeks_ago(n):
    """A recent weekly bar date — crosses.json only exports a trailing window."""
    return (pd.Timestamp.now().normalize() - pd.Timedelta(weeks=n)).strftime("%Y-%m-%d")


def test_generate_crosses_json_detects_golden_cross(_output_dir):
    _seed_signals("BTC-USD", "crypto", "1wk", [
        {"Date": _weeks_ago(2), "Close": 100.0, "stoch_rsi_k": 0.1, "stoch_rsi_d": 0.3},
        {"Date": _weeks_ago(1), "Close": 105.0, "stoch_rsi_k": 0.5, "stoch_rsi_d": 0.25},
    ])

    gad.generate_crosses_json()

    payload = json.loads((_output_dir / "crosses.json").read_text())
    assert len(payload["crosses"]) == 1
    cross = payload["crosses"][0]
    assert cross["symbol"] == "BTC-USD"
    # Prior bar's D was 0.3, i.e. not oversold — a cross, but not a confirmed one
    assert cross["type"] == "Golden Cross"
    assert cross["k"] == 0.5
    assert cross["d"] == 0.25


def test_golden_cross_out_of_oversold_is_confirmed(_output_dir):
    _seed_signals("BTC-USD", "crypto", "1wk", [
        {"Date": _weeks_ago(2), "Close": 100.0, "stoch_rsi_k": 0.05, "stoch_rsi_d": 0.15},
        {"Date": _weeks_ago(1), "Close": 105.0, "stoch_rsi_k": 0.30, "stoch_rsi_d": 0.18},
    ])

    gad.generate_crosses_json()

    payload = json.loads((_output_dir / "crosses.json").read_text())
    assert [c["type"] for c in payload["crosses"]] == ["Confirmed Golden Cross"]


def test_death_cross_confirmed_only_from_overbought(_output_dir):
    # Crosses down while mid-range: a death cross, but nothing to confirm it.
    _seed_signals("ETH-USD", "crypto", "1wk", [
        {"Date": _weeks_ago(2), "Close": 100.0, "stoch_rsi_k": 0.55, "stoch_rsi_d": 0.45},
        {"Date": _weeks_ago(1), "Close": 95.0, "stoch_rsi_k": 0.40, "stoch_rsi_d": 0.50},
    ])
    # Crosses down out of overbought: confirmed.
    _seed_signals("BTC-USD", "crypto", "1wk", [
        {"Date": _weeks_ago(2), "Close": 100.0, "stoch_rsi_k": 0.95, "stoch_rsi_d": 0.85},
        {"Date": _weeks_ago(1), "Close": 95.0, "stoch_rsi_k": 0.70, "stoch_rsi_d": 0.80},
    ])

    gad.generate_crosses_json()

    payload = json.loads((_output_dir / "crosses.json").read_text())
    by_symbol = {c["symbol"]: c["type"] for c in payload["crosses"]}
    assert by_symbol == {
        "ETH-USD": "Death Cross",
        "BTC-USD": "Confirmed Death Cross",
    }


def test_generate_crosses_json_drops_crosses_outside_the_window(_output_dir):
    old = (
        pd.Timestamp.now().normalize()
        - pd.Timedelta(days=gad.CROSSES_LOOKBACK_DAYS + 30)
    ).strftime("%Y-%m-%d")
    older = (
        pd.Timestamp.now().normalize()
        - pd.Timedelta(days=gad.CROSSES_LOOKBACK_DAYS + 37)
    ).strftime("%Y-%m-%d")
    _seed_signals("BTC-USD", "crypto", "1wk", [
        {"Date": older, "Close": 100.0, "stoch_rsi_k": 0.1, "stoch_rsi_d": 0.3},
        {"Date": old, "Close": 105.0, "stoch_rsi_k": 0.5, "stoch_rsi_d": 0.25},
    ])

    gad.generate_crosses_json()

    payload = json.loads((_output_dir / "crosses.json").read_text())
    assert payload["crosses"] == []


def test_generate_crosses_json_short_history_is_skipped(_output_dir):
    _seed_signals("BTC-USD", "crypto", "1wk", [
        {"Date": _weeks_ago(1), "Close": 100.0, "stoch_rsi_k": 0.1, "stoch_rsi_d": 0.3},
    ])
    gad.generate_crosses_json()
    payload = json.loads((_output_dir / "crosses.json").read_text())
    assert payload["crosses"] == []


# ── Supabase upload ────────────────────────────────────────────────────────────

@pytest.fixture
def _supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setenv("SUPABASE_BUCKET", "signalstack")


def _fake_urlopen(calls, error=None):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _open(req, timeout=None):
        calls.append((req.full_url, timeout))
        if error is not None:
            raise error
        return _Resp()

    return _open


def test_upload_passes_a_timeout(_output_dir, _supabase_env, monkeypatch):
    """A stalled socket used to hang the nightly job forever."""
    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-01", "Close": 100.0, "signal": "Hold"},
    ])
    gad.generate_latest_signals_json()

    calls = []
    monkeypatch.setattr(gad.urllib.request, "urlopen", _fake_urlopen(calls))

    assert gad.upload_to_supabase() is True
    assert calls and all(timeout == gad.UPLOAD_TIMEOUT_SECONDS for _, timeout in calls)


def test_upload_survives_connection_errors(_output_dir, _supabase_env, monkeypatch, capsys):
    """URLError (DNS/TLS/reset) used to escape and abort the whole export."""
    import urllib.error

    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-01", "Close": 100.0, "signal": "Hold"},
    ])
    gad.generate_latest_signals_json()

    monkeypatch.setattr(
        gad.urllib.request, "urlopen",
        _fake_urlopen([], error=urllib.error.URLError("name resolution failed")),
    )

    assert gad.upload_to_supabase() is False
    assert "upload failed" in capsys.readouterr().out


def test_upload_skips_unchanged_files(_output_dir, _supabase_env, monkeypatch):
    _seed_signals("BTC-USD", "crypto", "1d", [
        {"Date": "2026-01-01", "Close": 100.0, "signal": "Hold"},
    ])
    gad.generate_latest_signals_json()

    first = []
    monkeypatch.setattr(gad.urllib.request, "urlopen", _fake_urlopen(first))
    gad.upload_to_supabase()
    assert len(first) == 1

    # Nothing regenerated in between, so the second run has nothing to send.
    second = []
    monkeypatch.setattr(gad.urllib.request, "urlopen", _fake_urlopen(second))
    gad.upload_to_supabase()
    assert second == []


def test_upload_without_credentials_is_a_no_op(_output_dir, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    def _boom(*a, **k):
        raise AssertionError("should not attempt an upload")

    monkeypatch.setattr(gad.urllib.request, "urlopen", _boom)
    assert gad.upload_to_supabase() is True
