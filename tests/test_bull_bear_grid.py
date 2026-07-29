#!/usr/bin/env python3
"""Tests for bull/bear grid classification."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crypto_signal_station"))

from eink_bull_bear_grid import classify_bull_bear


def test_classify_bull():
    # ma_50 clearly above ma_200 → BULL
    result = classify_bull_bear(ma_50=55000, ma_200=50000)
    assert result == "BULL", f"Expected BULL, got {result}"


def test_classify_bear():
    # ma_50 clearly below ma_200 → BEAR
    result = classify_bull_bear(ma_50=45000, ma_200=50000)
    assert result == "BEAR", f"Expected BEAR, got {result}"


def test_classify_neutral_above():
    # Within 2% threshold → ?
    result = classify_bull_bear(ma_50=51000, ma_200=50000)  # 2% exactly = boundary
    assert result in ("BULL", "?"), f"Expected BULL or ?, got {result}"


def test_classify_neutral_below():
    # Within 2% below → ?
    result = classify_bull_bear(ma_50=49500, ma_200=50000)  # -1% → ?
    assert result == "?", f"Expected ?, got {result}"


def test_classify_nan_ma50():
    import math
    result = classify_bull_bear(ma_50=float("nan"), ma_200=50000)
    assert result == "?", f"Expected ? for NaN ma_50, got {result}"


def test_classify_nan_ma200():
    import math
    result = classify_bull_bear(ma_50=55000, ma_200=float("nan"))
    assert result == "?", f"Expected ? for NaN ma_200, got {result}"


def test_classify_zero_ma200():
    result = classify_bull_bear(ma_50=55000, ma_200=0)
    assert result == "?", f"Expected ? for zero ma_200, got {result}"


def test_custom_threshold():
    # With 5% threshold, 3% delta → ?
    result = classify_bull_bear(ma_50=51500, ma_200=50000, threshold_pct=0.05)
    assert result == "?", f"Expected ? with custom threshold, got {result}"

    # With 5% threshold, 6% delta → BULL
    result = classify_bull_bear(ma_50=53000, ma_200=50000, threshold_pct=0.05)
    assert result == "BULL", f"Expected BULL with custom threshold, got {result}"


if __name__ == "__main__":
    test_classify_bull()
    test_classify_bear()
    test_classify_neutral_above()
    test_classify_neutral_below()
    test_classify_nan_ma50()
    test_classify_nan_ma200()
    test_classify_zero_ma200()
    test_custom_threshold()
    print("All bull/bear grid tests passed.")
