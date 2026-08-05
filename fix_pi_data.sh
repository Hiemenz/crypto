#!/bin/bash
# Rebuild the crypto side of the Parquet lake from scratch.
#
# Use when crypto OHLCV is suspect — e.g. `verify` reports CONTAMINATED
# (the yfinance concurrency bug that mixed up symbol payloads) or gaps that
# the nightly self-heal can't close. Stock data is left untouched.
set -euo pipefail

cd "$(dirname "$0")"

echo "🔧 Rebuilding crypto data..."

echo "📥 Pulling latest code..."
git pull

echo "🗑️  Deleting crypto OHLCV (Parquet lake; see db.py for the layout)..."
rm -rf data/ohlcv/category=crypto/*

echo "📊 Re-fetching crypto data (this may take a while)..."
poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh

echo "📝 Regenerating and uploading JSON..."
poetry run python generate_api_data.py

# verify exits non-zero when it finds problems; report them without aborting
echo "🔎 Verifying..."
poetry run python crypto_signal_station/crypto_signal_pipeline.py verify || \
    echo "⚠️  verify reported issues — see above."

# Generated JSON is *not* committed — it ships to Supabase Storage from
# generate_api_data.py, and committing it previously bloated .git past 2 GB.
echo "✅ Done! Crypto data has been rebuilt."
