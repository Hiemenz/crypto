"""Post to Mastodon.

The client is built on first use, not at import: crypto_signal_pipeline imports
send_toot unconditionally, so an import-time client meant `refresh` — which
never toots — still needed a valid token, and died outright when the config was
missing or the process started from another working directory.
"""

import os

import yaml
from mastodon import Mastodon

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptos.yml")
API_BASE_URL = "https://mastodon.social"  # change if you're using another instance

mastodon = None


def _client():
    """Build (and memoise) the Mastodon client from cryptos.yml."""
    global mastodon
    if mastodon is None:
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        access_token = config.get("MASTODON_ACCESS_TOKEN")
        if not access_token or access_token == "insert":
            raise RuntimeError(f"MASTODON_ACCESS_TOKEN is not set in {CONFIG_PATH}")
        mastodon = Mastodon(access_token=access_token, api_base_url=API_BASE_URL)
    return mastodon


def send_toot(message):
    _client().toot(message)
    print("Tooted successfully!")
