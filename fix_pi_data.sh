#!/bin/bash
# Fix corrupted crypto data on Raspberry Pi

echo "🔧 Fixing corrupted crypto data..."

# 1. Pull latest code with atomic write fixes
echo "📥 Pulling latest code..."
git pull

# 2. Delete corrupted crypto data
echo "🗑️  Deleting corrupted crypto data directory..."
rm -rf crypto_history_csv/crypto/1d/*

# 3. Re-fetch crypto data with new atomic write code
echo "📊 Re-fetching crypto data (this may take a while)..."
poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh

# 4. Regenerate JSON files
echo "📝 Regenerating JSON files..."
poetry run python generate_api_data.py

# 5. Commit and push
echo "🚀 Pushing to GitHub..."
git add frontend/public/data
git commit -m "Fix: Regenerated crypto data with atomic writes"
git push

echo "✅ Done! Crypto data has been fixed."
