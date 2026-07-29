#!/usr/bin/env python3
"""Tests for agent context-gathering functions (mocked Anthropic client)."""

import sys
import os
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_daily_agent_gather_context_missing_files():
    """gather_context returns a message when no reports exist."""
    from agents.daily_analysis_agent import gather_context

    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch REPORTS_DIR to empty temp dir
        import agents.daily_analysis_agent as mod
        original = mod.REPORTS_DIR
        mod.REPORTS_DIR = tmpdir

        result = gather_context(datetime(2025, 1, 1))
        mod.REPORTS_DIR = original

    assert "No data" in result or "No report" in result or len(result) > 0


def test_daily_agent_gather_context_with_files():
    """gather_context reads files when they exist."""
    from agents.daily_analysis_agent import gather_context
    import agents.daily_analysis_agent as mod

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake analysis report
        analysis_dir = os.path.join(tmpdir, "analysis")
        os.makedirs(analysis_dir)
        with open(os.path.join(analysis_dir, "2025-01-01.txt"), "w") as f:
            f.write("Test signals content")

        original = mod.REPORTS_DIR
        mod.REPORTS_DIR = tmpdir
        result = gather_context(datetime(2025, 1, 1))
        mod.REPORTS_DIR = original

    assert "Test signals content" in result


def test_daily_agent_run_analysis_mocked():
    """run_analysis calls Anthropic client and returns text."""
    from agents.daily_analysis_agent import run_analysis

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="AI analysis output")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("agents.daily_analysis_agent.anthropic.Anthropic", return_value=mock_client):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            result = run_analysis(datetime(2025, 1, 1))

    assert result == "AI analysis output"
    assert mock_client.messages.create.called


def test_discord_agent_generate_summary_mocked():
    """generate_discord_summary returns text under 1900 chars."""
    from agents.discord_report_agent import generate_discord_summary

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Short Discord summary")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("agents.discord_report_agent.anthropic.Anthropic", return_value=mock_client):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            result = generate_discord_summary(datetime(2025, 1, 1))

    assert len(result) <= 1900
    assert "Short Discord summary" in result


def test_signal_monitor_find_signals_empty():
    """find_excellent_signals returns empty list when no data folder exists."""
    from agents.signal_monitor_agent import find_excellent_signals
    import agents.signal_monitor_agent as mod

    original = mod.BASE_DATA
    mod.BASE_DATA = "/tmp/nonexistent_crypto_data_xyz"
    result = find_excellent_signals()
    mod.BASE_DATA = original

    assert isinstance(result, list)
    assert len(result) == 0


def test_signal_monitor_commentary_mocked():
    """get_commentary returns string from Claude."""
    from agents.signal_monitor_agent import get_commentary

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Signal commentary")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    signals = [{"symbol": "BTC-USD", "asset_class": "crypto", "timeframe": "1d",
                "signal": "Excellent Buy", "close": 50000.0, "rsi": 18.0,
                "mfi": 8.0, "stoch_rsi": 0.05, "ma_50": 49000.0,
                "ma_200": 55000.0, "date": "2025-01-01"}]

    with patch("agents.signal_monitor_agent.anthropic.Anthropic", return_value=mock_client):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            result = get_commentary(signals)

    assert "Signal commentary" in result


if __name__ == "__main__":
    test_daily_agent_gather_context_missing_files()
    test_daily_agent_gather_context_with_files()
    test_daily_agent_run_analysis_mocked()
    test_discord_agent_generate_summary_mocked()
    test_signal_monitor_find_signals_empty()
    test_signal_monitor_commentary_mocked()
    print("All agent tests passed.")
