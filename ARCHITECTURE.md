# Architecture

How Crypto Signal Station is built: modules, data flow, storage schema, and
how the frontend and backend fit together.

---

## 1. System overview

```
┌─────────────────────────────────────────────────────────────────┐
│  External data sources                                          │
│  yfinance (OHLCV)   CoinGecko (universe, prices, global)       │
│  Wikipedia (S&P 500 constituents + GICS sectors)               │
│  alternative.me (Fear & Greed index)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │ nightly cron / systemd timer
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  crypto_signal_pipeline.py  (refresh command)                  │
│                                                                 │
│  1. update_symbol_universe()   scrape S&P 500, CoinGecko top-N │
│  2. process_crypto_data()  ──┐                                  │
│  3. process_stock_data()   ──┤  ThreadPoolExecutor (4 workers)  │
│     └─ _process_single_symbol() per ticker:                     │
│        ▸ _fetch_daily() via yfinance (serialised behind lock)   │
│        ▸ gap detection + heal-then-cache-failure                │
│        ▸ resample to 1d/2d/3d/1wk/2wk                          │
│        ▸ RSI, MFI, StochRSI, Bollinger, MACD, ATR indicators   │
│        ▸ MA-50/200 regime gate → _label_signal()               │
│        ▸ golden/death crosses, volume spikes, RSI divergence    │
│        ▸ db.replace_signals()  → Parquet lake                  │
│  4. _check_failure_rate()   alert if >33 % of a category fails  │
│  5. breadth_mod.record_daily()   breadth + vol-regime snapshot  │
│  6. momentum_mod.compute()       trailing returns, altcoin idx  │
│  7. sectors_mod.compute_and_save()  GICS sector breakdown       │
│  8. fetch_and_store_market_context()  BTC dom, F&G, SPY/QQQ    │
│  9. dashboard_mod.generate()     self-contained HTML dashboard  │
│  10. notify.notify_signals()     push to ntfy/Telegram/Discord  │
│  11. check_price_alerts()        per-symbol threshold alerts    │
└────────────────────────────┬────────────────────────────────────┘
                             │
            ┌────────────────┴─────────────────┐
            ▼                                  ▼
  data/  (Parquet lake)               data/dashboard/index.html
  queried via DuckDB                  served on the LAN
            │
            ▼
  generate_api_data.py
  ├─ generate_history_json()     frontend/public/data/history/<sym>.json
  ├─ generate_latest_signals_json()  …/latest_signals.json
  ├─ generate_crosses_json()         …/crosses.json
  └─ upload_to_supabase()        → Supabase Storage (SHA-256 skip-unchanged)
            │
            ▼
  Vercel frontend (React)  fetches JSON at runtime from Supabase
```

---

## 2. Module layout

```
crypto_signal_station/
  crypto_signal_pipeline.py   main orchestrator + signal computation
  dashboard.py                HTML dashboard generator (no network at render)
  breadth.py                  market-breadth + vol-regime recorder
  momentum.py                 trailing returns + altcoin season index
  sectors.py                  GICS sector breadth and momentum
  backtest.py                 forward-return scorer for stored signals
  digest.py                   weekly text digest (also posts to social)
  notify.py                   ntfy / Telegram / Discord push notifications
  toot.py                     Mastodon posting (lazy client, no import side-effects)
  send_to_x.py                Twitter/X OAuth1 posting
  display.py                  Waveshare E Ink display (Pi only)
  eink_generator.py           raster image renderer for the display
  cryptos.yml                 secrets + universe config (gitignored)
  cryptos.example.yml         checked-in template

db.py                         Parquet lake I/O (DuckDB, no pyarrow needed)
generate_api_data.py          JSON export + Supabase upload

frontend/
  src/components/
    ProDashboard.jsx           main interactive dashboard (signals, chart)
    StrategySimulator.jsx      backtest simulator (buy/sell signal replay)
    Dashboard.jsx              simpler watchlist dashboard
  src/utils/storage.js        Supabase URL resolver (dev vs prod)

tests/                        pytest suite (122 tests; lake fixture → tmp_path)
```

---

## 3. Parquet lake schema

All data lives under `data/` and is never committed to git.
DuckDB reads every table via glob patterns with `hive_partitioning=true`.

### OHLCV

