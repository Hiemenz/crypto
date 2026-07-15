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
        ├─ data/ohlcv/     partitioned Parquet lake (queried via DuckDB)
        ├─ data/signals/   indicators + Buy/Sell tiers per timeframe
        ├─ data/breadth/   daily market-breadth history
        ├─ data/dashboard/ self-contained index.html
        └─ push notification (ntfy / Telegram) with the day's signals
```

- **Storage** is an open table format: Hive-partitioned Parquet under `data/`
  (never committed), queried with DuckDB. See `db.py` for the schema and the
  bulk lake-scan helpers.
- **Signals**: RSI + MFI + StochRSI tiers (Good/Great/Excellent Buy/Sell),
  gated by the 50/200-MA regime, on 1d/2d/3d/1wk/2wk resamples of daily bars.
  ATR, golden/death crosses, and volume spikes are stored alongside for
  measurement but don't drive the tiers.
- **Universe**: `stocks:` auto-tracks current S&P 500 constituents
  (`auto_update_stocks: sp500`); the crypto list is curated in `cryptos.yml`
  (optionally unioned with the CoinGecko top-N via `auto_update_cryptos: N`).

## Commands

```bash
poetry run python crypto_signal_station/crypto_signal_pipeline.py <command>
```

| Command | What it does |
|---|---|
| `refresh` | Update universe + OHLCV + signals, record breadth, regenerate the dashboard, push notifications. Sends a failure alert if it crashes. |
| `verify` | Audit stored history: gaps, NaN rows, staleness, and cross-symbol contamination. |
| `backtest` | Score every historical signal: forward returns at 7/30/90 days, win rates vs baseline, per tier/timeframe/category. |
| `breadth` | Record today's market-breadth row (also part of `refresh`). |
| `dashboard` | Regenerate `data/dashboard/index.html` (also part of `refresh`). |
| `digest` | Print the weekly signal digest; `digest post` also toots/tweets it. |
| `tweet` | Render the E Ink image and post the daily signal summaries. |
| *(none)* | Render the E Ink image and show it on the display (Pi only). |

`--dry-run` on `tweet` / `digest post` prints what would be posted instead of
posting it.

## Dashboard

`refresh` writes a fully self-contained HTML dashboard (no external requests,
light/dark aware) with regime tiles, a breadth trend chart, the latest signals
per timeframe, recent golden/death crosses, the backtest scoreboard, and
watchlist sparklines. Serve it on the LAN:

```bash
python -m http.server -d data/dashboard 8080
```

## Notifications

Fill in the `notify:` section of `crypto_signal_station/cryptos.yml` with an
[ntfy](https://ntfy.sh) topic and/or a Telegram bot token + chat id. New-signal
pushes dedupe on content, so re-running the pipeline never re-pings; pipeline
failures always alert at high priority.

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
