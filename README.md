# Crypto Signal Station

A Raspberry Pi–hosted pipeline that tracks crypto and S&P 500 daily market
data, computes multi-timeframe technical signals, and surfaces them on an
E Ink display, a local web dashboard, push notifications, and social posts.

## How it works

```
yfinance (daily OHLCV)                 CoinGecko / Wikipedia (universe, prices)
        │                                        │
        ▼                                        ▼
crypto_signal_pipeline.py refresh  ──  nightly cron (21:30 America/Chicago)
        │
        ├─ data/ohlcv/      partitioned Parquet lake (queried via DuckDB)
        ├─ data/signals/    indicators + Buy/Sell tiers per timeframe
        ├─ data/breadth/    daily market-breadth + vol-regime history
        ├─ data/momentum/   trailing returns + altcoin season index
        ├─ data/sectors/    GICS sector breadth + momentum + signals
        ├─ data/market/     market context snapshot (BTC dom, SPY/QQQ, F&G)
        ├─ data/dashboard/  self-contained index.html
        └─ push notification (ntfy / Telegram / Discord) with the day's signals
```

- **Storage** is an open table format: Hive-partitioned Parquet under `data/`
  (never committed), queried with DuckDB. See `db.py` for the schema and the
  bulk lake-scan helpers.
- **Signals**: RSI + MFI + StochRSI tiers (Good/Great/Excellent Buy/Sell),
  gated by the 50/200-MA regime, on 1d/2d/3d/1wk/2wk resamples of daily bars.
  ATR, golden/death crosses, volume spikes, and RSI divergences are stored
  alongside for measurement.
- **Universe**: `stocks:` auto-tracks current S&P 500 constituents
  (`auto_update_stocks: sp500`); the crypto list is curated in `cryptos.yml`
  (optionally unioned with the CoinGecko top-N via `auto_update_cryptos: N`).

## Commands

```bash
poetry run python crypto_signal_station/crypto_signal_pipeline.py <command>
```

| Command | What it does |
|---|---|
| `refresh` | Update universe + OHLCV + signals, record breadth + vol regime, compute momentum + altcoin season, update sector breakdown, fetch market context, regenerate the dashboard, push notifications. Sends a failure alert if it crashes. |
| `verify` | Audit stored history: gaps, NaN rows, staleness, and cross-symbol contamination. |
| `backtest` | Score every historical signal: forward returns at 7/30/90 days, win rates vs baseline, per tier/timeframe/category. |
| `breadth` | Record today's market-breadth + vol-regime row (also part of `refresh`). |
| `dashboard` | Regenerate `data/dashboard/index.html` (also part of `refresh`). |
| `digest` | Print the weekly signal digest; `digest post` also toots/tweets it. |
| `tweet` | Render the E Ink image and post the daily signal summaries. |
| *(none)* | Render the E Ink image and show it on the display (Pi only). |

`--dry-run` on `tweet` / `digest post` prints what would be posted instead of
posting it.

## Dashboard

`refresh` writes a fully self-contained HTML dashboard (no external requests,
light/dark aware). Serve it on the LAN:

```bash
python -m http.server -d data/dashboard 8080
```

Sections:

| Section | Description |
|---|---|
| **Market Overview** | BTC dominance, total crypto market cap, 24h change, Fear & Greed index, SPY / QQQ / DIA price and 1d / 1m returns |
| **Breadth tiles** | % symbols above 200-day MA, regime (Risk-On/Off/Neutral), 20-day realized vol and vol regime (Low/Normal/High), 52-week highs/lows |
| **Breadth chart** | 90-day % above 200dMA trend for stocks and crypto, with crosshair tooltip |
| **Altcoin Season** | % of crypto symbols outperforming BTC over 90 days — flags "BTC Season", "Neutral", or "Altcoin Season" |
| **High-conviction signals** | Symbols where 2+ timeframes agree on buy or sell direction |
| **RSI Divergences** | Symbols where price is near a recent high/low but RSI is diverging — bullish or bearish |
| **Latest signals** | Today's Buy/Sell tiers per category and timeframe |
| **Volume spikes** | Symbols with >2× their 20-day average volume today |
| **Golden/death crosses** | MA crossovers in the last 30 days |
| **Signal backtest** | Historical win rates and average returns at 7/30/90 days vs baseline |
| **S&P 500 by GICS sector** | Breadth, 30-day return, and today's buy/sell signal count per sector |
| **Momentum** | Top and bottom movers by 1m/3m/6m return |
| **Crypto watchlist** | Price, 30-day return, and 90-day sparkline per symbol |
| **Correlation heatmap** | 30-day return correlations across the crypto watchlist |

## Market context features

### Realized volatility regime

Every breadth snapshot now includes annualized 20-day realized vol averaged
across active symbols. Labels are calibrated per category:

| Category | Low | Normal | High |
|---|---|---|---|
| Stocks (individual) | < 25% | 25–45% | ≥ 45% |
| Crypto (individual) | < 50% | 50–100% | ≥ 100% |

Signals generated in a High Vol regime have very different expected
reliability than those generated in a Low Vol environment.

### RSI divergence detection

For every symbol and timeframe, the pipeline flags:
- **Bullish divergence**: price near its 20-period low, RSI notably above where
  it was at that low (momentum recovering before price).
- **Bearish divergence**: price near its 20-period high, RSI notably below
  where it was at that high (momentum fading while price is still elevated).

Stored as `rsi_bullish_div` / `rsi_bearish_div` boolean columns in the signals
lake; today's 1d divergences appear on the dashboard.

### Altcoin season index

After each momentum computation, the pipeline computes the share of crypto
symbols whose 90-day return beats BTC-USD:
- ≥ 75% beating BTC → **Altcoin Season**
- 50–75% → **Neutral**
- < 50% → **BTC Season**

### S&P 500 sector breakdown

The sector breadth table (GICS sectors from Wikipedia) now includes the mean
30-day momentum return and today's buy/sell signal count for each sector —
useful for spotting which sectors are rotating in or out.

## Notifications

Fill in the `notify:` section of `crypto_signal_station/cryptos.yml`:

```yaml
notify:
  ntfy_topic: my-secret-topic
  ntfy_server: https://ntfy.sh
  telegram_bot_token: "123:abc"
  telegram_chat_id: "123456789"
  discord_webhook_url: "https://discord.com/api/webhooks/..."
```

New-signal pushes dedupe on content, so re-running the pipeline never re-pings;
pipeline failures always alert at high priority.

## Setup

```bash
poetry install
poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh   # first run backfills full history
```

Cron (the nightly refresh; add the Sunday digest if you want weekly posts):

```cron
30 21 * * * cd /home/pi/git/crypto && poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh >> ~/refresh.log 2>&1
```

Secrets (Twitter/X keys, Mastodon token, notify credentials) live in
`crypto_signal_station/cryptos.yml` — keep real values out of version control.

## Tests

```bash
poetry run pytest tests/
```

The `lake` fixture points the Parquet store at a temp directory, so tests
never touch `data/`.

## Notes

- Downloads are serialized behind a lock: concurrent `yf.download` calls can
  return each other's payloads (this once cross-contaminated 19 symbol pairs;
  `verify` now detects that failure mode by fingerprinting recent closes).
- On a Pi, never loop per-symbol Parquet reads across the S&P 500 — use the
  `db.scan_*` bulk helpers (one DuckDB glob scan instead of ~1,000 connections).
- During `refresh`, momentum runs before sectors so sector momentum uses the
  freshest 30-day returns; market context is fetched last so it doesn't hold
  up signal processing.
