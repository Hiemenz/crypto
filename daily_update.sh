#!/bin/bash
# Daily Update Script for SignalStack
# 1. Fetches latest market data and recomputes signals
# 2. Generates frontend JSON files
# 3. Uploads JSON to Supabase Storage (the Vercel frontend fetches it at runtime)
#
# Scheduling: see SCHEDULING.md. Run this under `flock -n` so two runs can
# never overlap — both write the same Parquet files via tmp-then-rename.
set -uo pipefail

# cron's PATH is minimal and Poetry lives in ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# generate_api_data.py writes to OUTPUT_DIR = "frontend/public/data" (relative),
# and Poetry expects to find pyproject.toml in the cwd.
cd "$(dirname "$0")" || exit 1

echo "Starting Daily Update: $(date)"

# Supabase credentials (SUPABASE_URL / SUPABASE_SERVICE_KEY / SUPABASE_BUCKET).
# Absent .env just means the upload step is skipped.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

run_step() {
    local label="$1"
    shift
    echo "----------------------------------------"
    echo "$label"
    echo "----------------------------------------"
    if ! "$@"; then
        echo "ERROR: $label failed!" >&2
        exit 1
    fi
}

run_step "Step 1: Updating Market Data..." \
    poetry run python crypto_signal_station/crypto_signal_pipeline.py refresh

run_step "Step 2: Generating and uploading Frontend data..." \
    poetry run python generate_api_data.py

echo "----------------------------------------"
echo "Update complete: $(date)"
echo "----------------------------------------"
