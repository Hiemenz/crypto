import yaml
import requests
from requests_oauthlib import OAuth1

def load_twitter_auth(yaml_path: str) -> dict:
    """Load Twitter API credentials from a YAML file."""
    with open(yaml_path, "r") as file:
        config = yaml.safe_load(file)
    return config["twitter"]


def post_tweet(api_key, api_key_secret, access_token, access_token_secret, tweet_text):

    """
    Posts a tweet using Twitter API v2 with OAuth 1.0a.

    :param api_key: str - Your Twitter API Key
    :param api_key_secret: str - Your Twitter API Key Secret
    :param access_token: str - Your Access Token
    :param access_token_secret: str - Your Access Token Secret
    :param tweet_text: str - The text of the tweet
    """
    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(api_key, api_key_secret, access_token, access_token_secret)
    payload = {"text": tweet_text}

    response = requests.post(url, auth=auth, json=payload)

    if response.status_code == 201:
        print("Tweet posted successfully!")
        print(f"Tweet ID: {response.json().get('data', {}).get('id')}")
    else:
        print(f"Failed to post tweet: {response.status_code}")
        print(response.json())

def send_tweet(tweet_text):
    credentials = load_twitter_auth('crypto_signal_station/cryptos.yml')

    post_tweet(credentials['api_key'], credentials['api_key_secret'], credentials['access_token'], credentials['access_token_secret'], tweet_text)


def main():

    TWEET_TEXT = "I am back!!!!"
    send_tweet(TWEET_TEXT)

