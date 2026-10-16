import pytest

from crypto_signal_station import notify, slack_report

BUY = """Buy on the weekly (2026-10-12):
Excellent:
  BTC-USD
  ETH-USD
Good:
  SOL-USD

Buy on the daily (2026-10-15):
Great:
  BTC-USD

"""
SELL = "Sell on the daily (2026-10-15):\nGood:\n  DOGE-USD\n\n"
PRICES = "TMC: $2,832,229,428,638\nBTC: $67,000.00\nBTC Dominance: 55.10%\nFear & Greed: 34 (Fear)\n12:00:00 • 10-15-2026 UTC\n"


def test_parse_summary_groups_by_timeframe_and_tier():
    g = slack_report.parse_summary(BUY)
    assert g[0] == ("weekly", "2026-10-12", {"Excellent": ["BTC-USD", "ETH-USD"], "Good": ["SOL-USD"]})
    assert g[1][0] == "daily"


def test_build_report_counts_distinct_tickers_and_drops_timestamp():
    text, blocks = slack_report.build_report("Thu Oct 15", BUY, SELL, "", "", PRICES)
    assert "Crypto: 3 buys, 1 sells" in text  # BTC counted once across timeframes
    flat = str(blocks)
    assert "*Excellent* BTC-USD, ETH-USD" in flat
    assert "No signals today" in flat  # empty stocks
    assert "12:00:00 •" not in flat and "TMC: $2,832" in flat


def test_post_slack_unconfigured_returns_false(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    assert notify.post_slack({}, "x") is False


class _Resp:
    def __init__(self, data, status=200, headers=None):
        self._d, self.status_code, self.headers = data, status, headers or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def _cfg():
    return {"slack_channel_id": "C01CD2XAS5D", "slack_bot_token": "t"}


def test_post_slack_retries_then_succeeds(monkeypatch):
    seq = [_Resp({"ok": False, "error": "internal_error"}), _Resp({"ok": True})]
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    assert notify.post_slack(_cfg(), "x") is True and not seq


def test_post_slack_permanent_error_raises_without_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: calls.append(1) or _Resp({"ok": False, "error": "not_in_channel"}))
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="not_in_channel"):
        notify.post_slack(_cfg(), "x")
    assert len(calls) == 1


def test_deliver_results_isolates_failures_and_exits_nonzero(monkeypatch):
    from crypto_signal_station import crypto_signal_pipeline as pipe
    notify = pipe.notify  # the pipeline imports notify top-level, not via the package
    sent, failures = [], []
    monkeypatch.setattr(notify, "_load_config", lambda: _cfg())
    monkeypatch.setattr(notify, "post_slack", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Slack post failed: boom")))
    monkeypatch.setattr(pipe, "send_tweet", lambda t: sent.append(t) or False)  # X rejects (401)
    monkeypatch.setattr(notify, "notify_failure", lambda ctx, detail: failures.append(detail))
    with pytest.raises(SystemExit) as e:
        pipe._deliver_results("c", "s", BUY, SELL, "", "", PRICES)
    assert e.value.code == 1
    assert sent == ["c", "s"]  # Slack blowing up did not stop either tweet
    assert "slack" in failures[0] and "x-crypto" in failures[0] and "x-stocks" in failures[0]


def test_deliver_results_all_ok_does_not_exit(monkeypatch):
    from crypto_signal_station import crypto_signal_pipeline as pipe
    notify = pipe.notify  # the pipeline imports notify top-level, not via the package
    monkeypatch.setattr(notify, "_load_config", lambda: _cfg())
    monkeypatch.setattr(notify, "post_slack", lambda *a, **k: True)
    monkeypatch.setattr(pipe, "send_tweet", lambda t: True)
    pipe._deliver_results("c", "s", BUY, SELL, "", "", PRICES)
