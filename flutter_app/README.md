# Crypto Signal Station — Flutter Web App

A mobile-first Flutter Web client for the Crypto Signal Station data lake.
Reads live JSON from `api.py` (FastAPI, at the repo root) instead of the old
static `docs/` site.

## Run it

1. Start the backend from the repo root:
   ```
   poetry run uvicorn api:app --reload --port 8000
   ```
2. Run the app:
   ```
   cd flutter_app
   flutter run -d chrome
   ```
   By default it points at `http://localhost:8000`. To point at a different
   host (e.g. your machine's LAN IP so you can test from a phone browser),
   either pass `--dart-define=API_BASE_URL=http://192.168.x.x:8000` to
   `flutter run`, or change it at runtime from the in-app Settings tab.

## Features

- **Feed** — latest signal per symbol, filterable by category/timeframe/signal
- **Watchlist** — star a symbol (tap the star or swipe a card) to save it locally; the Watchlist tab shows only saved symbols. On-device only (`shared_preferences`), no account system.
- **Near** — assets close to a Buy/Sell trigger (formerly "Watch")
- **Crosses** — MA 50/200 and StochRSI K/D cross history
- **Symbol detail** — price/RSI/StochRSI charts, plus a share button
- **Price alerts** (Settings) — managed via new `/api/alerts` endpoints that edit `price_alerts:` in `crypto_signal_station/cryptos.yml`. These are checked by the existing pipeline on every `refresh` and pushed via `notify.py`, so they fire even when the app is closed.
- **Live notifications** (Settings) — subscribes to the same ntfy.sh topic you set in `cryptos.yml`'s `notify:` section via Server-Sent Events, and shows a browser notification when the backend posts a signal change or alert. Only delivers while this tab is open (no service worker / background push); the alert itself is still real and backend-driven, this is just the "does the phone buzz while I'm not looking at the app" part, which needs a service worker to do properly.
- **Offline cache** — Feed/Near/Crosses show the last-fetched copy instantly (with a "cached" banner) while a fresh request runs in the background; if the network call fails, the cached copy is all you see instead of an error.
- **Haptics** — light taps on card selection, refresh, and watchlist toggles. No-op on web today; free upgrade if a native build is ever added.

**Deliberately not implemented** (need native iOS/Android, not Flutter Web):
home-screen widgets, biometric lock (Face ID / Touch ID).

## Structure

- `lib/models/signal.dart` — `Signal`, `WatchItem`, `CrossEvent`, `PriceAlert` JSON models
- `lib/services/api_client.dart` — HTTP client for the FastAPI backend (plain + cache-aware stream variants)
- `lib/services/api_config.dart` — persisted API base URL
- `lib/services/watchlist_service.dart` — on-device watchlist storage
- `lib/services/cache_service.dart` — raw-JSON response cache for offline support
- `lib/services/notification_service.dart` / `ntfy_service.dart` — browser Notification API + ntfy.sh SSE subscription (web-only implementation behind a conditional import, no-op stub elsewhere so `flutter test` still compiles on the VM)
- `lib/screens/` — `FeedScreen`, `WatchlistScreen`, `WatchScreen`, `CrossesScreen`, `SymbolDetailScreen`, `SettingsScreen`
- `lib/screens/home_shell.dart` — bottom navigation shell

## Tests

```
flutter test
flutter analyze
```
