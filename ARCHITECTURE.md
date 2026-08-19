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
  market_cycle.py             crypto cycle phase + sector business-cycle stage
  cycle_forecast.py           backtested breadth-band forward-return forecast
  prophet_backtest.py         Prophet BTC-USD forecast + walk-forward backtest
  prophet_forecast.py         Prophet per-symbol price forecasting
  ml_signal.py                 trained buy-signal model (logistic/gboost/tree, feature search)
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
data/momentum/altcoin_season.json    % of cryptos beating BTC over 90d, labeled
data/forecast/breadth_model_<cat>.parquet  backtested breadth-band -> forward-return lookup
data/forecasts/<cat>/<tf>/<sym>.parquet     Prophet per-symbol forecast (yhat + 80% CI)
data/backtest/prophet_<cat>_stats.parquet   Prophet walk-forward backtest results
data/ml_signal/model_<cat>.joblib           trained classifier + scaler + threshold
data/ml_signal/eval_<cat>.json              out-of-sample scorecard vs. rule-based tiers
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

## 5. Market cycle classification

`market_cycle.py` reads only stored tables (breadth history, momentum's
altcoin-season index, sector breadth, market context) — no network calls at
classification time — and turns them into a phase label per category.

**Crypto** — a scored Wyckoff-style phase:

| Signal | Points |
|---|---|
| `pct_above_ma200` ≥ 75% / ≥ 60% | +2 / +1 |
| `pct_above_ma200` ≤ 25% / ≤ 40% | −2 / −1 |
| breadth up/down ≥10pp over ~4wk | +1 / −1 |
| 52w highs > 2× lows (or reverse) | +1 / −1 |
| Fear & Greed ≥80 / ≤20 | +1 / −1 |

Score maps to a phase: ≤−3 `Markdown (Bear)`, −2..−1 `Distribution / Early
Bear`, 0 `Transition / Range-Bound`, 1..2 `Markup (Bull)`, ≥3 `Late-Stage
Bull / Euphoria` (only when confirmed by extreme greed or Altcoin Season).
Extreme Fear at ≤30% breadth overrides the score to `Capitulation /
Accumulation` — the classic contrarian bottom signature.

**Stocks** — each GICS sector gets an RRG-style quadrant from its breadth
level (strong ≥55% / weak ≤45% above 200dMA) crossed with its 30d return
relative to the peer-sector median (`Leading` / `Weakening` / `Lagging` /
`Improving`). Sectors are grouped into Fidelity-style business-cycle
clusters (`Early Cycle`, `Mid Cycle`, `Late Cycle`, `Recession / Defensive`;
Consumer Staples sits in both Late Cycle and Defensive); whichever cluster
has the best average quadrant score names the stage.

`algorithmic_summary()` renders both as digest-style text; `cycle` is the
pipeline CLI command that prints it.

### Backtested forward-return forecast