```
data/ohlcv/category=<cat>/symbol=<sym>/data.parquet
```

Columns: `Date  Open  High  Low  Close  Volume`

One file per symbol/category. Written atomically (`.tmp` → `os.replace`).
`upsert_ohlcv` merges on Date (newest row wins); `replace_ohlcv` overwrites
everything, used after a split/dividend re-adjustment.

### Signals

```
data/signals/category=<cat>/timeframe=<tf>/symbol=<sym>/data.parquet
```

Every OHLCV column plus:

| Column | Type | Source |
|---|---|---|
| `rsi` | float | RSI(14) |
| `mfi` | float | MFI(14) |
| `stoch_rsi` | float | StochRSI(14, 3, 3) |
| `stoch_rsi_k` | float | %K smoothed |
| `stoch_rsi_d` | float | %D smoothed |
| `bb_upper` / `bb_lower` / `bb_pband` | float | Bollinger(20, 2) |
| `macd` / `macd_signal` / `macd_hist` | float | MACD(12, 26, 9) |
| `ma_50` / `ma_200` | float | rolling means |
| `is_bull` | bool | ma_50 > ma_200 |
| `atr` / `atr_pct` | float | ATR(14) |
| `golden_cross` / `death_cross` | bool | MA-50/200 flip |
| `vol_spike` | bool | Volume > 2× 20-day mean |
| `rsi_bullish_div` / `rsi_bearish_div` | bool | RSI divergence (20-bar window) |
| `signal` | str | Excellent/Great/Good Buy/Sell/Hold |

Always written with `replace_signals` (full-history recompute is authoritative).

Timeframes: `1d`, `2d`, `3d`, `1wk`, `2wk`.
`2wk` bins are anchored to `TWO_WEEK_ORIGIN = 2014-01-06` (Monday) so
every symbol's fortnight bins align regardless of history start date.
`1wk` and `2wk` dates are labeled by the ending Sunday.

### Auxiliary tables

```
data/breadth/history.parquet         daily % above 200dMA + vol regime
data/momentum/returns.parquet        trailing 1m/3m/6m returns per symbol
data/sectors/breadth.parquet         per-GICS breadth, momentum, signal counts
data/market/context.json             BTC dom, F&G, SPY/QQQ/DIA (JSON not Parquet)
data/universe/sp500.json             cached S&P 500 symbol list
data/universe/top_cryptos.json       cached CoinGecko top-N tickers
data/universe/heal_failures.json     symbols whose gaps resisted full re-download
data/api/upload_manifest.json        SHA-256 hashes of last-uploaded JSON files
data/notify/state.json               dedup: hash of last sent signal body
data/notify/price_alert_state.json   per-symbol threshold direction
```

---

## 4. Signal computation

```
daily OHLCV (1d bars)
    │
    ├─ resample to 2d / 3d / 1wk / 2wk
    │
    └─ per timeframe:
       ├─ RSI(14), MFI(14), StochRSI(14,3,3)
       ├─ Bollinger(20,2), MACD(12,26,9), ATR(14)
       ├─ MA-50, MA-200  →  is_bull flag
       │
       ├─ _label_signal(row):
       │   if not is_bull:
       │     RSI<20 & MFI<10 & StochRSI<0.10  →  Excellent Buy
       │     RSI<30 & MFI<20 & StochRSI<0.20  →  Great Buy
       │     RSI<40 & MFI<30 & StochRSI<0.30  →  Good Buy
       │   if is_bull:
       │     RSI>80 & MFI>90 & StochRSI>0.90  →  Excellent Sell
       │     RSI>70 & MFI>80 & StochRSI>0.80  →  Great Sell
       │     RSI>60 & MFI>70 & StochRSI>0.70  →  Good Sell
       │   else  →  Hold
       │
       ├─ golden/death cross  (MA flip gated on MA-200 being valid on both sides)
       ├─ vol_spike           (Volume > 2× 20-bar rolling mean)
       └─ RSI divergence      (20-bar window, ±3% price tolerance, ±5 RSI threshold)
```

The regime gate (is_bull) means buy signals only appear in bear markets and
sell signals only in bull markets — mean-reversion tiers, not trend-following.

---

## 5. Download safety

