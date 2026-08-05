"""Export the signals lake to static JSON for the frontend (frontend/public/data/).

Reads from the Parquet lake via db.py — the same store crypto_signal_pipeline.py
writes to. Each 1d/1wk signals row already carries OHLCV + every computed
indicator (see crypto_signal_pipeline.py's _process_single_symbol), so no
separate "with signals" file format is needed here.

Output is *generated*, never committed: it ships to Supabase Storage and the
frontend fetches it from there at runtime (see frontend/src/utils/storage.js).
"""

import hashlib
import json
import math
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime

import numpy as np
import pandas as pd

import db

OUTPUT_DIR = "frontend/public/data"
CATEGORIES = ("crypto", "stocks")

# Per-symbol history feeds the chart and the strategy simulator, which read
# only OHLCV + the signal label. Exporting all ~31 lake columns made each file
# ~4x larger (≈2 MB/symbol, ≈1 GB/night across the S&P 500) for data nothing
# renders. Add a column here if the frontend starts using it.
HISTORY_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume", "signal"]

# crosses.json is a "what happened recently" feed, not an archive. Unbounded,
# it grew to 7.6 MB of all-time crossovers re-uploaded every night.
CROSSES_LOOKBACK_DAYS = 180

# StochRSI extremes. A K/D crossover carries information when it happens *out
# of* an extreme zone — up out of oversold, down out of overbought.
STOCH_OVERSOLD = 0.2
STOCH_OVERBOUGHT = 0.8

UPLOAD_TIMEOUT_SECONDS = 60


def _json_safe(value):
    """Recursively replace NaN/±inf with None and box numpy scalars.

    json.dump defaults to allow_nan=True, which emits bare `NaN` / `Infinity`
    tokens. Those are not valid JSON, and JSON.parse rejects the whole
    document — one bad row would blank every page that fetches the file.
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, (pd.Timestamp, datetime)):
        return str(value)
    if value is pd.NaT or value is pd.NA:
        return None
    return value


def _write_json_atomic(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        # allow_nan=False turns any sanitiser miss into a loud ValueError here
        # instead of silent invalid JSON in the browser.
        json.dump(_json_safe(payload), f, separators=(",", ":"), allow_nan=False)
    os.replace(tmp, path)


def _clean_records(df):
    """Rows as JSON-safe dicts: Date as string, NaN/inf as null, no lake-only columns."""
    df = df.drop(columns=["symbol", "category", "timeframe"], errors="ignore").copy()
    df["Date"] = df["Date"].astype(str)
    # inf shows up wherever an indicator divides by a zero range (e.g. bb_pband
    # on a perfectly flat 20-bar window), so it has to be cleared alongside NaN.
    df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
    return df.to_dict(orient="records")


def generate_history_json():
    print(f"Generating history JSON to {OUTPUT_DIR}/history/...")
    count = 0
    for category in CATEGORIES:
        # Intersect with what's actually stored: a lake written before a column
        # existed would otherwise fail the projected SELECT outright.
        available = set(db.signals_lake_columns(category, "1d"))
        cols = [c for c in HISTORY_COLUMNS if c in available]
        if "Date" not in cols:
            continue
        lake = db.scan_signals_lake(category, "1d", columns=cols)
        if lake.empty:
            continue
        for symbol, g in lake.groupby("symbol"):
            g = g.sort_values("Date")
            output_path = os.path.join(OUTPUT_DIR, "history", f"{symbol}.json")
            _write_json_atomic(output_path, {"symbol": symbol, "data": _clean_records(g)})
            count += 1
    print(f"History JSON generation complete. ({count} symbols)")


# Base score per signal tier; anything unrecognised (incl. "Hold") is neutral.
_TIER_SCORES = {"excellent": 95, "great": 85, "good": 75}
_NEUTRAL_SCORE = 50


def calculate_score(row):
    """0-100 score for the strength/confidence of a signal.

    Tier sets the base; RSI nudges it so same-tier signals rank against each
    other (a buy at RSI 15 beats a buy at RSI 29, and vice versa for sells).
    """
    signal = str(row.get("signal", "")).lower()
    score = next(
        (v for tier, v in _TIER_SCORES.items() if tier in signal), _NEUTRAL_SCORE
    )

    rsi = row.get("rsi")
    if rsi is None or pd.isna(rsi):
        return score

    if "buy" in signal:
        score += (30 - float(rsi)) * 0.2   # deeper oversold = stronger buy
    elif "sell" in signal:
        score += (float(rsi) - 70) * 0.2   # deeper overbought = stronger sell

    return int(min(max(score, 0), 100))


def generate_latest_signals_json():
    print(f"Generating latest signals JSON to {OUTPUT_DIR}/latest_signals.json...")

    all_signals = []
    for category in CATEGORIES:
        lake = db.scan_signals_lake(category, "1d")
        if lake.empty:
            continue

        for symbol, g in lake.groupby("symbol"):
            last_row = g.sort_values("Date").iloc[-1]

            item = last_row.drop(labels=["symbol", "category", "timeframe"], errors="ignore").to_dict()
            item = {k: _json_safe(v) for k, v in item.items()}

            item["symbol"] = symbol
            item["category"] = category
            item["score"] = calculate_score(last_row)

            sig_str = str(item.get("signal", "")).lower()
            if "buy" in sig_str:
                item["side"] = "buy"
            elif "sell" in sig_str:
                item["side"] = "sell"
            else:
                item["side"] = "hold"

            all_signals.append(item)

    output_path = os.path.join(OUTPUT_DIR, "latest_signals.json")
    _write_json_atomic(output_path, {"updated": str(datetime.now()), "signals": all_signals})
    print(f"Latest signals JSON generation complete. ({len(all_signals)} items)")


def _cross_type(kind, prev_k, prev_d):
    """Label a K/D crossover, marking the ones that came out of an extreme.

    The crossover's information is in where it came *from*: a bullish cross is
    worth flagging when the prior bar was oversold, a bearish one when it was
    overbought. (This previously tested the post-cross values against inverted
    bounds, which marked nearly every death cross "Confirmed".)
    """
    if kind == "Golden Cross":
        confirmed = prev_k < STOCH_OVERSOLD and prev_d < STOCH_OVERSOLD
    else:
        confirmed = prev_k > STOCH_OVERBOUGHT and prev_d > STOCH_OVERBOUGHT
    return f"Confirmed {kind}" if confirmed else kind


def generate_crosses_json():
    """Scans recent 1wk data for StochRSI K/D crosses and exports to JSON."""
    print(f"Generating Stoch Crosses JSON to {OUTPUT_DIR}/crosses.json...")

    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=CROSSES_LOOKBACK_DAYS)
    crosses = []
    for category in CATEGORIES:
        lake = db.scan_signals_lake(category, "1wk", columns=["Date", "Close", "stoch_rsi_k", "stoch_rsi_d"])
        if lake.empty:
            continue

        for symbol, g in lake.groupby("symbol"):
            g = g.sort_values("Date")
            if len(g) < 2:
                continue

            # Shift before windowing so the first retained bar still has the
            # previous bar's K/D to compare against.
            g = g.assign(prev_k=g["stoch_rsi_k"].shift(1), prev_d=g["stoch_rsi_d"].shift(1))
            g = g[g["Date"] >= cutoff]
            if g.empty:
                continue

            golden_mask = (g["prev_k"] < g["prev_d"]) & (g["stoch_rsi_k"] > g["stoch_rsi_d"])
            death_mask = (g["prev_k"] > g["prev_d"]) & (g["stoch_rsi_k"] < g["stoch_rsi_d"])

            events = []
            for mask, kind in ((golden_mask, "Golden Cross"), (death_mask, "Death Cross")):
                hit = g[mask].copy()
                if not hit.empty:
                    hit["type"] = kind
                    events.append(hit)
            if not events:
                continue

            for _, row in pd.concat(events).iterrows():
                k = row["stoch_rsi_k"]
                d = row["stoch_rsi_d"]
                crosses.append({
                    "category": category,
                    "symbol": symbol,
                    "type": _cross_type(row["type"], row["prev_k"], row["prev_d"]),
                    "price": row.get("Close"),
                    "k": round(float(k), 2),
                    "d": round(float(d), 2),
                    "date": str(row["Date"]),
                })

    output_path = os.path.join(OUTPUT_DIR, "crosses.json")
    _write_json_atomic(output_path, {"updated": str(datetime.now()), "crosses": crosses})
    print(f"Stoch Crosses JSON generation complete. ({len(crosses)} items)")


# ── Supabase upload ────────────────────────────────────────────────────────────

def _manifest_path():
    """Hashes of what we last uploaded. Kept outside OUTPUT_DIR so the walk
    below doesn't try to upload the manifest itself."""
    return db.table_path("api", "upload_manifest.json")


