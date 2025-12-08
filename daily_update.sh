#!/bin/bash

# Daily Update Script for SignalStack
# 1. Fetches latest market data
# 2. Generates frontend JSON files
# 3. Pushes to GitHub (triggering Vercel deploy)

echo "🚀 Starting Daily Update: $(date)"

# Ensure we are in the project root
cd "$(dirname "$0")"

# 1. Update Data Pipeline
echo "----------------------------------------"
echo "📦 Step 1: Updating Market Data..."
echo "----------------------------------------"
poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh
if [ $? -ne 0 ]; then
    echo "❌ Data update failed!"
    exit 1
fi

# 2. Generate JSON APIs for Frontend
echo "----------------------------------------"
echo "📝 Step 2: Generating Frontend APIs..."
echo "----------------------------------------"
poetry run python generate_api_data.py
if [ $? -ne 0 ]; then
    echo "❌ API generation failed!"
    exit 1
fi

# 3. Commit and Push to Deploy
echo "----------------------------------------"
echo "🌐 Step 3: Pushing to GitHub (Deploying)..."
echo "----------------------------------------"

# Add only the data directory
git add frontend/public/data

# Commit
git commit -m "Daily data update: $(date '+%Y-%m-%d')"

# Push
git push

if [ $? -eq 0 ]; then
    echo "----------------------------------------"
    echo "✅ Update Complete & Pushed!"
    echo "----------------------------------------"
else
    echo "❌ Git push failed!"
    exit 1
fi