`cycle_forecast.py` answers "so what tends to happen next?" It reconstructs
the *full* historical breadth time series directly from the OHLCV lake
(every symbol's own rolling 200/50-day MA, years of daily bars) rather than
relying on the sparse day-by-day breadth.parquet snapshot — that table only
grows one row per day the pipeline runs, which isn't enough history to
backtest against. Every historical day is bucketed into the same breadth
bands `market_cycle.py` scores against (≤25% / 25-40% / 40-60% / 60-75% /
≥75%), and for each band the benchmark's realized forward return at 7/30/90
days is measured — BTC-USD's own forward return for crypto; the
equal-weight average forward return across all S&P 500 constituents in the
lake for stocks (no single stored index; stock rows only exist on trading
days, so 30/90-day horizons use ~21/63-trading-day shifts as the calendar
approximation). The result is a lookup table, not a fitted model: predicting
today's return is just reading off which band today's breadth falls in.

Confidence is sample-size gated: `High` needs n≥60 and a win rate that
clears 60/40; `Medium` needs n≥20; otherwise `Low`. `forecast_report()`
prints the market-cycle phase plus this forecast; `forecast` is the pipeline
CLI command.

Sample output against this repo's live lake (2026-08-17):

```
Crypto cycle: Markdown (Bear)  (score -3)
Stock sectors: Mid Cycle  (breadth Risk-On)

Backtested forward-return forecast:
  Crypto (breadth 0%, band ≤25%): 30d Up +1.2%/55% (n=1465, Medium)
  Stocks (breadth 74%, band 60-75%): 30d Up +1.4%/71% (n=1007, High)
```

### Prophet market forecast (crypto)

`prophet_backtest.py` is a second, independent forecast for BTC-USD (the
crypto benchmark), built on `prophet_forecast.py`'s existing per-symbol
Prophet fitting rather than the empirical bucket-lookup above. It adds a
walk-forward backtest: refit Prophet using only the data available at each
of several past cutoffs (`_fold_cutoffs`, ~60 days apart), forecast
forward, and compare the forecast to what BTC-USD actually did at 7/30/90
days. Each fold is a real Stan fit (a few seconds), so this is an on-demand
CLI job (`prophet` command), not part of the nightly refresh; stocks aren't
wired up yet — there's no single stored index to fit, only the equal-weight
average used above.

Run against this repo's live lake (2026-08-17), the backtest is a useful
warning, not a green light: directional accuracy came in at 40-50% (a coin
flip) with a consistent bullish bias — the live forecast called +48% over
7 days while the walk-forward folds' *actual* average outcome was negative
at every horizon. Prophet's trend+seasonality curve extrapolates BTC's
long-run uptrend and doesn't adapt to the regime break the breadth-bucket
model and `market_cycle.py` are both currently flagging (0% above 200dMA,
`Markdown (Bear)`). Treat its output as a second opinion to weigh against
the empirical model, not a standalone signal.

### Trained buy-signal model (ML, both categories)

`ml_signal.py` replaces `_label_signal()`'s hand-set RSI/MFI/StochRSI
thresholds with a classifier trained on stored indicator columns plus a
handful of engineered ones: 8 raw indicators (RSI, MFI, StochRSI K/D,
Bollinger %B, MACD histogram, ATR%, volume spike, RSI divergence) and 9
engineered features — `ma_spread` (ma_50/ma_200 - 1, a continuous version
of the is_bull regime gate), 5/10/20-day price momentum, 5-day ATR%
change, Bollinger bandwidth `(bb_upper-bb_lower)/Close` (squeeze/expansion,
distinct from %B's position-in-band), distance from the 52-week high/low,
and `mkt_breadth` — the symbol's category-wide breadth on that date,
reconstructed by `cycle_forecast.compute_breadth_timeseries()` and merged
in by Date, so the model can see "is the whole market supportive," not
just this one symbol's technicals. `_engineer_features()` computes all of
this on the *full* per-symbol history (several need rolling windows), and
both `_build_dataset()` (training) and `predict_latest()` (live) call it
the same way — `predict_latest()` engineers first, then truncates to each
symbol's latest bar, never the other order.

Label: forward 30-day return > 0, computed with `backtest.py`'s own
`_forward_returns()` applied to every daily bar instead of just signal
events.

Validation is a strict time split, not cross-validation: the most recent
20% of the date range is held out entirely from training (`_time_split`),
so no test-period row's outcome could have leaked into what the model
learned. The buy/sell decision threshold isn't hardcoded at 0.5 either —
`_select_threshold()` scans candidate cutoffs against the *training* data
only and picks whichever maximizes the resulting buy calls' average
return, but only among thresholds backed by at least 0.5% of training
rows (minimum 20). That floor exists because it was needed: an earlier,
unguarded version of this picked a threshold with 8-13 buy calls out of
hundreds of thousands of test rows and reported eye-catching returns
(stocks: +39%, 75% win rate) that were just noise wearing a good average —
scanning several thresholds and keeping whichever looks best in-sample is
exactly the kind of search that finds flukes. Every evaluation also scores
the existing rule-based Buy tiers over the *same* held-out window, so the
model is graded against what the pipeline already does, not just against
a coin flip.

Run against this repo's live lake (2026-08-17), 30d horizon:

```
[crypto] accuracy 58%, AUC 0.51 (threshold 0.65)
  model buy calls: 136 (2% of test) — avg -1.2%, win 41%
  rule-based Buy tiers: 218 calls — avg +9.5%, win 43%
  baseline: avg +3.4%, win 41%

[stocks] accuracy 45%, AUC 0.51 (threshold 0.60)
  model buy calls: 1246 (0.4% of test) — avg +9.9%, win 57%
  rule-based Buy tiers: 5087 calls — avg +2.0%, win 59%
  baseline: avg +1.4%, win 55%
```

Read this as: on crypto, the model has no edge and its buy calls did
worse than doing nothing — don't use it there. On stocks, the model's most
confident calls beat both baseline and the rule-based tiers on average
return (though not on win rate), a real result worth further scrutiny
(a single train/test split, not repeated across multiple time windows) —
not yet a green light to trade on. AUC ~0.51 on both means the model has
almost no overall discrimination; whatever edge exists on stocks lives
in a thin slice of its most-confident predictions, not broadly.

CLI: `mlsignal` (fits + evaluates both categories, all 12 indicators).
`predict_latest()` ranks every symbol's most recent bar by the model's buy
probability.

#### Algorithmic feature selection (`mlselect`)

Rather than always using all 12 indicators, `select_features()` searches
which *combination* earns its place: greedy forward selection, repeatedly
adding whichever remaining indicator most improves a validation slice's
buy-call average return, stopping the moment nothing clears the bar. This
needed a genuine three-way split (`_three_way_time_split`) — train to fit,
validation to decide which features to add, and a test slice the search
never touches, confirmed exactly once at the end. Scanning many feature
combinations and picking the best-looking one on the *test* set would be
the same threshold-overfitting mistake from above, one level up.

Run against this repo's live lake (2026-08-17):

```
[crypto] selected: rsi (only)
  validation:  +9.5% avg, 68% win, n=161   <- looked great in the search
  final test:  +4.0% avg, 37% win, n=2713, AUC 0.47   <- didn't hold up
  rule-based Buy tiers (same test window): +9.5% avg, 43% win

[stocks] selected: rsi, stoch_rsi_k, stoch_rsi_d
  validation:  +1.4% avg, 55% win, n≈167k
  final test:  +1.5% avg, 56% win, n=151090, AUC 0.51
  rule-based Buy tiers (same test window): +2.0% avg, 59% win
```

This is the useful outcome, not a disappointing one: the crypto result is
a clean, honest demonstration of *why* the held-out confirmation step
exists — a single feature looked strong in the search (+9.5%/68% win) and
then fell apart against data the search never saw (+4.0%/37% win, worse
than doing nothing). Neither the crypto nor stocks selection beat the
`mlsignal` full-feature model or the rule-based tiers on this pass. That's
a real answer to "does algorithmically combining indicators build a
better model" — on this data, not yet; the rule-based tiers and even the
plain 12-feature model hold up better than a search-selected subset does.

CLI: `mlselect` (searches + evaluates both categories, persists the
winner exactly like `mlsignal` does — so whichever ran last is what
`predict_latest()` serves).

#### Cycling methods x features (`mlcycle`)

`select_model()` goes one level further: it runs `_forward_select()`
(the same search above, factored out so both entry points share it)
independently for 3 different modeling methods — logistic regression, a
gradient-boosted tree ensemble (`HistGradientBoostingClassifier`, chosen
for speed on the stocks category's 1M+ rows), and a shallow decision tree
(`max_depth=4`, genuinely interpretable — its rules can be read off
directly) — then picks whichever method+feature combination scored best
*on validation*. Comparing 3 searches by whichever looks best on the test
set would repeat the exact threshold-overfitting mistake this module
already learned from, one level up, so only the single winner ever touches
test, exactly once.

Run against this repo's live lake with the expanded 20-feature pool
(2026-08-17):

```
[crypto] logistic +43.5% val (n=74)  gboost +17.3% val (n=341)  tree +19.9% val (n=158)
  winner: logistic -> dist_from_52w_high, is_bull, mkt_breadth, bb_bandwidth
  final test: accuracy 59%, AUC 0.50, avg return +3.4%, win 48% (n=774)
  rule-based Buy tiers (same window): avg +9.5%, win 43%
  baseline: avg +3.4%, win 41%

[stocks] logistic +7.4% val (n=26805)  gboost +7.8% val (n=16965)  tree +3.8% val (n=19758)
  winner: gboost -> dist_from_52w_low, mkt_breadth
  final test: accuracy 45%, AUC 0.50, avg return +11.9%, win 90% (n=804, 0.3% of test)
  rule-based Buy tiers (same window): avg +1.9%, win 59%
  baseline: avg +1.4%, win 56%
```

Two things worth flagging honestly, not glossing over:

1. **Crypto is the discipline working, not failing.** Its winning
   validation score (+43.5% on 74 calls) was the best of all 9 searches —
   and the most obviously overfit: 74 calls is thin, and the confirmed
   test result collapsed to exactly the unconditional baseline (+3.4%),
   worse than the rule-based tiers. `MIN_VAL_CALLS_FOR_SELECTION` scaling
   with dataset size caught the *last* round of overfitting (single-digit
   call counts); it didn't catch this one, because 74 calls cleared the
   bar and still wasn't enough on a 9-symbol universe. The held-out test
   slice is what caught it instead — which is exactly why it's there.

2. **The stocks result needs one more caveat before it's trustworthy.**
   `mkt_breadth` is a *category-wide* value, identical for every symbol on
   a given date — it's not an independent per-symbol signal. A model built
   substantially on it will tend to fire for many symbols simultaneously
   on the same handful of dates when breadth crossed into its favorable
   band, rather than 804 independent per-symbol calls scattered evenly
   across the test window. That means the *effective* sample size behind
   the 90% win rate is probably meaningfully smaller than 804 — this
   result is promising enough to investigate further (e.g., counting
   distinct calendar dates behind the buy calls, not just row count), not
   yet something to trust at face value.

`mkt_breadth` showing up as a top pick in nearly every method/category
combination this run is itself a real finding, though: market-wide
context is pulling weight that no single-symbol technical indicator
was providing on its own — a genuine answer to "does adding more features
help," independent of whether any single search result above holds up.

CLI: `mlcycle` (cycles all 3 methods for both categories, persists the
per-category winner).

#### Making a single split trustworthy (`mlwalkforward`, `--relative`, profit factor)

Three follow-ups after the `mkt_breadth` caveat above turned out to be a
pattern, not a one-off: a single train/val/test split (or a single
validation score during search) can be lucky or unlucky, win rate alone
doesn't say whether a strategy is actually profitable, and a call count
doesn't say how *independent* those calls really were.

**Walk-forward validation.** `walk_forward_validate()` fits the *same*
feature set + method repeatedly across several expanding-window folds
walking forward through history (`_walk_forward_folds`: each fold trains
on everything up to a cutoff and tests on the next slice of dates; the
cutoff walks forward each fold to include the prior fold's test data, the
same shape a periodically-retrained live model would see) and reports the
*distribution* of results, not one number. `select_features()` and
`select_model()` now run this automatically as a second confirmation
alongside the original single-split `evaluate()` — confined to the test
slice their search never touched (`min_train_end_date` = train+val's own
end), across `CONFIRM_N_FOLDS = 3` folds. `validate_persisted_model()` /
the `mlwalkforward` CLI command runs the same check standalone, any time,
against whatever model is currently persisted — a 5-fold check over the
model's full history, independent of re-running the search.

**Relative (cross-sectional) label.** `label_mode="relative"` changes what
the classifier is trained to predict: instead of "will this go up"
(mostly a bet on the whole category's shared drift — on any given day
most symbols move together), it's "will this beat the category's median
forward return on this same date" — canceling the shared move out and
isolating which symbols' setups actually differed from their peers.
Available on `_build_dataset()` and threaded through every entry point;
CLI: `--relative` flag on `mlsignal`/`mlselect`/`mlcycle`.

**Profit factor and n_dates.** Every buy-call scorecard now reports
`profit_factor` (total gains / total losses among the calls — a number
that actually answers "is this worth doing," since a sub-50% win rate
with big winners and small losers is a perfectly good strategy and win
rate alone can't tell them apart) and `n_dates` alongside `n_calls` (how
many *distinct* dates the calls span — directly answers the `mkt_breadth`
clustering question instead of leaving it as something to reason about by
hand each time a report comes out).

**Date-spread gating, and its limit.** `_select_threshold()` and
`_forward_select()` now also require `min_dates` distinct calendar dates
behind a threshold/feature choice, not just `min_calls` rows
(`MIN_DATES_FOR_THRESHOLD` / `MIN_VAL_DATES_FOR_SELECTION`, both 10) —
verified against a synthetic feature engineered to cluster on 3 dates
(`test_forward_select_rejects_date_clustered_feature`). Re-running
`walk_forward_validate()` against the exact stocks configuration that
originally clustered (`dist_from_52w_low` + `mkt_breadth`, gboost)
confirms the fix is *partial*, not complete: one fold still landed 984
calls on 3 distinct dates. That's expected, not a bug — the gate only
governs which threshold gets *selected* during training, so it stops a
threshold from being picked *because* it happened to cluster favorably in
training data; it can't stop a genuinely market-wide feature from
clustering when applied to a *new* period, because clustering is a
property of when `mkt_breadth` enters its buy-worthy range for the whole
market at once, not a training-selection artifact. `n_dates` reporting is
what actually solves this — not by preventing the clustering, but by
making it impossible to miss in any report going forward. A real fix
would need to treat a market-wide-feature-driven call as one trading
decision across all symbols on that date, not N independent ones, when
computing win rate/profit factor — not yet implemented.

#### A validated edge: stocks, relative label, full feature set

Everything above exists to answer one question honestly, and for stocks
with `label_mode="relative"` (logistic regression, all 20 features), the
answer is yes. Walk-forward across 5 expanding-window folds spanning
2019-2026:

```
avg return across folds: +5.84% +/- 3.82% (win rate 61%, AUC 0.51, profit factor 2.95)
100% of folds beat their own baseline (5/5)
total buy calls: 30,193 across 1,665 distinct dates (~325/fold, ~18/date — not clustered)

fold 1 2019-08-19 - 2020-12-31: +12.29% vs baseline +2.33%, win 79%, n=12393 (325 dates)
fold 2 2021-01-04 - 2022-05-18: +2.86%  vs baseline +0.96%, win 59%, n=10343 (347 dates)
fold 3 2022-05-19 - 2023-10-05: +4.16%  vs baseline +0.63%, win 54%, n=3303  (333 dates)
fold 4 2023-10-06 - 2025-02-25: +3.64%  vs baseline +2.05%, win 55%, n=1423  (324 dates)
fold 5 2025-02-26 - 2026-07-15: +6.25%  vs baseline +1.66%, win 57%, n=2731  (336 dates)
```

This is what the other results in this file weren't: every fold beats its
own baseline (crypto's earlier check managed 1/3), the date spread is
broad in every fold (no fold anywhere near the `mkt_breadth`-clustering
problem above), and the standard deviation (3.82%) is smaller than the
mean (5.84%) rather than dwarfing it. Even the weakest fold (fold 4,
+3.64%) still clearly separates from its baseline (+2.05%). AUC is still
only ~0.51 — this isn't a strong overall classifier — but the threshold
selection doesn't need strong overall discrimination, only for its
highest-confidence calls to be right more than they're wrong, and across
1,665 dates and 5 independent time periods, they consistently are.

The label change (relative vs. absolute) is what did it: crypto's
`--relative` run came back flat (avg return +0.0%, profit factor 1.00,
no edge to validate), and every *absolute*-label result this session —
crypto and stocks alike — either failed walk-forward or clustered. Only
stocks + relative held up. This is the persisted stocks model as of this
run (`fit_and_evaluate("stocks", label_mode="relative")` — the full
feature set, no search needed).

Caveat worth carrying forward: still a 30-day-forward horizon on daily
technicals, still logistic regression on 20 features chosen by hand (not
searched) — `select_features(..., label_mode="relative")` combined with
walk-forward confirmation is the natural next step, to see whether a
searched subset beats "just use everything."

#### Exhaustive k-feature search (`mlexhaustive`)

`select_features()`'s greedy forward search has a real blind spot: it
builds a combination up one feature at a time, so it can only ever try
feature B after feature A if A looked like the *single best* addition in
some earlier round. A pair that's individually mediocre but only works
*together* — an interaction the greedy search's own logic guarantees it
never tries — would never surface.

`exhaustive_feature_search()` tries whole combinations directly instead:
every k-feature subset of `candidates` (`itertools.combinations`), each
scored on validation with the exact same gates as the greedy search
(`min_calls`, `min_dates`, must beat the validation baseline). With the
default 20 candidates, C(20, 7) = 77,520 combinations — measured at
~0.24s/combo for crypto and ~1.25s/combo for stocks (fit + score), that's
~5 hours for crypto alone and completely infeasible for stocks. `max_combos`
randomly samples down to a fixed, reproducible (`seed`) budget when the
full space is too large; `mlexhaustive <k> <max_combos>` defaults to
k=7, max_combos=3000 (~12 min crypto, ~63 min stocks). The winning
combination gets the same treatment as every other search: refit on
train+validation, confirmed via `evaluate()` *and* `walk_forward_validate()`
on the untouched test slice — never picked by peeking at test performance.

---

## 6. Download safety

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

## 7. JSON export and upload

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

## 8. Frontend

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

## 9. Scheduling

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

## 10. Testing

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
  test_market_cycle.py     crypto phase scoring, sector quadrants/stage
  test_cycle_forecast.py   breadth-band backtest, forward-return lookup
  test_prophet_backtest.py  fold selection, walk-forward scoring (stubbed fit)
  test_ml_signal.py        feature engineering, labels (absolute/relative), threshold/feature/
                           method/exhaustive-combination selection, walk-forward folds, profit factor
  test_backtest.py         forward-return scoring, win-rate calculation
  test_notify.py           channel dispatch, dedup, failure alerts
  test_toot.py             lazy Mastodon client, missing-token guard
  test_send_to_x.py        OAuth1 tweet construction
  test_universe.py         S&P 500 scrape, CoinGecko top-N, symbol filter
  test_dashboard_digest.py  HTML generation, digest formatting
  test_summaries.py        multi-timeframe signal summaries
```

All 238 tests run in ~30 s on a Pi 5 (longer, ~2.5 min, if run alongside
other CPU-heavy work — the suite itself is unchanged). The `lake` fixture redirects every
Parquet read/write to a temp directory so the real `data/` is never touched.
`test_prophet_backtest.py` stubs out the actual Prophet/Stan fit (`_fit_fn`)
so the suite doesn't pay for real model training — only prophet_backtest.py's
own fold-selection and forward-matching logic is under test. `test_ml_signal.py`
does fit real (cheap) logistic/gboost/tree models on synthetic, perfectly-
separable data to prove the train/evaluate/predict/select pipeline is wired
correctly, without asserting anything about real-world predictive power.
