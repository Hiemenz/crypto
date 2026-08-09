# Scheduling the pipeline

How to run Crypto Signal Station unattended on a Raspberry Pi (or any Linux
box). Covers cron, systemd timers, overlap protection, logging, and how to
tell whether last night's run actually worked.

---

## 1. What you are scheduling

| Job | Command | Suggested cadence |
|---|---|---|
| **Nightly refresh** | `./daily_update.sh` | daily, after both markets close |
| Weekly digest post | `crypto_signal_pipeline.py digest post` | Sunday evening |
| Daily social post | `crypto_signal_pipeline.py tweet` | daily, after the refresh |
| Backtest rebuild | `crypto_signal_pipeline.py backtest` | weekly (it is slow) |
| Health audit | `crypto_signal_pipeline.py verify` | weekly, or after any incident |

`daily_update.sh` is the one that matters. It runs two steps and stops on the
first failure:

1. `crypto_signal_pipeline.py refresh` — universe → OHLCV → signals → breadth →
   momentum → sectors → market context → dashboard → push notification.
2. `generate_api_data.py` — exports JSON to `frontend/public/data/` and uploads
   it to Supabase Storage.

---

## 2. Pick a time

Both markets have to have closed, or you will store partial candles.

| Market | Bar closes | In `America/Chicago` |
|---|---|---|
| US equities | 16:00 ET | 15:00 CDT / 14:00 CST |
| Crypto (UTC daily candle) | 00:00 UTC | 19:00 CDT / 18:00 CST |

**21:30 local time** clears both year-round with a comfortable margin for
Yahoo to settle its data, and it is what the rest of the docs assume. If you
move it, keep it after 19:00 local or `_last_complete_daily_date()` will judge
yesterday's crypto candle to be the newest complete one and you will lag a day.

Cron uses the **system** timezone, not UTC:

```bash
timedatectl        # confirm: Time zone: America/Chicago (CDT, -0500)
```

DST shifts the job by an hour twice a year. That is harmless here — the window
between 19:00 and midnight is wide.

---

## 3. Prerequisites

Three things bite people scheduling this for the first time.

**a. You must run from the repo root.** `generate_api_data.py` writes its output
to `frontend/public/data/` (a relative path), and Poetry needs `pyproject.toml`
in the current directory. `daily_update.sh` already does `cd "$(dirname "$0")"`;
if you invoke Python directly from cron, `cd` yourself first.

**b. Cron's `PATH` is minimal** (`/usr/bin:/bin`), and Poetry lives in
`~/.local/bin`. `daily_update.sh` exports the right `PATH` at the top. If you
schedule anything else, use the absolute path:

```bash
/home/pi/.local/bin/poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh
```

**c. Secrets.** Two separate places:

- `crypto_signal_station/cryptos.yml` — Mastodon/X keys, ntfy/Telegram/Discord
  notify settings, price alerts. Gitignored; copy it from `cryptos.example.yml`.
- `.env` in the repo root — Supabase upload credentials, sourced by
  `daily_update.sh`:

  ```bash
  SUPABASE_URL=https://<project>.supabase.co
  SUPABASE_SERVICE_KEY=<key>
  SUPABASE_BUCKET=signalstack
  ```

  `chmod 600 .env` (it is gitignored). With the vars unset the upload is
  skipped and the rest of the run still succeeds, which is what you want for a
  local-only box.

---

## 4. How long a run takes

Plan for this before you pick an interval. On a Pi 5 with the full S&P 500
universe (~500 symbols) plus the crypto watchlist, a nightly refresh runs for
**tens of minutes**, dominated by Yahoo downloads: those are serialized behind
a global lock, because concurrent `yf.download` calls can return each other's
payloads.

(Per-symbol PNG charts are off by default — they added ~11 minutes and ~350 MB
per run and nothing reads them. `CSS_RENDER_CHARTS=1` turns them back on.)