`yf.download` is **not thread-safe**: parallel callers can receive each
other's payloads. This was observed in production (ETH-USD received ADA-USD's
history). All downloads go through `_YF_LOCK` (a module-level `threading.Lock`),
serialising them even though the thread pool has 4 workers.

Gap healing: if stored OHLCV has gaps (crashed run, transient outage), a
full re-download is attempted. If the re-download doesn't add bars (genuine
halt, not a network issue), the failure is cached in `heal_failures.json` keyed
by `(category, symbol, bar_count)`. The cache is checked before each attempt;
a changed bar count means new data arrived and is worth retrying.

---

## 6. JSON export and upload

`generate_api_data.py` exports three files for the React frontend:

| File | Contents | Notes |
|---|---|---|
| `history/<sym>.json` | OHLCV + signal label, 1d, all history | 7 columns only; no indicators (saves ~4× per file) |
| `latest_signals.json` | Most recent signal row per symbol, all indicators | Includes a 0–100 `score` and `side` (buy/sell/hold) |
| `crosses.json` | StochRSI K/D crossovers in the last 180 days | Confirmed only when prior bar was in an extreme zone |

All outputs go through `_json_safe()` which replaces `NaN`/`±Inf`/numpy
scalars/`pd.NaT` before serialisation, and `allow_nan=False` on `json.dump`
turns any missed value into a loud `ValueError` rather than silent invalid JSON.

Upload skips files whose SHA-256 matches the last run (`upload_manifest.json`),
times out after 60 s per file, and catches `URLError`/`socket.timeout`/`OSError`
per file so one bad file never aborts the whole export.

---

## 7. Frontend

The React app (`frontend/`) fetches JSON from Supabase Storage at runtime.
`src/utils/storage.js` resolves the base URL from `VITE_SUPABASE_URL` (set in
Vercel) or falls back to `frontend/public/data/` for local dev.

**ProDashboard** — main view: signal list ranked by score, candlestick/line
chart for the selected symbol (history JSON), and a strategy simulator that
replays buy/sell signal tiers against real price history.

**StrategySimulator** — runs an in-browser backtest: configurable initial
capital, buy strength (% of cash per signal), sell percentage (% of holdings),
and fee rate. Compares signal-driven strategy vs buy-and-hold.

The history JSON exports exactly `["Date", "Open", "High", "Low", "Close",
"Volume", "signal"]` — the 7 columns the frontend reads. The full indicator
set lives in `latest_signals.json` only, which the signal list reads.

---

## 8. Scheduling

The nightly pipeline runs via `daily_update.sh`, which sources `.env` for
Supabase credentials and then:

1. `crypto_signal_pipeline.py refresh` — download, compute, store, dashboard, alert
2. `generate_api_data.py` — JSON export + upload

`flock -n` prevents two runs from overlapping (both write the same Parquet
files via `.tmp`-then-`os.replace`; a second writer would clobber the first's
temp file).

See **[SCHEDULING.md](SCHEDULING.md)** for cron vs systemd-timer setup,
log rotation, failure alerts, and how to verify a run worked.

---

## 9. Testing

```
tests/
  conftest.py              lake fixture: patches db.DATA_DIR → tmp_path
  test_pipeline.py         _process_single_symbol, signal labelling,
                           failure accounting, symbol validation,
                           gap-heal backoff, market context JSON safety
  test_generate_api_data.py  JSON export correctness, NaN/Inf sanitisation,
                              cross confirmation logic, upload timeout/dedupe
  test_db.py               Parquet I/O, merge semantics, schema helpers
  test_breadth.py          vol-regime calibration, breadth recording
  test_momentum.py         trailing returns, altcoin season index
  test_sectors.py          GICS aggregation, sector map persistence
  test_backtest.py         forward-return scoring, win-rate calculation
  test_notify.py           channel dispatch, dedup, failure alerts
  test_toot.py             lazy Mastodon client, missing-token guard
  test_send_to_x.py        OAuth1 tweet construction
  test_universe.py         S&P 500 scrape, CoinGecko top-N, symbol filter
  test_dashboard_digest.py  HTML generation, digest formatting
  test_summaries.py        multi-timeframe signal summaries
```

All 122 tests run in ~10 s on a Pi 5. The `lake` fixture redirects every
Parquet read/write to a temp directory so the real `data/` is never touched.
