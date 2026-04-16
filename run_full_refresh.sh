#!/usr/bin/env bash
# Focused Meta ETL Refresh Script
# Runs account metadata + delivery insights pipelines.
#
# Usage:
#   chmod +x run_full_refresh.sh
#   ./run_full_refresh.sh

set -e  # exit immediately on any error

cd "$(dirname "$0")"

echo "======================================================="
echo "    STARTING FULL META ETL REFRESH"
echo "======================================================="

echo "[INFO] Step 1: Fetching Account Metadata..."
python main.py accounts-info

echo "[INFO] Step 2: Fetching Insights (Last 7 Days)..."
python main.py insights-daily --date-preset last_7d

echo "[INFO] Step 3: Refreshing Ads Dimension Compatibility Table..."
python main.py ads-info

echo "[INFO] Step 4: Fetching Insights (Today)..."
python main.py insights-daily --date-preset today

echo "======================================================="
echo "    FULL REFRESH COMPLETED SUCCESSFULLY"
echo "======================================================="
