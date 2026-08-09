from crypto_signal_station import toot


class _FakeMastodon:
    def __init__(self):
        self.tooted = []

    def toot(self, message):
        self.tooted.append(message)


def test_send_toot_posts_message(monkeypatch, capsys):
    fake = _FakeMastodon()
    monkeypatch.setattr(toot, "mastodon", fake)

    toot.send_toot("hello world")

    assert fake.tooted == ["hello world"]
    assert "Tooted successfully!" in capsys.readouterr().out
