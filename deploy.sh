#!/bin/bash

# Configuration
SOURCE_DIR="$(pwd)"
DOCS_DIR="$SOURCE_DIR/docs"
DEST_REPO="/Users/kevinhiemenz/git/hiemenz.github.io"

# Ensure destination exists
if [ ! -d "$DEST_REPO/.git" ]; then
    echo "Error: Destination repository not found at $DEST_REPO"
    exit 1
fi

echo "🚀 Starting Deployment..."

# 1. Generate Site
echo "Generating static site..."
poetry run python generate_site.py

# 2. Sync Content (Efficiently)
echo "Syncing content to destination..."
# Use rsync to copy only changed files and delete removed ones, excluding .git
rsync -av --delete --exclude '.git' "$DOCS_DIR/" "$DEST_REPO/"

# 3. Commit and Push
echo "Pushing to GitHub..."
cd "$DEST_REPO" || exit
git add .
git commit -m "Deploy crypto reports: $(date '+%Y-%m-%d %H:%M')"
git push

echo "✅ Deployment Complete!"
