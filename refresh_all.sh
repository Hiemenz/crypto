#!/bin/bash

# Master Refresh Script for Crypto Signal Station
# 1. Updates Data (Pipeline)
# 2. Generates Reports (Backfill 5 days)
# 3. Deploys Website

echo "🚀 Starting Master Refresh..."

# 1. Update Data
echo "----------------------------------------"
echo "📦 Step 1: Updating Data..."
echo "----------------------------------------"
poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh
if [ $? -ne 0 ]; then
    echo "❌ Data update failed!"
    exit 1
fi

# 2. Generate Reports
echo "----------------------------------------"
echo "📝 Step 2: Generating Reports..."
echo "----------------------------------------"
# Backfill 5 days to ensure recent history is correct and consistent
poetry run python crypto_signal_station/daily_report.py --backfill --days 5
if [ $? -ne 0 ]; then
    echo "❌ Report generation failed!"
    exit 1
fi

# 2.5 Generate Feeds (Parallel on Pi)
echo "----------------------------------------"
echo "🚀 Step 2.5: Generating Feeds (Parallel)..."
echo "----------------------------------------"

# Run in background
poetry run python cross_feed.py &
PID_CROSS=$!

poetry run python watch_feed.py &
PID_WATCH=$!



# Wait for all
wait $PID_CROSS
EXIT_CROSS=$?

wait $PID_WATCH
EXIT_WATCH=$?



if [ $EXIT_CROSS -ne 0 ] || [ $EXIT_WATCH -ne 0 ]; then
    echo "❌ One or more feeds failed!"
    # Don't exit strictly, let website deploy proceed if possible, or exit? 
    # Proper bash usage says we should probably warn but maybe proceed, 
    # but the original script exited on error. Let's be sticklers.
    exit 1
fi
echo "✅ Feeds generated."

# 3. Deploy Website
echo "----------------------------------------"
echo "🌐 Step 3: Deploying Website..."
echo "----------------------------------------"
./deploy.sh
if [ $? -ne 0 ]; then
    echo "❌ Deployment failed!"
    exit 1
fi

echo "----------------------------------------"
echo "✅ Master Refresh Complete!"
echo "----------------------------------------"
