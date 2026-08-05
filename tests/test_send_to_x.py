import yaml

from crypto_signal_station import send_to_x


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_load_twitter_auth_reads_credentials(tmp_path):
    path = tmp_path / "cryptos.yml"
    creds = {
        "api_key": "K", "api_key_secret": "KS",
        "access_token": "T", "access_token_secret": "TS",
    }
    path.write_text(yaml.dump({"twitter": creds}))
    assert send_to_x.load_twitter_auth(str(path)) == creds


def test_post_tweet_success(monkeypatch, capsys):
    calls = []

    def fake_post(url, auth, json):
        calls.append((url, auth, json))
        return _FakeResp(201, {"data": {"id": "999"}})

    monkeypatch.setattr(send_to_x.requests, "post", fake_post)
    send_to_x.post_tweet("key", "key_secret", "token", "token_secret", "hello world")

    url, auth, payload = calls[0]
    assert url == "https://api.twitter.com/2/tweets"
    assert payload == {"text": "hello world"}
    assert "Tweet ID: 999" in capsys.readouterr().out


def test_post_tweet_failure_logs_error(monkeypatch, capsys):
    monkeypatch.setattr(
        send_to_x.requests, "post",
        lambda url, auth, json: _FakeResp(400, {"error": "bad request"}),
    )
    send_to_x.post_tweet("key", "key_secret", "token", "token_secret", "hello world")
    assert "Failed to post tweet: 400" in capsys.readouterr().out


def test_send_tweet_loads_config_and_posts(monkeypatch):
    calls = []
    monkeypatch.setattr(send_to_x, "post_tweet", lambda *a: calls.append(a))
    send_to_x.send_tweet("hello world")
    assert len(calls) == 1
    assert calls[0][-1] == "hello world"
    assert len(calls[0]) == 5  # 4 credential args + tweet text