A first run is much slower — it backfills history from 2014 for every symbol.
**Run it once by hand and time it** before trusting a schedule:

```bash
cd /home/pi/git/crypto
time ./daily_update.sh 2>&1 | tee ~/first-refresh.log
```

Whatever that number is, make sure consecutive runs cannot overlap (§5).

---

## 5. Option A — cron (recommended)

Two runs must never overlap. Both write the same Parquet files through a
`.tmp`-then-`rename` dance, and a second process will clobber the first one's
temp file. `flock` makes a late-running job skip its next slot instead:

```bash
crontab -e
```

```cron
# ── Crypto Signal Station ──────────────────────────────────────────────
# Nightly refresh + JSON export/upload, 21:30 local. -n = skip if the
# previous run is still going rather than piling up.
30 21 * * *  /usr/bin/flock -n /tmp/crypto-refresh.lock /home/pi/git/crypto/daily_update.sh >> /home/pi/logs/crypto-refresh.log 2>&1

# Weekly digest to Mastodon/X, Sunday 22:30 (after the refresh has landed).
30 22 * * 0  cd /home/pi/git/crypto && /home/pi/.local/bin/poetry run python crypto_signal_station/crypto_signal_pipeline.py digest post >> /home/pi/logs/crypto-digest.log 2>&1

# Weekly integrity audit, Saturday 08:00. Exits non-zero when it finds problems.
0 8 * * 6    cd /home/pi/git/crypto && /home/pi/.local/bin/poetry run python crypto_signal_station/crypto_signal_pipeline.py verify >> /home/pi/logs/crypto-verify.log 2>&1

# Weekly backtest rebuild, Saturday 09:00 (slow; feeds the dashboard scoreboard).
0 9 * * 6    cd /home/pi/git/crypto && /home/pi/.local/bin/poetry run python crypto_signal_station/crypto_signal_pipeline.py backtest >> /home/pi/logs/crypto-backtest.log 2>&1
```

```bash
mkdir -p ~/logs
crontab -l          # verify it took
```

Notes:

- `%` is special in crontab and must be escaped as `\%` if you ever put a
  `date` format string in a line.
- Drop `-n` for `--wait` if you would rather queue than skip; on a daily job,
  skipping is almost always right.
- Cron mails you stdout unless you redirect it. The redirects above suppress
  that in favour of log files — see §7 for the alerting you actually want.

---

## 6. Option B — systemd timer

Better logging (`journalctl`), built-in overlap protection, and it catches up
after the Pi has been off (`Persistent=true`). Two files:

`/etc/systemd/system/crypto-refresh.service`

```ini
[Unit]
Description=Crypto Signal Station nightly refresh
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/git/crypto
ExecStart=/home/pi/git/crypto/daily_update.sh
# Refuse to hang forever on a wedged network call.
TimeoutStartSec=2h
Nice=10
```

`/etc/systemd/system/crypto-refresh.timer`

```ini
[Unit]
Description=Run the Crypto Signal Station refresh nightly

[Timer]
OnCalendar=*-*-* 21:30:00
# Stagger a few minutes so 500 symbols don't hit Yahoo on the exact minute.
RandomizedDelaySec=300
# If the Pi was off at 21:30, run at next boot.
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-refresh.timer
systemctl list-timers crypto-refresh.timer     # next scheduled run
sudo systemctl start crypto-refresh.service    # run once, now
journalctl -u crypto-refresh.service -f        # follow it
```

systemd will not start a second `oneshot` while the first is running, so you
do not need `flock` here.

---

## 7. Know when it breaks

**Push alerts.** `refresh` wraps itself in a try/except and fires a
high-priority `notify.notify_failure()` on an unhandled exception. Configure at
least one channel in `cryptos.yml` so a crash reaches your phone:

```yaml
notify:
  ntfy_topic: some-hard-to-guess-string
  ntfy_server: https://ntfy.sh
```

Then subscribe to that topic in the ntfy app. Test it end to end:

