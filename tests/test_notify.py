import json

import db
from crypto_signal_station import notify


class _FakeResp:
    status_code = 200

    def raise_for_status(self):
        pass


def test_disabled_channels_send_nothing(lake, monkeypatch):
    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: calls.append(a) or _FakeResp())
    assert notify.send_notification("t", "m", config={}) is False
    assert calls == []


def test_ntfy_send(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return _FakeResp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    cfg = {"ntfy_topic": "my-topic", "ntfy_server": "https://ntfy.sh"}
    assert notify.send_notification("Title", "Body", config=cfg) is True
    url, kw = calls[0]
    assert url == "https://ntfy.sh/my-topic"
    assert kw["data"] == b"Body"
    assert kw["headers"]["Title"] == "Title"


def test_telegram_send(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return _FakeResp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    cfg = {"telegram_bot_token": "123:abc", "telegram_chat_id": "42"}
    assert notify.send_notification("Title", "Body", config=cfg) is True
    url, kw = calls[0]
    assert "bot123:abc/sendMessage" in url
    assert kw["json"]["chat_id"] == "42"
    assert "Body" in kw["json"]["text"]


def test_discord_send(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return _FakeResp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    cfg = {"discord_webhook_url": "https://discord.com/api/webhooks/xyz"}
    assert notify.send_notification("Title", "Body", config=cfg) is True
    url, kw = calls[0]
    assert url == "https://discord.com/api/webhooks/xyz"
    assert kw["json"]["content"] == "**Title**\nBody"


def test_channel_failure_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(notify.requests, "post", boom)
    cfg = {"ntfy_topic": "t"}
    assert notify.send_notification("x", "y", config=cfg) is False


def test_notify_signals_dedupes_identical_content(lake, monkeypatch):
    sent = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: sent.append(a) or _FakeResp())
    cfg = {"ntfy_topic": "t"}

    assert notify.notify_signals("Buy: BTC\n", "", config=cfg) is True
    assert notify.notify_signals("Buy: BTC\n", "", config=cfg) is False  # unchanged
    assert notify.notify_signals("Buy: ETH\n", "", config=cfg) is True   # new content
    assert len(sent) == 2

    with open(db.table_path("notify", "state.json")) as f:
        assert "last_digest" in json.load(f)


def test_notify_signals_skips_empty(monkeypatch):
    monkeypatch.setattr(
        notify.requests, "post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not post")),
    )
    assert notify.notify_signals("", "", config={"ntfy_topic": "t"}) is False


def test_notify_failure_always_sends_at_high_priority(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(kw)
        return _FakeResp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    cfg = {"ntfy_topic": "t"}
    assert notify.notify_failure("refresh", "Traceback: boom", config=cfg) is True
    kw = calls[0]
    assert kw["headers"]["Priority"] == "high"
    assert kw["headers"]["Title"] == "Crypto Signal Station FAILED: refresh"
    assert kw["data"] == b"Traceback: boom"


def test_notify_failure_truncates_long_detail(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: calls.append(k) or _FakeResp())
    long_detail = "x" * 2000
    notify.notify_failure("refresh", long_detail, config={"ntfy_topic": "t"})
    assert len(calls[0]["data"]) == 1500
