# Crypto Signal Station

This project fetches historical cryptocurrency data, calculates technical indicators, generates trading signals, and visualizes both forecasts and buy/sell signals. It also produces daily summaries and supports output to an E Ink display when running on a Raspberry Pi.

## Features

- Downloads crypto OHLCV data from Yahoo Finance
- Calculates RSI, MFI, and Stochastic RSI indicators using `ta`
- Labels signals as Buy/Sell/Hold based on trend and indicators
- Forecasts future prices using Facebook Prophet
- Saves signal-enhanced CSVs and forecast charts
- Summarizes daily Buy/Sell signals
- Optionally displays images on an E Ink screen on Raspberry Pi

## Requirements

- Python 3.9+
- [`yfinance`](https://pypi.org/project/yfinance/)
- [`prophet`](https://pypi.org/project/prophet/)
- `ta`, `matplotlib`, `PyYAML`, `requests`

Install dependencies using [Poetry](https://python-poetry.org/):

```bash
poetry install