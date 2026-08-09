import os
import sys

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
# crypto_signal_pipeline does `from eink_generator import ...` (script-style
# sibling imports), so its directory must be importable too.
sys.path.insert(0, os.path.join(REPO_ROOT, "crypto_signal_station"))
# generate_api_data.py writes OUTPUT_DIR = "frontend/public/data" (relative),
# so tests that exercise it monkeypatch OUTPUT_DIR; everything else needs cwd
# at the repo root so Poetry-discovered imports resolve correctly.
os.chdir(REPO_ROOT)

import db  # noqa: E402


@pytest.fixture
def lake(tmp_path, monkeypatch):
    """Point the parquet lake at a temp directory so tests never touch data/."""
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(db, "OHLCV_DIR", str(tmp_path / "data" / "ohlcv"))
    monkeypatch.setattr(db, "SIGNALS_DIR", str(tmp_path / "data" / "signals"))
    db.init_db()
    return tmp_path


def make_ohlcv(dates, close=None):
    close = list(close) if close is not None else [100.0] * len(dates)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(list(dates)),
            "Open": close,
            "High": [c * 1.1 for c in close],
            "Low": [c * 0.9 for c in close],
            "Close": close,
            "Volume": [1000.0] * len(close),
        }
    )