def _load_manifest():
    try:
        with open(_manifest_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_manifest(manifest):
    path = _manifest_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f)
    os.replace(tmp, path)


def upload_to_supabase():
    """Upload changed JSON files from OUTPUT_DIR to Supabase Storage.

    Reads SUPABASE_URL, SUPABASE_SERVICE_KEY, and SUPABASE_BUCKET from the
    environment. Skips (and reports success) if the vars are not set, so local
    runs without Supabase configured still work.

    Files whose content hash matches the last successful upload are skipped.
    Returns True if everything that needed uploading went up.
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    bucket = os.environ.get("SUPABASE_BUCKET", "signalstack")

    if not supabase_url or not service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — skipping upload.")
        return True

    manifest = _load_manifest()
    new_manifest = dict(manifest)
    uploaded = skipped = failed = 0

    for dirpath, _, filenames in os.walk(OUTPUT_DIR):
        for filename in sorted(filenames):
            if not filename.endswith(".json"):
                continue
            local_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(local_path, OUTPUT_DIR).replace("\\", "/")

            with open(local_path, "rb") as f:
                body = f.read()
            digest = hashlib.sha256(body).hexdigest()
            if manifest.get(rel_path) == digest:
                skipped += 1
                continue

            url = f"{supabase_url}/storage/v1/object/{bucket}/{rel_path}"
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {service_key}",
                    "Content-Type": "application/json",
                    "x-upsert": "true",
                },
            )
            try:
                # Without a timeout a stalled socket hangs the whole nightly
                # job indefinitely, which is worse than failing.
                with urllib.request.urlopen(req, timeout=UPLOAD_TIMEOUT_SECONDS):
                    uploaded += 1
                    new_manifest[rel_path] = digest
            except urllib.error.HTTPError as e:
                print(f"  upload failed {rel_path}: {e.code} {e.reason}")
                failed += 1
            except (urllib.error.URLError, socket.timeout, OSError) as e:
                # DNS/TLS/connection-reset/timeout: transient and per-file, so
                # log and keep going rather than aborting the whole export.
                print(f"  upload failed {rel_path}: {e}")
                failed += 1

    _save_manifest(new_manifest)
    print(f"Supabase upload: {uploaded} uploaded, {skipped} unchanged, {failed} failed.")
    return failed == 0


def main():
    generate_history_json()
    generate_latest_signals_json()
    generate_crosses_json()
    if not upload_to_supabase():
        # Non-zero exit so daily_update.sh reports the failure instead of
        # logging "Update complete" over a half-published dataset.
        raise SystemExit(1)


if __name__ == "__main__":
    main()
