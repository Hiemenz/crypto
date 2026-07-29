import requests
import yaml

# Load symbols from YAML file
with open("cryptos.yml", "r") as f:
    config = yaml.safe_load(f)

symbols = [entry["id"] for entry in config["cryptos"]]
id_to_symbol = {entry["id"]: entry["symbol"] for entry in config["cryptos"]}

vs_currency = "usd"
url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(symbols)}&vs_currencies={vs_currency}"

response = requests.get(url)


prices = response.json()

for symbol in symbols:
    price = prices[symbol][vs_currency]
    if price >= 1:
        print(f"{id_to_symbol[symbol]}: ${price:.2f}")
    else:
        print(f"{id_to_symbol[symbol]}: ${price:.5f}")