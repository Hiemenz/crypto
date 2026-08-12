"""Tests for the data freshness monitor."""

import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crypto_signal_station"))

import freshness_check


def test_fresh_data_returns_true():
    recent = datetime.now(timezone.utc) - timedelta(hours=6)
    with patch.object(freshness_check, "_latest_signal_date", return_value=recent):
        with patch.object(freshness_check, "_alert") as mock_alert:
            result = freshness_check.check_freshness(max_age_hours=36)
    assert result is True
    mock_alert.assert_not_called()


def test_stale_data_returns_false_and_alerts():
    stale = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(freshness_check, "_latest_signal_date", return_value=stale):
        with patch.object(freshness_check, "_alert") as mock_alert:
            result = freshness_check.check_freshness(max_age_hours=36)
    assert result is False
    mock_alert.assert_called_once()
    title, message = mock_alert.call_args[0]
    assert "stale" in title.lower()
    assert "48" in message or "h old" in message


def test_no_data_returns_false_and_alerts():
    with patch.object(freshness_check, "_latest_signal_date", return_value=None):
        with patch.object(freshness_check, "_alert") as mock_alert:
            result = freshness_check.check_freshness()
    assert result is False
    mock_alert.assert_called_once()


def test_exactly_at_threshold_is_fresh():
    # 36h - 1 second: should be fresh
    just_fresh = datetime.now(timezone.utc) - timedelta(hours=36) + timedelta(seconds=1)
    with patch.object(freshness_check, "_latest_signal_date", return_value=just_fresh):
        with patch.object(freshness_check, "_alert") as mock_alert:
            result = freshness_check.check_freshness(max_age_hours=36)
    assert result is True
    mock_alert.assert_not_called()


def test_naive_datetime_treated_as_utc():
    # Naive datetime (no tzinfo) — should not raise
    naive = datetime.now() - timedelta(hours=4)
    with patch.object(freshness_check, "_latest_signal_date", return_value=naive):
        with patch.object(freshness_check, "_alert"):
            result = freshness_check.check_freshness(max_age_hours=36)
    assert result is True
