from mastodon import Mastodon
import os
import yaml

# Replace with your values
with open('crypto_signal_station/cryptos.yml', 'r') as f:
    config = yaml.safe_load(f)
access_token = config.get('MASTODON_ACCESS_TOKEN')
api_base_url = 'https://mastodon.social'  # change if you're using another instance

# Initialize Mastodon
mastodon = Mastodon(
    access_token=access_token,
    api_base_url=api_base_url
)

def send_toot(message):

    mastodon.toot(message)
    print("Tooted successfully!")