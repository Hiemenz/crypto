"""Push notifications for signals and pipeline failures.

Two zero-infrastructure channels, enabled by filling in the `notify:` section
of cryptos.yml (either or both; empty values disable a channel):

    notify:
      ntfy_topic: my-secret-topic     # subscribe in the ntfy app / browser
      ntfy_server: https://ntfy.sh
      telegram_bot_token: "123:abc"   # via @BotFather
      telegram_chat_id: "123456789"

New-signal alerts dedupe on message content per day (state in
data/notify/state.json) so re-running the pipeline doesn't re-ping the phone.
Failure alerts always send.
"""

import hashlib
import json
import os
import sys
import time

import requests
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

TELEGRAM_MAX_LEN = 4096


# Resolved from this file, not the working directory, so scheduled runs from
# any cwd still find the config.
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptos.yml")


def _load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f).get("notify") or {}


def _state_path():
    return db.table_path("notify", "state.json")


def _send_ntfy(cfg, title, message, priority):
    topic = (cfg.get("ntfy_topic") or "").strip()
    if not topic:
        return False
    server = (cfg.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
    resp = requests.post(
        f"{server}/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": priority},
        timeout=30,
    )
    resp.raise_for_status()
    return True


def _send_telegram(cfg, title, message):
    token = (cfg.get("telegram_bot_token") or "").strip()
    chat_id = str(cfg.get("telegram_chat_id") or "").strip()
    if not token or not chat_id:
        return False
    text = f"{title}\n\n{message}"[:TELEGRAM_MAX_LEN]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    resp.raise_for_status()
    return True


def _send_discord(cfg, title, message):
    url = (cfg.get("discord_webhook_url") or "").strip()
    if not url:
        return False
    text = f"**{title}**\n{message}"[:2000]
    resp = requests.post(url, json={"content": text}, timeout=30)
    resp.raise_for_status()
    return True


def _slack_token(cfg):
    """SLACK_BOT_TOKEN env, else cfg slack_bot_token, else SLACK_BOT_TOKEN in cfg slack_env_file."""
    tok = os.environ.get("SLACK_BOT_TOKEN") or (cfg.get("slack_bot_token") or "").strip()
    if tok:
        return tok
    try:
        with open(os.path.expanduser(cfg.get("slack_env_file") or "")) as f:
            for line in f:
                if line.startswith("SLACK_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def post_slack(cfg, text, blocks=None, attempts=3):
    """Post to cfg slack_channel_id, retrying transient errors. Returns True only if Slack said ok.

    Returns False when Slack is unconfigured; raises RuntimeError once the retries are exhausted
    so callers can't mistake a failed delivery for a sent one.
    """
    channel = str(cfg.get("slack_channel_id") or "").strip()
    token = _slack_token(cfg)
    if not channel or not token:
        return False
    payload = {"channel": channel, "text": text, "unfurl_links": False}
    if blocks:
        payload["blocks"] = blocks
    err = "unknown"
    for attempt in range(attempts):
        try:
            resp = requests.post(
                "https://slack.com/api/chat.postMessage",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if resp.status_code == 429:
                err = "rate_limited"
                time.sleep(min(int(resp.headers.get("Retry-After", 2)), 30))
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return True
            err = data.get("error", "unknown")
            if err in ("invalid_auth", "not_authed", "token_revoked", "channel_not_found", "not_in_channel",
                       "is_archived", "missing_scope", "account_inactive"):
                break  # permanent: retrying won't help
        except requests.RequestException as e:
            err = str(e)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Slack post failed: {err}")


def send_notification(title, message, priority="default", config=None):
    """Send to every configured channel; True if at least one accepted it.

    A channel failing (network, bad token) is logged and never raises: alerts
    are best-effort and must not break the pipeline they report on.
    """
    cfg = _load_config() if config is None else config
    sent = False
    for chan, fn in (
        ("ntfy", lambda: _send_ntfy(cfg, title, message, priority)),
        ("telegram", lambda: _send_telegram(cfg, title, message)),
        ("discord", lambda: _send_discord(cfg, title, message)),
        ("slack", lambda: post_slack(cfg, f"*{title}*\n{message}")),
    ):
        try:
            if fn():
                print(f"Notification sent via {chan}")
                sent = True
        except Exception as e:
            print(f"Notification via {chan} failed: {e}")
    return sent


def _already_sent(digest):
    try:
        with open(_state_path()) as f:
            return json.load(f).get("last_digest") == digest
    except (OSError, ValueError):
        return False


def _mark_sent(digest):
    os.makedirs(os.path.dirname(_state_path()), exist_ok=True)
    with open(_state_path(), "w") as f:
        json.dump({"last_digest": digest}, f)


def notify_signals(buy_summary, sell_summary, config=None):
    """Push today's signals; skipped when empty or identical to the last push."""
    body = (sell_summary + "\n" + buy_summary).strip() if (buy_summary or sell_summary) else ""
    if not body:
        print("No signals to notify.")
        return False
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if _already_sent(digest):
        print("Signals unchanged since last notification; not re-sending.")
        return False
    if send_notification("Crypto Signal Station: new signals", body, config=config):
        _mark_sent(digest)
        return True
    return False


def notify_failure(context, detail, config=None):
    """High-priority alert that a pipeline stage crashed."""
    return send_notification(
        f"Crypto Signal Station FAILED: {context}",
        str(detail)[-1500:],  # tail: tracebacks end with the real error
        priority="high",
        config=config,
    )