```bash
cd /home/pi/git/crypto
poetry run python -c "import sys; sys.path.insert(0,'crypto_signal_station'); \
  import notify; notify.notify_failure('scheduling test', 'if you see this, alerts work')"
```

**What counts as a failure.** Individual symbols failing is normal (delistings,
Yahoo hiccups), so the run tolerates them and logs a per-category tally:

```
Completed stocks processing: 498/503 succeeded.
  failed stocks: BRK-B, XYZ
```

If more than a third of a category's universe fails, the run raises, alerts,
and exits non-zero rather than publishing a dashboard built on stale data. Tune
`MAX_FAILURE_RATE` in `crypto_signal_pipeline.py` if that is too strict.

**Log rotation.** Cron logs grow forever. Drop
`/etc/logrotate.d/crypto-signal-station`:

```
/home/pi/logs/crypto-*.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

(systemd users get rotation free via the journal.)

---

## 8. Verify a run actually worked

Freshness of the outputs is the honest signal — check these the morning after
your first scheduled run:

```bash
cd /home/pi/git/crypto

# Every stage of refresh writes one of these. A missing directory means the
# run died before reaching that stage.
ls -la data/ohlcv data/signals data/breadth data/momentum data/sectors \
       data/market data/dashboard

# Symbol coverage — should be roughly your universe size, not a handful.
find data/ohlcv -name data.parquet | wc -l

# Newest stored bar per category, plus gaps/staleness/contamination.
poetry run python crypto_signal_station/crypto_signal_pipeline.py verify

# What the frontend will actually serve.
python -c "import json;d=json.load(open('frontend/public/data/latest_signals.json'));\
print(d['updated'], len(d['signals']),'signals')"
```

Serve the dashboard locally to eyeball it:

```bash
python -m http.server -d data/dashboard 8080
```

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: crypto_signal_station/cryptos.yml` | job ran from the wrong directory | `cd` to the repo root in the cron line |
| `poetry: command not found` | cron's minimal `PATH` | use `/home/pi/.local/bin/poetry`, or keep the `export PATH` line in `daily_update.sh` |
| Nothing runs at all | cron daemon not active | `systemctl status cron` |
| Two runs tripping over each other, corrupt Parquet | no overlap guard | add `flock -n`, or switch to a systemd timer |
| `SUPABASE_URL / SUPABASE_SERVICE_KEY not set — skipping upload` | `.env` absent or unreadable by the cron user | create it, `chmod 600`, confirm `daily_update.sh` sources it |
| Job hangs for hours | a download stalled (uploads already time out after 60 s) | `TimeoutStartSec=` (systemd) or `timeout 2h` in the cron line |
| Frontend shows stale data but the run "succeeded" | uploads may have partially failed | grep the log for `upload failed`; the run exits non-zero if any file failed |
| `Too many symbols failed to process` | data source or network was down mid-run | check the per-symbol errors above it in the log; re-run once connectivity is back |
| Log shows only `Fetching new data for …` then stops | first-run backfill, still working | let it finish once by hand before scheduling |

A defensive wrapper for the cron line, if you want a hard ceiling:

```cron
30 21 * * * /usr/bin/flock -n /tmp/crypto-refresh.lock timeout 2h /home/pi/git/crypto/daily_update.sh >> /home/pi/logs/crypto-refresh.log 2>&1
```

---

## 10. Scheduling elsewhere

The pipeline has no hard Pi dependency: the E Ink display path is skipped off
ARM (`is_raspberry_pi()`), and the display drivers are an optional extra, so
`poetry install` works anywhere. On the Pi itself, install them with:

```bash
poetry install --extras eink
```

The one thing to solve elsewhere is persisting `data/` between runs — it is the
whole state store, and re-backfilling 12 years of history every run is not
viable. Committing it back to the repo is *not* a workable strategy: that is
exactly how `frontend/public/data/` grew `.git` to 2.9 GB. Use a mounted
volume, an object-store sync, or a restic/rclone snapshot.
